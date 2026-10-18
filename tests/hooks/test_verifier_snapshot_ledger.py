"""verifier_snapshot_ledger: a verifier's PreToolUse shell calls are listed per agent; at SubagentStop the snapshots it
lists that are still on disk are deleted, and nothing else.

Each test runs the hook as a subprocess with the hook-input JSON on stdin and the system temp folder (TMP/TEMP/TMPDIR)
pointed at a test folder, so the kit guard's own `snap_path` and verifier_inflight_gate's `snap_dir` both land there.
Input field names are the ones measured on a real verifier run (2026-10-18): PreToolUse carries agent_id, agent_type,
session_id, tool_use_id, tool_name; SubagentStop carries agent_id, agent_type.

Guard -> killing test:
  tool_name allow-list (record)            test_a_non_shell_tool_is_not_recorded
  agent is a verifier (worth_loading)      test_non_verifier_agents_and_the_main_session_are_ignored
  agent_id allow-list (ledger_path)        test_an_agent_id_that_is_not_a_plain_id_writes_no_ledger
  snap_path None (no tool_use_id)          test_a_call_without_tool_use_id_records_nothing
  snapshot name allow-list (own_snapshot)  test_ledger_lines_outside_the_snap_folder_are_not_deleted (notes.txt)
  folder IS the snap folder (own_snapshot) test_ledger_lines_outside_the_snap_folder_are_not_deleted (elsewhere, ..)
  corrupt ledger deletes nothing           test_a_corrupt_ledger_deletes_nothing_and_exits_0
  event allow-list (worth_loading)         test_other_events_neither_record_nor_clean
  verifier pre-filter before any import    test_non_verifier_calls_never_load_the_kit_module
  prune ledgers older than the kit TTL     test_stale_ledgers_of_killed_verifiers_are_pruned_at_stop
  fail open on any error (main)            test_bad_input_exits_0, test_a_missing_kit_module_exits_0
  fail open on SystemExit (BaseException)  test_a_kit_module_that_exits_at_import_never_blocks
Mutation run: VSL_HOOK_PATH points the tests at a patched copy of the hook.
"""
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
HOOK = pathlib.Path(os.environ.get("VSL_HOOK_PATH") or REPO / "scripts" / "hooks" / "verifier_snapshot_ledger.py")
KIT_GUARD = REPO / ".claude" / "hooks" / "verifier_write_guard.py"
SID = "31cafa70-c470-4e7c-9a1e-d3dcea92a6f1"  # a real session id from the 2026-10-18 measurement run
AGENT_A = "a31827cf74add011e"  # real agent_id shape from the same run
AGENT_B = "a135aa58a66dc2e29"


@pytest.fixture
def tmp(tmp_path):
    return tmp_path


def env_for(tmp: pathlib.Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("OFO_VERIFIER_SNAP_DIR", "VERIFIER_WRITE_GUARD_AGENTS")}
    env.update(TMP=str(tmp), TEMP=str(tmp), TMPDIR=str(tmp))
    return env


def run(tmp: pathlib.Path, payload, hook: pathlib.Path = HOOK) -> subprocess.CompletedProcess:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(hook)], input=text, capture_output=True, text=True,  # noqa: S603
                          env=env_for(tmp), timeout=60, check=False)


def snap_folder(tmp: pathlib.Path) -> pathlib.Path:
    return tmp / "verifier-write-guard" / "snap"


def ledger(tmp: pathlib.Path, agent: str) -> pathlib.Path:
    """The agent's ledger path (its folder is created, so a test can write one by hand)."""
    p = tmp / "verifier-write-guard" / "owners" / f"{agent}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def kit_snap_path(tmp: pathlib.Path, tid: str) -> str:
    """The kit guard's own snap_path for this call, with the system temp folder pointed at `tmp`."""
    spec = importlib.util.spec_from_file_location("_kit_guard_for_test", KIT_GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    saved = tempfile.tempdir
    tempfile.tempdir = str(tmp)
    try:
        return mod.snap_path({"session_id": SID, "tool_use_id": tid})
    finally:
        tempfile.tempdir = saved


def hand_snap_path(tmp: pathlib.Path, tid: str) -> pathlib.Path:
    """Independent hand computation of the same name: sha256(session_id NUL tool_use_id), first 16 hex."""
    name = hashlib.sha256(f"{SID}\0{tid}".encode()).hexdigest()[:16] + ".json"
    return snap_folder(tmp) / name


def pre(agent: str, tid: str, agent_type="verifier", tool="Bash") -> dict:
    d = {"hook_event_name": "PreToolUse", "agent_id": agent, "agent_type": agent_type, "session_id": SID,
         "tool_use_id": tid, "tool_name": tool, "tool_input": {"command": "git status --short"}, "cwd": str(REPO)}
    if agent_type is None:
        del d["agent_type"], d["agent_id"]
    return d


def stop(agent: str, agent_type="verifier") -> dict:
    return {"hook_event_name": "SubagentStop", "agent_id": agent, "agent_type": agent_type, "session_id": SID,
            "stop_hook_active": False}


def make_snap(path) -> pathlib.Path:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"roots": []}')
    return p


def test_pre_records_the_exact_path_the_kit_snap_path_gives(tmp):
    """Pre: the ledger line is the kit guard's snap_path for this call (and matches the hand-computed name)."""
    r = run(tmp, pre(AGENT_A, "toolu_014kSDwtBkLW4Vchheyy4q6M"))
    assert r.returncode == 0, r.stderr
    expected = kit_snap_path(tmp, "toolu_014kSDwtBkLW4Vchheyy4q6M")
    assert pathlib.Path(expected) == hand_snap_path(tmp, "toolu_014kSDwtBkLW4Vchheyy4q6M")
    assert ledger(tmp, AGENT_A).read_text(encoding="utf-8") == expected + "\n"


def test_stop_deletes_this_agents_leftover_snapshots_and_its_ledger(tmp):
    """Stop: every listed snapshot still on disk is deleted, then the ledger."""
    for tid in ("toolu_A1", "toolu_A2"):
        assert run(tmp, pre(AGENT_A, tid)).returncode == 0
        make_snap(hand_snap_path(tmp, tid))
    r = run(tmp, stop(AGENT_A))
    assert r.returncode == 0, r.stderr
    assert not hand_snap_path(tmp, "toolu_A1").exists()
    assert not hand_snap_path(tmp, "toolu_A2").exists()
    assert not ledger(tmp, AGENT_A).exists()


def test_a_second_agents_live_snapshot_survives(tmp):
    """Attack 1: verifier A stops while B's call is in flight: B's snapshot and B's ledger are untouched."""
    assert run(tmp, pre(AGENT_A, "toolu_A1")).returncode == 0
    make_snap(hand_snap_path(tmp, "toolu_A1"))
    assert run(tmp, pre(AGENT_B, "toolu_B1")).returncode == 0
    b_snap = make_snap(hand_snap_path(tmp, "toolu_B1"))
    assert run(tmp, stop(AGENT_A)).returncode == 0
    assert not hand_snap_path(tmp, "toolu_A1").exists()
    assert b_snap.read_text() == '{"roots": []}'
    assert ledger(tmp, AGENT_B).read_text(encoding="utf-8") == str(b_snap) + "\n"


def test_an_already_removed_snapshot_is_not_an_error(tmp):
    """Attack 2: an unblocked call's snapshot was removed by the kit guard's Post; Stop finds nothing, exits 0."""
    assert run(tmp, pre(AGENT_A, "toolu_A1")).returncode == 0
    r = run(tmp, stop(AGENT_A))
    assert (r.returncode, r.stderr) == (0, "")
    assert not ledger(tmp, AGENT_A).exists()


def test_stop_without_a_ledger_exits_0(tmp):
    """Ledger missing: the verifier made no shell call; nothing happens."""
    other = make_snap(snap_folder(tmp) / "0123456789abcdef.json")
    assert run(tmp, stop(AGENT_A)).returncode == 0
    assert other.exists()


def test_ledger_lines_outside_the_snap_folder_are_not_deleted(tmp):
    """Attack 3: only `<16 hex>.json` directly in the snap folder is deleted; `..`, other folders, other names stay."""
    folder = snap_folder(tmp)
    elsewhere = make_snap(tmp / "elsewhere" / "0123456789abcdef.json")
    parent = make_snap(folder.parent / "fedcba9876543210.json")
    notes = make_snap(folder / "notes.txt")
    wrong_case = make_snap(folder / "0123456789ABCDEF.json")
    own = make_snap(folder / "aaaaaaaaaaaaaaaa.json")
    lines = [str(elsewhere), str(folder / ".." / "fedcba9876543210.json"), str(notes), str(wrong_case),
             "0123456789abcdef.json", str(own)]
    ledger(tmp, AGENT_A).parent.mkdir(parents=True, exist_ok=True)
    ledger(tmp, AGENT_A).write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert run(tmp, stop(AGENT_A)).returncode == 0
    assert elsewhere.exists() and parent.exists() and notes.exists() and wrong_case.exists()
    assert not own.exists()


def test_non_verifier_agents_and_the_main_session_are_ignored(tmp):
    """A builder and the main session (no agent_type) write no ledger; a builder's Stop deletes nothing."""
    assert run(tmp, pre(AGENT_A, "toolu_X", agent_type="builder")).returncode == 0
    assert run(tmp, pre(AGENT_A, "toolu_Y", agent_type=None)).returncode == 0
    assert not (tmp / "verifier-write-guard" / "owners").exists()
    snap = make_snap(hand_snap_path(tmp, "toolu_X"))
    ledger(tmp, AGENT_A).write_text(str(snap) + "\n", encoding="utf-8")
    assert run(tmp, stop(AGENT_A, agent_type="builder")).returncode == 0
    assert snap.exists() and ledger(tmp, AGENT_A).exists()


def test_a_namespaced_verifier_counts(tmp):
    """`plugin:verifier` is a verifier, as in the kit guard (last ':' part)."""
    assert run(tmp, pre(AGENT_A, "toolu_A1", agent_type="plugin:verifier")).returncode == 0
    snap = make_snap(hand_snap_path(tmp, "toolu_A1"))
    assert run(tmp, stop(AGENT_A, agent_type="plugin:verifier")).returncode == 0
    assert not snap.exists()


def test_an_agent_id_that_is_not_a_plain_id_writes_no_ledger(tmp):
    """agent_id absent or with path characters: no ledger anywhere (it would name the ledger file)."""
    for bad in ("../../x", "", None, "a/b"):
        d = pre(AGENT_A, "toolu_A1")
        d["agent_id"] = bad
        assert run(tmp, d).returncode == 0
    assert not (tmp / "verifier-write-guard" / "owners").exists()
    assert not (tmp / "x.txt").exists()


def test_a_call_without_tool_use_id_records_nothing(tmp):
    """No tool_use_id: the kit guard writes no snapshot either, so nothing is listed."""
    d = pre(AGENT_A, "toolu_A1")
    del d["tool_use_id"]
    assert run(tmp, d).returncode == 0
    assert not ledger(tmp, AGENT_A).exists()


def test_a_non_shell_tool_is_not_recorded(tmp):
    """Only Bash and PowerShell calls get a kit snapshot; a Read call is not listed."""
    assert run(tmp, pre(AGENT_A, "toolu_A1", tool="Read")).returncode == 0
    assert run(tmp, pre(AGENT_A, "toolu_A2", tool="PowerShell")).returncode == 0
    assert ledger(tmp, AGENT_A).read_text(encoding="utf-8") == str(hand_snap_path(tmp, "toolu_A2")) + "\n"


def test_other_events_neither_record_nor_clean(tmp):
    """PostToolUse (or any event but Pre/SubagentStop) leaves the ledger and the snapshots alone."""
    assert run(tmp, pre(AGENT_A, "toolu_A1")).returncode == 0
    snap = make_snap(hand_snap_path(tmp, "toolu_A1"))
    for event in ("PostToolUse", "Stop"):
        d = stop(AGENT_A)
        d["hook_event_name"] = event
        assert run(tmp, d).returncode == 0
    assert snap.exists()
    assert ledger(tmp, AGENT_A).read_text(encoding="utf-8") == str(snap) + "\n"


def test_a_corrupt_ledger_deletes_nothing_and_exits_0(tmp):
    """A ledger that is not UTF-8: nothing deleted, the ledger kept, exit 0."""
    snap = make_snap(hand_snap_path(tmp, "toolu_A1"))
    ledger(tmp, AGENT_A).parent.mkdir(parents=True, exist_ok=True)
    ledger(tmp, AGENT_A).write_bytes(str(snap).encode("utf-8") + b"\n\xff\xfe\n")
    r = run(tmp, stop(AGENT_A))
    assert r.returncode == 0
    assert snap.exists() and ledger(tmp, AGENT_A).exists()


@pytest.mark.parametrize("payload", ["{not json", "[1, 2]", "", '"verifier"'])
def test_bad_input_exits_0(tmp, payload):
    """Attack 4: bad JSON or a non-object input never blocks (exit 0, nothing written)."""
    r = run(tmp, payload)
    assert (r.returncode, r.stderr) == (0, "")
    assert not (tmp / "verifier-write-guard").exists()


def test_a_missing_kit_module_exits_0(tmp):
    """The kit guard file is absent: Pre and Stop both exit 0 and touch nothing."""
    hooks = tmp / "copy" / "scripts" / "hooks"
    hooks.mkdir(parents=True)
    for name in ("verifier_snapshot_ledger.py", "verifier_inflight_gate.py"):
        shutil.copy2(HOOK.parent / name, hooks / name)
    snap = make_snap(hand_snap_path(tmp, "toolu_A1"))
    ledger(tmp, AGENT_A).write_text(str(snap) + "\n", encoding="utf-8")
    for payload in (pre(AGENT_A, "toolu_A2"), stop(AGENT_A)):
        r = run(tmp, payload, hook=hooks / "verifier_snapshot_ledger.py")
        assert (r.returncode, r.stderr) == (0, "")
    assert snap.exists()
    assert ledger(tmp, AGENT_A).read_text(encoding="utf-8") == str(snap) + "\n"


def copy_with_stub_kit(tmp: pathlib.Path, kit_source: str) -> pathlib.Path:
    """A copy of the hook (and verifier_inflight_gate) whose kit module is `kit_source`; returns the hook path."""
    hooks = tmp / "copy" / "scripts" / "hooks"
    hooks.mkdir(parents=True)
    for name in ("verifier_snapshot_ledger.py", "verifier_inflight_gate.py"):
        shutil.copy2(HOOK.parent / name, hooks / name)
    kit = tmp / "copy" / ".claude" / "hooks"
    kit.mkdir(parents=True)
    (kit / "verifier_write_guard.py").write_text(kit_source, encoding="utf-8")
    return hooks / "verifier_snapshot_ledger.py"


def test_a_kit_module_that_exits_at_import_never_blocks(tmp):
    """Fix 1: a kit module calling sys.exit(2) at import: the hook still exits 0 (SystemExit is caught)."""
    hook = copy_with_stub_kit(tmp, "import sys\nsys.exit(2)\n")
    for payload in (pre(AGENT_A, "toolu_A1"), stop(AGENT_A)):
        r = run(tmp, payload, hook=hook)
        assert r.returncode == 0, r.stderr


def test_non_verifier_calls_never_load_the_kit_module(tmp):
    """Fix 2: the main session, a builder and other events return before the kit module is imported; a verifier's
    call does import it (so the probe discriminates)."""
    marker = tmp / "kit-imported.txt"
    hook = copy_with_stub_kit(tmp, f"open({str(marker)!r}, 'a').write('x')\nraise RuntimeError('imported')\n")
    post = pre(AGENT_A, "toolu_A3")
    post["hook_event_name"] = "PostToolUse"
    for payload in (pre(AGENT_A, "toolu_A1", agent_type=None), pre(AGENT_A, "toolu_A2", agent_type="builder"),
                    stop(AGENT_A, agent_type="builder"), post):
        r = run(tmp, payload, hook=hook)
        assert (r.returncode, r.stderr) == (0, "")
    assert not marker.exists()
    assert run(tmp, pre(AGENT_A, "toolu_A4"), hook=hook).returncode == 0
    assert marker.read_text() == "x"


def test_stale_ledgers_of_killed_verifiers_are_pruned_at_stop(tmp):
    """Fix 3: at a verifier's SubagentStop, ledgers older than the kit's SNAP_TTL_SECONDS are deleted; a younger
    one (a live parallel verifier's) stays."""
    spec = importlib.util.spec_from_file_location("_kit_guard_ttl", KIT_GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    old = ledger(tmp, "killedagent01")
    old.write_text("x\n", encoding="utf-8")
    t = old.stat().st_mtime - mod.SNAP_TTL_SECONDS - 60
    os.utime(old, (t, t))
    young = ledger(tmp, AGENT_B)
    young.write_text("y\n", encoding="utf-8")
    t2 = young.stat().st_mtime - mod.SNAP_TTL_SECONDS + 600
    os.utime(young, (t2, t2))
    assert run(tmp, stop(AGENT_A)).returncode == 0
    assert not old.exists()
    assert young.read_text(encoding="utf-8") == "y\n"


def test_the_hook_is_wired_fail_open_on_pre_shell_and_subagent_stop():
    """Attack 5: hooks.json wires the hook on PreToolUse Bash|PowerShell and on SubagentStop, in the fail-open form."""
    cfg = json.loads((REPO / ".claude" / "project" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    form = 'f="$CLAUDE_PROJECT_DIR/scripts/hooks/verifier_snapshot_ledger.py"; [ -f "$f" ] || exit 0; python "$f"'
    pre_cmds = [h["command"] for e in cfg["PreToolUse"] if e.get("matcher") == "Bash|PowerShell" for h in e["hooks"]]
    stop_cmds = [h["command"] for e in cfg["SubagentStop"] for h in e["hooks"]]
    assert pre_cmds.count(form) == 1
    assert stop_cmds == [form]
