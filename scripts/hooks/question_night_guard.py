"""PreToolUse hook (AskUserQuestion): refuse the question tool 22:00-08:00 IST (row-review.md L17 by machine).

The owner may be away at night; a question box then freezes the run until morning. Refused with the L17 text: write the
question to docs/process/owner-questions-<date>.md and keep building. Override: env `OFO_QUESTION_NIGHT_OK=1` AND a
stated reason in the question text, a line `Night reason: <why this cannot wait>`.
The clock is the IST helper in backend/ofo/timeutil.py (never a typed offset). Exit 0 = allow, 2 = block. Any crash,
a missing helper or an unreadable input allows (fail open, run-discipline E1).
`decide(tool_name, tool_input, now=None, env=None, transcript_path=None)`.

Owner present (2026-10-26): at night the question is ALSO allowed when the owner typed a real message in the last
OWNER_PRESENT_MINUTES (10). The signal is the session transcript (`transcript_path` in the hook's stdin JSON): the
newest `type: user` entry that is the person's own text, i.e. `origin.kind == "human"`, text content (a string, or
`text` and `image` parts, no `tool_result`), not `isMeta`, and not injected text (`<system-reminder>`,
`<task-notification>`, `<command-name>`, `<local-command`, `Stop hook feedback`, `[Request interrupted`,
`SYSTEM NOTIFICATION - NOT USER INPUT`). Slash-command wrappers (`<command-name>`) are NOT counted: filtered on
purpose (real ones carry no human origin anyway). The time used is when the owner typed (queued messages: the enqueue
line, see `owner_last_seen`), within the window and not in the future.
FAIL CLOSED here, unlike the rest of the hook: a missing transcript_path, a missing or unreadable file, a bad
timestamp or no genuine message all mean "owner away" and the question is refused. Unreadable lines are skipped; the
rest still count.
A crash of the whole hook still fails open (run-discipline E1).
Known bypass, not chased: anyone who can type into the session counts as the owner.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

TOOL = "askuserquestion"
NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 8
OWNER_PRESENT_MINUTES = 10
FUTURE_SKEW = datetime.timedelta(minutes=1)
# promptSource values stamped when the owner typed (measured over 431 real human entries: typed 134,
# suggestion_accepted 28, queued 263, missing 6); anything else is dated only by its enqueue line
DIRECT_SOURCES = frozenset({"typed", "suggestion_accepted"})
INJECTED_PREFIXES = (
    "<system-reminder>",
    "<task-notification>",
    "<command-name>",
    "<local-command",
    "stop hook feedback",
    "[request interrupted",
)
OVERRIDE_ENV = "OFO_QUESTION_NIGHT_OK"
REASON = re.compile(r"night reason:\s*\S", re.I)
MESSAGE = (
    "BLOCKED by question_night_guard: owner may be away (22:00-08:00 IST): write the question to "
    "docs/process/owner-questions-{date}.md and keep building (row-review.md lesson L17). Override only with "
    "OFO_QUESTION_NIGHT_OK=1 and a line 'Night reason: <why this cannot wait>' in the question."
)


def ist_now() -> datetime.datetime:
    """The current time in IST from the project's clock helper, run by file so no package init side effect happens."""
    helper = runpy.run_path(str(HERE.parents[1] / "backend" / "ofo" / "timeutil.py"))
    return datetime.datetime.now(helper["IST"])


def is_night(now: datetime.datetime) -> bool:
    return now.hour >= NIGHT_START_HOUR or now.hour < NIGHT_END_HOUR


def _strings(value: object) -> list[str]:
    """Every string inside the tool input, unescaped (the reason is judged on the real text, not its JSON form)."""
    if isinstance(value, str):
        return [value]
    items = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
    return [s for v in items for s in _strings(v)]


def _human_text(entry: dict) -> str | None:
    """The person's own text of a transcript entry, or None when the entry is anything else (fail closed)."""
    origin = entry.get("origin")
    if entry.get("type") != "user" or entry.get("isMeta"):
        return None
    if not isinstance(origin, dict) or origin.get("kind") != "human":
        return None
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(not isinstance(p, dict) or p.get("type") not in ("text", "image") for p in content):
            return None  # a tool_result (or any other part) is not the person typing; text + image is
        content = "\n".join(str(p.get("text", "")) for p in content if p.get("type") == "text")
    if not isinstance(content, str):
        return None
    head = content.lstrip().lower()
    if not head or head.startswith(INJECTED_PREFIXES) or "system notification - not user input" in head:
        return None
    return content


def _enqueue_stamp(entry: dict) -> tuple[str, datetime.datetime] | None:
    """(text, time the owner typed it) of a `queue-operation` enqueue line, else None."""
    if entry.get("type") != "queue-operation" or entry.get("operation") != "enqueue":
        return None
    text = entry.get("content")
    if not isinstance(text, str):
        return None
    return text.strip(), datetime.datetime.fromisoformat(str(entry["timestamp"]))


def _typed_stamp(entry: object, pending: dict[str, list[datetime.datetime]]) -> datetime.datetime | None:
    """When the owner typed this transcript entry, or None if it is not a genuine owner message (may raise)."""
    if not isinstance(entry, dict):
        return None
    queued = _enqueue_stamp(entry)
    if queued is not None:
        pending.setdefault(queued[0], []).append(queued[1])
        return None
    text = _human_text(entry)
    if text is None:
        return None
    stamp = datetime.datetime.fromisoformat(str(entry["timestamp"]))
    source = entry.get("promptSource")
    if source in DIRECT_SOURCES:
        return stamp
    waiting = pending.get(text.strip())
    if waiting:
        return min(stamp, waiting.pop(0))  # an enqueue line with the same text dates it
    # no enqueue line: a missing source field (6 real human entries) keeps its own stamp; queued or an unknown
    # source was typed at an unknown earlier time, so the delivery stamp is never trusted
    return stamp if source is None else None


def owner_last_seen(transcript_path: str | None, now: datetime.datetime | None = None) -> datetime.datetime | None:
    """When the owner last TYPED a genuine message; None on any doubt (missing, unreadable, none).

    A message typed while the agent was busy is stamped on DELIVERY, not when typed (real case: enqueued 01:45:38Z,
    delivered 03:17:39Z). Such an entry (`promptSource: queued`) is paired with the `queue-operation` enqueue line that
    has the same text, first in first out, and the enqueue time is used. No match: the entry is skipped. Stamps later
    than `now` + FUTURE_SKEW are ignored. A bad line (even RecursionError) is skipped, the rest still count.
    """
    if not transcript_path:
        return None
    newest: datetime.datetime | None = None
    pending: dict[str, list[datetime.datetime]] = {}
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    stamp = _typed_stamp(json.loads(line), pending)
                except Exception:  # noqa: BLE001, S112 - one bad line never hides the others
                    continue
                if stamp is None or stamp.tzinfo is None or (now is not None and stamp - now > FUTURE_SKEW):
                    continue
                if newest is None or stamp > newest:
                    newest = stamp
    except OSError:
        return None
    return newest


def owner_present(now: datetime.datetime, transcript_path: str | None) -> bool:
    seen = owner_last_seen(transcript_path, now)
    if seen is None:
        return False
    return now - seen <= datetime.timedelta(minutes=OWNER_PRESENT_MINUTES)


def decide(
    tool_name: str,
    tool_input: dict,
    now: datetime.datetime | None = None,
    env: dict[str, str] | None = None,
    transcript_path: str | None = None,
) -> str | None:
    if tool_name.lower() != TOOL:
        return None
    moment = now if now is not None else ist_now()
    if not is_night(moment):
        return None
    environ = os.environ if env is None else env
    if environ.get(OVERRIDE_ENV) == "1" and any(REASON.search(s) for s in _strings(tool_input)):
        return None
    if owner_present(moment, transcript_path):
        return None
    return MESSAGE.format(date=moment.date().isoformat())


def main() -> int:
    try:
        from _route_common import read_input  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - a missing helper module fails open, silently
        return 0
    try:
        data = read_input()
        path = data.get("transcript_path")
        tool_input = data.get("tool_input") or {}
        transcript = path if isinstance(path, str) else None
        reason = decide(str(data.get("tool_name", "")), tool_input, transcript_path=transcript)
    except Exception:  # noqa: BLE001 - a hook must never block on its own bug
        return 0
    if not reason:
        return 0
    sys.stderr.write(reason + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
