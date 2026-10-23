"""Reach check (finding verified-on-a-module-the-product-does-not-call): synthetic mini-trees in tmp_path.

Each test builds a tiny repo (backend/ofo, backend/ofo_app, work, requirements, evidence, tests) and asserts the verdict
of one AC: reached, UNREACHED or UNRESOLVED, and the exit code of `main` with and without a baseline.
"""
import importlib.util
import json
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("reach_check", ROOT / "scripts" / "orchestrator" / "reach_check.py")
rc = importlib.util.module_from_spec(_spec)
sys.modules["reach_check"] = rc
_spec.loader.exec_module(rc)

SETUP_FAULT = 2  # exit code for an unusable baseline
REQ_DIR = ("sp" + "ec", "requirements")


def _w(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


def _tree(tmp_path: Path, app_imports: str = "", files: dict[str, str] | None = None, test: str | None = None,
          **ev: str) -> Path:
    """One requirement REQ-001, owned by W-001 with AC-1 evidence; the app (ofo_app.main) holds `app_imports`."""
    _w(tmp_path, "backend/ofo/__init__.py", "")
    _w(tmp_path, "backend/ofo_app/__init__.py", "")
    _w(tmp_path, "backend/ofo_app/main.py", app_imports + "\n")
    for rel, text in (files or {}).items():
        _w(tmp_path, "backend/" + rel, text)
    if test is not None:
        _w(tmp_path, "tests/x/test_a.py", test)
    req = ev.get("req_status", "Verified")
    work = ev.get("work_status", "done")
    named = ev.get("evidence_tests", "tests/x/test_a.py")
    _w(tmp_path, "/".join((*REQ_DIR, "REQ-001.md")), f"---\nid: REQ-001\nstatus: {req}\n---\n")
    _w(tmp_path, "work/W-001.md", f"---\nid: W-001\nrequirement_ids:\n- REQ-001\nstatus: {work}\n---\n")
    _w(tmp_path, "evidence/W-001/AC-1.md",
       f"---\nwork_item: W-001\nac: AC-1\nresult: {ev.get('result', 'pass')}\n"
       f"commands: \"python -m pytest {named}\"\n---\n")
    return tmp_path


DOMAIN = {"ofo/x/__init__.py": "", "ofo/x/y.py": "VALUE = 1\n"}
TEST_Y = "from ofo.x.y import VALUE\n"


def _verdicts(root: Path) -> list[tuple[str, str]]:
    return [(h["kind"], h["key"]) for h in rc.find_hits(root)]


def test_reached_through_a_route_module(tmp_path):
    root = _tree(tmp_path, app_imports="from ofo_app.routes import r\n",
                 files={**DOMAIN, "ofo_app/routes/__init__.py": "", "ofo_app/routes/r.py": "import ofo.x.y\n"},
                 test=TEST_Y)
    assert _verdicts(root) == []


def test_reached_through_a_package_reexport(tmp_path):
    """Attack 3: the app imports ofo.x, whose __init__ re-exports from ofo.x.y; a test on ofo.x.y is reached."""
    files = {"ofo/x/__init__.py": "from ofo.x.y import VALUE\n", "ofo/x/y.py": "VALUE = 1\n"}
    root = _tree(tmp_path, app_imports="import ofo.x\n", files=files, test=TEST_Y)
    assert _verdicts(root) == []
    (root / "tests/x/test_a.py").write_text("import ofo.x\n", encoding="utf-8")
    assert _verdicts(root) == []


def test_aliased_and_from_package_imports_resolve_to_the_same_module(tmp_path):
    """Attack 2: `import ofo.x.y as p` and `from ofo.x import y` both name ofo.x.y."""
    root = _tree(tmp_path, files=DOMAIN)
    index = rc.build_index(root)
    for src in ("import ofo.x.y as p\n", "from ofo.x import y\n", "from ofo.x import y as q\n"):
        f = root / "probe.py"
        f.write_text(src, encoding="utf-8")
        found, _plain, bad = rc.scan_source(f, None, False, index)
        assert "ofo.x.y" in found and bad == [], src


def test_app_aliased_import_reaches_the_module(tmp_path):
    root = _tree(tmp_path, app_imports="import ofo.x.y as p\n", files=DOMAIN, test="from ofo.x import y\n")
    assert _verdicts(root) == []


def test_relative_import_inside_backend_is_followed(tmp_path):
    files = {**DOMAIN, "ofo_app/routes/__init__.py": "", "ofo_app/routes/r.py": "from .. import helper\n",
             "ofo_app/helper.py": "import ofo.x.y\n"}
    root = _tree(tmp_path, app_imports="from ofo_app.routes import r\n", files=files, test=TEST_Y)
    assert _verdicts(root) == []


def test_unreached_domain_module_is_flagged_and_exit_is_one(tmp_path, capsys):
    root = _tree(tmp_path, files=DOMAIN, test=TEST_Y)
    assert _verdicts(root) == [("UNREACHED", "UNREACHED REQ-001 W-001 AC-1")]
    assert rc.main(["--root", str(root), "--no-baseline"]) == 1
    line = capsys.readouterr().out.splitlines()[0]
    assert line == "UNREACHED REQ-001 W-001 AC-1 tests/x/test_a.py ofo.x.y  [NEW]"


def test_from_package_import_names_only_the_submodule(tmp_path):
    root = _tree(tmp_path, files=DOMAIN, test="from ofo.x import y\n")
    assert [h["modules"] for h in rc.find_hits(root)] == ["ofo.x.y"]


def test_importing_a_package_runs_its_init_when_a_submodule_is_reached(tmp_path):
    files = {**DOMAIN, "ofo/x/helper.py": "H = 1\n"}
    root = _tree(tmp_path, app_imports="import ofo.x.helper\n", files=files, test="import ofo.x\n")
    assert _verdicts(root) == []


def test_deleting_the_only_app_import_turns_the_ac_unreached(tmp_path):
    """Attack 1: the same tree, the app's import of the domain module removed in the copy."""
    files = {**DOMAIN, "ofo_app/routes/__init__.py": "", "ofo_app/routes/r.py": "import ofo.x.y\n"}
    root = _tree(tmp_path, app_imports="from ofo_app.routes import r\n", files=files, test=TEST_Y)
    assert _verdicts(root) == []
    (root / "backend/ofo_app/routes/r.py").write_text("import json\n", encoding="utf-8")
    assert _verdicts(root) == [("UNREACHED", "UNREACHED REQ-001 W-001 AC-1")]


def test_a_test_on_a_helper_the_app_reaches_does_not_hide_the_unreached_subject(tmp_path):
    """The test is about ofo.x.* (its folder); the app reaches only the shared helper ofo.x.helper."""
    files = {**DOMAIN, "ofo/x/helper.py": "H = 1\n"}
    root = _tree(tmp_path, app_imports="import ofo.x.helper\n", files=files,
                 test="from ofo.x.helper import H\nfrom ofo.x.y import VALUE\n")
    assert _verdicts(root) == [("UNREACHED", "UNREACHED REQ-001 W-001 AC-1")]


def test_a_test_about_its_folder_is_judged_on_that_package_only(tmp_path):
    """tests/x/ is about ofo.x: an unreached module of another package it also imports does not decide the AC."""
    files = {**DOMAIN, "ofo/x/helper.py": "H = 1\n", "ofo/other/__init__.py": "", "ofo/other/z.py": "Z = 1\n"}
    root = _tree(tmp_path, app_imports="import ofo.x.helper\n", files=files,
                 test="from ofo.x.helper import H\nfrom ofo.other.z import Z\n")
    assert _verdicts(root) == []


def test_type_checking_import_is_not_a_runtime_import(tmp_path):
    app = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import ofo.x.y\n"
    root = _tree(tmp_path, app_imports=app, files=DOMAIN, test=TEST_Y)
    assert _verdicts(root) == [("UNREACHED", "UNREACHED REQ-001 W-001 AC-1")]


def test_dynamic_import_in_a_reached_module_is_unresolved_not_reached(tmp_path):
    """Attack 4: importlib.import_module("ofo.x.y") in the app: named UNRESOLVED, never silently reached."""
    app = 'import importlib\nimportlib.import_module("ofo.x.y")\n'
    root = _tree(tmp_path, app_imports=app, files=DOMAIN, test=TEST_Y)
    hits = rc.find_hits(root)
    assert [(h["kind"], h["key"]) for h in hits] == [("UNRESOLVED", "UNRESOLVED REQ-001 W-001 AC-1")]
    assert "ofo_app.main" in hits[0]["detail"] and "dynamic import" in hits[0]["detail"]


@pytest.mark.parametrize("app", ["from importlib import import_module as im\n", "f = __import__\n",
                                 "import importlib\ng = importlib.import_module\n"])
def test_aliased_dynamic_import_shapes_are_unresolved(tmp_path, app):
    root = _tree(tmp_path, app_imports=app, files=DOMAIN, test=TEST_Y)
    assert _verdicts(root) == [("UNRESOLVED", "UNRESOLVED REQ-001 W-001 AC-1")]


def test_dynamic_import_in_the_test_file_is_unresolved(tmp_path):
    root = _tree(tmp_path, files=DOMAIN, test=TEST_Y + "import importlib\nimportlib.import_module('ofo.x.y')\n")
    hits = rc.find_hits(root)
    assert [h["kind"] for h in hits] == ["UNRESOLVED"] and "tests/x/test_a.py" in hits[0]["detail"]


def test_import_of_an_unknown_product_module_is_unresolved(tmp_path):
    root = _tree(tmp_path, files=DOMAIN, test="import ofo.x.y\nimport ofo.nowhere\n")
    hits = rc.find_hits(root)
    assert [h["kind"] for h in hits] == ["UNRESOLVED"] and "ofo.nowhere" in hits[0]["detail"]


def test_evidence_naming_no_test_file_is_unresolved(tmp_path):
    root = _tree(tmp_path, files=DOMAIN, test=TEST_Y, evidence_tests="the e2e run")
    hits = rc.find_hits(root)
    assert [h["kind"] for h in hits] == ["UNRESOLVED"] and "names no python test file" in hits[0]["detail"]


def test_missing_and_unparseable_test_files_are_unresolved(tmp_path):
    root = _tree(tmp_path, files=DOMAIN, test=TEST_Y, evidence_tests="tests/x/test_gone.py")
    hits = rc.find_hits(root)
    assert [h["kind"] for h in hits] == ["UNRESOLVED"] and "test_gone.py" in hits[0]["detail"]
    root2 = _tree(tmp_path / "b", files=DOMAIN, test="def broken(:\n")
    hits2 = rc.find_hits(root2)
    assert [h["kind"] for h in hits2] == ["UNRESOLVED"] and "unreadable" in hits2[0]["detail"]


def test_evidence_with_a_node_id_finds_and_parses_the_file(tmp_path):
    """Attack 5: `tests/x/test_a.py::test_a` names the file."""
    root = _tree(tmp_path, files=DOMAIN, test=TEST_Y, evidence_tests="tests/x/test_a.py::test_a")
    assert _verdicts(root) == [("UNREACHED", "UNREACHED REQ-001 W-001 AC-1")]


def test_evidence_naming_a_directory_expands_to_its_test_files(tmp_path):
    root = _tree(tmp_path, files=DOMAIN, test=TEST_Y, evidence_tests="tests/x/")
    assert _verdicts(root) == [("UNREACHED", "UNREACHED REQ-001 W-001 AC-1")]


def test_work_item_tests_required_is_used_when_evidence_names_none(tmp_path):
    root = _tree(tmp_path, files=DOMAIN, test=TEST_Y, evidence_tests="a live run")
    _w(root, "work/W-001.md",
       "---\nid: W-001\nrequirement_ids:\n- REQ-001\ntests_required:\n- 'AC-1: tests/x/test_a.py'\nstatus: done\n---\n")
    assert _verdicts(root) == [("UNREACHED", "UNREACHED REQ-001 W-001 AC-1")]


def test_scope_is_verified_or_owned_by_an_in_review_or_done_item(tmp_path):
    out = _tree(tmp_path / "a", files=DOMAIN, test=TEST_Y, req_status="Approved", work_status="in_progress")
    assert _verdicts(out) == []  # neither Verified nor a finished owner: not in scope
    inrev = _tree(tmp_path / "b", files=DOMAIN, test=TEST_Y, req_status="Approved", work_status="in_review")
    assert len(_verdicts(inrev)) == 1
    ver = _tree(tmp_path / "c", files=DOMAIN, test=TEST_Y, req_status="Verified", work_status="todo")
    assert len(_verdicts(ver)) == 1


def test_failing_evidence_is_not_judged(tmp_path):
    root = _tree(tmp_path, files=DOMAIN, test=TEST_Y, result="fail")
    assert _verdicts(root) == []


def test_process_runner_must_be_classified(tmp_path):
    root = _tree(tmp_path, files={**DOMAIN, "ofo_app/job.py": 'if __name__ == "__main__":\n    pass\n'}, test=TEST_Y)
    with pytest.raises(SystemExit, match=r"ofo_app\.job"):
        rc.find_hits(root)


def test_baseline_accepts_known_hit_and_refuses_new_and_stale_entries(tmp_path, capsys):
    root = _tree(tmp_path, files=DOMAIN, test=TEST_Y)
    base = root / "baseline.json"
    entry = {"key": "UNREACHED REQ-001 W-001 AC-1", "reason": "r - #532", "issue": "#532"}
    base.write_text(json.dumps({"entries": [entry]}), encoding="utf-8")
    assert rc.main(["--root", str(root), "--baseline", str(base)]) == 0
    base.write_text(json.dumps({"entries": []}), encoding="utf-8")
    assert rc.main(["--root", str(root), "--baseline", str(base)]) == 1  # a NEW hit
    (root / "backend/ofo_app/main.py").write_text("import ofo.x.y\n", encoding="utf-8")  # the hit goes away
    base.write_text(json.dumps({"entries": [entry]}), encoding="utf-8")
    capsys.readouterr()
    assert rc.main(["--root", str(root), "--baseline", str(base)]) == 1  # attack 6: a stale entry
    assert "STALE baseline entry no longer occurs: UNREACHED REQ-001 W-001 AC-1" in capsys.readouterr().out


BAD_BASELINES = ['{"entries": [{"key": "k", "reason": "r"}]}',
                 '{"entries": [{"key": "k", "reason": "", "issue": "i"}]}', '{"nope": []}', "not json"]


@pytest.mark.parametrize("body", BAD_BASELINES)
def test_malformed_baseline_is_a_setup_fault(tmp_path, body):
    root = _tree(tmp_path, files=DOMAIN, test=TEST_Y)
    base = root / "baseline.json"
    base.write_text(body, encoding="utf-8")
    assert rc.main(["--root", str(root), "--baseline", str(base)]) == SETUP_FAULT


def test_json_output_lists_hits_new_and_stale(tmp_path, capsys):
    root = _tree(tmp_path, files=DOMAIN, test=TEST_Y)
    assert rc.main(["--root", str(root), "--no-baseline", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["counts"] == {"UNREACHED": 1, "UNRESOLVED": 0}
    assert data["new"] == ["UNREACHED REQ-001 W-001 AC-1"] and data["stale"] == []


def test_a_test_importing_no_product_module_is_unresolved(tmp_path):
    root = _tree(tmp_path, files=DOMAIN, test="import json\n")
    hits = rc.find_hits(root)
    assert [h["kind"] for h in hits] == ["UNRESOLVED"] and hits[0]["detail"] == "test imports no product module"


def test_one_missing_test_file_among_real_ones_is_unresolved(tmp_path):
    root = _tree(tmp_path, app_imports="import ofo.x.y\n", files=DOMAIN, test=TEST_Y,
                 evidence_tests="tests/x/test_a.py tests/x/test_gone.py")
    hits = rc.find_hits(root)
    assert [h["kind"] for h in hits] == ["UNRESOLVED"] and "test_gone.py" in hits[0]["detail"]


def test_baseline_reason_without_an_issue_reference_is_refused(tmp_path, capsys):
    root = _tree(tmp_path, files=DOMAIN, test=TEST_Y)
    base = root / "baseline.json"
    entry = {"key": "UNREACHED REQ-001 W-001 AC-1", "reason": "owner decision", "issue": "#532"}
    base.write_text(json.dumps({"entries": [entry]}), encoding="utf-8")
    assert rc.main(["--root", str(root), "--baseline", str(base)]) == 1
    assert "REFUSED baseline reason without an issue reference" in capsys.readouterr().err
    entry["reason"] = "unreached: ofo.x.y imported by no app entry point - #532"
    base.write_text(json.dumps({"entries": [entry]}), encoding="utf-8")
    assert rc.main(["--root", str(root), "--baseline", str(base)]) == 0
