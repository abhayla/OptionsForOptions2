"""#242: the selector picks the tests_app files a backend change can break (finding
targeted-tests-miss-dependent-files, 4th occurrence). File-level and coarse on purpose (see select_app_tests.py).
Pure: PR #241's real backend diff and snapshots of the backend files live in fixtures/ (so a later edit to those files
cannot turn this red); the matching runs against the repo's real, current tests_app/ folder. No DB, network or git."""
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "orchestrator"))
import select_app_tests as sel  # noqa: E402

TESTS_APP = ROOT / "tests_app"
FIX = pathlib.Path(__file__).parent / "fixtures"
SRC = FIX / "pr241-src"  # backend files, saved as .py.txt so the repo's import guard does not scan them
DIFF = (FIX / "pr241-backend.diff").read_text(encoding="utf-8")
FILES = ["backend/ofo/errors/explanations.py", "backend/ofo_app/catalogue_picker.py",
         "backend/ofo_app/routes/catalogue.py", "backend/ofo_app/routes/strategies.py"]
RED = {"tests_app/test_response_door.py", "tests_app/test_strategy_planned_entry.py"}
ROUTES = [f"backend/ofo_app/routes/{n}.py" for n in
          ("broker", "catalogue", "health", "live", "outcome", "planned_entry", "strategies")]


def snap(rel: str) -> str:
    return (SRC / (pathlib.PurePosixPath(rel).name + ".txt")).read_text(encoding="utf-8")


def pick(files, diff):
    return sel.select(files, diff, TESTS_APP, snap, ROUTES)


def _line_of(rel: str, needle: str) -> int:
    for n, line in enumerate(snap(rel).splitlines(), 1):
        if line.startswith(needle):
            return n
    raise AssertionError(needle)


def add_after(rel: str, needle: str, new_line: str) -> str:
    """A synthetic diff that adds one code line right after the first line starting with `needle`."""
    n = _line_of(rel, needle)
    ctx = snap(rel).splitlines()[n - 1]
    return (f"diff --git a/{rel} b/{rel}\n--- a/{rel}\n+++ b/{rel}\n@@ -{n},1 +{n},2 @@\n {ctx}\n+{new_line}\n")


def replace_line(rel: str, needle: str, new_line: str) -> str:
    n = _line_of(rel, needle)
    old = snap(rel).splitlines()[n - 1]
    return f"diff --git a/{rel} b/{rel}\n--- a/{rel}\n+++ b/{rel}\n@@ -{n},1 +{n},1 @@\n-{old}\n+{new_line}\n"


#: The #241 diff's selection over today's tests_app. It grows when a later test file names one of the diff's keys (a
#: route path, a class, a module): the backend snapshots are frozen but tests_app is the live folder. The selector
#: never truncates to MAX_FILES (dropping a file could drop a red one); the cap is a budget that atool.py enforces
#: (it refuses a selection over MAX_FILES unless --route-tests-anyway). So this pins the set, and each later file that
#: legitimately joined it is listed with why.
PR241_SELECTION = {
    "tests_app/test_catalogue_picker_api.py", "tests_app/test_chain_live.py", "tests_app/test_chain_permissions.py",
    "tests_app/test_eligibility_from_zerodha.py", "tests_app/test_response_door.py",
    "tests_app/test_strategy_closed_shape.py", "tests_app/test_strategy_followups.py",
    "tests_app/test_strategy_planned_entry.py", "tests_app/test_strategy_store.py",
    "tests_app/test_exit_adopted_313b.py",  # imports StrategyRefused from ofo_app.routes.strategies
    "tests_app/test_pinned_clock.py",  # calls the /api/catalogue/{underlying}/... routes
    "tests_app/test_strategy_tracking.py",  # W-122: GET /strategies/{strategy_id}
    "tests_app/test_stored_contract_feed_keys.py",  # issue #500: GET /strategies/{id} and /history, StrategyRefused
    "tests_app/test_strategy_tracking_imports.py",  # issue #500: its scan names ofo_app.catalogue_picker as a source
    "tests_app/test_ready_made_route.py",  # W-125: raises StrategyRefused and posts to /api/strategies/... routes
}


def test_pr241_diff_selects_both_red_files_within_the_cap() -> None:
    """Both #241 red files are selected; the selection is exactly the pinned set (see PR241_SELECTION for why it is
    above MAX_FILES now: tests_app grew; the cap is atool's budget, never a reason for the selector to drop files)."""
    chosen = pick(FILES, DIFF)
    print("CASE #241:", len(chosen), chosen)
    assert RED <= set(chosen), chosen
    assert set(chosen) == PR241_SELECTION, sorted(set(chosen) ^ PR241_SELECTION)


def test_pr241_diff_does_not_select_the_catalogue_loading_tests() -> None:
    loaders = [p for p in pick(FILES, DIFF) if re.search(r"test_catalogue_(load|ingest|instruments|refresh)", p)]
    assert loaders == [], loaders


def test_a_changed_route_file_keys_on_every_route_and_class_it_defines() -> None:
    names = {k.name for k in sel.keys_for(FILES, DIFF, ROOT, snap, ROUTES)}
    assert {"/strategies", "/strategies/{strategy_id}", "/strategies/{strategy_id}/history",
            "/strategies/{strategy_id}/restore/{seq}", "/api/catalogue/{underlying}/contracts",
            "/api/catalogue/{underlying}/expiries"} <= names
    assert {"LegOut", "StrategyOut", "HistoryOut", "ContractOut"} <= names  # every class, changed or not
    assert "ofo_app.catalogue_picker" in names  # a non-route file keys on its module name


def test_a_response_model_field_in_a_route_file_reaches_the_outcome_route_tests() -> None:
    chosen = pick(["backend/ofo_app/routes/outcome.py"],
                  add_after("backend/ofo_app/routes/outcome.py", "class RowOut", "    extra: int"))
    print("CASE model field:", len(chosen), chosen)
    assert "tests_app/test_outcome_route.py" in chosen


def test_editing_a_handler_helper_yields_the_route_key() -> None:
    chosen = pick(["backend/ofo_app/routes/outcome.py"],
                  add_after("backend/ofo_app/routes/outcome.py", "def outcome_response", "    x = 1"))
    print("CASE helper:", len(chosen), chosen)
    assert "tests_app/test_outcome_route.py" in chosen


def test_a_store_change_reaches_the_http_tests_through_the_route_that_imports_it() -> None:
    chosen = pick(["backend/ofo_app/strategy_store.py"],
                  add_after("backend/ofo_app/strategy_store.py", "def check_strategy_id", "    pass"))
    print("CASE store:", len(chosen), chosen)
    assert "tests_app/test_strategy_planned_entry.py" in chosen


def test_a_changed_module_constant_is_not_a_silent_zero() -> None:
    chosen = pick(["backend/ofo_app/routes/outcome.py"],
                  replace_line("backend/ofo_app/routes/outcome.py", "MARKER_CODES", 'MARKER_CODES = {"X": "Y"}'))
    print("CASE constant:", len(chosen), chosen)
    assert chosen != [] and "tests_app/test_outcome_route.py" in chosen


def test_a_diff_touching_no_ofo_app_file_selects_nothing() -> None:
    diff = ("diff --git a/backend/ofo/errors/explanations.py b/backend/ofo/errors/explanations.py\n"
            "--- a/backend/ofo/errors/explanations.py\n+++ b/backend/ofo/errors/explanations.py\n"
            "@@ -1,1 +1,2 @@\n x\n+y = 1\n")
    assert pick(["backend/ofo/errors/explanations.py"], diff) == []
    assert pick([], "") == []


def test_a_comment_only_edit_in_a_route_file_selects_nothing() -> None:
    rel = "backend/ofo_app/routes/strategies.py"
    n = _line_of(rel, "    exchange_token: int")
    diff = (f"diff --git a/{rel} b/{rel}\n--- a/{rel}\n+++ b/{rel}\n"
            f"@@ -{n},1 +{n},2 @@\n-    exchange_token: int\n+    exchange_token: int  # the token\n"
            f"+    # a new comment line\n")
    assert pick([rel], diff) == []


def test_a_docstring_only_edit_selects_nothing() -> None:
    rel = "backend/ofo_app/strategy_store.py"
    n = _line_of(rel, "def check_strategy_id")
    doc = next(i for i, line in enumerate(snap(rel).splitlines()[n:], n + 1) if '"""' in line)
    old = snap(rel).splitlines()[doc - 1]
    diff = f"diff --git a/{rel} b/{rel}\n--- a/{rel}\n+++ b/{rel}\n@@ -{doc},1 +{doc},1 @@\n-{old}\n+{old} more words\n"
    assert pick([rel], diff) == []


def test_a_crlf_diff_selects_the_same_files() -> None:
    crlf = DIFF.replace("\r\n", "\n").replace("\n", "\r\n")
    assert pick(FILES, crlf) == pick(FILES, DIFF)


def test_an_unreadable_diff_fails_closed() -> None:
    with pytest.raises(sel.DiffNotParsed):
        pick(["backend/ofo_app/routes/strategies.py"], "Binary files a/x and b/x differ\n")
    rename = ("diff --git a/backend/ofo_app/routes/old.py b/backend/ofo_app/routes/strategies.py\n"
              "similarity index 100%\nrename from backend/ofo_app/routes/old.py\n"
              "rename to backend/ofo_app/routes/strategies.py\n")
    with pytest.raises(sel.DiffNotParsed):
        pick(["backend/ofo_app/routes/strategies.py"], rename)


def test_a_route_path_that_is_not_a_literal_fails_closed() -> None:
    src = 'from fastapi import APIRouter\nrouter = APIRouter()\n\n@router.get(build_path())\ndef f():\n    return 1\n'
    diff = "diff --git a/backend/ofo_app/routes/x.py b/backend/ofo_app/routes/x.py\n@@ -5,1 +5,1 @@\n-    return 2\n+    return 1\n"
    with pytest.raises(sel.DiffNotParsed):
        sel.select(["backend/ofo_app/routes/x.py"], diff, TESTS_APP, lambda rel: src, ROUTES)
