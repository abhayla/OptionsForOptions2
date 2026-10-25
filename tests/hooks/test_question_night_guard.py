"""question_night_guard: the question tool is refused 22:00-08:00 IST, allowed by day, overridable with a stated
reason, and a crash or missing file never blocks (fail open)."""

import datetime
import io
import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
HOOKS = REPO / "scripts" / "hooks"
sys.path.insert(0, str(HOOKS))
import question_night_guard as qng  # noqa: E402

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")  # the hook's own clock is tested at the end
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)

BLOCK = 2
Q = {"questions": [{"question": "Which option?", "options": []}]}
REASON_TEXT = "Which option?\nNight reason: the market opens at 09:15 and the order path is blocked"
Q_REASON = {"questions": [{"question": REASON_TEXT}]}
Q_EMPTY_REASON = {"questions": [{"question": "Which option?\nNight reason:   "}]}


def at(hour: int, minute: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 10, 23, hour, minute, tzinfo=IST)


def test_2330_ist_is_refused_with_r17_text():
    msg = qng.decide("AskUserQuestion", Q, now=at(23, 30), env={})
    assert msg and "owner may be away (22:00-08:00 IST)" in msg
    assert "docs/process/owner-questions-2026-10-23.md" in msg and "row-review.md lesson L17" in msg


def test_1000_ist_is_allowed():
    assert qng.decide("AskUserQuestion", Q, now=at(10), env={}) is None


EDGES = [(21, 59, False), (22, 0, True), (7, 59, True), (8, 0, False), (0, 0, True)]


@pytest.mark.parametrize(("hour", "minute", "blocked"), EDGES)
def test_boundaries(hour, minute, blocked):
    assert bool(qng.decide("AskUserQuestion", Q, now=at(hour, minute), env={})) is blocked


def test_clock_is_ist_not_the_machine_zone():
    # 23:30 IST is 18:00 UTC: an aware UTC time must be judged on the IST wall clock by the caller's helper
    utc_evening = datetime.datetime(2026, 10, 23, 18, 0, tzinfo=datetime.UTC)
    assert qng.is_night(utc_evening.astimezone(IST))


def test_override_needs_env_and_a_stated_reason():
    ok = {qng.OVERRIDE_ENV: "1"}
    assert qng.decide("AskUserQuestion", Q_REASON, now=at(23), env=ok) is None
    assert qng.decide("AskUserQuestion", Q, now=at(23), env=ok)  # env alone: no reason
    assert qng.decide("AskUserQuestion", Q_EMPTY_REASON, now=at(23), env=ok)  # empty reason
    assert qng.decide("AskUserQuestion", Q_REASON, now=at(23), env={})  # reason alone: no env
    assert qng.decide("AskUserQuestion", Q_REASON, now=at(23), env={qng.OVERRIDE_ENV: "0"})


def test_other_tools_are_untouched_at_night():
    assert qng.decide("Bash", {"command": "ls"}, now=at(23), env={}) is None


def run_main(monkeypatch, payload: str, clock) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    monkeypatch.setattr(qng, "ist_now", clock)
    return qng.main()


def test_main_blocks_with_exit_2_at_night(monkeypatch, capsys):
    code = run_main(monkeypatch, json.dumps({"tool_name": "AskUserQuestion", "tool_input": Q}), lambda: at(23, 30))
    assert code == BLOCK
    assert "owner-questions" in capsys.readouterr().err


def test_crash_in_the_clock_or_bad_input_exits_0(monkeypatch):
    def boom():
        raise RuntimeError("clock broke")

    payload = json.dumps({"tool_name": "AskUserQuestion", "tool_input": Q})
    assert run_main(monkeypatch, payload, boom) == 0
    assert run_main(monkeypatch, "not json {", lambda: at(23)) == 0
    assert run_main(monkeypatch, "[1, 2]", lambda: at(23)) == 0


def test_missing_helper_module_exits_0(monkeypatch):
    monkeypatch.setitem(sys.modules, "_route_common", None)  # makes `from _route_common import ...` raise ImportError
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_name": "AskUserQuestion", "tool_input": Q})))
    monkeypatch.setattr(qng, "ist_now", lambda: at(23))
    assert qng.main() == 0


def test_wired_command_exits_0_when_the_script_is_missing():
    # the egress guard refuses to start bash inside tests, so the wired shape is asserted instead of run
    wired = json.loads((REPO / ".claude" / "project" / "hooks.json").read_text(encoding="utf-8"))
    cmd = next(e for e in wired["hooks"]["PreToolUse"] if e["matcher"] == "AskUserQuestion")["hooks"][0]["command"]
    assert '[ -f "$f" ] || exit 0' in cmd
    assert cmd.index("exit 0") < cmd.index("python")


def test_real_subprocess_with_garbage_stdin_exits_0():
    p = subprocess.run(  # noqa: S603
        [sys.executable, str(HOOKS / "question_night_guard.py")],
        input="garbage",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert p.returncode == 0


def test_hook_is_wired_for_the_question_tool():
    wired = json.loads((REPO / ".claude" / "project" / "hooks.json").read_text(encoding="utf-8"))
    entries = [e for e in wired["hooks"]["PreToolUse"] if e["matcher"] == "AskUserQuestion"]
    assert entries and "question_night_guard.py" in json.dumps(entries)


def test_hook_clock_is_the_project_ist_helper():
    now = qng.ist_now()
    assert now.utcoffset() == IST_OFFSET
    assert now <= datetime.datetime.now(IST)  # a real clock reading, not a typed constant
