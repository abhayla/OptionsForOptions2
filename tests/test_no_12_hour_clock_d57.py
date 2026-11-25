"""GC-ICLIVE-E D-57 guard: no served text is built as a 12-hour clock (strftime %I / %p, `% 12`, an "AM"/"PM" literal)
in backend/ofo or backend/ofo_app. The ONE named exception is the ADR-015 Q182 / REQ-049 AC-5 sentence's Clock slot in
gate_slots.py (ClockSeconds in explanations.py only delegates to it): each exception line carries the marker below."""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parents[1]
TWELVE = re.compile(r"%[Ip]\b|%\s*12\b|[\"'](?:AM|PM)[\"']")
MARKER = "owner question: ADR-015 Q182 12-hour vs ADR-320 D-57 24-hour"
EXCEPTIONS = {"backend/ofo/errors/gate_slots.py"}


def _hits() -> list[tuple[str, int, bool]]:
    out = []
    for base in ("backend/ofo", "backend/ofo_app"):
        for path in (ROOT / base).rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if "/alembic/" in rel:  # SQL format(%I), not a clock
                continue
            lines = path.read_text(encoding="utf-8").split("\n")
            for i, line in enumerate(lines):
                if TWELVE.search(line) and not line.lstrip().startswith("#"):
                    marked = MARKER in line or (i > 0 and MARKER in lines[i - 1])
                    out.append((rel, i + 1, marked))
    return out


def test_no_12_hour_clock_outside_the_named_exception():
    bad = [f"{f}:{n}" for f, n, marked in _hits() if f not in EXCEPTIONS or not marked]
    assert bad == []


def test_the_exception_still_exists_and_is_marked():
    assert {f for f, _n, marked in _hits() if marked} == EXCEPTIONS
    assert MARKER in (ROOT / "backend/ofo/errors/explanations.py").read_text(encoding="utf-8")  # ClockSeconds


def test_the_scan_matches_the_12_hour_forms():
    for bad in ['t.strftime("%I:%M %p")', "hour = ist.hour % 12 or 12", 'half = "AM" if x else "PM"']:
        assert TWELVE.search(bad), bad
    for ok in ['t.strftime("%H:%M")', "x = a % 120", "name = 'AMBER'"]:
        assert not TWELVE.search(ok), ok
