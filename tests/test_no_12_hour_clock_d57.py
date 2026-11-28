"""GC-ICLIVE-E D-57 guard: no served text is built as a 12-hour clock (strftime %I / %p, `% 12`, an "AM"/"PM" literal)
in backend/ofo or backend/ofo_app. No exception is left (ADR-326 (4))."""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parents[1]
TWELVE = re.compile(r"%[Ip]\b|%\s*12\b|[\"'](?:AM|PM)[\"']")


def _hits() -> list[tuple[str, int]]:
    out = []
    for base in ("backend/ofo", "backend/ofo_app"):
        for path in (ROOT / base).rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if "/alembic/" in rel:  # SQL format(%I), not a clock
                continue
            lines = path.read_text(encoding="utf-8").split("\n")
            for i, line in enumerate(lines):
                if TWELVE.search(line) and not line.lstrip().startswith("#"):
                    out.append((rel, i + 1))
    return out


def test_no_12_hour_clock_anywhere():
    """ADR-326 (4): 24-hour IST time everywhere; no exception is left (the ADR-015 Q182 sentence is 24-hour too)."""
    assert [f"{f}:{n}" for f, n in _hits()] == []


def test_the_scan_matches_the_12_hour_forms():
    for bad in ['t.strftime("%I:%M %p")', "hour = ist.hour % 12 or 12", 'half = "AM" if x else "PM"']:
        assert TWELVE.search(bad), bad
    for ok in ['t.strftime("%H:%M")', "x = a % 120", "name = 'AMBER'"]:
        assert not TWELVE.search(ok), ok
