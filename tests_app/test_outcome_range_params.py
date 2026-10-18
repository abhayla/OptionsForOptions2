"""REQ-034 AC-4 (W-090): a user-chosen scenario step and range reach POST /api/strategies/outcome and change the levels
the Strategy Builder shows. Same real 2026-10-08 replay and NIFTY iron condor as test_outcome_route.py (spot 22533.25).
No database is needed."""
from __future__ import annotations

import pathlib
import sys
from http import HTTPStatus
from decimal import Decimal

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests_app"))

from test_outcome_route import _body, _post, replayed  # noqa: E402,F401  (replayed is the module fixture)

SPOT = "22533.25"
STEP = 200  # a listed NIFTY step, for the step-alone case
MAX_COLUMNS = 200  # ScenarioConfig.max_columns of the Admin defaults


def _levels(out: dict) -> list[str]:
    return [lv["level"] for lv in out["scenario"]["levels"]]


async def test_custom_range_and_step_give_exactly_the_hand_computed_grid(replayed):  # noqa: F811
    """AC-4: NIFTY step 50, range 22,800-23,600 -> the 17 grid levels 22800, 22850 ... 23600 (800 / 50 + 1), plus the
    live level (AC-2) and any breakeven inside the range (AC-5), nothing else."""
    default = (await _post(_body(replayed), replayed)).json()
    assert default["scenario"]["step"] == "100"  # the Admin default is unchanged when nothing is sent
    body = dict(_body(replayed), step="50", range_start="22800", range_end="23600")
    resp = await _post(body, replayed)
    assert resp.status_code == HTTPStatus.OK, resp.text
    out = resp.json()
    grid = [str(22800 + 50 * k) for k in range(17)]
    assert grid[0] == "22800" and grid[-1] == "23600"
    levels = _levels(out)
    inserted = set(levels) - set(grid)
    assert SPOT in inserted  # the live level is shown even though the range excludes it
    breakevens = {b for b in default["summary"]["breakevens"] if Decimal("22800") <= Decimal(b) <= Decimal("23600")}
    assert inserted == {SPOT} | (breakevens - set(grid))
    assert set(grid) <= set(levels)
    assert levels == sorted(levels, key=Decimal)  # the columns stay in price order
    assert (out["scenario"]["step"], out["scenario"]["start"], out["scenario"]["end"]) == ("50", "22800", "23600")
    assert [lv["level"] for lv in out["scenario"]["levels"] if lv["current"]] == [SPOT]
    assert {lv["level"] for lv in out["scenario"]["levels"] if lv["zero_pnl"]} == breakevens


async def test_step_alone_keeps_the_default_range_logic(replayed):  # noqa: F811
    """AC-4: a step without a range keeps the computed range and lays it out at the new step (all on that step)."""
    out = (await _post(dict(_body(replayed), step=str(STEP)), replayed)).json()
    assert out["scenario"]["step"] == str(STEP)
    start, end = Decimal(out["scenario"]["start"]), Decimal(out["scenario"]["end"])
    assert (end - start) % STEP == 0
    grid = {str(start + STEP * k) for k in range(int((end - start) / STEP) + 1)}
    assert grid <= set(_levels(out))


async def test_switching_the_column_keeps_the_range_and_step(replayed):  # noqa: F811
    """AC-4: the same range/step with estimated_now gives the same level columns as at_expiry."""
    pick = {"step": "50", "range_start": "22800", "range_end": "23600"}
    a = (await _post(dict(_body(replayed), **pick), replayed)).json()
    n = (await _post(dict(_body(replayed), view="estimated_now", **pick), replayed)).json()
    assert n["scenario"]["view"] == "estimated_now" and n["scenario"]["kind"] == "estimate"
    assert _levels(n) == _levels(a)


@pytest.mark.parametrize("bad", [
    {"step": "0"}, {"step": "-50"}, {"step": "75"}, {"step": "50.5"}, {"step": "1000"},  # off the NIFTY list
    {"range_start": "22800"}, {"range_end": "23600"},  # one end only
    {"range_start": "23600", "range_end": "22800"}, {"range_start": "22800", "range_end": "22800"},
    {"range_start": "22825", "range_end": "23600"},  # not on the strike grid
    {"step": "200", "range_start": "22800", "range_end": "23650"},  # not a whole number of steps
    {"step": "50", "range_start": "1000", "range_end": "999950"},  # wider than the response cap
    {"step": "50", "range_start": "1000", "range_end": "11050"},  # 202 columns, past the 200 cap
])
async def test_off_list_step_or_range_is_refused_and_nothing_is_computed(replayed, bad):  # noqa: F811
    """AC-4: an off-list step or range is a 422 (the error boundary's catalogue text), never a silent default."""
    resp = await _post(dict(_body(replayed), **bad), replayed)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, resp.text
    assert "scenario" not in resp.json()


async def test_the_cap_boundary_is_accepted(replayed):  # noqa: F811
    """AC-4: exactly 200 columns (the configured maximum, (10950 - 1000) / 50 + 1 = 200) is allowed."""
    body = dict(_body(replayed), step="50", range_start="1000", range_end="10950")
    resp = await _post(body, replayed)
    assert resp.status_code == HTTPStatus.OK, resp.text
    assert len(_levels(resp.json())) >= MAX_COLUMNS


async def test_sensex_uses_its_own_step_list(replayed):  # noqa: F811
    """AC-4 / ADR-042: SENSEX steps come from the SENSEX list: 300 is allowed there, 50 is refused."""
    from ofo.scenario.config import STEP_CHOICES
    assert Decimal("50") not in STEP_CHOICES["SENSEX"] and Decimal("300") in STEP_CHOICES["SENSEX"]
    resp = await _post(dict(_body(replayed), underlying="SENSEX", step="50"), replayed)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
