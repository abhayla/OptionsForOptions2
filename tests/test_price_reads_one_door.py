"""G1 (modular-doors Phase 8, PLAN 5.8): a decision price is read through ONE door, ``ofo_app.market_read.read_market``.

Rule: a call to (or a reference to) a provider/snapshot reader, ``underlying_quote``, ``futures_quote``,
``option_chain_snapshot``, ``latest_depth``, ``latest_day_stats``, ``depth_after_close``, ``held_quote_time``,
``read_snapshot`` or ``resolve_spot``, in ``backend/ofo_app`` is allowed only in ``market_read.py`` or at a site on
``EXEMPT``. A site is keyed by (file, enclosing function, name), never by a line, and carries a category and a reason:

- ``own_process``: a reader inside the process that owns the feed or a transaction (no wait, by design);
- ``display``: a screen or push that shows a price and decides nothing;
- ``real_path``: the real-order path (ADR-016 to ADR-019);
- ``awaiting_phase_N``: a decision read not yet moved (a deferred issue names it).

The list is "shrink only": an entry whose site is gone fails (``stale exemption``). Fail closed: an aliased import of
one of the names (``from x import underlying_quote as q``) is a problem, because a call through the alias would be
invisible; so is a file that does not parse. ``getattr(obj, "<name>")`` and a bare reference (``q = read_snapshot``)
count as a read. Tests are not scanned. Entries come from a fresh AST scan of the Phase 8 head (25 Nov 2026).
"""
from __future__ import annotations

import ast
import re
import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan

BACKEND = Path(__file__).resolve().parents[1] / "backend"
DOOR = "ofo_app/market_read.py"
NAMES = frozenset({"underlying_quote", "futures_quote", "option_chain_snapshot", "latest_depth", "latest_day_stats",
                   "depth_after_close", "held_quote_time", "read_snapshot", "resolve_spot"})
CATEGORY = re.compile(r"own_process|display|real_path|awaiting_phase_\d+")
Key = tuple[str, str, str]  # (file under backend/, enclosing function, name)


def _entries(category: str, reason: str, file: str, sites: Mapping[str, str]) -> dict[Key, tuple[str, str]]:
    """``sites``: enclosing function -> space-separated names it reads."""
    return {(f"ofo_app/{file}", func, name): (category, reason)
            for func, names in sites.items() for name in names.split()}


EXEMPT: dict[Key, tuple[str, str]] = {
    # own process (the feed or the transaction owner reads what it holds; no wait by design)
    **_entries("own_process", "the background tick reads the prices it holds in its own process", "background.py",
               {"read_prices": "option_chain_snapshot underlying_quote latest_day_stats",
                "state_from_market": "resolve_spot", "_window_tokens_of": "underlying_quote"}),
    **_entries("own_process", "the market reader of the adjustment check is a different read_market of the same name",
               "adjustment_readers.py", {"read_market": "underlying_quote"}),
    **_entries("own_process", "paper monitor: in-transaction read, no wait, by design", "paper_monitor.py",
               {"provider_prices": "read_snapshot", "_index_now": "underlying_quote"}),
    # display (shows a price, decides nothing)
    **_entries("display", "outcome screen figures", "routes/outcome.py",
               {"judge_spot": "resolve_spot", "outcome_response": "read_snapshot"}),
    **_entries("display", "live socket push of a held index price", "live_push.py",
               {"_hold_forward": "underlying_quote"}),
    **_entries("display", "chain push rows", "chain_push.py",
               {"_spot_quote": "underlying_quote", "_day_stats": "latest_day_stats depth_after_close",
                "window_quotes": "option_chain_snapshot", "model_of": "option_chain_snapshot"}),
    **_entries("display", "index strip push row", "index_push.py", {"_row": "underlying_quote"}),
    **_entries("display", "leg picker quotes, depth and forward shown to the user", "routes/leg_picker.py",
               {"_index_quote": "underlying_quote", "_held_quotes": "option_chain_snapshot",
                "_future_ltp": "futures_quote", "_forward": "option_chain_snapshot",
                "_after_close": "depth_after_close held_quote_time",
                "depth_answer": "latest_depth latest_day_stats"}),
    **_entries("display", "leg editor spot shown beside the legs", "routes/leg_edit.py",
               {"_live_spot": "underlying_quote"}),
    **_entries("display", "ready-made card spot", "routes/ready_made.py", {"_spot": "underlying_quote"}),
    **_entries("display", "planned-entry card price", "routes/planned_entry.py", {"_read": "read_snapshot"}),
    **_entries("display", "open-interest block of the outcome", "outcome_oi.py",
               {"oi_block": "option_chain_snapshot"}),
    **_entries("display", "adjustment screen read of the market it shows", "adjustment_readers.py",
               {"read": "underlying_quote option_chain_snapshot latest_day_stats", "_window_spot": "resolve_spot"}),
    **_entries("display", "paper book display (the exit read goes through paper_exit.live_exit_prices)",
               "routes/paper.py",
               {"_hold_until_ready": "underlying_quote read_snapshot", "_snapshot": "read_snapshot"}),
    # real path
    **_entries("display", "tracking panel display read (_answer_core, list_tracking) and, via exit_snapshot, the paper "
                          "exit door's live read (paper_exit.live_exit_prices)",
               "routes/tracking.py", {"_snapshot": "read_snapshot"}),
    **_entries("real_path", "real-order leg quote and index price (ADR-016 to ADR-019)", "routes/execute.py",
               {"leg_quote": "latest_depth", "underlying_price": "underlying_quote"}),
    **_entries("real_path", "replay of a real order frame", "execute_replay.py", {"frame_quote": "latest_depth"}),
    **_entries("real_path", "the depth reader the real-order leg quote asks for (getattr: a provider may lack depth)",
               "live_market.py", {"latest_depth": "latest_depth"}),
    # decision read not yet moved
    **_entries("awaiting_phase_8", "first-fill entry facts are a decision read outside read_market (deferred issue: "
                                   "plan section 6 row 13 (entry_facts_now decision read))",
               "adjustment_readers.py", {"entry_facts_now": "underlying_quote"}),
}


def scan(rel: str, source: str) -> tuple[list[tuple[str, int, str]], list[str]]:
    """Sites ``(function, line, name)`` and fail-closed issues of one file."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [], [f"unparsable file, cannot be checked: {rel}: {exc.msg} (line {exc.lineno})"]
    sites: list[tuple[str, int, str]] = []
    issues: list[str] = []

    def walk(node: ast.AST, func: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else func
            if isinstance(child, ast.ImportFrom):
                issues.extend(f"aliased import: {rel}:{child.lineno} imports {a.name} as {a.asname}; a call through "
                              f"the alias is invisible, import it by its own name" for a in child.names
                              if a.name in NAMES and a.asname and a.asname != a.name)
            elif isinstance(child, ast.Import):
                issues.extend(f"aliased import: {rel}:{child.lineno} imports {a.name} as {a.asname}; import it by "
                              f"its own name" for a in child.names
                              if a.asname and a.name.rsplit(".", 1)[-1] in NAMES)
            elif isinstance(child, ast.Name) and child.id in NAMES:
                sites.append((inner, child.lineno, child.id))
            elif isinstance(child, ast.Attribute) and child.attr in NAMES:
                sites.append((inner, child.lineno, child.attr))
            elif (isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                  and child.func.id in ("getattr", "hasattr") and len(child.args) > 1
                  and isinstance(child.args[1], ast.Constant) and child.args[1].value in NAMES):
                sites.append((inner, child.lineno, child.args[1].value))
            walk(child, inner)

    walk(tree, "<module>")
    return sites, issues


def load_sources(backend: Path = BACKEND) -> dict[str, str]:
    """Every ``ofo_app`` module (not alembic) as ``{ofo_app/<path>.py: text}``."""
    return {p.relative_to(backend).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted((backend / "ofo_app").rglob("*.py")) if "alembic" not in p.parts}


def problems(sources: Mapping[str, str], exempt: Mapping[Key, tuple[str, str]] = EXEMPT) -> list[str]:
    """Pure: the problems of ``sources`` ({file: text}) against ``exempt``. Empty means the one door holds."""
    out: list[str] = []
    seen: set[Key] = set()
    for rel, text in sorted(sources.items()):
        sites, issues = scan(rel, text)
        out += issues
        for func, line, name in sites:
            key = (rel, func, name)
            seen.add(key)
            if rel != DOOR and key not in exempt:
                out.append(f"price read outside read_market: {rel}:{line} in {func} calls {name}(). Use "
                           f"ofo_app.market_read.read_market, or add (file, function) to EXEMPT with a category "
                           f"and reason.")
    out += [f"stale exemption: {f}::{fn} no longer calls {n}; delete the entry"
            for (f, fn, n) in sorted(exempt) if (f, fn, n) not in seen]
    return out


def test_every_price_read_goes_through_the_door():
    assert problems(load_sources()) == []


def test_exemptions_carry_a_category_and_a_reason():
    bad = [k for k, (category, reason) in EXEMPT.items() if not CATEGORY.fullmatch(category) or not reason.strip()]
    assert bad == []


def test_the_shared_tracking_snapshot_is_display_and_the_open_decision_read_names_its_issue():
    category, reason = EXEMPT[("ofo_app/routes/tracking.py", "_snapshot", "read_snapshot")]
    assert category == "display"
    assert "paper_exit.live_exit_prices" in reason
    category, reason = EXEMPT[("ofo_app/adjustment_readers.py", "entry_facts_now", "underlying_quote")]
    assert category == "awaiting_phase_8"
    assert "plan section 6 row 13" in reason


def test_the_door_itself_is_not_an_exemption():
    assert [k for k in EXEMPT if k[0] == DOOR] == []


# ---- mutation tests: the guard goes red where it should and only there -----------------------------------------------
READ = "def f(p):\n    return p.underlying_quote('NIFTY')\n"
ENTRY: dict[Key, tuple[str, str]] = {("ofo_app/x.py", "f", "underlying_quote"): ("display", "a shown price")}


def test_mutation_bad_sample_gives_exactly_one_problem_naming_the_door():
    found = problems({"ofo_app/routes/x.py": READ}, exempt={})
    assert len(found) == 1
    assert found[0].startswith("price read outside read_market: ofo_app/routes/x.py:2 in f calls underlying_quote().")
    assert "ofo_app.market_read.read_market" in found[0]


def test_mutation_same_sample_in_the_allowed_home_gives_none():
    assert problems({DOOR: READ}, exempt={}) == []


def test_mutation_an_exempt_site_passes():
    assert problems({"ofo_app/x.py": READ}, exempt=ENTRY) == []


def test_mutation_a_reference_and_a_getattr_are_reads():
    assert len(problems({"ofo_app/x.py": "def f():\n    return read_snapshot\n"}, exempt={})) == 1
    assert len(problems({"ofo_app/x.py": "def f(p):\n    return getattr(p, 'latest_depth', None)\n"}, exempt={})) == 1


@pytest.mark.parametrize("source", [
    "from ofo.x import underlying_quote as q\n\ndef f():\n    return q('NIFTY')\n",
    "import ofo.x.underlying_quote as q\n\ndef f():\n    return q('NIFTY')\n",
])
def test_mutation_an_aliased_import_gives_one_problem(source):
    found = problems({"ofo_app/x.py": source}, exempt={})
    assert len(found) == 1
    assert found[0].startswith("aliased import: ofo_app/x.py:1")


def test_mutation_an_unparsable_file_fails_closed():
    found = problems({"ofo_app/x.py": "def f(:\n"}, exempt={})
    assert len(found) == 1
    assert found[0].startswith("unparsable file")


def test_mutation_a_deleted_exempt_site_is_a_stale_exemption():
    found = problems({"ofo_app/x.py": "def f(p):\n    return None\n"}, exempt=ENTRY)
    assert found == ["stale exemption: ofo_app/x.py::f no longer calls underlying_quote; delete the entry"]


def test_mutation_deleting_a_real_exempt_site_goes_red_with_the_stale_message():
    sources = load_sources()
    rel = "ofo_app/routes/ready_made.py"
    assert "underlying_quote" in sources[rel]
    sources[rel] = sources[rel].replace("underlying_quote", "spot_value")
    assert problems(sources) == [
        "stale exemption: ofo_app/routes/ready_made.py::_spot no longer calls underlying_quote; delete the entry"]


def test_mutation_a_provider_call_added_to_a_copy_of_routes_paper_is_named(tmp_path):
    copy = tmp_path / "backend"
    (copy / "ofo_app" / "routes").mkdir(parents=True)
    for rel in load_sources():
        target = copy / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BACKEND / rel, target)
    assert problems(load_sources(copy)) == []  # the copy alone is as green as the tree
    paper = copy / "ofo_app" / "routes" / "paper.py"
    paper.write_text(paper.read_text(encoding="utf-8")
                     + "\n\ndef _new_price_reader(provider):\n    return provider.futures_quote('NIFTY')\n",
                     encoding="utf-8")
    found = problems(load_sources(copy))
    assert len(found) == 1
    assert "ofo_app/routes/paper.py" in found[0]
    assert "_new_price_reader" in found[0]
    assert "futures_quote()" in found[0]
