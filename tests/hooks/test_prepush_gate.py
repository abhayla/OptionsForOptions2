"""prepush_gate: a `git push` is refused unless prepush.py passed on exactly the HEAD being pushed.
Real temp git repos and real marker files; the hook also runs as a subprocess fed the hook-input JSON."""
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
HOOKS = REPO / "scripts" / "hooks"
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(REPO / "scripts" / "orchestrator"))
import prepush  # noqa: E402
import prepush_gate as pg  # noqa: E402

REFUSED_WORD = "BLOCKED by prepush_gate"
REFUSED_RC = 2


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()  # noqa: S603, S607


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "proj"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("a", encoding="utf-8")
    git(r, "add", "a.txt")
    git(r, "commit", "-q", "-m", "one")
    return r


def mark(repo):
    sha = git(repo, "rev-parse", "HEAD")
    path = pathlib.Path(prepush.marker_path(str(repo), sha))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"sha": sha, "steps": []}), encoding="utf-8")
    return sha


def check(command, cwd, tool="Bash"):
    return pg.decide(tool, {"command": command}, str(cwd))


PUSHES = [
    "git push",
    "git push origin HEAD",
    "git push -u origin feat/x",
    "git push --force-with-lease origin feat/x",
    "git status && git push origin HEAD",
    "git status; git push origin HEAD",
    "git status\ngit push origin HEAD",
    "bash -c 'git push origin HEAD'",
    "git -c core.editor=true push origin HEAD",
    "git -c a=b -c c=d push origin HEAD",
    "FOO=1 git push origin HEAD",
    "timeout 60 git push origin HEAD",
    "git push origin HEAD:refs/heads/feat/x",
]


@pytest.mark.parametrize("command", PUSHES)
def test_push_without_marker_is_refused(repo, command):
    reason = check(command, repo)
    assert reason and REFUSED_WORD in reason
    assert "python scripts/orchestrator/prepush.py" in reason
    assert "PREPUSH_GATE_ALLOW=<reason>" in reason
    assert git(repo, "rev-parse", "--short", "HEAD") in reason


@pytest.mark.parametrize("command", PUSHES)
def test_push_with_marker_for_head_is_allowed(repo, command):
    mark(repo)
    assert check(command, repo) is None


def test_powershell_form(repo):
    assert REFUSED_WORD in check("git push origin HEAD", repo, tool="PowerShell")
    assert REFUSED_WORD in check("git status; git push origin HEAD", repo, tool="PowerShell")
    mark(repo)
    assert check("git push origin HEAD", repo, tool="PowerShell") is None


def test_marker_for_a_different_sha_does_not_satisfy(repo):
    mark(repo)
    git(repo, "commit", "-q", "--amend", "-m", "reworded")  # the attack: amend after the run
    assert REFUSED_WORD in check("git push origin HEAD", repo)
    (repo / "b.txt").write_text("b", encoding="utf-8")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-q", "-m", "two")
    assert REFUSED_WORD in check("git push", repo)


ALLOWED_SHAPES = [
    "git push --dry-run origin HEAD",
    "git push -n origin HEAD",
    "git push --delete origin feat/x",
    "git push -d origin feat/x",
    "git push origin :feat/x",
    "git push origin :feat/x :feat/y",
    "git push --tags",
    "git push --tags origin",
    "PREPUSH_GATE_ALLOW=docs-only-hotfix git push origin HEAD",
    'PREPUSH_GATE_ALLOW="owner said so" git push origin HEAD',
    "export PREPUSH_GATE_ALLOW=urgent; git push origin HEAD",
    "echo git push",
    "git status",
    "git commit -m 'git push later'",
    "git log --oneline -3 && git diff",
    "git pull --ff-only",
    "grep -r 'git push' docs",
]


@pytest.mark.parametrize("command", ALLOWED_SHAPES)
def test_allowed_shapes_pass_without_marker(repo, command):
    assert check(command, repo) is None


def test_tags_plus_a_branch_refspec_is_still_gated(repo):
    assert REFUSED_WORD in check("git push --tags origin HEAD", repo)


def test_empty_allow_reason_does_not_bypass(repo):
    for command in ("PREPUSH_GATE_ALLOW= git push origin HEAD", 'PREPUSH_GATE_ALLOW="" git push origin HEAD',
                    "PREPUSH_GATE_ALLOW=''; git push origin HEAD"):
        assert REFUSED_WORD in check(command, repo), command


def test_dash_C_resolves_the_directory(repo, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert REFUSED_WORD in check(f"git -C {repo.as_posix()} push origin HEAD", other)  # cwd is not a repo, -C is
    mark(repo)
    assert check(f"git -C {repo.as_posix()} push origin HEAD", other) is None
    # the other way round: cwd has the marker, -C points at an unmarked repo
    unmarked = tmp_path / "unmarked"
    shutil.copytree(repo, unmarked)
    git(unmarked, "commit", "-q", "--allow-empty", "-m", "new")
    assert REFUSED_WORD in check(f"git -C {unmarked.as_posix()} push origin HEAD", repo)


def test_preceding_cd_resolves_the_directory(repo, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert REFUSED_WORD in check(f"cd {repo.as_posix()} && git push origin HEAD", other)
    mark(repo)
    assert check(f"cd {repo.as_posix()} && git push origin HEAD", other) is None
    assert check(f"cd '{repo.as_posix()}'; git push origin HEAD", other) is None
    assert check(f"Set-Location {repo.as_posix()}; git push origin HEAD", other, tool="PowerShell") is None


def test_relative_cd_and_dash_C_compose_with_the_hook_cwd(repo, tmp_path):
    (repo / "sub").mkdir()
    assert REFUSED_WORD in check("cd sub && git push origin HEAD", repo)
    assert REFUSED_WORD in check("git -C sub push origin HEAD", repo)
    mark(repo)
    assert check("cd sub && git push origin HEAD", repo) is None
    assert check("git -C sub push origin HEAD", repo) is None


def test_fail_open_on_unusable_shapes(tmp_path, repo):
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    assert check("git push origin HEAD", not_a_repo) is None  # an existing folder, git failure
    assert pg.decide("Bash", {"command": 5}, str(repo)) is None
    assert pg.decide("Bash", {"command": ""}, str(repo)) is None
    assert pg.decide("Bash", {}, str(repo)) is None
    assert pg.decide("Edit", {"command": "git push"}, str(repo)) is None
    assert pg.decide("Bash", {"command": "git push " + "x" * 200_000}, str(repo)) is None


WIN_PATH = "D:\\Abhay\\Ventures\\OptionsForOptions2-batch1"  # review F1's exact input path


def win(path):
    """The repo path written the Windows way, with backslashes (what the review's attack used)."""
    return str(path).replace("/", "\\")


@pytest.mark.skipif(sys.platform != "win32", reason="a backslash path names a folder only on Windows, where the hook runs")
@pytest.mark.parametrize("shape", ['cd "{d}" && git push -u origin HEAD', 'git -C "{d}" push -u origin HEAD',
                                   'cd "{d}"; git push origin HEAD', 'bash -c \'cd "{d}" && git push\''])
def test_quoted_windows_path_resolves_to_the_real_folder(repo, tmp_path, shape):
    # review F1: the scanner used to drop every backslash inside "..." -> a missing folder -> fail open
    other = tmp_path / "elsewhere"
    other.mkdir()
    command = shape.format(d=win(repo))
    assert REFUSED_WORD in check(command, other)
    mark(repo)
    assert check(command, other) is None  # the marker of THAT folder is found: the path resolved, not just blocked


@pytest.mark.parametrize("shape", ['cd "{d}" && git push -u origin HEAD', 'git -C "{d}" push -u origin HEAD',
                                   "cd {d} && git push", "git -C {d} push origin HEAD"])
def test_a_push_folder_that_does_not_exist_is_refused(repo, tmp_path, shape):
    missing = tmp_path / "no-such-folder"
    reason = check(shape.format(d=missing.as_posix()), repo)
    assert reason and REFUSED_WORD in reason and "does not exist" in reason
    mark(repo)  # a marker in the hook cwd must not rescue a push from elsewhere
    assert REFUSED_WORD in check(shape.format(d=missing.as_posix()), repo)


def test_the_review_input_blocks_when_its_folder_is_absent_or_unmarked(tmp_path):
    reason = check(f'cd "{WIN_PATH}" && git push -u origin HEAD', tmp_path)
    assert reason and REFUSED_WORD in reason  # absent here: does not exist; present: no marker unless prepush passed


def test_a_hook_cwd_that_does_not_exist_is_refused(tmp_path):
    assert REFUSED_WORD in check("git push origin HEAD", tmp_path / "does-not-exist")


def test_tilde_is_expanded(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(repo.parent))
    monkeypatch.setenv("USERPROFILE", str(repo.parent))
    mark(repo)
    assert check(f"cd ~/{repo.name} && git push origin HEAD", tmp_path) is None


def test_double_quote_backslash_rule_in_the_shared_scanner():
    import gate_before_commit as g

    steps, unterminated = g._scan('echo "D:\\Abhay\\x" "a\\"b" "c\\$d" "e\\\\f" "g\\`h" "i\\\nj"')
    assert not unterminated
    assert steps[0][0] == ["echo", "D:\\Abhay\\x", 'a"b', "c$d", "e\\f", "g`h", "ij"]
    ps_steps, _ = g._scan('echo "D:\\Abhay\\x"', True)  # PowerShell: backslash is never an escape
    assert ps_steps[0][0] == ["echo", "D:\\Abhay\\x"]


def test_a_missing_prepush_module_allows(repo, monkeypatch):
    monkeypatch.setattr(pg, "ORCH_DIR", str(REPO / "no-such-dir"))
    monkeypatch.delitem(sys.modules, "prepush", raising=False)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if not p.endswith("orchestrator")])
    assert check("git push origin HEAD", repo) is None


def run_hook(payload, text=None, cwd=REPO):
    body = text if text is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOKS / "prepush_gate.py")], input=body, capture_output=True,  # noqa: S603
                          text=True, cwd=cwd, timeout=120, check=False)


def test_subprocess_exit_codes(repo):
    payload = {"tool_name": "Bash", "tool_input": {"command": "git push origin HEAD"}, "cwd": str(repo)}
    refused = run_hook(payload)
    assert refused.returncode == REFUSED_RC
    assert REFUSED_WORD in refused.stderr
    mark(repo)
    assert run_hook(payload).returncode == 0


def test_subprocess_garbage_input_exits_0():
    for text in ("", "not json", "[]", '{"tool_name": 5}', "\x00\x01", '{"tool_name":"Bash","tool_input":"x"}'):
        r = run_hook(None, text=text)
        assert r.returncode == 0, text
        assert r.stderr == ""

