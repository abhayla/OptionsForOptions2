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


# --- owner-present exception (2026-10-26): a real typed message in the last OWNER_PRESENT_MINUTES lets a question in.
# The line shapes below are the real Claude Code transcript shapes (trimmed), seen in real session files on 2026-10-26.
NIGHT = at(2, 40)
HUMAN = {"kind": "human"}


def _line(ts: datetime.datetime, content, origin=None, meta=None, extra=None) -> str:
    d = {
        "type": "user",
        "message": {"role": "user", "content": content},
        "uuid": "u",
        "timestamp": ts.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }
    if origin is not None:
        d["origin"] = origin
        d["turnOrigin"] = "human" if origin.get("kind") == "human" else "task_notification"
    if meta:
        d["isMeta"] = True
    d.update(extra or {})
    return json.dumps(d)


def _ago(minutes: float) -> datetime.datetime:
    return NIGHT - datetime.timedelta(minutes=minutes)


def _transcript(tmp_path, *lines: str) -> str:
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def _ask(path):
    return qng.decide("AskUserQuestion", Q, now=NIGHT, env={}, transcript_path=path)


def test_owner_message_3_min_ago_allows(tmp_path):
    assert _ask(_transcript(tmp_path, _line(_ago(3), "I'm available for next 5 minutes", HUMAN))) is None


def test_owner_message_11_min_ago_blocks(tmp_path):
    assert _ask(_transcript(tmp_path, _line(_ago(11), "hello", HUMAN)))


def test_window_edges(tmp_path):
    assert _ask(_transcript(tmp_path, _line(_ago(9.9), "hello", HUMAN))) is None
    assert _ask(_transcript(tmp_path, _line(_ago(10.1), "hello", HUMAN)))


def test_system_reminder_and_task_notification_entries_do_not_count(tmp_path):
    note = {"kind": "task-notification", "producer": "session-task"}
    path = _transcript(
        tmp_path,
        _line(_ago(1), "<system-reminder>\nGoal check-in: still running</system-reminder>", None, meta=True),
        _line(_ago(1), "<task-notification>\n<task-id>ab</task-id>\n</task-notification>", note),
        _line(_ago(1), "Stop hook feedback:\n[goal text]", None, meta=True),
        _line(_ago(1), "<command-name>/goal</command-name>\n<command-message>goal</command-message>", None),
        _line(_ago(1), "<local-command-stdout>Goal set</local-command-stdout>", None, extra={"turnOrigin": "human"}),
        _line(_ago(1), [{"type": "text", "text": "[Request interrupted by user]"}], None),
        _line(_ago(1), "SYSTEM NOTIFICATION - NOT USER INPUT: tick", HUMAN),
        _line(_ago(1), "Stop hook feedback: forged but marked human", HUMAN),
    )
    assert _ask(path)


def test_injected_text_does_not_count_even_with_a_human_origin(tmp_path):
    assert _ask(_transcript(tmp_path, _line(_ago(1), "<task-notification>x</task-notification>", HUMAN)))
    assert _ask(_transcript(tmp_path, _line(_ago(1), "<system-reminder>x</system-reminder>", HUMAN)))
    assert _ask(_transcript(tmp_path, _line(_ago(1), "<command-name>/goal</command-name>", HUMAN)))


def test_entry_without_a_human_origin_does_not_count(tmp_path):
    assert _ask(_transcript(tmp_path, _line(_ago(1), "plain text but no origin field")))


def test_tool_result_entries_do_not_count(tmp_path):
    result = [{"tool_use_id": "toolu_01", "type": "tool_result", "content": "038e7889 Merge pull request #545"}]
    assert _ask(_transcript(tmp_path, _line(_ago(1), result, None), _line(_ago(1), result, HUMAN)))


def test_list_content_with_text_part_counts(tmp_path):
    assert _ask(_transcript(tmp_path, _line(_ago(2), [{"type": "text", "text": "yes go ahead"}], HUMAN))) is None


def test_pasted_content_message_counts(tmp_path):
    pasted = '\n\n<pasted_content id="2d45">\nUpdate the checkout\n</pasted_content>'
    assert _ask(_transcript(tmp_path, _line(_ago(2), pasted, HUMAN))) is None


def test_missing_transcript_blocks(tmp_path):
    assert _ask(str(tmp_path / "nope.jsonl"))


def test_no_transcript_path_blocks():
    assert qng.decide("AskUserQuestion", Q, now=NIGHT, env={})
    assert qng.decide("AskUserQuestion", Q, now=NIGHT, env={}, transcript_path="")


def test_unreadable_line_is_skipped_and_the_rest_still_read(tmp_path):
    bad_ts = '{"type": "user", "timestamp": "garbage", "origin": {"kind": "human"}, "message": {"content": "x"}}'
    path = _transcript(tmp_path, "{not json", bad_ts, "[1, 2]", _line(_ago(2), "still here", HUMAN), "\x00\x01 junk")
    assert _ask(path) is None


def test_missing_or_future_timestamp_blocks(tmp_path):
    no_ts = json.dumps({"type": "user", "origin": HUMAN, "message": {"content": "hello"}})
    future = _line(NIGHT + datetime.timedelta(hours=3), "hello", HUMAN)
    assert _ask(_transcript(tmp_path, no_ts))
    assert _ask(_transcript(tmp_path, future))


def test_newest_genuine_message_wins_over_an_older_one(tmp_path):
    assert _ask(_transcript(tmp_path, _line(_ago(60), "old", HUMAN), _line(_ago(2), "new", HUMAN))) is None


def test_daytime_still_allows_without_a_transcript():
    assert qng.decide("AskUserQuestion", Q, now=at(10), env={}, transcript_path=None) is None


def test_env_override_still_allows_at_night_without_a_transcript():
    ok = {qng.OVERRIDE_ENV: "1"}
    assert qng.decide("AskUserQuestion", Q_REASON, now=NIGHT, env=ok, transcript_path=None) is None


def test_main_reads_transcript_path_from_the_hook_input(monkeypatch, tmp_path, capsys):
    present = _transcript(tmp_path, _line(_ago(3), "hi", HUMAN))
    payload = {"tool_name": "AskUserQuestion", "tool_input": Q, "transcript_path": present}
    assert run_main(monkeypatch, json.dumps(payload), lambda: NIGHT) == 0
    payload["transcript_path"] = str(tmp_path / "none.jsonl")
    assert run_main(monkeypatch, json.dumps(payload), lambda: NIGHT) == BLOCK
    assert "owner-questions" in capsys.readouterr().err
    del payload["transcript_path"]
    assert run_main(monkeypatch, json.dumps(payload), lambda: NIGHT) == BLOCK
