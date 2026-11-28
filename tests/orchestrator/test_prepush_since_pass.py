"""prepush: pass records per step (resume) and the docs-since-pass lane (27 Nov, lane G2 part 2)."""
import json
import os
import sys
from pathlib import Path

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, str(Path(HERE).resolve().parents[1] / "scripts" / "orchestrator"))
import merge_preflight  # noqa: E402
import prepush  # noqa: E402
from test_prepush import Runner, commit_file, docs_repo, git, sha_of, which  # noqa: E402

READERS = lambda r: (0, ["tests_app/test_reads_docs.py"], "1 files")  # noqa: E731
THREE = 3


def go(repo, tmp_path, runner, tag="l", **kw):
    kw.setdefault("since_pass", True)
    kw.setdefault("select_docs_app", READERS)
    kw.setdefault("select_domain", lambda r: ["tests/test_a.py"])
    kw.setdefault("select_app", lambda r: (0, ["tests_app/test_a.py"], "1 files"))
    kw.setdefault("select_frontend", lambda r: [])
    return prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / tag), which=which, **kw)


def marker(repo, sha=None):
    return json.loads(Path(prepush.marker_path(str(repo), sha or sha_of(repo))).read_text(encoding="utf-8"))


def stems(runner):
    return [Path(c[2]).stem for c in runner.calls]


def full_pass_on_code(tmp_path):
    """docs_repo + a code commit, gated in the full lane: the full-pass marker A."""
    repo = docs_repo(tmp_path)
    commit_file(repo, "backend/new.py", "y = 2\n")
    assert go(repo, tmp_path, Runner(), "a") == 0
    assert marker(repo)["mode"]["lane"] == "full"
    return repo, sha_of(repo)


# ---- docs-since-pass lane ----

def test_a_docs_commit_after_a_full_pass_runs_the_since_pass_lane_and_names_its_anchor(tmp_path, capsys):
    repo, a = full_pass_on_code(tmp_path)
    commit_file(repo, "spec/decisions/ADR-9.md", "row")
    runner, bases = Runner(), []
    pick = lambda r, b: bases.append(b) or ["tests/test_rec.py"]  # noqa: E731
    assert go(repo, tmp_path, runner, "b", select_since_domain=pick) == 0
    out = capsys.readouterr().out
    assert f"LANE docs-since-pass (1 files since {a[:8]})" in out
    assert bases == [a]  # the domain selection diffs against the full-pass commit, not against main
    pre = next(c[0] for c in runner.calls if Path(c[2]).stem == "preflight")
    assert prepush.SINCE_PASS_FLAG in pre
    dom = next(c[0] for c in runner.calls if Path(c[2]).stem == "domain_tests")
    assert dom[-1] == "tests/test_rec.py"
    app = next(c[0] for c in runner.calls if Path(c[2]).stem == "app_tests")
    assert app[-1] == "tests_app/test_reads_docs.py"
    assert marker(repo)["mode"]["lane"].startswith("docs-since-pass") and marker(repo)["mode"]["anchor"] == a


def test_a_chain_of_docs_commits_keeps_the_original_full_pass_as_anchor(tmp_path):
    repo, a = full_pass_on_code(tmp_path)
    for n in range(2):
        commit_file(repo, f"spec/decisions/ADR-{n}.md", "row")
        assert go(repo, tmp_path, Runner(), f"c{n}", select_since_domain=lambda r, b: ["tests/test_rec.py"]) == 0
        assert marker(repo)["mode"]["anchor"] == a


@pytest.mark.parametrize("rel", ["backend/x.py", "tests/test_x.py", "tests_app/test_x.py", "tools/x.py",
                                 ".github/x.yml", "frontend/src/a.js", "scripts/x.py", "docs/api/script.py",
                                 "pytest.ini"])
def test_any_non_records_file_since_the_full_pass_is_the_full_lane(tmp_path, capsys, rel):
    repo, _ = full_pass_on_code(tmp_path)
    commit_file(repo, "spec/decisions/ADR-1.md", "row")
    commit_file(repo, rel, "z = 1\n")
    runner = Runner()
    assert go(repo, tmp_path, runner, "d") == 0
    assert "docs-since-pass" not in capsys.readouterr().out
    assert marker(repo)["mode"]["lane"] == "full"
    pre = next(c[0] for c in runner.calls if Path(c[2]).stem == "preflight")
    assert prepush.SINCE_PASS_FLAG not in pre


def test_a_code_change_hidden_in_an_earlier_commit_is_seen_because_the_diff_is_against_the_anchor(tmp_path):
    repo, _ = full_pass_on_code(tmp_path)
    commit_file(repo, "backend/sneaky.py", "s = 1\n")  # never gated on its own
    commit_file(repo, "spec/decisions/ADR-2.md", "row")  # this one alone is docs-only
    assert prepush.since_pass_lane(str(repo), False, sha_of(repo)) is None


def test_no_marker_at_all_is_the_full_lane(tmp_path):
    repo = docs_repo(tmp_path)
    commit_file(repo, "spec/decisions/ADR-3.md", "row")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD~1")
    assert prepush.last_full_pass(str(repo), sha_of(repo)) is None
    assert prepush.since_pass_lane(str(repo), False, sha_of(repo)) is None


def test_a_docs_only_vs_main_marker_is_not_a_full_pass(tmp_path):
    repo = docs_repo(tmp_path)
    commit_file(repo, "spec/decisions/ADR-4.md", "row")
    prepush.write_marker(str(repo), sha_of(repo), [], {"jobs": 1, "lane": "docs-only (1 files)"})
    commit_file(repo, "spec/decisions/ADR-5.md", "row")
    assert prepush.last_full_pass(str(repo), sha_of(repo)) is None


def test_full_flag_never_takes_the_since_pass_lane(tmp_path):
    repo, _ = full_pass_on_code(tmp_path)
    commit_file(repo, "spec/decisions/ADR-6.md", "row")
    assert prepush.since_pass_lane(str(repo), True, sha_of(repo)) is None


def test_preflight_skips_only_the_two_python_only_layers_when_code_is_unchanged(monkeypatch, tmp_path, capsys):
    ran = []
    for name in ("build", "interface", "collect", "scans"):
        monkeypatch.setattr(merge_preflight, f"layer_{name}", lambda *a, _n=name, **k: (ran.append(_n), (0, "ok"))[1])
    assert merge_preflight.run(str(tmp_path), str(tmp_path), code_unchanged=True) == 0
    assert ran == ["build", "scans"] and capsys.readouterr().out.count("SKIP preflight-") == 2  # noqa: PLR2004
    ran.clear()
    assert merge_preflight.run(str(tmp_path), str(tmp_path)) == 0
    assert ran == ["build", "interface", "collect", "scans"]


# ---- resume ----

def test_a_rerun_on_the_same_tree_restarts_at_the_step_that_failed(tmp_path, capsys):
    repo = docs_repo(tmp_path)
    commit_file(repo, "backend/n.py", "y = 2\n")
    first = Runner(fail={"app_tests"})
    assert go(repo, tmp_path, first, "r1") == 1
    assert {"preflight", "ci_checks", "domain_tests", "app_tests"} <= set(stems(first))
    second = Runner()
    assert go(repo, tmp_path, second, "r2") == 0
    out = capsys.readouterr().out
    assert [s for s in stems(second) if s in prepush.RESUMABLE] == ["app_tests"]
    assert out.count("RESUME ") == THREE and "RESUME app_tests" not in out
    assert marker(repo)["steps"]  # a marker needs every step to have a passing row, resumed ones included


def test_a_failed_step_leaves_no_record_so_it_always_runs_again(tmp_path):
    repo = docs_repo(tmp_path)
    commit_file(repo, "backend/n.py", "y = 2\n")
    assert go(repo, tmp_path, Runner(fail={"domain_tests"}), "r1") == 1
    second = Runner(fail={"domain_tests"})
    assert go(repo, tmp_path, second, "r2") == 1
    assert "domain_tests" in stems(second)


def test_any_new_commit_changes_the_tree_and_nothing_is_reused(tmp_path):
    repo = docs_repo(tmp_path)
    commit_file(repo, "backend/n.py", "y = 2\n")
    assert go(repo, tmp_path, Runner(), "r1") == 0
    commit_file(repo, "backend/n.py", "y = 3\n")
    second = Runner()
    assert go(repo, tmp_path, second, "r2") == 0
    ran = {s for s in stems(second) if s in prepush.RESUMABLE}
    assert ran == {"preflight", "ci_checks", "domain_tests", "app_tests"}


def test_a_new_commit_with_the_same_tree_reuses_the_passes(tmp_path):
    repo = docs_repo(tmp_path)
    commit_file(repo, "backend/n.py", "y = 2\n")
    assert go(repo, tmp_path, Runner(), "r1") == 0
    git(repo, "commit", "-q", "--amend", "-m", "same tree, new message")
    second = Runner()
    assert go(repo, tmp_path, second, "r2") == 0
    assert [s for s in stems(second) if s in prepush.RESUMABLE] == []


def test_no_resume_runs_everything_again(tmp_path):
    repo = docs_repo(tmp_path)
    commit_file(repo, "backend/n.py", "y = 2\n")
    assert go(repo, tmp_path, Runner(), "r1") == 0
    again = Runner()
    assert go(repo, tmp_path, again, "r2", resume=False) == 0
    assert {"preflight", "ci_checks", "domain_tests", "app_tests"} <= set(stems(again))


def test_a_moved_origin_main_changes_the_selections_so_nothing_is_reused(tmp_path):
    repo = docs_repo(tmp_path)
    commit_file(repo, "backend/n.py", "y = 2\n")
    assert go(repo, tmp_path, Runner(), "r1") == 0
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD~2")
    second = Runner()
    assert go(repo, tmp_path, second, "r2") == 0
    assert "domain_tests" in stems(second)


def test_a_dirty_tree_neither_reads_nor_writes_pass_records(tmp_path):
    repo = docs_repo(tmp_path)
    commit_file(repo, "backend/n.py", "y = 2\n")
    (repo / "backend" / "n.py").write_text("y = 99\n", encoding="utf-8")  # tracked file modified, not committed
    first = Runner()
    go(repo, tmp_path, first, "r1")  # the marker is refused on a dirty tree; the steps still ran
    assert "domain_tests" in stems(first)
    root = prepush.marker_dir(str(repo))
    steps_dir = os.path.join(root, prepush.STEPS_DIR)
    assert not os.path.isdir(steps_dir) or not os.listdir(steps_dir)


def test_a_stopped_or_killed_step_leaves_no_record(tmp_path):
    repo = docs_repo(tmp_path)
    commit_file(repo, "backend/n.py", "y = 2\n")

    class Killed(Runner):
        def __call__(self, cmd, cwd, log_path):
            super().__call__(cmd, cwd, log_path)
            return prepush.STOPPED_RC if Path(log_path).stem == "app_tests" else 0

    assert go(repo, tmp_path, Killed(), "r1") == 1
    second = Runner()
    assert go(repo, tmp_path, second, "r2") == 0
    assert "app_tests" in stems(second)


# ---- review fixes (Opus review of d7e25431) ----

def test_the_since_pass_lane_is_opt_in(tmp_path, capsys):
    repo, _ = full_pass_on_code(tmp_path)
    commit_file(repo, "spec/decisions/ADR-7.md", "row")
    assert go(repo, tmp_path, Runner(), "o", since_pass=False) == 0
    assert "docs-since-pass" not in capsys.readouterr().out and marker(repo)["mode"]["lane"] == "full"


def test_frontend_steps_are_planned_in_the_since_pass_lane_as_in_the_full_lane(tmp_path):
    repo, _ = full_pass_on_code(tmp_path)
    (repo / "frontend" / "node_modules").mkdir(parents=True)
    commit_file(repo, "spec/decisions/ADR-8.md", "row")
    runner = Runner()
    assert go(repo, tmp_path, runner, "f", select_frontend=lambda r: ["src/a.js"],
              select_since_domain=lambda r, b: ["tests/test_rec.py"]) == 0
    assert "frontend_unit" in stems(runner) and marker(repo)["mode"]["lane"].startswith("docs-since-pass")


def test_a_classifier_changed_since_main_is_never_vouched_for_by_an_older_anchor(tmp_path):
    repo, _ = full_pass_on_code(tmp_path)
    commit_file(repo, "tools/change_scope.py", (repo / "tools" / "change_scope.py").read_text("utf-8") + "\n# x\n")
    assert go(repo, tmp_path, Runner(), "k") == 0
    commit_file(repo, "spec/decisions/ADR-9.md", "row")
    assert prepush.since_pass_lane(str(repo), False, sha_of(repo)) is None


def test_a_dirty_tree_never_takes_the_since_pass_lane(tmp_path, capsys):
    repo, _ = full_pass_on_code(tmp_path)
    commit_file(repo, "spec/decisions/ADR-10.md", "row")
    (repo / "backend" / "new.py").write_text("y = 3\n", encoding="utf-8")  # uncommitted code edit
    go(repo, tmp_path, Runner(), "d")
    assert "docs-since-pass" not in capsys.readouterr().out


def test_the_resume_key_has_the_merge_base_and_the_gate_files_and_the_checkout(tmp_path):
    repo = docs_repo(tmp_path)
    commit_file(repo, "backend/n.py", "y = 2\n")
    sha = sha_of(repo)
    parts = prepush.make_resume(str(repo), sha, False, "full", None, [], True).parts
    text = "\n".join(parts)
    assert any(p.startswith("mergebase=") for p in parts) and any(p.startswith("gate=") for p in parts)
    assert f"repo={repo}" in text and any(p.startswith("nm=") for p in parts)


def test_a_record_is_not_saved_when_head_moved_during_the_step(tmp_path):
    repo = docs_repo(tmp_path)
    commit_file(repo, "backend/n.py", "y = 2\n")

    class Moves(Runner):
        def __call__(self, cmd, cwd, log_path):
            if Path(log_path).stem == "domain_tests":
                commit_file(repo, "docs/moved.md", "m")  # HEAD moves while the step runs; the tree stays clean
            return super().__call__(cmd, cwd, log_path)

    go(repo, tmp_path, Moves(), "m")
    root = prepush.marker_dir(str(repo))
    steps_dir = os.path.join(root, prepush.STEPS_DIR)
    saved = os.listdir(steps_dir) if os.path.isdir(steps_dir) else []
    assert not [f for f in saved if f.startswith("domain_tests")]


def test_readers_include_tests_that_use_a_tools_module_naming_a_docs_path(tmp_path):
    repo = docs_repo(tmp_path)
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "scripts").mkdir(exist_ok=True)
    (repo / "scripts" / "register_check.py").write_text('P = "docs/process/ref.md"\n', encoding="utf-8")
    (repo / "tests" / "test_register.py").write_text("import register_check\n", encoding="utf-8")
    (repo / "tests" / "test_plain.py").write_text("x = 1\n", encoding="utf-8")
    rc, files, message = prepush.select_docs_readers(str(repo), "tests")
    assert rc == 0, message
    assert "tests/test_register.py" in files and "tests/test_plain.py" not in files


def test_a_non_dict_pass_record_or_marker_is_ignored_not_a_crash(tmp_path):
    repo, _ = full_pass_on_code(tmp_path)
    store = prepush.Resume(str(repo), ["k"], str(tmp_path / "steps"))
    os.makedirs(store.root)
    Path(store._path("app_tests")).write_text("[]", encoding="utf-8")
    assert store.hit("app_tests") is None


# ---- documentation-only path on by default, strict list (owner 28 Nov 2026) ----

def test_a_results_file_under_docs_design_takes_the_short_path(tmp_path, capsys):
    repo, a = full_pass_on_code(tmp_path)
    commit_file(repo, "docs/design/next-batch/RESULTS-lane-x.md", "results")
    assert go(repo, tmp_path, Runner(), "r", select_since_domain=lambda r, b: ["tests/test_rec.py"]) == 0
    assert f"LANE docs-since-pass (1 files since {a[:8]})" in capsys.readouterr().out
    assert marker(repo)["mode"]["anchor"] == a


def test_one_code_file_among_documentation_files_takes_the_full_path(tmp_path, capsys):
    repo, _ = full_pass_on_code(tmp_path)
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs" / "a.md").write_text("a", encoding="utf-8")
    (repo / "backend" / "b.py").write_text("b = 1\n", encoding="utf-8")
    git(repo, "add", "docs/a.md", "backend/b.py")
    git(repo, "commit", "-q", "-m", "mixed")
    assert prepush.since_pass_lane(str(repo), False, sha_of(repo)) is None
    assert go(repo, tmp_path, Runner(), "m") == 0
    assert "docs-since-pass" not in capsys.readouterr().out and marker(repo)["mode"]["lane"] == "full"


@pytest.mark.parametrize("rel", [".claude/rules/project/x.md", ".claude/skills/lanes/SKILL.md", "tests/README.md",
                                 "tests/test_x.py", "tests_app/README.md", "spec/schema.json", "spec/x.yaml",
                                 "docs/data.json", "docs/x.yaml", "docs/x.csv", "docs/x.html", "docs/x.png",
                                 "README.md", "CLAUDE.md", "backend/README.md", "frontend/README.md",
                                 "scripts/README.md", "tools/README.md", ".github/README.md", "alembic/README.md",
                                 "views/x.json"])
def test_a_claude_tests_code_data_or_root_file_among_docs_takes_the_full_path(tmp_path, rel):
    repo, _ = full_pass_on_code(tmp_path)
    commit_file(repo, "docs/design/RESULTS-x.md", "results")
    commit_file(repo, rel, "z")
    assert prepush.since_pass_lane(str(repo), False, sha_of(repo)) is None


@pytest.mark.parametrize("rel", ["docs/design/RESULTS-x.md", "spec/decisions/ADR-11.md", "spec/open-questions.md",
                                 "views/spec-digest.md", "knowledge/findings/f.md", "work/W-1.md"])
def test_the_strict_list_accepts_markdown_inside_a_records_folder(tmp_path, rel):
    repo, a = full_pass_on_code(tmp_path)
    commit_file(repo, rel, "text")
    assert prepush.since_pass_lane(str(repo), False, sha_of(repo)) == (a, 1)


def test_no_previous_passing_marker_takes_the_full_path(tmp_path, capsys):
    repo = docs_repo(tmp_path)
    commit_file(repo, "docs/design/RESULTS-y.md", "results")
    assert prepush.since_pass_lane(str(repo), False, sha_of(repo)) is None
    assert go(repo, tmp_path, Runner(), "n") == 0
    mode = marker(repo)["mode"]  # no anchor: the older docs-only-vs-main lane (it skips nothing), never since-pass
    assert "anchor" not in mode and not mode["lane"].startswith("docs-since-pass")
    assert "LANE docs-since-pass" not in capsys.readouterr().out


def test_a_docs_only_push_after_a_failed_full_run_takes_the_full_path(tmp_path, capsys):
    repo, _ = full_pass_on_code(tmp_path)
    commit_file(repo, "backend/broken.py", "b = 1\n")
    assert go(repo, tmp_path, Runner(fail={"domain_tests"}), "f") == 1  # red: no marker for this commit
    assert not Path(prepush.marker_path(str(repo), sha_of(repo))).exists()
    commit_file(repo, "docs/design/RESULTS-z.md", "results")
    assert prepush.since_pass_lane(str(repo), False, sha_of(repo)) is None  # the failed commit's code is in the diff
    assert go(repo, tmp_path, Runner(), "g") == 0
    assert "docs-since-pass" not in capsys.readouterr().out and marker(repo)["mode"]["lane"] == "full"


def test_the_documentation_path_is_the_default_and_can_be_turned_off(monkeypatch):
    seen = []
    monkeypatch.setattr(prepush, "run_all", lambda repo, full=False, **kw: seen.append(kw["since_pass"]) or 0)
    monkeypatch.setattr(prepush, "frontend_changes", lambda repo: [])
    import tools_present  # noqa: PLC0415
    monkeypatch.setattr(tools_present, "check", lambda *a, **k: [])
    monkeypatch.delenv("PREPUSH_SINCE_PASS", raising=False)
    assert prepush.since_pass_default({}) is True and prepush.since_pass_default({"PREPUSH_SINCE_PASS": "0"}) is False
    assert prepush.main([]) == 0 and prepush.main(["--no-since-pass"]) == 0
    monkeypatch.setenv("PREPUSH_SINCE_PASS", "0")
    assert prepush.main([]) == 0
    assert seen == [True, False, False]
