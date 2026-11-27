"""Detection, hotfix 27 Nov (finding: a request read waits for a NEW frame while a fresh quote is in the book).

Rule: a request path (``backend/ofo_app/routes``, the market reader, the adjustment readers) reaches the shared feed's
hold-and-wait ONLY through ``ofo_app.read_door.read_quotes``: no ``hold_and_read`` (retired), no ``fanout.subscribe``
and no ``asyncio.sleep(POLL_SECONDS)`` wait loop in a route. ``leg_picker.py`` owns the lease table the door uses.
Fail closed: a file that does not read is a problem. Limit: a wait loop with another sleep constant is not seen.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan

APP = Path(__file__).resolve().parents[1] / "backend" / "ofo_app"
SUBSCRIBE_ALLOWED = {"routes/leg_picker.py"}  # the lease table the door holds through
REQUEST_FILES = [*sorted((APP / "routes").glob("*.py")), APP / "market_read.py", APP / "adjustment_readers.py"]


def _code(path: Path) -> str:
    text = path.read_text(encoding="utf-8")  # raises on an unreadable file: the test fails closed
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def test_the_old_hold_and_read_is_gone_everywhere():
    hits = [str(p.relative_to(APP)) for p in APP.rglob("*.py")
            if re.search(r"(?<![_\w])hold_and_read\b", _code(p)) and not p.name.endswith("read_door.py")]
    assert hits == []


def test_a_request_path_never_subscribes_or_poll_waits_itself():
    bad = []
    for p in REQUEST_FILES:
        rel = str(p.relative_to(APP)).replace("\\", "/")
        code = _code(p)
        if rel not in SUBSCRIBE_ALLOWED and re.search(r"\.fanout\.subscribe\(", code):
            bad.append((rel, "fanout.subscribe"))
        if re.search(r"asyncio\.sleep\(\s*POLL_SECONDS", code):
            bad.append((rel, "sleep(POLL_SECONDS)"))
    assert bad == []


def test_the_request_readers_call_the_door():
    for name in ("market_read.py", "adjustment_readers.py", "routes/paper.py", "routes/planned_entry.py",
                 "routes/indices.py"):
        assert "read_quotes(" in _code(APP / name), name
