"""W-122 (REQ-109 AC-1, AC-2): paper tracking and the order path never import each other, in either direction.
No database needed."""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_ac1_the_tracking_modules_import_nothing_from_the_order_path():
    """AC-1 (structural): the tracking route, store and domain import no execute/execution/basket module."""
    for path in (ROOT / "backend/ofo_app/routes/tracking.py", ROOT / "backend/ofo_app/paper_store.py",
                 ROOT / "backend/ofo/tracking/paper.py", ROOT / "backend/ofo/tracking/book.py"):
        imports = [line for line in path.read_text(encoding="utf-8").splitlines()
                   if line.startswith(("import ", "from "))]
        assert not [line for line in imports if "execut" in line or "basket" in line or "orders" in line], path


#: GC-BP step 5 (REQ-109 AC-3): the order path a paper module must never import, matched on the import source.
ORDER_PATH = ("execut", "basket", "orders", "order_book", "place_order", "kite_order")


def _imported_names(path: pathlib.Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            found += [f"{node.module or ''}.{a.name}" for a in node.names]
        elif isinstance(node, ast.Import):
            found += [a.name for a in node.names]
    return found


def test_req109_ac3_paper_tracking_and_exit_import_nothing_from_the_order_path():
    """AC-3 (GC-BP step 5): start, view, list and paper exit never reach Execute: the route, store and domain import
    no module or name from the order path (execute*, basket*, broker order code), in any import form (AST, so a
    parenthesised multi-line import is read too)."""
    for rel in ("backend/ofo_app/routes/tracking.py", "backend/ofo_app/paper_store.py",
                "backend/ofo/tracking/paper.py", "backend/ofo/tracking/book.py"):
        bad = [m for m in _imported_names(ROOT / rel) if any(word in m.lower() for word in ORDER_PATH)]
        assert not bad, (rel, bad)


TRACKING_CODE = ("backend/ofo_app/routes/tracking.py", "backend/ofo_app/paper_store.py")
#: The raw catalogue identity a stored contract id could be priced by without the live-identity check.
RAW_IDENTITY = ("exchange_token", "catalogue_contracts", "load_contract", "live_contract_id")


def _raw_identity_uses(path: pathlib.Path) -> list[str]:
    """Every way ``path`` could turn a stored contract id into a feed key without ofo_app.tracked_contracts: an import
    of the catalogue store (by import source, whatever local name it gets), a relative or dynamic import (cannot be
    resolved: fails closed), and any name, attribute or string naming the raw identity."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names = {a.name for a in node.names}
            if node.level or node.module is None:
                found.append(f"{node.lineno}: relative import (unresolvable)")
            elif node.module.startswith("ofo_app.catalogue_store") or (
                    node.module == "ofo_app" and "catalogue_store" in names) or "*" in names:
                found.append(f"{node.lineno}: from {node.module} import {sorted(names)}")
        elif isinstance(node, ast.Import):
            found += [f"{node.lineno}: import {a.name}" for a in node.names
                      if "catalogue_store" in a.name or a.name.split(".")[0] == "importlib"]
        elif isinstance(node, ast.Name) and node.id in {"__import__", "import_module"}:
            found.append(f"{node.lineno}: dynamic import {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in RAW_IDENTITY:
            found.append(f"{node.lineno}: .{node.attr}")
        elif isinstance(node, ast.Name) and node.id in RAW_IDENTITY:
            found.append(f"{node.lineno}: {node.id}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and any(
                r in node.value for r in RAW_IDENTITY[:2]):
            found.append(f"{node.lineno}: string naming {node.value[:40]!r}")
    return found


def test_tracking_reaches_a_feed_key_only_through_tracked_contracts():
    """Round-3 detection upgrade (run-discipline C8): ofo_app.tracked_contracts is the single choke point from a stored
    contract id to a feed key. The tracking route and store never import the catalogue store, never name the raw
    identity (exchange_token, the catalogue table, load_contract, live_contract_id) and never import dynamically or
    relatively; the route does import the choke point."""
    for name in TRACKING_CODE:
        path = ROOT / name
        assert path.exists(), path
        assert _raw_identity_uses(path) == [], name
    route = (ROOT / TRACKING_CODE[0]).read_text(encoding="utf-8")
    assert "from ofo_app import paper_store, tracked_contracts" in route


def test_the_choke_point_checks_the_live_holder_of_the_token():
    """The choke point itself prices nothing unless the live contract holding the token is the stored id: it calls
    catalogue_store.live_contract_id (or its one-query batch live_contract_ids, GC-BP F-3) and compares the holder with
    the contract id, in both the single and the batch path."""
    source = (ROOT / "backend/ofo_app/tracked_contracts.py").read_text(encoding="utf-8")
    imported = set(_imported_names(ROOT / "backend/ofo_app/tracked_contracts.py"))
    assert {f"ofo_app.catalogue_store.{n}" for n in ("CatalogueStoreError", "StoredContract", "live_contract_id",
                                                     "live_contract_ids", "load_contract", "load_contracts")} <= imported  # noqa: E501 - long line kept whole
    assert source.count("holder != stored.contract_id") == 2  # noqa: PLR2004 - literal is the pinned value
    assert source.count("return LIVE if holder == stored.contract_id") == 2  # noqa: PLR2004 - literal is the pinned value


@pytest.mark.parametrize("snippet", [
    "from ofo_app.catalogue_store import load_contract as lc\n",
    "from ofo_app import catalogue_store\n",
    "from . import catalogue_store\n",
    "import ofo_app.catalogue_store as c\n",
    "import importlib\n",
    "m = __import__('ofo_app.catalogue_store')\n",
    "key = f'{c.exchange_segment}:{c.exchange_token}'\n",
    "q = 'SELECT id FROM public.catalogue_contracts'\n",
])
def test_the_scan_fails_closed_on_every_bypass_shape(tmp_path, snippet):
    """Mutation check of the scan itself: each bypass shape is flagged."""
    path = tmp_path / "bypass.py"
    path.write_text(snippet, encoding="utf-8")
    assert _raw_identity_uses(path) != []


#: Issue #500: the primitives that turn a STORED contract id into its exchange identity (the catalogue store's
#: id -> row and token -> holder reads, the catalogue table itself). Outside the reviewed modules below, every module of
#: backend/ofo_app reaches a stored contract's feed key only through ofo_app.tracked_contracts.resolve.
STORED_IDENTITY = ("load_contract", "live_contract_id")
APP = "backend/ofo_app"
MIN_APP_MODULES = 50  # backend/ofo_app holds well over this many modules
#: Reviewed modules that may touch the raw catalogue identity, each with why it never prices a stored id by its token.
#: A new module that touches it fails the scan until it routes through resolve or is reviewed and added here.
REVIEWED_RAW_IDENTITY = {
    "backend/ofo_app/tracked_contracts.py": "THE choke point: key only for a live row holding its own token",
    "backend/ofo_app/catalogue_store.py": "owns the table: writes rows, answers id -> row and live token -> holder",
    "backend/ofo_app/alembic/": "migrations: schema DDL only, no runtime read",
    "backend/ofo_app/models.py": "ORM table definition for migrations; no query",
    "backend/ofo_app/catalogue_picker.py": "lists LIVE contracts only (not retired, not delisted); no stored id",
    "backend/ofo_app/seed_test_catalogue.py": "test seeding: counts rows; no key handed out",
    "backend/ofo_app/execute_replay.py": "APP_ENV=test replay seeding: inserts the recorded contract",
    "backend/ofo_app/execution_plan_store.py": "key -> broker symbol with its live flag (key -> row)",
    "backend/ofo_app/live_market.py": "imports the store for load_catalogue (live rows by key); no stored id read",
    "backend/ofo_app/routes/leg_edit.py": "key -> LIVE holder -> its stored id (live_contract_id): never id -> key",
    "backend/ofo_app/routes/outcome.py": "key -> LIVE holder -> its row (live_contract_id first): never id -> key",
    "backend/ofo_app/strategy_store.py": "save-time validation of a picked id (live, terms); returns no feed key",
    # review round 1 (table constants and f-string SQL now seen):
    "backend/ofo_app/eligibility_from_zerodha.py": "by id -> that row's own eligibility status (no key out); the "
                                                   "registry reads LIVE rows only (not retired, not delisted)",
    "backend/ofo_app/freeze_store.py": "exchange_freeze_limits keyed by the exchange file's token; no stored id",
    "backend/ofo_app/freeze_read.py": "the freeze_store read moved here (row 20): exchange_freeze_limits by the "
                                      "exchange file's token; no stored id",
    "backend/ofo_app/audit_allowlist.py": "docstring only (exchange_token is not in the order reply); no query",
    "backend/ofo_app/routes/catalogue.py": "docstring names the fields; lists live contracts via catalogue_picker",
    # GC-CLEAN (2026-10-30), GC-TP settlement (F-72): option legs by stored id give TERMS only (name, type, strike,
    # expiry) to settle at the index close; the one key read is the INDEX's, from load_catalogue's live rows by the
    # fixed INDEX_ROWS key (as live_market.py). No stored id -> feed key.
    "backend/ofo_app/paper_settlement.py": "stored id -> terms only; index token from live rows by INDEX_ROWS key",
}
#: Paths that must never be in the reviewed list: the callers issue #500 moved onto resolve.
MUST_USE_RESOLVE = ("backend/ofo_app/routes/strategies.py", "backend/ofo_app/routes/execute.py",
                    "backend/ofo_app/routes/tracking.py", "backend/ofo_app/paper_store.py")


def _reviewed(rel: str) -> bool:
    return any(rel == k or (k.endswith("/") and rel.startswith(k)) for k in REVIEWED_RAW_IDENTITY)


def _import_from_uses(node: ast.ImportFrom) -> list[str]:
    """The ``from X import ...`` shapes of _stored_identity_uses, judged by import source (any local alias)."""
    names = {a.name for a in node.names}
    if node.level or node.module is None:
        return [f"{node.lineno}: relative import (unresolvable)"]
    if node.module.split(".")[0] == "importlib":
        return [f"{node.lineno}: from {node.module} import {sorted(names)} (dynamic import)"]
    if node.module in TABLE_MODULES and (constants := sorted(n for n in names if n.isupper())):
        # a table-name constant by import source, whatever it is called there or aliased to here
        return [f"{node.lineno}: table constant {constants} from {node.module}"]
    if "*" in names or (node.module == "ofo_app" and "catalogue_store" in names) or (
            node.module.startswith("ofo_app.catalogue_store")
            and (names & set(STORED_IDENTITY) or node.module != "ofo_app.catalogue_store")):
        # the whole store, a star, a submodule, or an id -> identity read; its other names (load_catalogue: live rows
        # by key, apply_update) never turn a stored id into a key
        return [f"{node.lineno}: from {node.module} import {sorted(names)}"]
    return []


def _stored_identity_uses(path: pathlib.Path) -> list[str]:
    """Every way ``path`` could read a stored contract's exchange identity without ofo_app.tracked_contracts: an
    import of the catalogue store or a catalogue table constant by import source (any local name), a relative or
    dynamic import (unresolvable: fails closed), a name or attribute naming load_contract / live_contract_id or a
    table constant, and SQL text (a string or any f-string part) naming a catalogue table or the exchange identity."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        text_ = _sql_text(node)
        if text_ is not None and _names_stored_identity(text_):
            found.append(f"{node.lineno}: SQL text naming the identity {text_[:60]!r}")
        if isinstance(node, ast.ImportFrom):
            found += _import_from_uses(node)
        elif isinstance(node, ast.Import):
            found += [f"{node.lineno}: import {a.name}" for a in node.names
                      if "catalogue_store" in a.name or a.name.split(".")[0] == "importlib"]
        elif isinstance(node, ast.Name) and node.id in {"__import__", "import_module", *STORED_IDENTITY}:
            found.append(f"{node.lineno}: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in {"import_module", *STORED_IDENTITY, *TABLE_CONSTANTS}:
            found.append(f"{node.lineno}: .{node.attr}")
    return found


#: Modules that define the catalogue's table-name constants (CONTRACTS, BROKER_ROWS, ...).
TABLE_MODULES = ("ofo_app.catalogue_picker", "ofo_app.catalogue_store")
#: The catalogue's tables: any SQL naming one of them reads the raw catalogue.
CATALOGUE_TABLES = ("catalogue_contracts", "broker_instruments")
_SQL_WORD = re.compile(r"\b(select|from|join|where|update|insert|returning)\b", re.IGNORECASE)


def _table_constants() -> frozenset[str]:
    """Every module-level name in TABLE_MODULES bound to a string naming a catalogue table (read from the source, so a
    new constant is covered without editing this list)."""
    out = set()
    for module in TABLE_MODULES:
        source = ROOT / "backend" / (module.replace(".", "/") + ".py")
        for node in ast.parse(source.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, str) and any(t in node.value.value for t in CATALOGUE_TABLES):
                out |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return frozenset(out)


TABLE_CONSTANTS = _table_constants()


def _sql_text(node: ast.AST) -> str | None:
    """A string's text: a plain constant, or every literal part of an f-string joined (the parts a JoinedStr holds)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return " ".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    return None


def _names_stored_identity(text_: str) -> bool:
    """A catalogue table named anywhere, or the exchange identity (exchange_token / exchange_segment) in SQL text."""
    if any(t in text_ for t in CATALOGUE_TABLES):
        return True
    return ("exchange_token" in text_ or "exchange_segment" in text_) and bool(_SQL_WORD.search(text_))


def test_app_wide_a_stored_contract_reaches_a_feed_key_only_through_resolve():
    """Issue #500 detection upgrade (run-discipline C8, standing item c): every module of backend/ofo_app is scanned by
    import source; any module touching a stored contract's raw identity must be in the reviewed list with a reason, and
    the callers #500 moved (strategies, execute, tracking) never are. A reviewed entry that no longer exists or no
    longer touches it fails too (no stale exemptions)."""
    files = sorted((ROOT / APP).rglob("*.py"))
    assert len(files) > MIN_APP_MODULES  # the package really was scanned
    touching = {p.relative_to(ROOT).as_posix(): _stored_identity_uses(p) for p in files}
    touching = {k: v for k, v in touching.items() if v}
    unreviewed = {k: v for k, v in touching.items() if not _reviewed(k)}
    assert unreviewed == {}
    stale = [k for k in REVIEWED_RAW_IDENTITY if not any(t == k or (k.endswith("/") and t.startswith(k))
                                                          for t in touching)]
    assert stale == []  # every exemption still needed
    assert not [m for m in MUST_USE_RESOLVE if _reviewed(m)]
    for name in MUST_USE_RESOLVE[:3]:
        assert "tracked_contracts" in (ROOT / name).read_text(encoding="utf-8"), name


@pytest.mark.parametrize("snippet", [
    "from ofo_app.catalogue_store import load_contract as lc\n",
    "from ofo_app import catalogue_store\n",
    "from . import catalogue_store\n",
    "import ofo_app.catalogue_store as c\n",
    "import importlib\n",
    "m = __import__('ofo_app.catalogue_store')\n",
    "q = 'SELECT exchange_token FROM public.catalogue_contracts WHERE id = :id'\n",
    "row = await store.load_contract(db, cid)\n",
    "holder = await live_contract_id(db, key)\n",
    # review round 1 (#500 MAJOR): the table by an imported constant, the identity in an f-string, an importlib alias
    "from ofo_app.catalogue_picker import CONTRACTS\n",
    "from ofo_app.catalogue_picker import BROKER_ROWS as B\n",
    "from ofo_app.catalogue_store import CONTRACTS as T\n",
    "q = f'SELECT c.id, c.exchange_token FROM {T} AS c WHERE c.id = :id'\n",
    "q = f'SELECT c.exchange_segment FROM {t} c'\n",
    "from ofo_app import catalogue_picker\nq = catalogue_picker.CONTRACTS\n",
    "from importlib import import_module as im\n",
    "import importlib as il\n",
    "import importlib.util\n",
])
def test_the_app_wide_scan_fails_closed_on_every_bypass_shape(tmp_path, snippet):
    """Mutation check of the app-wide scan: each bypass shape (by import source, raw SQL in a string or any f-string
    part, an imported table constant, the store's reads by any receiver name, any dynamic import) is flagged."""
    path = tmp_path / "bypass.py"
    path.write_text(snippet, encoding="utf-8")
    assert _stored_identity_uses(path) != []


@pytest.mark.parametrize("snippet", [
    "leg['exchange_token'] = feed_id.exchange_token\n",  # a response key, not a catalogue read
    "from ofo_app.catalogue_picker import database_today\n",
    "from ofo_app.catalogue_store import load_catalogue\n",
])
def test_the_app_wide_scan_passes_shapes_that_read_no_stored_identity(tmp_path, snippet):
    """Discrimination: a dict key named exchange_token and the picker's / store's non-identity helpers pass."""
    path = tmp_path / "plain.py"
    path.write_text(snippet, encoding="utf-8")
    assert _stored_identity_uses(path) == []


def test_the_real_eligibility_reader_is_seen_by_the_scan():
    """The review's real miss: eligibility_from_zerodha imports CONTRACTS / BROKER_ROWS from the picker and selects
    c.exchange_token in an f-string. The scan flags it (so it must be reviewed or routed through resolve)."""
    uses = _stored_identity_uses(ROOT / APP / "eligibility_from_zerodha.py")
    assert any("CONTRACTS" in u for u in uses) and any("exchange_token" in u for u in uses), uses


ORDER_PATH = ("backend/ofo/execution", "backend/ofo/orders", "backend/ofo_app/basket_post.py",
              "backend/ofo_app/checked_basket.py", "backend/ofo_app/execute_plan.py")


def test_ac1_no_order_path_module_imports_the_tracking_code():
    """REQ-109 AC-1/AC-2 (no account-wide switch, paper never mixed with real): the reverse direction - no module of
    the order path (execution, orders, the basket and execute-plan modules) imports ofo.tracking or
    ofo_app.paper_store (the paper order book since GC-TP 1a part 4), so a paper entry cannot be read into an
    order. Every listed path must exist (a renamed
    module fails here, never passes silently)."""
    files = []
    for name in ORDER_PATH:
        path = ROOT / name
        assert path.exists(), path
        files += sorted(path.rglob("*.py")) if path.is_dir() else [path]
    offenders = []
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            names_tracking = "ofo.tracking" in stripped or "paper_store" in stripped
            if stripped.startswith(("import ", "from ")) and names_tracking:
                offenders.append(f"{path.relative_to(ROOT)}: {stripped}")
    assert offenders == []
    assert len(files) > len(ORDER_PATH)  # the directories really held modules
