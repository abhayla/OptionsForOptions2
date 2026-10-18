"""REQ-034 AC-4 (W-090): a user-chosen scenario RANGE reaches POST /api/strategies/outcome and changes the levels the
Strategy Builder shows; the step is the Admin setting per index (ADR-042: NIFTY 100, SENSEX 300), never the user's.
Same real 2026-10-08 replay and NIFTY iron condor as test_outcome_route.py (spot 22533.25). No database is needed."""
from __future__ import annotations

import pathlib
import sys
from decimal import Decimal
from http import HTTPStatus

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests_app"))

from test_outcome_route import _body, _post, replayed  # noqa: E402,F401  (replayed is the module fixture)

SPOT = "22533.25"
NIFTY_STEP = 100  # ADR-042 default; AC-5: the grid sits on rounded 100-point levels
MAX_COLUMNS = 200  # ScenarioConfig.max_columns of the Admin defaults


def _levels(out: dict) -> list[str]:
    return [lv["level"] for lv in out["scenario"]["levels"]]


async def test_custom_range_gives_exactly_the_hand_computed_grid(replayed):  # noqa: F811
    """AC-4: NIFTY range 22,800-23,600 at the Admin step 100 -> the 9 grid levels 22800 ... 23600 (800 / 100 + 1), plus
    the live level (AC-2) and any breakeven inside the range (AC-5), nothing else."""
    default = (await _post(_body(replayed), replayed)).json()
    assert default["scenario"]["step"] == str(NIFTY_STEP)
    body = dict(_body(replayed), range_start="22800", range_end="23600")
    resp = await _post(body, replayed)
    assert resp.status_code == HTTPStatus.OK, resp.text
    out = resp.json()
    grid = [str(22800 + NIFTY_STEP * k) for k in range(9)]
    assert grid[0] == "22800" and grid[-1] == "23600"
    levels = _levels(out)
    inserted = set(levels) - set(grid)
    assert SPOT in inserted  # the live level is shown even though the range excludes it
    breakevens = {b for b in default["summary"]["breakevens"] if Decimal("22800") <= Decimal(b) <= Decimal("23600")}
    assert inserted == {SPOT} | (breakevens - set(grid))
    assert set(grid) <= set(levels)
    assert levels == sorted(levels, key=Decimal)  # the columns stay in price order
    sc = out["scenario"]
    assert (sc["step"], sc["start"], sc["end"]) == (str(NIFTY_STEP), "22800", "23600")
    assert [lv["level"] for lv in out["scenario"]["levels"] if lv["current"]] == [SPOT]
    assert {lv["level"] for lv in out["scenario"]["levels"] if lv["zero_pnl"]} == breakevens


async def test_switching_the_column_keeps_the_range(replayed):  # noqa: F811
    """AC-4: the same range with estimated_now gives the same level columns as at_expiry."""
    pick = {"range_start": "22800", "range_end": "23600"}
    a = (await _post(dict(_body(replayed), **pick), replayed)).json()
    n = (await _post(dict(_body(replayed), view="estimated_now", **pick), replayed)).json()
    assert n["scenario"]["view"] == "estimated_now" and n["scenario"]["kind"] == "estimate"
    assert _levels(n) == _levels(a)


@pytest.mark.parametrize("bad", [
    {"step": "50"},  # the step is not a request field (ADR-042: Admin setting)
    {"range_start": "22800"}, {"range_end": "23600"},  # one end only
    {"range_start": "0", "range_end": "23600"}, {"range_start": "-100", "range_end": "23600"},
    {"range_start": "22800.5", "range_end": "23600"},
    {"range_start": "23600", "range_end": "22800"}, {"range_start": "22800", "range_end": "22800"},
    {"range_start": "22850", "range_end": "23600"},  # not on the 100-point grid (AC-5)
    {"range_start": "22800", "range_end": "23650"},  # end not on the grid
    {"range_start": "1000", "range_end": "999900"},  # wider than the response cap
    {"range_start": "1000", "range_end": "21100"},  # 202 columns, past the 200 cap
])
async def test_bad_range_is_refused_and_nothing_is_computed(replayed, bad):  # noqa: F811
    """AC-4: an off-grid, one-ended or too-wide range, or a step field, is a 422, never a silent default."""
    resp = await _post(dict(_body(replayed), **bad), replayed)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, resp.text
    assert "scenario" not in resp.json()


async def test_the_cap_boundary_is_accepted(replayed):  # noqa: F811
    """AC-4: exactly 200 columns (the configured maximum, (20900 - 1000) / 100 + 1 = 200) is allowed."""
    body = dict(_body(replayed), range_start="1000", range_end="20900")
    resp = await _post(body, replayed)
    assert resp.status_code == HTTPStatus.OK, resp.text
    assert len(_levels(resp.json())) >= MAX_COLUMNS


async def test_sensex_range_uses_its_own_admin_step(replayed):  # noqa: F811
    """AC-4 / ADR-042: SENSEX's grid is its own Admin step 300: a range on 100-point levels that is not a multiple of
    300 is refused."""
    resp = await _post(dict(_body(replayed), underlying="SENSEX", range_start="74100", range_end="74500"), replayed)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
