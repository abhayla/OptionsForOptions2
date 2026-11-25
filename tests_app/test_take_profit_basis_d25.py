"""D-25 (ADR-238 (6), ADR-294 (4), ADR-320 point 4): the offer of Take profit (A-24, A-25) states its basis. The profit
test is BEFORE charges; the offer carries that figure and the whole-trade result AFTER charges beside it, each named,
so a
trader never reads an offered Take profit at a result of -223 as if it were a profit.

Real case 23 Nov, strategy 162: Take profit offered with the same numbers as Exit while the page showed P&L -223
(case 143 of 13 Nov is the same shape: +61.75 before charges, -218.85 after charges)."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest
import t19_support as t
from ofo_app.api_models import AdjustApproachOut
from ofo_app.routes import adjustment as adj
from ofo_app.routes.adjustment import as_of_market, priced_approach, take_profit_block


def _run(a: str, whole: D, paid: D, rates=t.RATES):
    tr, mk, spot = t.inputs(t.load("ADJ-10"))
    built0, _ = priced_approach("A-24", as_of_market(tr, mk), mk, spot, t.RATES, t.PREFS.approach, roll_basis=t.BASIS)
    open_part = sum(((c.exit - c.entry) * c.quantity * (1 if c.side == "BUY" else -1) for c in built0.closed), D(0))
    tr = as_of_market(replace(tr, booked=whole - open_part, paid_charges=paid), mk)
    return priced_approach(a, tr, mk, spot, rates, t.PREFS.approach, roll_basis=t.BASIS)


@pytest.mark.parametrize("a", ["A-24", "A-25"])
def test_profit_before_charges_but_loss_after_is_no_longer_offered(a):
    """ADR-326 (1): the case this test once pinned as an offer (+61.75 before charges, a loss after) is now refused
    (tests_app/test_take_profit_after_charges_f1.py states the reason); no offer block exists beside the loss."""
    built, priced = _run(a, D("61.75"), D("403.45"))
    assert built.refusal is not None and priced is None and take_profit_block(built, priced) is None


def test_offer_in_profit_both_ways_carries_both_positive_figures():
    built, priced = _run("A-24", D("5000"), D("403.45"))
    block = take_profit_block(built, priced)
    assert block["before_charges"] == D("5000") and block["after_charges"] > 0


def test_refused_take_profit_and_other_approaches_carry_no_block():
    built, priced = _run("A-24", D("-32.50"), D("403.45"))
    assert built.refusal is not None and take_profit_block(built, priced) is None
    built, priced = _run("A-31", D("61.75"), D("403.45"))
    assert take_profit_block(built, priced) is None


def test_the_reply_model_has_the_block():
    assert "take_profit" in AdjustApproachOut.model_fields


# ---- ADR-326 (1): refused at an after-charges loss (was tests_app/test_take_profit_after_charges_f1.py) ----
REASON = "Not in profit after charges: "


@pytest.mark.parametrize("a", ["A-24", "A-25"])
def test_profit_before_charges_but_loss_after_is_refused_with_the_after_figure(a):
    built, priced = _run(a, D("61.75"), D("403.45"))  # +61.75 before charges, a loss after them
    assert priced is None and built.refusal is not None and built.refusal_message is not None
    assert built.refusal.startswith(REASON)
    assert built.trades == () and built.whole_before_charges is None
    assert take_profit_block(built, priced) is None  # never an offer block beside an after-charges loss


def test_the_refusal_names_the_after_charges_figure():
    built, _ = _run("A-24", D("61.75"), D("403.45"))  # A-24 closes what A-31 closes: the same charges
    _, offered = _run("A-31", D("61.75"), D("403.45"))
    after = D("61.75") - offered.after.total_charges
    assert after < 0 and f"{abs(after):,.2f}" in built.refusal


def test_exit_stays_offered_at_the_same_numbers():
    built, priced = _run("A-31", D("61.75"), D("403.45"))
    assert built.refusal is None and priced is not None and built.trades


@pytest.mark.parametrize("a", ["A-24", "A-25"])
def test_profit_before_and_after_charges_is_offered_with_both_figures(a):
    built, priced = _run(a, D("5000"), D("403.45"))
    block = take_profit_block(built, priced)
    assert built.refusal is None and block["before_charges"] == D("5000") and block["after_charges"] > 0


@pytest.mark.parametrize("a", ["A-24", "A-25"])
def test_loss_before_charges_is_refused_as_before(a):
    built, priced = _run(a, D("-32.50"), D("403.45"))
    assert priced is None and built.refusal is not None and not built.refusal.startswith(REASON)
    assert "not in profit" in built.refusal


@pytest.mark.parametrize("a", ["A-24", "A-25"])
def test_charges_unreadable_is_refused_with_its_own_reason(a):
    built, priced = _run(a, D("5000"), D("403.45"), rates=None)  # no charge rates: the after-charges result is unknown
    assert priced is None and built.refusal is not None
    assert not built.refusal.startswith(REASON) and "charges" in built.refusal


@pytest.mark.parametrize("a", ["A-24", "A-25"])
async def test_the_place_route_refuses_a_take_profit_basket_at_an_after_charges_loss(a, monkeypatch):
    from ofo_app.strategy_refused import StrategyRefused  # noqa: PLC0415
    tr, mk, spot = t.inputs(t.load("ADJ-10"))
    built0, _ = priced_approach("A-24", as_of_market(tr, mk), mk, spot, t.RATES, t.PREFS.approach, roll_basis=t.BASIS)
    open_part = sum(((c.exit - c.entry) * c.quantity * (1 if c.side == "BUY" else -1) for c in built0.closed), D(0))
    tr = replace(tr, booked=D("61.75") - open_part, paid_charges=D("403.45"))

    async def tracked_reader(_sid, _rates):
        return tr

    async def market_reader(_tracked, _ctx):
        return mk
    monkeypatch.setattr(adj, "get_market_reader", lambda: market_reader)

    async def rest(_u):
        return None
    monkeypatch.setattr(adj, "get_rest_spot_reader", lambda: rest)
    monkeypatch.setattr(adj, "judge_spot", lambda *_a: type("S", (), {"available": True, "value": spot})())
    with pytest.raises(StrategyRefused) as err:
        await adj.refuse_take_profit_at_loss(a, 1, tracked_reader, None, t.RATES, t.PREFS, t.BASIS)
    assert REASON in str(err.value.message.what_happened)
    # Exit-all is never asked about here: another id passes through
    await adj.refuse_take_profit_at_loss("A-31", 1, tracked_reader, None, t.RATES, t.PREFS, t.BASIS)


def test_the_paper_basket_body_takes_only_a_take_profit_approach_id():
    from ofo_app.routes.paper import PaperOrdersIn  # noqa: PLC0415
    order = {"contract_id": 1, "side": "BUY", "quantity": 65, "price": "1.00", "kind": "exit"}
    assert PaperOrdersIn.model_validate({"orders": [order], "approach_id": "A-24"}).approach_id == "A-24"
    assert PaperOrdersIn.model_validate({"orders": [order]}).approach_id is None
    with pytest.raises(ValueError, match="approach_id"):
        PaperOrdersIn.model_validate({"orders": [order], "approach_id": "A-31"})


@pytest.mark.parametrize("a", ["A-24", "A-25"])
async def test_the_paper_place_helper_refuses_with_the_sentence_and_passes_an_ordinary_basket(a, monkeypatch):
    """The paper route's own helper (what ``place_paper_orders`` calls when ``approach_id`` is sent): refused at an
    after-charges loss with the sentence; no approach id (an ordinary basket) is not asked at all."""
    from ofo.settings import defaults as registry_defaults  # noqa: PLC0415
    from ofo_app import user_preferences_store as ups  # noqa: PLC0415
    from ofo_app.routes import paper  # noqa: PLC0415
    from ofo_app.strategy_refused import StrategyRefused  # noqa: PLC0415
    tr, mk, spot = t.inputs(t.load("ADJ-10"))
    built0, _ = priced_approach("A-24", as_of_market(tr, mk), mk, spot, t.RATES, t.PREFS.approach, roll_basis=t.BASIS)
    open_part = sum(((c.exit - c.entry) * c.quantity * (1 if c.side == "BUY" else -1) for c in built0.closed), D(0))
    tr = replace(tr, booked=D("61.75") - open_part, paid_charges=D("403.45"))

    async def tracked_reader(_sid, _rates):
        return tr

    async def market_reader(_tracked, _ctx):
        return mk

    async def rest(_u):
        return None

    async def values(_db, _user):
        return registry_defaults()
    monkeypatch.setattr(adj, "get_market_reader", lambda: market_reader)
    monkeypatch.setattr(adj, "get_rest_spot_reader", lambda: rest)
    monkeypatch.setattr(adj, "judge_spot", lambda *_a: type("S", (), {"available": True, "value": spot})())
    monkeypatch.setattr(ups, "values_for", values)
    with pytest.raises(StrategyRefused) as err:
        await paper._refuse_take_profit_at_loss(None, "owner", 1, a, None, t.RATES, tracked_reader)
    assert err.value.message.what_happened.startswith(REASON)


def test_a_take_profit_on_a_two_expiry_trade_has_its_own_reason(monkeypatch):
    """A-25 leaves legs of two expiries: ``whole_trade_after`` cannot value them, charges ARE known. Refused (fail
    closed) with a reason that says so, not 'charges cannot be worked out'."""
    from ofo.engine.metrics import MultiExpiryError  # noqa: PLC0415

    real = adj.whole_trade_after

    def two(open_legs, **kw):
        if open_legs is not None:  # A-24 leaves nothing open; A-25 leaves legs
            raise MultiExpiryError("two expiries")
        return real(open_legs, **kw)
    monkeypatch.setattr(adj, "whole_trade_after", two)
    built, priced = _run("A-25", D("5000"), D("403.45"))
    assert priced is None and built.refusal is not None
    assert "two expiries" in built.refusal and "charges" in built.refusal
    assert built.refusal_message.what_happened != adj.render("adjust_take_profit_charges_unknown").what_happened
