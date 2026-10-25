"""PreToolUse hook (AskUserQuestion): refuse the question tool between 22:00 and 08:00 IST (row-review.md L17 by machine).

The owner may be away at night; a question box then freezes the run until morning. Refused with the L17 text: write the
question to docs/process/owner-questions-<date>.md and keep building. Override: env `OFO_QUESTION_NIGHT_OK=1` AND a
stated reason in the question text, a line `Night reason: <why this cannot wait>`.
The clock is the IST helper in backend/ofo/timeutil.py (never a typed offset). Exit 0 = allow, 2 = block. Any crash,
a missing helper or an unreadable input allows (fail open, run-discipline E1).
`decide(tool_name, tool_input, now=None, env=None)`.
"""

from __future__ import annotations

import datetime
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


def decide(
    tool_name: str,
    tool_input: dict,
    now: datetime.datetime | None = None,
    env: dict[str, str] | None = None,
) -> str | None:
    if tool_name.lower() != TOOL:
        return None
    moment = now if now is not None else ist_now()
    if not is_night(moment):
        return None
    environ = os.environ if env is None else env
    if environ.get(OVERRIDE_ENV) == "1" and any(REASON.search(s) for s in _strings(tool_input)):
        return None
    return MESSAGE.format(date=moment.date().isoformat())


def main() -> int:
    try:
        from _route_common import run_hook  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - a missing helper module fails open, silently
        return 0
    return run_hook(decide)


if __name__ == "__main__":
    sys.exit(main())
