"""ADR-140 / ADR-143: the Execute reply's ``risk`` block and the Strategy Guard acknowledgement, without a database
(pure functions and the request model). The route's acceptance flow end to end is in ``test_execute_route.py`` (CI
database)."""
from __future__ import annotations

import dataclasses
import datetime
import json
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.execution.risk_tier import Reason
from ofo.strategy.guard import StrategyGuard
from ofo_app import api_models
from ofo_app.routes import execute as route
from ofo_app.routes.execute import ExecuteIn, ReviewOut, risk_out
from pydantic import ValidationError


def review(loss, unlimited=False):
    return ReviewOut.model_validate({"max_loss": None if loss is None else D(loss), "max_loss_unlimited": unlimited,
                                     "max_profit": None, "max_profit_unlimited": False,
                                     "max_loss_display": None if loss is None else D(loss), "max_profit_display": None})


def dump(out):
    return None if out is None else json.loads(api_models.emit(out))


def test_normal_carries_a_one_decimal_percent_string():
    assert dump(risk_out(review("5900.00"), D("240000.00"))) == {
        "tier": "NORMAL", "percent_of_funds": "2.5", "reason": None, "needs_acceptance": False, "acknowledgement": None}


def test_elevated_needs_no_acceptance():
    out = dump(risk_out(review("70000.00"), D("240000.00")))
    assert (out["tier"], out["percent_of_funds"], out["needs_acceptance"]) == ("ELEVATED", "29.2", False)


@pytest.mark.parametrize(("rev", "funds", "reason"), [
    (review(None, unlimited=True), D("240000.00"), "UNLIMITED"),
    (review("240000.01"), D("240000.00"), "ABOVE_FUNDS"),
    (review("1.00"), D("0.00"), "ABOVE_FUNDS"),
])
def test_exceptional_needs_acceptance(rev, funds, reason):
    out = dump(risk_out(rev, funds))
    assert (out["tier"], out["reason"], out["needs_acceptance"]) == ("EXCEPTIONAL", reason, True)


def test_funds_unknown_has_no_percent_and_at_least_elevated():
    out = dump(risk_out(review("5900.00"), None))
    assert (out["tier"], out["percent_of_funds"], out["needs_acceptance"]) == ("ELEVATED", None, False)


def test_unknown_loss_on_an_entry_is_elevated_and_with_an_uncovered_short_exceptional():
    """ADR-143: no worst case from the engine is never a silent pass; an uncovered short needs the acknowledgement."""
    out = dump(risk_out(review(None), D("240000.00")))
    assert (out["tier"], out["reason"], out["needs_acceptance"]) == ("ELEVATED", "LOSS_UNKNOWN", False)
    out = dump(risk_out(review(None), D("240000.00"), unknown_loss=Reason.UNCOVERED_SHORT))
    assert (out["tier"], out["reason"], out["needs_acceptance"]) == ("EXCEPTIONAL", "UNCOVERED_SHORT", True)


def test_an_exit_with_no_known_loss_has_no_risk_block():
    assert risk_out(review(None), D("240000.00"), unknown_loss=None) is None


def test_the_token_rides_the_reply_and_only_as_an_identifier():
    out = dump(risk_out(review(None, unlimited=True), D("1.00"), acknowledgement="abc-DEF_123"))
    assert out["acknowledgement"] == "abc-DEF_123"


def test_the_request_takes_a_token_never_a_bare_accept():
    assert ExecuteIn.model_validate({"action": "ENTRY"}).acknowledgement is None
    assert ExecuteIn.model_validate({"action": "ENTRY", "acknowledgement": "tok"}).acknowledgement == "tok"
    for bad in ({"action": "ENTRY", "accept_risk": True}, {"action": "ENTRY", "acknowledgement": True},
                {"action": "ENTRY", "acknowledgement": "x" * 129}):
        with pytest.raises(ValidationError):
            ExecuteIn.model_validate(bad)


# ---- the amounts the screen shows come from the engine's one money formatter (ADR-008) -------------------------------

def test_review_amounts_are_written_by_the_engine_money_formatter():
    rev = ReviewOut.model_validate({"max_loss": D("1234567.50"), "max_loss_unlimited": False, "max_profit": D("-8175"),
                                    "max_profit_unlimited": False, "max_loss_display": D("1234567.50"),
                                    "max_profit_display": D("-8175")})
    body = json.loads(api_models.emit(rev))
    assert (body["max_loss"], body["max_loss_display"]) == ("1234567.50", "₹12,34,567.50")
    assert body["max_profit_display"] == "\u2212\u20b98,175.00"  # a true minus, as ofo.engine.display writes it
    assert json.loads(api_models.emit(review(None)))["max_loss_display"] is None


def test_review_out_carries_the_display_twin_of_the_engine_figures():
    from ofo.engine import Action, Instrument, Leg, Strategy  # noqa: PLC0415

    leg = Leg(Action.BUY, Instrument.CE, D("23650"), datetime.date(2026, 10, 19), 65, D("3.35"), D("3.35"))
    body = json.loads(api_models.emit(route.review_out(Strategy((leg,)), "ENTRY")))
    assert (body["max_loss"], body["max_loss_display"]) == ("217.75", "₹217.75")
    assert body["max_profit"] is None and body["max_profit_display"] is None


# ---- the acknowledgement: a single-use Strategy Guard token bound to THIS exact proposal ----------------------------

def real_orders():
    from test_execute_route import _real_basket  # noqa: PLC0415

    return _real_basket().orders


def make_request(guard, token=None, *, user="user-1", action="ENTRY"):
    return route._Request(db=None, user_ref=user, strategy_id=1, action=action, session=None, quotes=None,
                          now=None, clock=None, rates=None, guard=guard, acknowledgement=token)


STORED = SimpleNamespace(revision=3)
EXCEPTIONAL = risk_out(review(None, unlimited=True), D("1003.00"))


def binding(req, orders=None, rev=None):
    return route._risk_binding(req, STORED, real_orders() if orders is None else orders,
                               review(None, unlimited=True) if rev is None else rev, EXCEPTIONAL)


def issue(guard, req, **kw):
    return guard._issue_flagged(binding(req, **kw)).acknowledgement


def test_a_token_issued_for_this_proposal_redeems_once():
    guard = StrategyGuard()
    token = issue(guard, make_request(guard))
    assert isinstance(token, str) and token.isascii() and not token.isspace()
    req = make_request(guard, token)
    assert route._redeemed(req, binding(req)) is True
    assert route._redeemed(req, binding(req)) is False  # single use: the same token again is refused


def test_a_first_call_with_nothing_or_a_bare_accept_is_refused_and_nothing_is_consumed():
    guard = StrategyGuard()
    token = issue(guard, make_request(guard))
    req = make_request(guard, None)
    assert route._redeemed(req, binding(req)) is False
    again = make_request(guard, token)  # the issued decision is still open for its own token
    assert route._redeemed(again, binding(again)) is True


def test_a_never_issued_proposal_refuses_any_token():
    guard = StrategyGuard()
    req = make_request(guard, "anything-at-all")
    assert route._redeemed(req, binding(req)) is False


def test_a_forged_token_is_refused_and_the_real_one_still_works():
    guard = StrategyGuard()
    token = issue(guard, make_request(guard))
    forged = make_request(guard, token[:-1] + ("A" if token[-1] != "A" else "B"))
    assert route._redeemed(forged, binding(forged)) is False
    real = make_request(guard, token)
    assert route._redeemed(real, binding(real)) is True


def test_a_token_does_not_fit_a_re_priced_basket():
    guard = StrategyGuard()
    token = issue(guard, make_request(guard))
    order = real_orders()[0]
    repriced = [SimpleNamespace(**{**vars_of(order), "price": order.price + D("0.05")})]
    req = make_request(guard, token)
    assert route._redeemed(req, binding(req, orders=repriced)) is False


def test_a_token_does_not_fit_a_changed_loss():
    guard = StrategyGuard()
    token = issue(guard, make_request(guard))
    req = make_request(guard, token)
    assert route._redeemed(req, binding(req, rev=review("900000.00"))) is False


def test_a_token_does_not_fit_another_user_or_another_action():
    guard = StrategyGuard()
    token = issue(guard, make_request(guard))
    other = make_request(guard, token, user="user-2")
    assert route._redeemed(other, binding(other)) is False
    exit_req = make_request(guard, token, action="EXIT")
    assert route._redeemed(exit_req, binding(exit_req)) is False


def test_issuing_again_replaces_the_earlier_token():
    guard = StrategyGuard()
    first = issue(guard, make_request(guard))
    second = issue(guard, make_request(guard))
    assert first != second
    old = make_request(guard, first)
    assert route._redeemed(old, binding(old)) is False
    new = make_request(guard, second)
    assert route._redeemed(new, binding(new)) is True


def vars_of(order):
    return {f.name: getattr(order, f.name) for f in dataclasses.fields(order)}
