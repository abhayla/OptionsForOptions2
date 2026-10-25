"""verifier_inflight_gate: while a verifier tool call is in flight (a fresh kit snapshot file exists), the main session
cannot write work/spec/evidence of any worktree or run a tree-rewriting git command.

Each test runs the hook as a subprocess with the hook-input JSON on stdin and OFO_VERIFIER_SNAP_DIR pointing at a temp
folder. Killing tests (mutation): see the module-level MUTATIONS table, each entry is run against a patched copy."""
import importlib.util
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
    # (path, cwd, kind): "backslash" only separates on Windows; "case" only matters on a case-insensitive disk
    cases = [
        ("..\\..\\work\\W-1.md", other, "backslash"),  # relative with backslashes, from a subfolder
        ("../../work/W-1.md", other, "plain"),
        (str(root / "Work" / "W-1.md"), root, "case"),  # mixed case on a case-insensitive disk
        (str(root / "SPEC" / "x.md"), root, "case"),
    ]
    case_insensitive = (root / "WORK").exists() or (root / "SPEC").exists() or os.path.normcase("A") == "a"
    for fp, cwd, kind in cases:
        if (kind == "backslash" and os.sep == "/") or (kind == "case" and not case_insensitive):
            continue  # that spelling cannot reach the guarded folder on this OS / disk
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


# ---- round 2: closed read-only allow-list, watched roots, writer scripts, path normalisation ----
CLEAN = "cl" + "ean"  # spelled in pieces so this file never carries the command text
NOT_READ_ONLY = [
    "git apply p.patch", "git rm work/W-1.md", "git mv work/a work/b", "git " + CLEAN + " -fdx",
    "git checkout-index -a -f", "git read-tree -u -m HEAD", "git submodule update", "git sparse-checkout set x",
    "git bisect start", "git commit -am x", "git add .", "git tag v1", "git gc", "git notes add", "git frobnicate",
    "git -c alias.m=merge m x", "git -c alias.status=!rm status", "git --exec-path=/x status",
    "git diff --output=work/out.txt", "git log --output work/out.txt", "git grep -Ocmd x",
    "git branch newname", "git branch -D x", "git branch -m a b", "git remote add o url", "git remote set-url o u",
    "git worktree remove w", "git worktree prune", "git stash drop", "git stash pop", "git config user.name x",
    "git config --unset x", "git --no-pager -c x=y MERGE x",
    "xargs git merge", "echo x | xargs git merge", "find . -exec git rm {} +", "eval 'git merge x'",
    "$g merge x", "python scripts/orchestrator/agit.py abc12345 merge x",
    "python scripts/orchestrator/agit.py abc12345 -C d reset --hard",
]
READ_ONLY_MORE = [
    "git ls-tree HEAD", "git cat-file -p HEAD", "git describe --tags", "git blame f.py", "git shortlog -sn",
    "git grep -n foo", "git merge-base a b", "git for-each-ref", "git remote", "git remote -v", "git branch",
    "git branch --list", "git branch -a", "git branch -r", "git branch --show-current", "git branch -v",
    "git branch --contains abc123", "git branch --list 'feat/*'", "git worktree list", "git worktree list --porcelain",
    "git stash list", "git config --get user.name", "git config --list", "git --version", "git -C d status",
    "git --no-pager log -3", "git -P diff", "git log --grep=merge", "git diff --stat", "git show HEAD:work/W-1.md",
    "python scripts/orchestrator/agit.py abc12345 status", "echo xargs git merge", "ls | xargs wc -l",
]


@pytest.mark.parametrize("cmd", NOT_READ_ONLY)
def test_non_read_only_git_refused_while_in_flight(snap, cmd):
    fresh(snap)
    r = run(bash(cmd), snap)
    assert r.returncode == REFUSED, (cmd, r.stderr)


@pytest.mark.parametrize("cmd", READ_ONLY_MORE)
def test_whole_allow_list_passes_while_in_flight(snap, cmd):
    fresh(snap)
    r = run(bash(cmd), snap)
    assert r.returncode == OK, (cmd, r.stderr)


@pytest.mark.parametrize("cmd", NOT_READ_ONLY + READ_ONLY_MORE + GIT_REWRITES)
def test_nothing_refused_when_no_verifier_runs(snap, cmd):
    assert run(bash(cmd), snap).returncode == OK


def snapshot_with_roots(snap_dir, roots):
    f = snap_dir / "aaaabbbbccccdddd.json"
    f.write_text(json.dumps({"roots": [{"root": str(r), "files": {}, "dirs": []} for r in roots]}))
    return f


def test_cd_then_git_in_a_watched_folder_refused(snap, layout):
    snapshot_with_roots(snap, [layout["main"]])
    cmd = f'cd "{layout["main"].as_posix()}" && git merge x'
    assert run(bash(cmd, cwd=str(layout["linked"])), snap).returncode == REFUSED


def test_only_watched_roots_are_blocked(snap, layout):
    snapshot_with_roots(snap, [layout["main"]])
    main, other = layout["main"], layout["linked"]
    # a write under the other worktree passes; under the watched one it is refused
    assert run(write(other / "work" / "W-1.md"), snap).returncode == OK
    assert run(write(main / "work" / "W-1.md"), snap).returncode == REFUSED
    # git: a step whose cwd is outside the roots passes; cwd or -C inside is refused
    assert run(bash("git merge x", cwd=str(other)), snap).returncode == OK
    assert run(bash("git merge x", cwd=str(main)), snap).returncode == REFUSED
    assert run(bash("git merge x", cwd=str(main / "backend")), snap).returncode == REFUSED
    assert run(bash(f'git -C "{main.as_posix()}" merge x', cwd=str(other)), snap).returncode == REFUSED
    assert run(bash(f'git -C "{other.as_posix()}" merge x', cwd=str(main)), snap).returncode == OK
    assert run(bash("git --git-dir=.git merge x", cwd=str(other)), snap).returncode == REFUSED  # place unknown
    assert run(bash("git --work-tree .. merge x", cwd=str(other)), snap).returncode == REFUSED


def test_temp_repo_outside_roots_never_blocked(snap, layout, tmp_path):
    snapshot_with_roots(snap, [layout["main"]])
    scratch = tmp_path / "scratch"
    (scratch / "work").mkdir(parents=True)
    (scratch / ".git").mkdir()
    assert run(write(scratch / "work" / "x.md"), snap).returncode == OK
    cmds = ("git init", "git add .", "git commit -m x", "git checkout -b t", "git merge x", "git " + CLEAN + " -fdx")
    for cmd in cmds:
        assert run(bash(cmd, cwd=str(scratch)), snap).returncode == OK, cmd


@pytest.mark.parametrize("content", ["{not json", "{}", '{"roots": []}', '{"roots": [{"nope": 1}]}', "[1]", ""])
def test_unreadable_or_rootless_snapshot_watches_everything(snap, layout, content):
    (snap / "0000111122223333.json").write_text(content)
    assert run(write(layout["main"] / "work" / "W-1.md"), snap).returncode == REFUSED
    assert run(bash("git merge x", cwd=str(layout["linked"])), snap).returncode == REFUSED


def test_refusal_names_the_snapshot_and_how_to_clear_it(snap):
    f = fresh(snap)
    r = run(bash("git merge x"), snap)
    assert r.returncode == REFUSED
    assert str(f) in r.stderr and "delete" in r.stderr and "15 minutes" in r.stderr


def load_hook():
    spec = importlib.util.spec_from_file_location("vif_under_test", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_directory_name_is_case_folded(tmp_path, monkeypatch):
    """`Work/` must count as work/ on a case-insensitive disk. realpath is neutralised so the test does not depend
    on the disk resolving the case for us."""
    root = tmp_path / "r"
    (root / ".git").mkdir(parents=True)
    mod = load_hook()
    monkeypatch.setattr(os.path, "realpath", os.path.abspath)
    for name in ("Work", "WORK", "Spec", "EVIDENCE"):
        assert mod.guarded_holder(str(root / name / "x.md"), "") is not None, name


def test_dotdot_is_normalised_before_judging(tmp_path):
    root = tmp_path / "r"
    for d in ("work", "backend"):
        (root / d).mkdir(parents=True)
    (root / ".git").mkdir()
    mod = load_hook()
    # resolves OUT of work/, so it is not a guarded write ...
    assert mod.guarded_holder(str(root / "work" / ".." / "backend" / "x.py"), "") is None
    # ... and a relative path that resolves INTO work/ only after normalisation is
    assert mod.guarded_holder("../work/x.md", str(root / "backend")) is not None


SCRIPTS = REPO / "scripts" / "orchestrator"


def run_script(name, args, snap_dir):
    env = dict(os.environ, OFO_VERIFIER_SNAP_DIR=str(snap_dir), PYTHONUTF8="1")
    return subprocess.run([sys.executable, str(SCRIPTS / name), *args], capture_output=True, text=True,  # noqa: S603
                          env=env, cwd=REPO, timeout=120, check=False)


@pytest.fixture
def evidence_args(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    blocks = [{"ac": "AC-1", "result": "pass", "commands": "c", "observed": "o", "attack": "a",
               "requirement": "REQ-1", "ac_fp": "x"}]
    jf = tmp_path / "blocks.json"
    jf.write_text(json.dumps(blocks))
    return wt, [str(wt), "W-001", "builder", "verifier", str(jf)]


def test_ev_agent_refuses_in_flight(snap, evidence_args):
    _, args = evidence_args
    fresh(snap)
    r = run_script("ev_agent.py", [args[0], args[-1]], snap)
    assert r.returncode == REFUSED and "verifier_inflight_gate" in r.stderr, r.stderr
    r = run_script("ev_agent.py", ["zzzzzzzz", args[-1]], snap)
    assert r.returncode == REFUSED and "verifier_inflight_gate" in r.stderr, r.stderr


KIT_FAIL = 3


def _load_ev_agent():
    spec = importlib.util.spec_from_file_location("ev_agent", SCRIPTS / "ev_agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ev_agent_passes_root_and_reply_to_the_kit_tool_and_its_exit_code(evidence_args, monkeypatch, capsys):
    wt, args = evidence_args
    mod = _load_ev_agent()
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, KIT_FAIL if cmd[1].endswith("record_evidence.py") else 0, stdout="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod, "_refuse_if_verifier_in_flight", lambda target: None)
    assert mod.main([str(wt), args[-1], "--replace", "--dry-run"]) == KIT_FAIL  # a kit failure is never hidden
    tool_call = calls[-1]
    assert tool_call[1] == str(pathlib.Path(mod.REPO) / "tools" / "record_evidence.py")
    assert tool_call[2:] == [args[-1], "--root", str(wt), "--replace", "--dry-run"]


def test_ev_agent_fails_closed_when_the_kit_tool_is_missing(evidence_args, monkeypatch, capsys):
    wt, args = evidence_args
    mod = _load_ev_agent()
    monkeypatch.setattr(mod, "REPO", str(wt))
    monkeypatch.setattr(mod, "_refuse_if_verifier_in_flight", lambda target: None)
    assert mod.main([str(wt), args[-1]]) == REFUSED
    assert "kit tool missing" in capsys.readouterr().err


def test_gh_issue_stage_refuses_in_flight_before_creating_anything(snap, tmp_path):
    body = tmp_path / "b.md"
    body.write_text("x")
    fresh(snap)
    r = run_script("gh_issue.py", ["app", "label", "title", str(body), "--stage", "S1"], snap)
    assert r.returncode == REFUSED and "verifier_inflight_gate" in r.stderr, r.stderr
    assert "issues/" not in r.stdout


def test_writer_scripts_use_the_shared_function_not_a_copy():
    for name in ("ev_agent.py", "gh_issue.py"):
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "inflight_block_reason" in text and "INFLIGHT_SECONDS" not in text, name


# ---- killing tests: each guard removed in turn must turn at least the named test red ----
MUTATIONS = [
    ("writes branch", "    if tool in WRITE_TOOLS:\n", "    if False:\n",
     "test_guarded_writes_refused_in_any_worktree"),
    ("allow-list (rewrites)", "    if sub not in READ_ONLY or", "    if False and sub not in READ_ONLY or",
     "test_rewriting_git_refused_while_in_flight"),
    ("15 minute window", "    fresh = [(a, p) for a, p in ages if a < INFLIGHT_SECONDS]\n",
     "    fresh = list(ages)\n", "test_stale_snapshot_ignored"),
    ("verifier pass-through", '    if agent == "verifier" or', "    if False or", "test_verifier_calls_pass_through"),
    ("allow-list", "    if sub not in READ_ONLY or not _read_only_ok(sub, words[i + 1:]):\n", "    if False:\n",
     "test_non_read_only_git_refused_while_in_flight"),
    ("roots filter", "            if roots is None or path is None or any(_under(path, r) for r in roots)]\n",
     "            if True]\n", "test_only_watched_roots_are_blocked"),
    ("no roots = everything", "    return roots or None\n", "    return roots\n",
     "test_unreadable_or_rootless_snapshot_watches_everything"),
    ("unparseable = everything", "unreadable = watch everything\n        return None",
     "unreadable = watch everything\n        return []", "test_unreadable_or_rootless_snapshot_watches_everything"),
    ("opaque wrapper", "    if h in OPAQUE_HEADS and GIT_WORD.search(joined):\n", "    if False:\n",
     "test_non_read_only_git_refused_while_in_flight"),
    ("variable head", '    if h.startswith(("$", "`")):\n', "    if False:\n",
     "test_non_read_only_git_refused_while_in_flight"),
    ("agit helper", '== "agit.py":', "== 'never':", "test_non_read_only_git_refused_while_in_flight"),
    ("-c config", '                unsafe = unsafe or "git -c (config can define a command)"\n',
     "                pass\n",
     "test_non_read_only_git_refused_while_in_flight"),
    ("--output", '    if any(a == "--output" or', '    if False and any(a == "--output" or',
     "test_non_read_only_git_refused_while_in_flight"),
    ("cd unknown", "            dir_unknown = True  # a later step runs somewhere we cannot resolve\n",
     "            pass\n",
     "test_cd_then_git_in_a_watched_folder_refused"),
    ("git-dir unknown", "                workdir = None\n            i += 2\n",
     "                pass\n            i += 2\n",
     "test_only_watched_roots_are_blocked"),
    ("-C workdir", "                workdir = os.path.join(workdir, nxt) if workdir is not None else None\n",
     "                pass\n", "test_only_watched_roots_are_blocked"),
    ("case fold", "parts[i].lower() in GUARDED_DIRS", "parts[i] in GUARDED_DIRS", "test_directory_name_is_case_folded"),
    ("realpath", "os.path.realpath(os.path.join(", "(os.path.join(", "test_dotdot_is_normalised_before_judging"),
    ("holder .git check", ' and os.path.exists(os.path.join(*parts[:i], ".git"))', "",
     "test_unguarded_writes_pass"),
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
