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
from ofo.errors import CATALOGUE
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


def test_the_return_door_changed_sentence_does_not_claim_no_order_was_prepared():
    """Lane FD5 review F1 (real case): Return said "no order was prepared", false when a plan exists. The Return door's
    sentence (Lane RA2's ``execution_return_changed``; this lane's duplicate was dropped) says only what is true at
    Return: nothing was recorded."""
    t = CATALOGUE["execution_return_changed"]
    text = " ".join((t.what_happened, t.impact, t.what_is_blocked, t.next_action))
    assert "prepared" not in text and "nothing was recorded" in t.what_happened


def test_the_entries_sentences_are_the_wording_in_the_build():
    """Item 4. Two lanes chose opposite wordings for the Add-to-Paper line; the build carries RA2's (item 9), with
    the prefix "The market is closed.", and this test pins THAT until the owner answers (RESULTS, "Question for
    the owner": is the prefix printed twice on a screen). The dialog prints the sentence alone
    (PaperConfirmDialog.vue ``marketLine``)."""
    said = render_explanation("exit_market_closed_entries_no_day")
    assert said == "The market is closed. Orders can be placed when it opens."
