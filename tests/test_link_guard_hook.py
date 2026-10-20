"""link_guard hook (finding worktree-link-into-main-checkout, GC-6 row WT-LINK-GUARD).

Every case feeds a recorded tool-call string to the hook; nothing here runs the commands. Cases are the 2026-10-19
incident (a junction onto the main checkout's frontend/node_modules, then `git worktree remove --force`)
and its variants.
Mutation tests: with the target check or the force check removed, the refused cases pass through,
so each check is needed."""

import json
import os
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
HOOKS = REPO / "scripts" / "hooks"
sys.path.insert(0, str(HOOKS))
import link_guard as lg  # noqa: E402

BLOCK_EXIT = 2
MAIN = r"D:\Abhay\Ventures\OptionsForOptions2"
MAIN_POSIX = "/d/Abhay/Ventures/OptionsForOptions2"
SCRATCH = r"C:\Users\itsab\AppData\Local\Temp\claude\scratchpad"
ROOTS = [lg._key(MAIN)]
CWD = SCRATCH + r"\rv-cg"
NM = MAIN + r"\frontend\node_modules"
NM_POSIX = MAIN_POSIX + "/frontend/node_modules"

REFUSED = {
    "mklink_junction": ("Bash", rf"mklink /J {CWD}\frontend\node_modules {NM}"),
    "cmd_c_mklink_junction": ("Bash", rf'cmd /c mklink /J "{CWD}\frontend\node_modules" "{NM}"'),
    "cmd_c_mklink_dir": ("Bash", rf'cmd /c "mklink /D {CWD}\nm {NM}"'),
    "cmd_c_mklink_hard": ("Bash", rf"cmd.exe /c mklink /H {CWD}\a.txt {MAIN}\package-lock.json"),
    "powershell_new_item_junction": ("PowerShell", rf"New-Item -ItemType Junction -Path {CWD}\nm -Target {NM}"),
    "powershell_new_item_junction_value": ("PowerShell", rf"New-Item -ItemType Junction -Path nm -Value '{NM}'"),
    "powershell_ni_symboliclink": ("PowerShell", rf'ni -Type SymbolicLink -Path x -Target "{NM}"'),
    "powershell_new_item_hardlink": ("PowerShell", rf"New-Item -ItemType HardLink -Path x -Target {MAIN}\a"),
    "ln_s_git_bash_path": ("Bash", f"ln -s {NM_POSIX} x"),
    "ln_s_windows_path": ("Bash", rf"ln -s {NM} x"),
    "ln_sf": ("Bash", f"ln -sf {NM_POSIX} x"),
    "ln_symbolic_long": ("Bash", f"ln --symbolic {NM_POSIX} x"),
    "ln_s_mnt_path": ("Bash", "ln -s /mnt/d/Abhay/Ventures/OptionsForOptions2/frontend/node_modules x"),
    "ln_s_after_other_steps": ("Bash", f"cd /tmp && echo hi; ln -s {NM_POSIX} x"),
    "ln_s_case_insensitive": ("Bash", "ln -s /d/ABHAY/ventures/optionsforoptions2/Frontend/node_modules x"),
    "python_inline_symlink": ("Bash", f"python -c \"import os; os.symlink('{NM}', 'x')\""),
    "python_inline_junction": ("Bash", f"python -c \"import _winapi; _winapi.CreateJunction(r'{NM}', 'x')\""),
    "fsutil_hardlink": ("Bash", rf"fsutil hardlink create x {MAIN}\a"),
    "link_chained_after_gate": ("Bash", rf"npm ci && mklink /J nm {NM}"),
    "variable_target": ("PowerShell", r"New-Item -ItemType Junction -Path nm -Target $env:MAIN\frontend\node_modules"),
    "force_remove": ("Bash", rf"git worktree remove --force {CWD}"),
    "force_remove_short": ("Bash", f"git worktree remove -f {CWD}"),
    "force_remove_double": ("Bash", f"git worktree remove -f -f {CWD}"),
    "force_remove_after_path": ("Bash", f"git worktree remove {CWD} --force"),
    "force_remove_with_C": ("Bash", rf"git -C {MAIN} worktree remove --force {CWD}"),
    "force_remove_powershell": ("PowerShell", rf"git worktree remove --force {CWD}"),
    "force_remove_chained": ("Bash", f"cd x && git worktree remove -f {CWD}"),
}
ALLOWED = {
    "mkdir": ("Bash", f"mkdir -p {CWD}/frontend"),
    "npm_ci": ("Bash", "cd frontend && npm ci"),
    "npm_ci_powershell": ("PowerShell", "npm ci --no-audit"),
    "plain_worktree_remove": ("Bash", f"git worktree remove {CWD}"),
    "worktree_remove_path_with_f": ("Bash", rf"git worktree remove {SCRATCH}\rv-f-fix"),
    "worktree_add": ("Bash", f"git worktree add {CWD} -b x origin/main"),
    "junction_into_scratchpad": ("Bash", rf"mklink /J {CWD}\a {SCRATCH}\b"),
    "ln_s_into_scratchpad": ("Bash", f"ln -s {SCRATCH}/b {CWD}/a"),
    "new_item_junction_into_scratchpad": (
        "PowerShell",
        rf"New-Item -ItemType Junction -Path {CWD}\a -Target {SCRATCH}\b",
    ),
    "link_created_elsewhere_text_only": ("Bash", f"echo mklink is blocked > {SCRATCH}\\note.txt"),
    "grep_for_ln": ("Bash", f"grep -rn 'ln -s' {MAIN}/docs"),
    "read_main_file": ("Bash", f"cat {MAIN}/README.md"),
    "new_item_directory": ("PowerShell", rf"New-Item -ItemType Directory -Path {CWD}\x"),
    "git_status_in_main": ("Bash", f"git -C {MAIN} status"),
}


def verdict(case: tuple[str, str]) -> str | None:
    return lg.decide(case[0], {"command": case[1]}, roots=ROOTS, cwd=CWD)


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_refused(name: str) -> None:
    msg = verdict(REFUSED[name])
    assert msg is not None and msg.startswith("BLOCKED by link_guard")
    assert "2026-10-19" in msg


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_allowed(name: str) -> None:
    assert verdict(ALLOWED[name]) is None


def test_non_shell_tools_and_empty_input_pass() -> None:
    assert lg.decide("Read", {"command": REFUSED["mklink_junction"][1]}, roots=ROOTS, cwd=CWD) is None
    assert lg.decide("Bash", {}, roots=ROOTS, cwd=CWD) is None
    assert lg.decide("Bash", {"command": 5}, roots=ROOTS, cwd=CWD) is None  # type: ignore[dict-item]


def test_relative_target_is_resolved_against_cwd_in_main() -> None:
    msg = lg.decide("Bash", {"command": r"mklink /J nm frontend\node_modules"}, roots=ROOTS, cwd=MAIN)
    assert msg is not None
    assert lg.decide("Bash", {"command": r"mklink /J nm frontend\node_modules"}, roots=ROOTS, cwd=CWD) is None


def test_guard_is_target_based_not_a_banned_shape() -> None:
    """Same verb, same shape: only the target decides (finding guard-by-banned-shapes)."""
    assert verdict(("Bash", rf"mklink /J x {NM}")) is not None
    assert verdict(("Bash", rf"mklink /J x {SCRATCH}\y")) is None


def test_mutation_without_the_target_check_links_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    link_cases = [n for n in REFUSED if not n.startswith("force_") and n != "variable_target"]
    monkeypatch.setattr(lg, "_inside", lambda *_a, **_k: False)
    assert all(verdict(REFUSED[n]) is None for n in link_cases)


def test_mutation_without_the_force_check_removals_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lg, "_force_refusal", lambda _c: None)
    assert all(verdict(REFUSED[n]) is None for n in REFUSED if n.startswith("force_"))


# ---------------------------------------------------------------- real subprocess, real git roots
def _run(
    script: pathlib.Path, project: pathlib.Path, payload: dict | str, cwd: pathlib.Path
) -> subprocess.CompletedProcess:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    return subprocess.run(  # noqa: S603
        [sys.executable, str(script)],
        input=text,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=60,
        check=False,
    )


@pytest.fixture
def fake_main(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    main = tmp_path / "main"
    (main / "frontend" / "node_modules").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(main)], check=True, capture_output=True)  # noqa: S603, S607
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    return main, scratch


def test_subprocess_refuses_link_into_real_git_root_and_allows_scratch(
    fake_main: tuple[pathlib.Path, pathlib.Path],
) -> None:
    main, scratch = fake_main
    bad = {"tool_name": "Bash", "tool_input": {"command": f"ln -s {main}/frontend/node_modules {scratch}/nm"}}
    good = {"tool_name": "Bash", "tool_input": {"command": f"ln -s {scratch}/b {scratch}/nm"}}
    r = _run(HOOKS / "link_guard.py", main, bad, scratch)
    assert r.returncode == BLOCK_EXIT and "BLOCKED by link_guard" in r.stderr
    assert _run(HOOKS / "link_guard.py", main, good, scratch).returncode == 0
    ps = {
        "tool_name": "PowerShell",
        "tool_input": {"command": f"New-Item -ItemType Junction -Path nm -Target '{main}\\frontend\\node_modules'"},
    }
    assert _run(HOOKS / "link_guard.py", main, ps, scratch).returncode == BLOCK_EXIT


def test_subprocess_main_root_found_from_a_linked_worktree(fake_main: tuple[pathlib.Path, pathlib.Path]) -> None:
    main, scratch = fake_main
    env_git = ["git", "-C", str(main), "-c", "user.email=a@b.c", "-c", "user.name=t"]
    subprocess.run([*env_git, "commit", "-q", "--allow-empty", "-m", "x"], check=True, capture_output=True)  # noqa: S603
    wt = scratch / "wt"
    subprocess.run([*env_git, "worktree", "add", "-q", str(wt), "-b", "b"], check=True, capture_output=True)  # noqa: S603
    bad = {"tool_name": "Bash", "tool_input": {"command": f"ln -s {main}/frontend/node_modules {wt}/nm"}}
    assert (
        _run(HOOKS / "link_guard.py", wt, bad, wt).returncode == BLOCK_EXIT
    )  # project dir is the worktree; main still protected


def test_subprocess_fails_open_on_garbage_and_missing_helper(
    fake_main: tuple[pathlib.Path, pathlib.Path], tmp_path: pathlib.Path
) -> None:
    main, scratch = fake_main
    assert _run(HOOKS / "link_guard.py", main, "not json", scratch).returncode == 0
    alone = tmp_path / "alone"
    alone.mkdir()
    (alone / "link_guard.py").write_text((HOOKS / "link_guard.py").read_text(encoding="utf-8"), encoding="utf-8")
    bad = {"tool_name": "Bash", "tool_input": {"command": "git worktree remove --force x"}}
    assert _run(alone / "link_guard.py", main, bad, scratch).returncode == 0  # no _route_common next to it -> allow


def test_wiring_is_present_and_missing_script_safe() -> None:
    hooks = json.loads((REPO / ".claude" / "project" / "hooks.json").read_text(encoding="utf-8"))
    cmds = [h["command"] for g in hooks["hooks"]["PreToolUse"] if g["matcher"] == "Bash|PowerShell" for h in g["hooks"]]
    wired = [c for c in cmds if "link_guard.py" in c]
    assert len(wired) == 1
    assert '[ -f "$f" ] || exit 0' in wired[0]
    assert (HOOKS / "link_guard.py").is_file()
