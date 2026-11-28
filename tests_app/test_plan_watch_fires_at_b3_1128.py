"""Lane B3 (28 Nov 2026), Lane F2's W-30: a plan-watch row that is "not checked" still carries the stop's stored
level.

Real case (walker W-30, market closed): the Positions row and the plan block could not show a stop's figure because
``plan_watch`` dropped ``fires_at`` for every row it could not check. The reason it is not checked travels beside
the level. A level that is not known stays absent (never a guess). Checked rows are unchanged. Stand-ins only.
"""
from __future__ import annotations

import datetime
import types
from decimal import Decimal

import pytest
from ofo_app.routes import plan_watch as pw

D = Decimal


def _lim(trigger: str, state: str, *, amount=None, threshold=None, rule: str | None = None):
    why = "adjust_trigger_missing_days_left" if state != "checked" else None
    return types.SimpleNamespace(rule_id=rule or f"r.{trigger}", trigger_id=trigger, state=state, amount=amount,
                                 threshold=threshold, reason=why)


PNL, MAX_PROFIT = D("-500"), D("10000")


def _run(limits, *, max_profit=MAX_PROFIT):
    shown = [types.SimpleNamespace(text=f"label {x.trigger_id}", reason="why not checked") for x in limits]
    state = types.SimpleNamespace(pnl=PNL, max_profit=max_profit)
    return types.SimpleNamespace(out=types.SimpleNamespace(results=[], limits=shown), state=state,
                                 ev=types.SimpleNamespace(limits=limits, values=[]))


def test_a_stop_that_is_not_checked_keeps_its_stored_level_and_its_reason():
    lines = pw._plan_lines_all(_run([_lim("T-03", "not_checked", amount=D("12000"))]), live=True)
    assert len(lines) == 1
    assert lines[0]["state"] == "not_computable" and lines[0]["fires_at"] == D("-12000.00")  # the rupee loss line
    assert lines[0]["reason"] == "why not checked"
    assert lines[0]["now"] is None and lines[0]["distance_rs"] is None


def test_a_target_that_is_not_checked_keeps_its_level_when_it_is_known():
    lines = pw._plan_lines_all(_run([_lim("T-07", "not_checked", threshold=D("50"))]), live=False)
    assert lines[0]["state"] == "not_computable" and lines[0]["fires_at"] == D("5000.00")  # 50 % of the max profit


@pytest.mark.parametrize("limit", [_lim("T-03", "not_checked"), _lim("T-07", "not_checked")],
                         ids=["stop without a figure", "target without a figure"])
def test_a_level_that_is_not_known_stays_absent_never_a_guess(limit):
    lines = pw._plan_lines_all(_run([limit], max_profit=None), live=True)
    assert lines[0]["state"] == "not_computable" and lines[0]["fires_at"] is None


def test_a_checked_stop_is_unchanged():
    lines = pw._plan_lines_all(_run([_lim("T-03", "checked", amount=D("12000"))]), live=True)
    assert lines[0]["state"] == "watching" and lines[0]["fires_at"] == D("-12000.00")
    assert lines[0]["now"] == D("-500.00")


async def test_an_armed_leg_stop_whose_contract_cannot_be_read_keeps_its_stored_level(monkeypatch):
    trigger = types.SimpleNamespace(id=7, kind="leg_stop", direction="above", level=D("90"), contract_id=555,
                                    underlying=None)
    row = types.SimpleNamespace(trigger=trigger, fired_at=None, cancelled_at=None,
                                created_at=datetime.datetime(2026, 11, 27, tzinfo=datetime.UTC))

    async def reads(_db, _sid, _reads):
        return [row], {}, "paper"  # the contract is not among the answers: it cannot be named

    monkeypatch.setattr(pw, "_armed_reads", reads)
    run = types.SimpleNamespace(market=None, tracked=None, spot=None)
    lines = await pw._armed_lines(object(), 1, run, True)
    assert lines[0]["state"] == "not_computable" and lines[0]["fires_at"] == D("90.00")
