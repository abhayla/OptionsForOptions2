"""D-25 (ADR-326 (1), ADR-238 (6), ADR-294 (4)): "Take profit" (A-24, A-25) is refused when the whole trade closed at
the planned prices is a loss AFTER charges, as well as when it is a loss before charges; Exit (A-31) stays
offered. The one
build path (``priced_approach``: the approaches route, the Compare and the check's T-19 all call it) decides it, and the
paper place route asks the same function (offered and accepted agree).

Real case 23 Nov, strategy 162: P&L -223 after charges with Take profit offered, the same figures as Exit (debit 8,468);
case 143 of 13 Nov has the same shape (+61.75 before charges, -218.85 after charges)."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest
import t19_support as t
from ofo_app.routes import adjustment as adj
from ofo_app.routes.adjustment import as_of_market, priced_approach, take_profit_block

REASON = "Not in profit after charges: "


def _run(a: str, whole: D, paid: D, rates=t.RATES):
    tr, mk, spot = t.inputs(t.load("ADJ-10"))
    built0, _ = priced_approach("A-24", as_of_market(tr, mk), mk, spot, t.RATES, t.PREFS.approach, roll_basis=t.BASIS)
    open_part = sum(((c.exit - c.entry) * c.quantity * (1 if c.side == "BUY" else -1) for c in built0.closed), D(0))
    tr = as_of_market(replace(tr, booked=whole - open_part, paid_charges=paid), mk)
    return priced_approach(a, tr, mk, spot, rates, t.PREFS.approach, roll_basis=t.BASIS)


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
