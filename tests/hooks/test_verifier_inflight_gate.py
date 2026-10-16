"""verifier_inflight_gate: while a verifier tool call is in flight (a fresh kit snapshot file exists), the main session
cannot write work/spec/evidence of any worktree or run a tree-rewriting git command.

Each test runs the hook as a subprocess with the hook-input JSON on stdin and OFO_VERIFIER_SNAP_DIR pointing at a temp
folder. Killing tests (mutation): see the module-level MUTATIONS table, each entry is run against a patched copy."""
import json
import os
import pathlib
import subprocess
import sys
import time

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
HOOK = pathlib.Path(os.environ.get("VIF_HOOK_PATH") or REPO / "scripts" / "hooks" / "verifier_inflight_gate.py")
REFUSED = 2
OK = 0
STALE_SECONDS = 16 * 60


@pytest.fixture
def snap(tmp_path):
    d = tmp_path / "verifier-write-guard" / "snap"
    d.mkdir(parents=True)
    return d


def fresh(snap_dir, age=0):
    f = snap_dir / "0123456789abcdef.json"
    f.write_text("{}")
    if age:
        t = time.time() - age
        os.utime(f, (t, t))
    return f


@pytest.fixture
def layout(tmp_path):
    """A main checkout (.git folder) and a linked worktree (.git FILE), each with work/spec/evidence/backend."""
    out = {}
    for name, marker in (("main", "dir"), ("linked", "file")):
        root = tmp_path / name
        for sub in ("work", "spec/decisions", "evidence/W-001", "backend/ofo"):
            (root / sub).mkdir(parents=True)
        if marker == "dir":
            (root / ".git").mkdir()
        else:
            (root / ".git").write_text("gitdir: elsewhere")
        out[name] = root
    return out


def run(payload, snap_dir, raw=None, cwd=None):
    env = dict(os.environ, OFO_VERIFIER_SNAP_DIR=str(snap_dir), PYTHONUTF8="1")
    text = raw if raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK)], input=text, capture_output=True, text=True,  # noqa: S603
                          env=env, cwd=cwd or REPO, timeout=120, check=False)


def bash(command, tool="Bash", **extra):
    return {"tool_name": tool, "tool_input": {"command": command}, **extra}


def write(path, tool="Write", **extra):
    return {"tool_name": tool, "tool_input": {"file_path": str(path)}, **extra}


GIT_REWRITES = [
    "git merge origin/main",
    "git -C some/dir pull",
    "cd x && git checkout y",
    "git switch -c b",
    "git rebase origin/main",
    "git reset --hard HEAD~1",
    "git cherry-pick abc123",
    "git revert abc123",
    "git am p.patch",
    "git restore f.txt",
    "git stash pop",
    "git stash push -u -m x",
    "git worktree add ../w b",
    "git clone https://example.invalid/r.git",
    "git -c x=y merge b",
    "git --git-dir=.. merge b",
    "git --no-pager merge b",
    "/usr/bin/git merge b",
    "git.exe merge b",
    'bash -c "git merge b"',
    "git status; git merge b",
    "git fetch\ngit merge b",
]
GIT_READ_ONLY = ["git status", "git fetch", "git diff", "git log -3", "git show HEAD", "git rev-parse HEAD",
                 "git ls-files", "git branch --list", "git worktree list", "pytest -q", "echo git merge"]


@pytest.mark.parametrize("cmd", GIT_REWRITES)
def test_rewriting_git_refused_while_in_flight(snap, cmd):
    fresh(snap)
    r = run(bash(cmd), snap)
    assert r.returncode == REFUSED, (cmd, r.stderr)
    assert "verifier_inflight_gate" in r.stderr and "Wait for the verifier" in r.stderr


def test_powershell_forms_refused(snap):
    fresh(snap)
    for cmd in ("& git merge b", "git merge b; git status", "& 'git' pull"):
        r = run(bash(cmd, tool="PowerShell"), snap)
        assert r.returncode == REFUSED, (cmd, r.stderr)


@pytest.mark.parametrize("cmd", GIT_READ_ONLY)
def test_read_only_commands_pass_while_in_flight(snap, cmd):
    fresh(snap)
    assert run(bash(cmd), snap).returncode == OK


@pytest.mark.parametrize("layout_name", ["main", "linked"])
@pytest.mark.parametrize("rel,tool", [("work/W-001.md", "Write"), ("spec/decisions/ADR-001.md", "Edit"),
                                      ("evidence/W-001/AC-1.md", "Write"), ("work/W-002.md", "MultiEdit"),
                                      ("work/W-003.ipynb", "NotebookEdit")])
def test_guarded_writes_refused_in_any_worktree(snap, layout, layout_name, rel, tool):
    fresh(snap)
    r = run(write(layout[layout_name] / rel, tool), snap)
    assert r.returncode == REFUSED, r.stderr


def test_write_path_spellings_refused(snap, layout):
    fresh(snap)
    root = layout["linked"]
    other = root / "backend" / "ofo"
    cases = [
        ("..\\..\\work\\W-1.md", other),       # relative with backslashes, from a subfolder
        ("../../work/W-1.md", other),
        (str(root / "Work" / "W-1.md"), root),  # mixed case on a case-insensitive disk
        (str(root / "SPEC" / "x.md"), root),
    ]
    for fp, cwd in cases:
        if os.sep == "/" and fp.lower() != fp and not (root / fp.split("/")[-2]).exists():
            continue  # case-insensitive spelling only matters where the disk is
        r = run({"tool_name": "Write", "tool_input": {"file_path": fp}, "cwd": str(cwd)}, snap)
        assert r.returncode == REFUSED, (fp, r.stderr)


def test_symlink_into_guarded_folder_refused(snap, layout, tmp_path):
    link = layout["main"] / "backend" / "alias"
    try:
        link.symlink_to(layout["main"] / "work", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted here")
    fresh(snap)
    assert run(write(link / "W-9.md"), snap).returncode == REFUSED


def test_unguarded_writes_pass(snap, layout):
    fresh(snap)
    assert run(write(layout["main"] / "backend" / "ofo" / "x.py"), snap).returncode == OK
    # a folder called work that is not directly under a git root
    assert run(write(layout["main"] / "backend" / "work" / "x.py"), snap).returncode == OK
    folder = layout["main"].parent / "plain" / "work"
    folder.mkdir(parents=True)
    assert run(write(folder / "x.md"), snap).returncode == OK


def test_verifier_calls_pass_through(snap, layout):
    fresh(snap)
    for at in ("verifier", "kit:verifier", "Verifier"):
        assert run(bash("git merge origin/main", agent_type=at), snap).returncode == OK
        assert run(write(layout["main"] / "work" / "W-1.md", agent_type=at), snap).returncode == OK
    # another agent type is judged like the main session
    assert run(bash("git merge origin/main", agent_type="builder"), snap).returncode == REFUSED


def test_stale_snapshot_ignored(snap, layout):
    fresh(snap, age=STALE_SECONDS)
    assert run(bash("git merge origin/main"), snap).returncode == OK
    assert run(write(layout["main"] / "work" / "W-1.md"), snap).returncode == OK
    r = run(bash("git merge origin/main"), snap)
    assert "snapshot" not in r.stderr


def test_just_inside_window_refused_and_age_cited(snap):
    fresh(snap, age=14 * 60)
    r = run(bash("git merge b"), snap)
    assert r.returncode == REFUSED and "snapshot 84" in r.stderr  # 840..849 s old


def test_mixed_stale_and_fresh_snapshots_refuse(snap):
    fresh(snap, age=STALE_SECONDS)
    g = snap / "fedcba9876543210.json"
    g.write_text("{}")
    assert run(bash("git merge b"), snap).returncode == REFUSED


def test_no_snapshot_folder_or_empty_folder_passes(tmp_path, snap, layout):
    assert run(bash("git merge b"), snap).returncode == OK
    assert run(bash("git merge b"), tmp_path / "does-not-exist").returncode == OK
    assert run(write(layout["main"] / "work" / "W-1.md"), tmp_path / "does-not-exist").returncode == OK


def test_deleting_the_snapshot_reopens_the_gate(snap, layout):
    f = fresh(snap)
    assert run(bash("git merge origin/main"), snap).returncode == REFUSED
    assert run(write(layout["main"] / "work" / "W-001.md"), snap).returncode == REFUSED
    f.unlink()
    assert run(bash("git merge origin/main"), snap).returncode == OK
    assert run(write(layout["main"] / "work" / "W-001.md"), snap).returncode == OK


def test_malformed_input_fails_open(snap):
    fresh(snap)
    assert run(None, snap, raw="{not json").returncode == OK
    assert run(None, snap, raw="").returncode == OK
    assert run(None, snap, raw="[1,2]").returncode == OK
    assert run({"tool_name": "Bash", "tool_input": {"command": 5}}, snap).returncode == OK
    assert run({"tool_name": "Write", "tool_input": {}}, snap).returncode == OK


def test_other_tools_untouched(snap):
    fresh(snap)
    assert run({"tool_name": "Read", "tool_input": {"file_path": "work/W-1.md"}}, snap).returncode == OK


# ---- killing tests: each guard removed in turn must turn at least the named test red ----
MUTATIONS = [
    ("writes branch", "    if tool in WRITE_TOOLS:\n", "    if False:\n",
     "test_guarded_writes_refused_in_any_worktree"),
    ("git rewrite set", "    if sub in REWRITES:\n", "    if False:\n",
     "test_rewriting_git_refused_while_in_flight"),
    ("15 minute window", "    fresh = [a for a in ages if a < INFLIGHT_SECONDS]\n",
     "    fresh = list(ages)\n", "test_stale_snapshot_ignored"),
    ("verifier pass-through", '    if agent == "verifier" or', "    if False or", "test_verifier_calls_pass_through"),
]


@pytest.mark.parametrize("name,old,new,killer", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_mutation_is_killed(tmp_path, name, old, new, killer):
    src = HOOK.read_text(encoding="utf-8")
    assert old in src, name
    mdir = tmp_path / "mut"
    mdir.mkdir()
    for f in HOOK.parent.glob("*.py"):
        (mdir / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    (mdir / HOOK.name).write_text(src.replace(old, new, 1), encoding="utf-8")
    env = dict(os.environ, VIF_HOOK_PATH=str(mdir / HOOK.name))
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x",  # noqa: S603
                        f"{pathlib.Path(__file__)}::{killer}"], env=env, cwd=REPO, capture_output=True,
                       text=True, timeout=300, check=False)
    assert r.returncode != 0, f"mutation '{name}' survived {killer}"
