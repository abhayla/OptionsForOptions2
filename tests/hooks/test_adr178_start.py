"""adr178_start: the SessionStart hook prints only the tracker rows still open or missed, never blocks, and is wired."""

import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
HOOKS = REPO / "scripts" / "hooks"
sys.path.insert(0, str(HOOKS))
import adr178_start as st  # noqa: E402

SAMPLE = """| # | Audit change | Counter | Limit | Status |
|---|---|---|---|---|
| 1 | Context diet | ctx per turn | < 250k | open |
| 2 | Fresh session | rows per session | <= 3 | followed 2026-10-23 |
| 3 | No tables | prints | 0 | missed (finding x) |
"""


def test_open_and_missed_rows_only():
    rows = st.open_rows(SAMPLE)
    assert [r.split("[")[1][:6] for r in rows] == ["open] ", "missed"]
    assert "row 1 [open] Context diet -- limit < 250k" in rows[0]


def test_real_tracker_parses():
    assert st.open_rows(st.TRACKER.read_text(encoding="utf-8")), "no open tracker row parsed: check the table shape"


def test_subprocess_exits_0():
    p = subprocess.run(  # noqa: S603
        [sys.executable, str(HOOKS / "adr178_start.py")], input="", capture_output=True, text=True, timeout=60,
        check=False,
    )
    assert p.returncode == 0 and "ADR-178 tracker" in p.stdout


def test_hook_is_wired_at_session_start_and_fails_open():
    wired = json.loads((REPO / ".claude" / "project" / "hooks.json").read_text(encoding="utf-8"))
    entries = wired["hooks"]["SessionStart"]
    cmd = json.dumps(entries)
    assert "adr178_start.py" in cmd and '[ -f \\"$f\\" ] || exit 0' in cmd
