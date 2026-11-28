"""Lane B3 I-202 (O-P-03): a RUNNING paper trade with no live data shows "prices are not live", not the draft label.

Real case (plan row I-202): "A running paper trade shows the Draft Live data not connected heading above the monitoring
badge". No database, no provider (ctx None): the no-provider branch of ``outcome_response``.
Every answer state: running (paper strategy with open fills) -> the running sentence on the answer and every leg; a
saved draft (paper strategy, no fills), a plan (no paper id), an unreadable book (fills None) -> the draft label
as before.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.errors.explanations import render_explanation
from ofo.settings import defaults as _d
from ofo_app.routes import outcome as route
from ofo_app.routes.outcome import Booked, OutcomeRequest

LEG = "NSE_FO:44624"
DRAFT = "Draft — Live data not connected"
RUNNING = "Prices are not live"


def _req() -> OutcomeRequest:
    return OutcomeRequest(underlying="NIFTY", legs=[{
        "instrument_id": LEG, "action": "SELL", "lots": 1, "planned_entry": "10.00",
        "captured_at": datetime.datetime(2026, 10, 8, 3, 50, 5, tzinfo=datetime.UTC)}])


def _answer(booked: Booked | None) -> dict:
    return route.outcome_response(_req(), None, booked=booked, settings=_d()).model_dump(mode="json")


def test_the_catalogue_sentence_is_the_running_one():
    assert render_explanation("outcome_running_not_live") == RUNNING


def test_a_running_trade_is_told_prices_are_not_live():
    out = _answer(Booked(Decimal("0"), False, {LEG: (-75, Decimal("10.00"))}, True, None))
    assert out["state"] == "NOT_CONNECTED"
    assert out["status_label"] == RUNNING
    assert [leg["label"] for leg in out["legs"]] == [RUNNING]


@pytest.mark.parametrize("booked", [
    None,                                                      # no booked reading at all
    Booked(),                                                  # a plan: no paper id
    Booked(None, False, {}, True, None),                       # a saved draft: a paper id, no open position
    Booked(None, True, None, True, None),                      # the book could not be read: not said to be running
], ids=["none", "plan", "draft", "unreadable"])
def test_every_other_state_keeps_the_draft_label(booked):
    out = _answer(booked)
    assert out["status_label"] == DRAFT
    assert [leg["label"] for leg in out["legs"]] == [DRAFT]
