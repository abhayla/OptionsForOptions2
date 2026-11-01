"""merge_preflight.py: the finding filter, the changed-file list and the stop-at-first-red-layer order.

The real-data proof (the 2026-11-01 merge breaks put back into a scratch copy are all flagged; the fixed tree is clean)
is recorded in the PR body; these tests pin the pieces that decide it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "orchestrator"))
import merge_preflight as mp

# real mypy lines of 2026-11-01 (the five background breaks and two test breaks), plus noise the filter must drop
BREAKS = [
    'ofo_app\\background.py:265: error: Missing named argument "windows" for "resolve_spot"  [call-arg]',
    'ofo_app\\background.py:266: error: Missing named argument "config" for "state_of"  [call-arg]',
    'ofo_app\\background.py:275: error: Missing named argument "gap_until" for "evaluate_and_remember"  [call-arg]',
    'ofo_app\\background.py:515: error: Module "ofo_app.live_market" has no attribute "LIVE_RATE"  [attr-defined]',
    'tests\\x.py:12: error: Name "QUALITY" is not defined  [name-defined]',
    'tests_app\\y.py:9: error: Too many positional arguments for "fwd"  [call-arg]',
]
NOISE = [
    'ofo\\engine\\model.py:123: error: "ModelInputs" has no attribute "inputs"  [attr-defined]',
    'ofo_app\\adjustment_readers.py:97: error: Argument 4 to "PositionLeg" has incompatible type  [arg-type]',
    'ofo_app\\background.py:366: error: Incompatible return value type  [return-value]',
    'ofo\\errors\\templates.py:1341: error: Invalid "type: ignore" comment  [syntax]',
    "ofo_app\\background.py:265: note: \"resolve_spot\" defined in \"ofo.marketdata.spot_source\"",
]


def test_the_filter_keeps_every_merge_break_and_drops_the_noise():
    assert mp.interface_findings("\n".join(BREAKS + NOISE)) == BREAKS


def test_an_empty_or_clean_mypy_run_has_no_findings():
    assert mp.interface_findings("") == []
    assert mp.interface_findings("\n".join(NOISE)) == []


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)  # noqa: S603, S607


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    (r / "backend" / "pkg").mkdir(parents=True)
    (r / "docs").mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    (r / "backend" / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (r / "backend" / "pkg" / "b.py").write_text("y = 1\n", encoding="utf-8")
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "base")
    git(r, "checkout", "-q", "-b", "work")
    return r


def test_changed_files_are_committed_dirty_and_untracked_python_under_the_roots(repo):
    (repo / "backend" / "pkg" / "a.py").write_text("x = 2\n", encoding="utf-8")
    git(repo, "commit", "-qam", "change a")
    (repo / "backend" / "pkg" / "b.py").write_text("y = 2\n", encoding="utf-8")  # uncommitted
    (repo / "tests").mkdir()
    (repo / "tests" / "test_new.py").write_text("", encoding="utf-8")  # untracked
    (repo / "docs" / "note.py").write_text("", encoding="utf-8")  # outside the roots
    (repo / "backend" / "pkg" / "data.json").write_text("{}", encoding="utf-8")  # not Python
    assert mp.changed_python(str(repo), "main") == ["backend/pkg/a.py", "backend/pkg/b.py", "tests/test_new.py"]


def test_a_deleted_file_is_not_checked(repo):
    git(repo, "rm", "-q", "backend/pkg/b.py")
    git(repo, "commit", "-qm", "drop b")
    assert mp.changed_python(str(repo), "main") == []


def test_an_unreadable_base_fails_closed_to_none(repo):
    assert mp.changed_python(str(repo), "no-such-branch") is None


def test_the_first_red_layer_stops_the_run(monkeypatch, tmp_path, capsys):
    ran = []

    def layer(name, rc):
        def go(*_a):
            ran.append(name)
            return rc, f"{name} note"
        return go
    monkeypatch.setattr(mp, "layer_interface", layer("interface", 1))
    monkeypatch.setattr(mp, "layer_collect", layer("collect", 0))
    monkeypatch.setattr(mp, "layer_scans", layer("scans", 0))
    assert mp.run(str(tmp_path), "main", str(tmp_path)) == 1
    out = capsys.readouterr().out
    assert ran == ["interface"] and "FAIL preflight-interface" in out and "PREFLIGHT FAIL at interface" in out


def test_all_layers_green_is_a_pass(monkeypatch, tmp_path, capsys):
    for name in ("layer_interface", "layer_collect", "layer_scans"):
        monkeypatch.setattr(mp, name, lambda *_a: (0, "ok"))
    assert mp.run(str(tmp_path), "main", str(tmp_path)) == 0
    assert "PREFLIGHT PASS" in capsys.readouterr().out


def test_a_missing_mypy_fails_the_interface_layer_closed(monkeypatch, repo, tmp_path):
    (repo / "backend" / "pkg" / "a.py").write_text("x = 3\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "mypy", None)  # import mypy -> ImportError
    rc, note = mp.layer_interface(str(repo), "main", str(tmp_path / "log"))
    assert rc == 1 and "mypy is not installed" in note


def _frontend(tmp_path, manifest=True, config_manifest=True):
    """A frontend tree whose Vite config turns the manifest on (or not), with an index.html build stamp; the config is
    two minutes old so it is never the newest input unless a test says so."""
    fe = tmp_path / "frontend"
    (fe / "src").mkdir(parents=True)
    (fe / "src" / "a.js").write_text("1", encoding="utf-8")
    config = fe / "vite.config.js"
    config.write_text("export default { build: { manifest: true } }\n" if config_manifest else "export default {}\n",
                      encoding="utf-8")
    _age(config, 120)
    (fe / "dist" / ".vite").mkdir(parents=True)
    (fe / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    if manifest:
        (fe / "dist" / ".vite" / "manifest.json").write_text("{}", encoding="utf-8")
    return fe


def _age(path, seconds_ago):
    t = time.time() - seconds_ago
    os.utime(path, (t, t))


def test_no_build_passes_because_the_bundle_scan_skips_locally(tmp_path):
    rc, note = mp.layer_build(str(tmp_path), str(tmp_path / "log"))
    assert rc == 0 and "skips" in note


def test_a_build_without_its_manifest_fails_with_the_fix(tmp_path):
    _frontend(tmp_path, manifest=False)
    rc, note = mp.layer_build(str(tmp_path), str(tmp_path / "log"))
    assert rc == 1 and "manifest" in note and "npm run build" in note


def test_a_build_older_than_a_frontend_input_fails_and_names_it(tmp_path):
    fe = _frontend(tmp_path)
    _age(fe / "dist" / ".vite" / "manifest.json", 60)  # built a minute before the source changed
    rc, note = mp.layer_build(str(tmp_path), str(tmp_path / "log"))
    assert rc == 1 and "frontend/src/a.js" in note


def test_a_build_newer_than_every_input_passes(tmp_path):
    fe = _frontend(tmp_path)
    _age(fe / "src" / "a.js", 60)
    rc, _note = mp.layer_build(str(tmp_path), str(tmp_path / "log"))
    assert rc == 0


def test_the_build_check_runs_first_and_its_red_stops_the_run(monkeypatch, tmp_path, capsys):
    ran = []
    for name in ("layer_interface", "layer_collect", "layer_scans"):
        monkeypatch.setattr(mp, name, lambda *_a, n=name: ran.append(n) or (0, "ok"))
    monkeypatch.setattr(mp, "layer_build", lambda *_a: (1, "stale"))
    assert mp.run(str(tmp_path), "main", str(tmp_path)) == 1
    assert ran == [] and "PREFLIGHT FAIL at build" in capsys.readouterr().out


def test_no_domain_scans_skips_only_the_tests_repo_scan(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(mp, "_run", lambda cmd, *_a, **_k: calls.append(" ".join(cmd)) or 0)
    monkeypatch.setattr(mp, "CHECKS", ())
    mp.layer_scans(str(tmp_path), str(tmp_path / "log"), domain_scans=False)
    assert not any("repo_scan tests" in c and "tests_app" not in c for c in calls)
    assert any("-m repo_scan tests_app" in c for c in calls)


# ---- review 2026-11-01 (REVISE: 3 MAJOR, 8 MINOR): each fix below has its test -------------------------------------
def test_major3_a_config_without_a_manifest_is_judged_by_index_html(tmp_path):
    """MAJOR 3: main's Vite config writes no manifest; demanding one was a false red on every main-based push."""
    fe = _frontend(tmp_path, manifest=False, config_manifest=False)
    _age(fe / "src" / "a.js", 60)
    assert mp.layer_build(str(tmp_path), str(tmp_path / "log"))[0] == 0
    _age(fe / "dist" / "index.html", 90)  # the build is now older than the source
    rc, note = mp.layer_build(str(tmp_path), str(tmp_path / "log"))
    assert rc == 1 and "frontend/src/a.js" in note


def test_major3_a_config_with_a_manifest_still_requires_it(tmp_path):
    _frontend(tmp_path, manifest=False, config_manifest=True)
    rc, note = mp.layer_build(str(tmp_path), str(tmp_path / "log"))
    assert rc == 1 and "manifest.json" in note


def test_finding_key_drops_the_line_number_and_normalises_the_slashes():
    assert mp.finding_key(r'tests\a\b.py:12: error: Name "x" is not defined  [name-defined]') == (
        "tests/a/b.py", 'Name "x" is not defined  [name-defined]')


def test_major2_a_known_entry_allows_only_its_counted_copies():
    """MAJOR 2: one reviewed copy must not hide a second, real copy of the same message in that file."""
    line1 = 'tests/x.py:10: error: Missing named argument "q" for "f"  [call-arg]'
    line2 = 'tests/x.py:99: error: Missing named argument "q" for "f"  [call-arg]'
    known = Counter({mp.finding_key(line1): 1})
    assert mp.new_findings([line1], known) == []
    assert mp.new_findings([line1, line2], known) == [line2]


def test_minor6_a_malformed_known_list_fails_closed_with_its_name(tmp_path, monkeypatch):
    monkeypatch.setattr(mp, "scope_files", lambda *_a: (["backend/x.py"], "changed"))
    known = tmp_path / mp.KNOWN_FILE
    known.parent.mkdir(parents=True)
    known.write_text('{"known": [{"file": "a", "message": "b", "count": 0}]}', encoding="utf-8")
    rc, note = mp.layer_interface(str(tmp_path), "main", str(tmp_path / "log"))
    assert rc == 1 and "merge_preflight_known.json is unreadable" in note


def test_minor5_a_folder_that_is_not_a_git_checkout_fails_closed(tmp_path):
    rc, note = mp.layer_interface(str(tmp_path), "main", str(tmp_path / "log"))
    assert rc == 1 and "cannot read the repository" in note


def test_minor7_domain_scans_on_runs_the_tests_repo_scan(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(mp, "_run", lambda cmd, *_a, **_k: calls.append(" ".join(cmd)) or 0)
    monkeypatch.setattr(mp, "CHECKS", ())
    mp.layer_scans(str(tmp_path), str(tmp_path / "log"), domain_scans=True)
    assert any(c.endswith("-m repo_scan tests") for c in calls)


def test_module_of_maps_backend_files_and_packages():
    assert mp.module_of("backend/ofo/a/b.py") == "ofo.a.b"
    assert mp.module_of("backend/ofo/a/__init__.py") == "ofo.a"
    assert mp.module_of("tests/test_x.py") is None


def test_major1_a_caller_added_on_main_is_checked_after_merging_main_in(tmp_path):
    """MAJOR 1, the reviewer's own attack: main adds a caller f(1) while the branch changes f(a) to f(a, b); after
    `git merge main` the diff lists only the callee, so the caller must come in as an importer and mypy must flag it."""
    r = tmp_path / "r"
    pkg = r / "backend" / "pkg"
    pkg.mkdir(parents=True)
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "callee.py").write_text("def f(a: int) -> int:\n    return a\n", encoding="utf-8")
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "base")
    git(r, "checkout", "-q", "-b", "work")
    (pkg / "callee.py").write_text("def f(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    git(r, "commit", "-qam", "f takes b")
    git(r, "checkout", "-q", "main")
    (pkg / "caller.py").write_text("from pkg.callee import f\n\n\ndef g() -> int:\n    return f(1)\n", encoding="utf-8")
    git(r, "add", ".")
    git(r, "commit", "-qm", "caller on main")
    git(r, "checkout", "-q", "work")
    git(r, "merge", "-q", "--no-edit", "main")
    assert mp.changed_python(str(r), "main") == ["backend/pkg/callee.py"]  # the diff alone misses the caller
    assert mp.importers_of(str(r), ["backend/pkg/callee.py"]) == ["backend/pkg/caller.py"]
    rc, note = mp.layer_interface(str(r), "main", str(tmp_path / "log"))
    assert rc == 1, note
    assert 'Missing positional argument "b"' in (tmp_path / "log").read_text(encoding="utf-8")
