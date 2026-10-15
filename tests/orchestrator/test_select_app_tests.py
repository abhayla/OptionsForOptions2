"""#242: the selector picks the tests_app files a route / response-model change can break (finding
targeted-tests-miss-dependent-files, 4th occurrence). Pure: the fixture carries PR #241's real backend diff (feature
commits before its fix round 2e317c2); tests_app/ and backend/ are the repo's real folders. No DB, network or git."""
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "orchestrator"))
import select_app_tests as sel  # noqa: E402

TESTS_APP = ROOT / "tests_app"
DIFF = (pathlib.Path(__file__).parent / "fixtures" / "pr241-backend.diff").read_text(encoding="utf-8")
FILES = ["backend/ofo/errors/explanations.py", "backend/ofo_app/catalogue_picker.py",
         "backend/ofo_app/routes/catalogue.py", "backend/ofo_app/routes/strategies.py"]
SRC = pathlib.Path(__file__).parent / "fixtures" / "pr241-src"  # the files as at 3d76787, not today's


def snap(rel: str) -> str:
    return (SRC / pathlib.PurePosixPath(rel).name).read_text(encoding="utf-8")


EXACT = ["tests_app/test_catalogue_picker_api.py", "tests_app/test_response_door.py",
         "tests_app/test_strategy_closed_shape.py", "tests_app/test_strategy_followups.py",
         "tests_app/test_strategy_planned_entry.py", "tests_app/test_strategy_store.py"]
RED = {"tests_app/test_response_door.py", "tests_app/test_strategy_planned_entry.py"}


def test_pr241_diff_selects_both_red_files_and_exactly_the_six() -> None:
    chosen = sel.select(FILES, DIFF, TESTS_APP, snap)
    print("SELECTED", len(chosen), chosen)
    assert RED <= set(chosen), chosen
    assert chosen == EXACT, chosen  # exact: any drift in the matching or in tests_app/ shows here


def test_pr241_diff_does_not_select_the_catalogue_loading_tests() -> None:
    chosen = sel.select(FILES, DIFF, TESTS_APP, snap)
    loaders = [p for p in chosen if re.search(r"test_catalogue_(load|ingest|instruments|refresh)", p)]
    assert loaders == [], loaders


def test_keys_name_what_the_diff_changed() -> None:
    names = {k.name for k in sel.keys_for(FILES, DIFF, ROOT, snap)}
    assert {"LegOut", "ContractOut", "PickableContract"} <= names
    assert "/strategies/{strategy_id}" in names and "/strategies" in names  # routes reached through _strategy_out
    assert "StrategyOut" not in names and "HistoryOut" not in names  # defined in the file, not changed
    assert "/api/catalogue/{underlying}/contracts" in names


def test_each_red_file_has_its_key() -> None:
    by_key = sel.select_by_key(FILES, DIFF, TESTS_APP, snap)
    for name, files in by_key.items():
        print("KEY", name, len(files), files)
    assert "tests_app/test_strategy_planned_entry.py" in by_key["/strategies"]  # route path
    assert "tests_app/test_response_door.py" in by_key["LegOut"]  # response-model name


def _line_of(rel: str, needle: str) -> int:
    for n, line in enumerate(snap(rel).splitlines(), 1):
        if line.startswith(needle):
            return n
    raise AssertionError(needle)


def test_a_diff_touching_no_route_or_model_selects_nothing() -> None:
    diff = ("diff --git a/backend/ofo/errors/explanations.py b/backend/ofo/errors/explanations.py\n"
            "--- a/backend/ofo/errors/explanations.py\n+++ b/backend/ofo/errors/explanations.py\n"
            "@@ -1,1 +1,2 @@\n x\n+y = 1\n")
    assert sel.select(["backend/ofo/errors/explanations.py"], diff, TESTS_APP, snap) == []
    assert sel.select([], "", TESTS_APP) == []


def test_a_comment_only_edit_in_a_route_file_selects_nothing() -> None:
    n = _line_of("backend/ofo_app/routes/strategies.py", "    exchange_token: int")
    diff = ("diff --git a/backend/ofo_app/routes/strategies.py b/backend/ofo_app/routes/strategies.py\n"
            "--- a/backend/ofo_app/routes/strategies.py\n+++ b/backend/ofo_app/routes/strategies.py\n"
            f"@@ -{n},1 +{n},2 @@\n-    exchange_token: int\n+    exchange_token: int  # the token\n"
            f"+    # a new comment line\n")
    assert sel.select(["backend/ofo_app/routes/strategies.py"], diff, TESTS_APP, snap) == []


def test_an_unreadable_diff_fails_closed() -> None:
    with pytest.raises(sel.DiffNotParsed):
        sel.select(["backend/ofo_app/routes/strategies.py"], "Binary files a/x and b/x differ\n", TESTS_APP)
    rename = ("diff --git a/backend/ofo_app/routes/old.py b/backend/ofo_app/routes/strategies.py\n"
              "similarity index 100%\nrename from backend/ofo_app/routes/old.py\n"
              "rename to backend/ofo_app/routes/strategies.py\n")
    with pytest.raises(sel.DiffNotParsed):
        sel.select(["backend/ofo_app/routes/strategies.py"], rename, TESTS_APP)


def test_a_crlf_diff_selects_the_same_files() -> None:
    crlf = DIFF.replace("\r\n", "\n").replace("\n", "\r\n")
    assert sel.select(FILES, crlf, TESTS_APP, snap) == EXACT
