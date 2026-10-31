"""#242: the selector picks the tests_app files a backend change can break (finding
targeted-tests-miss-dependent-files, 4th occurrence). File-level and coarse on purpose (see select_app_tests.py).
Pure: PR #241's real backend diff and snapshots of the backend files live in fixtures/ (so a later edit to those files
cannot turn this red); the matching runs against the repo's real, current tests_app/ folder. No DB, network or git."""
import pathlib
import re
import sys

import pytest

pytestmark = pytest.mark.repo_scan  # reads every file in tests_app/ (the selector's own matching and the set checks)
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
    "tests_app/test_strategy_delete_app.py",
    "tests_app/test_strategy_planned_entry.py", "tests_app/test_strategy_store.py",
    "tests_app/test_exit_adopted_313b.py",  # imports StrategyRefused from ofo_app.routes.strategies
    "tests_app/test_pinned_clock.py",  # calls the /api/catalogue/{underlying}/... routes
    "tests_app/test_strategy_tracking.py",  # W-122: GET /strategies/{strategy_id}
    "tests_app/test_stored_contract_feed_keys.py",  # issue #500: GET /strategies/{id} and /history, StrategyRefused
    "tests_app/test_stored_chain_real.py",  # PR #580 (I-4): calls the real catalogue_picker readers and catalogue routes
    "tests_app/test_strategy_tracking_imports.py",  # issue #500: its scan names ofo_app.catalogue_picker as a source
    "tests_app/test_ready_made_route.py",  # W-125: raises StrategyRefused and posts to /api/strategies/... routes
    "tests_app/test_playbook_labels_route.py",  # GC-ADJ2 step 3: imports ofo.errors.explanations, which this diff changes
    "tests_app/test_order_closure_all_routes.py",  # W-121: names ofo_app.routes.strategies in its edge table
    # builder sequence rows 1-10 (2026-10-22/23) added app tests that import the same modules or call the same routes:
    "tests_app/test_underlying_refusal.py",  # row 1
    "tests_app/test_connect_gate_routes.py",  # row 2
    "tests_app/test_catalogue_refresh.py",  # row 5: imports the catalogue picker the #241 diff changed
    "tests_app/test_execute_health_clock.py",  # row 5/7
    "tests_app/test_busy_text_routes.py",  # row 10
    "tests_app/test_strategy_versions_app.py",  # row 16: PUT /strategies/{strategy_id} and its versions
    "tests_app/test_leg_picker_routes.py",  # row 19: imports ofo_app.catalogue_picker, which the #241 diff changes
    "tests_app/test_leg_edit_route.py",  # row 20: POST /api/strategies/leg-edit, a /api/strategies/... route
    "tests_app/test_strategy_name_app.py",  # row 29b: POST/PATCH/GET /strategies routes and the strategy store
    "tests_app/test_leg_edit_eligibility_db.py",  # row 30b: imports the leg-edit route's eligibility/list checks
    "tests_app/test_drawer_after_hours.py",  # GC-BM F-18: imports ofo_app.catalogue_picker, calls leg_picker answers
    "tests_app/test_outcome_open_interest.py",  # GC-UI D-B16: imports ofo_app.routes.outcome / live_push (explanations)
    "tests_app/test_strategy_tracking_list.py",  # GC-BP: calls /strategies/{id}/tracking routes (same reason as test_strategy_tracking)  # noqa: E501 - long line kept whole
    "tests_app/test_strategy_price_history_route.py",  # GC-UI step 5: imports ofo_app.routes.strategies (key measured)
    # backend/ofo/ modules are in scope since the run-40201288521 fix; the diff changes ofo.errors.explanations, which
    # these import (directly or through a route that imports it):
    "tests_app/test_api_models.py", "tests_app/test_identifier_and_slots.py", "tests_app/test_outcome_catalogue.py",
    "tests_app/test_outcome_margin.py", "tests_app/test_outcome_split_loss.py",
    "tests_app/test_strategy_templates_route.py",
    # GC-TP paper flow + target block: each names ofo.errors.explanations (5 also call /strategies routes)
    "tests_app/test_outcome_target_badge.py", "tests_app/test_outcome_target_booked.py",
    "tests_app/test_paper_list_figures.py", "tests_app/test_paper_reason_texts.py", "tests_app/test_paper_routes.py",
    "tests_app/test_paper_totals.py", "tests_app/test_paper_triggers_routes.py",
}


def test_pr241_diff_selects_both_red_files_within_the_cap() -> None:
    """Both #241 red files are selected; the selection is exactly the pinned set (see PR241_SELECTION for why it is
    above MAX_FILES now: tests_app grew; the cap is atool's budget, never a reason for the selector to drop files)."""
    chosen = pick(FILES, DIFF)
    print("CASE #241:", len(chosen), chosen)
    assert RED <= set(chosen), chosen
    assert set(chosen) == PR241_SELECTION, sorted(set(chosen) ^ PR241_SELECTION)


def test_pr241_diff_does_not_select_the_catalogue_loading_tests() -> None:
    # test_catalogue_refresh.py (row 5) imports ofo_app.catalogue_picker, a file this diff changes, so selecting it is
    # right (R13); the pure loaders below import nothing the diff touches and must stay unselected
    loaders = [p for p in pick(FILES, DIFF) if re.search(r"test_catalogue_(load|ingest|instruments)", p)]
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


def test_a_diff_touching_no_backend_python_file_selects_nothing() -> None:
    y = "backend/ofo/strategy/catalogue.yaml"
    diff = f"diff --git a/{y} b/{y}\n--- a/{y}\n+++ b/{y}\n@@ -1,1 +1,2 @@\n x\n+y: 1\n"
    assert pick(["backend/ofo/strategy/catalogue.yaml"], diff) == []  # known blind spot: data files, see the docstring
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


# ---- the three red "api / Run app tests" runs the selector let through (REAL branch diffs, saved in fixtures/) ----
# Diff bases: run 40201288521 = merge-base(9aa21296^1, 5d77c4b) (head was merged by PR #552; origin/main contains it, so
# the plain merge-base is the head itself); runs 40132982617 and 40146949616 = d549c211, the main commit the
# chunk-3 rows branched from (those heads are merged into main through chunk merges with no single PR parent).
RUNS_SRC = FIX / "runs-src"


def run_files(run: str) -> tuple:
    diff = (FIX / f"{run}-backend.diff").read_text(encoding="utf-8")
    return re.findall(r"^diff --git a/\S+ b/(\S+)", diff, re.M), diff


def run_snap(rel: str) -> str:
    """Snapshot of the backend file as the red head had it, else today's tree (docstring-line check only)."""
    p = RUNS_SRC / (pathlib.PurePosixPath(rel).name + ".txt")
    return p.read_text(encoding="utf-8") if p.exists() else (ROOT / rel).read_text(encoding="utf-8")


def pick_run(run: str) -> list:
    files, diff = run_files(run)
    return sel.select(files, diff, TESTS_APP, run_snap, ROUTES)


def test_run_40201288521_a_domain_module_change_reaches_the_test_that_imports_it() -> None:
    """backend/ofo/errors/gate_slots.py is outside backend/ofo_app/; test_identifier_and_slots.py imports it."""
    chosen = pick_run("40201288521")
    print("RUN 40201288521:", len(chosen), chosen)
    assert "tests_app/test_identifier_and_slots.py" in chosen, chosen


def test_run_40132982617_the_catalogue_route_change_selects_the_pinned_clock_test() -> None:
    """Measured: the selector already picks test_pinned_clock.py for this diff (route key /api/catalogue/{underlying}/
    expiries). The run was red because the selection is over MAX_FILES (atool refuses and defers to CI), not because
    the file was missed. This pins that the file stays selected."""
    chosen = pick_run("40132982617")
    print("RUN 40132982617:", len(chosen), chosen)
    assert "tests_app/test_pinned_clock.py" in chosen, chosen


def test_run_40146949616_a_migration_change_selects_the_migration_and_pin_tests() -> None:
    chosen = pick_run("40146949616")
    print("RUN 40146949616:", len(chosen), chosen)
    assert {"tests_app/test_migration_0024_typed_entry.py", "tests_app/test_strategy_shape_matrix.py"} <= set(chosen)


MIG = "backend/ofo_app/alembic/versions/0099_x.py"


def test_a_migration_only_diff_selects_the_fixed_migration_set() -> None:
    diff = f"diff --git a/{MIG} b/{MIG}\n--- a/{MIG}\n+++ b/{MIG}\n@@ -1,1 +1,2 @@\n x = 1\n+X = 1\n"
    chosen = sel.select([MIG], diff, TESTS_APP, lambda r: "x = 1\nX = 1\n", ROUTES)
    names = {pathlib.PurePosixPath(p).name for p in chosen}
    assert chosen and {p.name for p in TESTS_APP.glob("test_*migration*.py")} <= names
    assert "test_strategy_shape_matrix.py" in names and "test_alembic_migration_guard.py" in names
    # every tests_app file that only says "alembic" (no NEW_PINS, no _migration_replay) is in the set too
    alembic_only = {p.name for p in TESTS_APP.glob("test_*.py")
                    if re.search(r"\balembic\b", p.read_text(encoding="utf-8"))}
    assert alembic_only and alembic_only <= names, sorted(alembic_only - names)


def test_a_top_level_package_init_change_selects_its_importers() -> None:
    """backend/ofo/__init__.py keys on the package 'ofo'; every tests_app file importing ofo must be picked."""
    rel = "backend/ofo/__init__.py"
    diff = f"diff --git a/{rel} b/{rel}\n--- a/{rel}\n+++ b/{rel}\n@@ -1,1 +1,2 @@\n x = 1\n+X = 1\n"
    chosen = sel.select([rel], diff, TESTS_APP, lambda r: "x = 1\nX = 1\n", ROUTES)
    importers = {f"tests_app/{p.name}" for p in TESTS_APP.glob("test_*.py")
                 if re.search(r"^\s*(?:import ofo\b|from ofo[. ])", p.read_text(encoding="utf-8"), re.M)}
    assert importers and importers <= set(chosen), sorted(importers - set(chosen))


def test_the_selector_source_holds_no_control_bytes() -> None:
    """A '\\b' once landed as a literal backspace byte and silently dropped 16 migration tests (PR #567 review)."""
    src = (ROOT / "scripts" / "orchestrator" / "select_app_tests.py").read_bytes()
    assert not [c for c in src if c < 32 and c not in (9, 10, 13)]


def test_a_comment_only_migration_edit_selects_nothing() -> None:
    diff = f"diff --git a/{MIG} b/{MIG}\n--- a/{MIG}\n+++ b/{MIG}\n@@ -1,1 +1,2 @@\n x = 1\n+# a comment\n"
    assert sel.select([MIG], diff, TESTS_APP, lambda r: "x = 1\n# a comment\n", ROUTES) == []


def test_a_domain_module_edit_with_a_missing_hunk_fails_closed() -> None:
    rel = "backend/ofo/errors/gate_slots.py"
    diff = f"diff --git a/{rel} b/{rel}\nsimilarity index 100%\n"
    with pytest.raises(sel.DiffNotParsed):
        sel.select([rel], diff, TESTS_APP, run_snap, ROUTES)


def test_a_domain_module_edit_absent_from_the_diff_fails_closed() -> None:
    with pytest.raises(sel.DiffNotParsed):
        sel.select(["backend/ofo/errors/gate_slots.py"], "", TESTS_APP, run_snap, ROUTES)


def test_a_comment_only_edit_in_a_domain_module_selects_nothing() -> None:
    rel = "backend/ofo/errors/gate_slots.py"
    diff = f"diff --git a/{rel} b/{rel}\n--- a/{rel}\n+++ b/{rel}\n@@ -1,1 +1,2 @@\n x\n+# only a comment\n"
    assert sel.select([rel], diff, TESTS_APP, run_snap, ROUTES) == []


# ---- GC-CLEAN (2026-10-30): a deleted backend module. Its hunk is `@@ -1,N +0,0 @@` (new side starts at 0), so the
# parser saw "no hunk" and the selector failed closed on every branch that deletes a module (GC-TP 1a deleted
# ofo_app/tracking_store.py). A deletion keys on the module's name: any test still importing it is selected. --------

DELETED = "backend/ofo_app/strategy_store.py"


def _deletion(rel: str, lines: int = 2) -> str:
    body = "".join(f"-x{i} = {i}\n" for i in range(lines))
    return (f"diff --git a/{rel} b/{rel}\ndeleted file mode 100644\nindex 1111111..0000000\n--- a/{rel}\n"
            f"+++ /dev/null\n@@ -1,{lines} +0,0 @@\n{body}")


def test_a_deleted_module_is_parsed_as_deleted_not_as_no_hunk() -> None:
    assert sel.parse_diff(_deletion(DELETED)) == {DELETED: sel.DELETED}


def test_a_deleted_module_selects_the_tests_that_still_name_it_and_reads_no_source() -> None:
    def no_read(rel: str) -> str:
        raise AssertionError(f"read {rel}")  # a deleted file has no source to read

    assert sel.keys_for([DELETED], _deletion(DELETED), ROOT, no_read, []) == [sel.Key("ofo_app.strategy_store",
                                                                                      "module")]
    assert "tests_app/test_execute_revision.py" in sel.select([DELETED], _deletion(DELETED), TESTS_APP, no_read, [])


def test_a_deletion_still_reaches_a_route_file_that_imports_the_module() -> None:
    route = "backend/ofo_app/routes/strategies.py"
    keys = sel.keys_for([DELETED], _deletion(DELETED), ROOT, snap, [route])
    assert "/strategies" in {k.name for k in keys}  # strategies.py imports strategy_store (PR #241 snapshot)


def test_a_deleted_migration_selects_the_fixed_migration_set_not_nothing() -> None:
    """Review MAJOR (GC-CLEAN): a deleted migration keyed on its module name selected 0 files (fail open)."""
    names = {pathlib.PurePosixPath(p).name for p in sel.select([MIG], _deletion(MIG), TESTS_APP, snap, [])}
    assert "test_strategy_shape_matrix.py" in names and "test_alembic_migration_guard.py" in names


def test_a_deleted_route_file_fails_closed() -> None:
    """Review MINOR: a deleted route loses its route-path keys; with no source to read them from, refuse."""
    route = "backend/ofo_app/routes/outcome.py"
    with pytest.raises(sel.DiffNotParsed):
        sel.keys_for([route], _deletion(route), ROOT, snap, [])


def test_a_path_deleted_then_added_in_one_diff_fails_closed() -> None:
    """Review MINOR: delete + add of the same path (a type change) must not read as a plain deletion."""
    add = (f"diff --git a/{DELETED} b/{DELETED}\nnew file mode 100644\n--- /dev/null\n+++ b/{DELETED}\n"
           "@@ -0,0 +1,1 @@\n+y = 1\n")
    with pytest.raises(sel.DiffNotParsed):
        sel.parse_diff(_deletion(DELETED) + add)
