"""INSTR-FRESH round 3: no route test pins the Execute request clock and leaves the instrument-list stamp on the wall
clock (finding targeted-tests-miss-dependent-files; the seam is described in ``test_execute_clock_seams.py``)."""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.repo_scan
TESTS_APP = pathlib.Path(__file__).resolve().parent

#: an assignment ``...[x.get_execute_clock] = ...`` or a dict key ``x.get_execute_clock: ...`` (an ``update({...})``)
_PINS_REQUEST_CLOCK = re.compile(r"\bget_execute_clock\s*(\]\s*=(?!=)|:)")
_PINS_LIST_STAMP = re.compile(r"replay_clocks\(\)|dependency_overrides\[\s*\w+\.get_list_stamp\s*\]\s*=")


def test_no_route_test_pins_the_request_clock_without_the_list_stamp():
    """Finding targeted-tests-miss-dependent-files: a route test that pins only the request clock judges the list on
    the wall clock again. Every tests_app file that pins ``get_execute_clock`` also pins ``get_list_stamp`` (directly or
    through ``replay_clocks()``). Fails closed: a file that pins the request clock in another spelling is not seen
    as pinning the list stamp."""
    pinned = [p for p in sorted(TESTS_APP.glob("*.py"))
              if p.name != pathlib.Path(__file__).name and _PINS_REQUEST_CLOCK.search(p.read_text(encoding="utf-8"))]
    assert [p.name for p in pinned if not _PINS_LIST_STAMP.search(p.read_text(encoding="utf-8"))] == []
    assert "test_execution_return.py" in {p.name for p in pinned}  # it sees the one direct pin: not reading nothing


@pytest.mark.parametrize("text, pins", [
    ("app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: AT)", True),
    ("app.dependency_overrides.update({route.get_execute_clock: lambda: (lambda: AT)})", True),
    ("assert app.dependency_overrides[execute.get_execute_clock]()() == er.AT", False),
    ("assert app.dependency_overrides[execute.get_execute_clock] == x", False),
])
def test_the_scan_recognises_a_request_clock_pin(text, pins):
    assert bool(_PINS_REQUEST_CLOCK.search(text)) is pins
