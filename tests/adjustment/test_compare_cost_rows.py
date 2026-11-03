"""GC-MU A2 (ADR-230 (3)): the compare's "Cost as % of premium left" and "Change in max profit" rows and the cost
breakdown. Expected values are the scenario generator's engine-free ones (``expected.compare_cost``, exact fractions
from the published rates), so the engine and the generator check each other to the paisa."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal as D

import pytest
from ofo.adjustment import compare_cost_rows as ccr
from ofo.adjustment.approaches import APPROACH_IDS, build_approach
from ofo.adjustment.compare import ROWS, Column, Context, MarginRead, compare
from ofo.charges import ChargeRates
from ofo.charges.calculator import ChargeOrder, charges_for_orders
from ofo.charges.round_trip import charge_segment, to_paise_up
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import UNLIMITED, MultiExpiryError
from ofo.engine.strategy import Strategy
from ofo.engine.whole_trade import whole_trade_after
from ofo.errors.explanations import ADJUSTMENT_CHARGE_LABEL_TEXT, render_explanation
from test_approach_compare import CFG, PAID, PREFS, greeks_of, load, row
from test_approaches import inputs  # the position's expiry AND the next one (A-04, ADR-239 (2)), as the route

RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=date(2026, 10, 15), source_url="https://zerodha.com/charges")


def _strategy(legs, lot):
    return Strategy(tuple(Leg(Action(x.side), Instrument(x.type), x.strike, x.expiry, x.lots * lot, x.entry)
                          for x in legs)) if legs else None


def _exit_charges(legs, lot, segment):
    if not legs:
        return D(0)
    orders = [ChargeOrder(segment, "SELL" if x.side == "BUY" else "BUY", x.lots * lot, x.entry) for x in legs]
    return to_paise_up(charges_for_orders(orders, RATES).total)


def build(sid: str):
    """Columns priced with the real rate set the way the route prices them, plus the Before's whole-trade answer."""
    sc = load(sid)
    position, chain, spot = inputs(sc)
    segment = charge_segment(position.underlying)
    cols = []
    for a in APPROACH_IDS:
        built = build_approach(position, chain, spot, a, CFG)
        if built.refusal is not None:
            continue
        orders = [ChargeOrder(segment, t.action, t.quantity, t.price) for t in built.trades]
        adj = to_paise_up(charges_for_orders(orders, RATES).total) if orders else D(0)
        booked = D(sc["expected"]["approach_after"][a]["booked_pnl"])
        try:
            whole = whole_trade_after(_strategy(built.after, position.lot), booked_pnl=booked,
                                      paid_charges=PAID, adjustment_charges=adj,
                                      open_exit_charges=_exit_charges(built.after, position.lot, segment))
        except MultiExpiryError:  # A-04 spans two expiries: no After, the engine's own reason (as price_after)
            cols.append(Column(built, None, render_explanation("adjust_needs_one_expiry"), True,
                               MarginRead(D("100000")), adj))
            continue
        cols.append(Column(built, whole, None, True, MarginRead(D("100000"))))
    before = whole_trade_after(_strategy(position.legs, position.lot), booked_pnl=D(sc["position"]["booked_pnl"]),
                               paid_charges=PAID, adjustment_charges=D(0),
                               open_exit_charges=_exit_charges(position.legs, position.lot, segment))
    ctx = Context(position, spot, chain, RATES, False, MarginRead(D("100000")), greeks_of(sc),
                  sc["position"]["adjustments_used"], PREFS.compare)
    return sc, cols, ctx, before


def _hand(v):
    return None if v is None else D(v)


@pytest.mark.parametrize("sid", ["ADJ-02", "ADJ-13"])
def test_core_both_figures_and_breakdown_equal_the_generator_to_the_paisa(sid):
    """Core proof: cost as % of premium left, change in max profit and every charge component equal the generator's
    independently computed values for every built approach."""
    sc, cols, ctx, before = build(sid)
    cmp = compare(cols, ctx, before, True)
    hand = sc["expected"]["compare_cost"]
    assert set(hand) == {c.built.id for c in cols}
    pct, change, cost = row(cmp, "cost_pct"), row(cmp, "max_profit_change"), row(cmp, "cost")
    for a, h in hand.items():
        assert cost.values[a].value == D(h["cost"]), a
        assert pct.values[a].value == _hand(h["cost_pct"]), a
        assert change.values[a].value == _hand(h["max_profit_change"]), a
        got = cost.values[a].breakdown
        if h["charges_total"] == "0.00":
            assert got is None, a  # no trade: nothing to itemise
            continue
        lines = dict(got)
        assert {k: str(lines[k]) for k in ("brokerage", "stt", "gst", "stamp", "sebi")} == {
            k: h["charges"][k] for k in ("brokerage", "stt", "gst", "stamp", "sebi")}, a
        assert str(lines["exchange"]) == h["charges"]["exchange"], a
        assert str(lines[ccr.TOTAL_ID]) == h["charges_total"] and str(lines[ccr.SPREAD_ID]) == h["bid_ask"], a
        assert lines[ccr.TOTAL_ID] + lines[ccr.SPREAD_ID] == cost.values[a].value, a  # the lines add up to the cost row
        assert [k for k, _ in got] == [c for c, _ in ccr.COMPONENTS] + [ccr.TOTAL_ID, ccr.SPREAD_ID]


def test_rows_sit_after_cost_in_money_now_with_leaders_low_and_high():
    ids = [r[0] for r in ROWS]
    assert ids[ids.index("cost") + 1:ids.index("cost") + 3] == ["cost_pct", "max_profit_change"]
    by = {r[0]: r for r in ROWS}
    assert by["cost_pct"][1:] == ("money_now", "low") and by["max_profit_change"][1:] == ("money_now", "high")


def test_leaders_follow_the_hand_values_and_unavailable_cannot_lead():
    sc, cols, ctx, before = build("ADJ-02")
    cmp = compare(cols, ctx, before, True)
    hand = sc["expected"]["compare_cost"]
    pcts = {a: D(h["cost_pct"]) for a, h in hand.items() if h["cost_pct"] is not None}
    assert row(cmp, "cost_pct").leaders == tuple(a for a in hand if a in pcts and pcts[a] == min(pcts.values()))
    gains = {a: D(h["max_profit_change"]) for a, h in hand.items() if h["max_profit_change"] is not None}
    assert row(cmp, "max_profit_change").leaders == tuple(a for a in hand if a in gains
                                                          and gains[a] == max(gains.values()))
    assert row(cmp, "max_profit_change").values["A-04"].value is None  # two expiries: a dash, never a figure
    assert "A-31" not in row(cmp, "cost_pct").leaders


def test_state_premium_left_zero_is_a_dash_with_a_reason_not_a_division_error():
    _, cols, ctx, before = build("ADJ-02")
    cell = row(compare(cols, ctx, before, True), "cost_pct").values["A-31"]  # closes every leg: nothing left to earn
    assert (cell.text, cell.value, cell.rank) == ("-", None, None)
    assert cell.unavailable_reason == render_explanation("adjust_cmp_no_premium_left")
    assert ccr.cost_pct_of_premium_left(D("10"), None, D("-5"), None).value is None
    zero = ccr.cost_pct_of_premium_left(D("10"), None, D("0"), None)
    assert zero.reason == render_explanation("adjust_cmp_no_premium_left")


def test_state_premium_left_unknown_carries_that_reason():
    reason = render_explanation("adjust_cmp_no_price", leg="X")
    fig = ccr.cost_pct_of_premium_left(D("10"), None, None, reason)
    assert (fig.text, fig.value, fig.reason, fig.rank) == ("-", None, reason, None)
    _, cols, ctx, before = build("ADJ-02")
    chain = [replace(r, ltp=None, bid=None, ask=None) for r in ctx.chain]
    cell = row(compare(cols, replace(ctx, chain=chain), before, True), "cost_pct").values["A-36"]
    assert cell.value is None and cell.unavailable_reason is not None


def test_state_cost_unknown_charges_unknown_is_a_dash_with_the_charges_reason():
    _, cols, ctx, before = build("ADJ-02")
    cols = [replace(c, charges_known=False) for c in cols]
    cmp = compare(cols, ctx, before, True)
    cell = row(cmp, "cost_pct").values["A-01"]
    assert cell.value is None and cell.unavailable_reason == render_explanation("adjust_charges_unknown")
    unknown = render_explanation("adjust_charges_unknown")
    assert row(cmp, "max_profit_change").values["A-01"].unavailable_reason == unknown
    no_quote = render_explanation("adjust_cmp_no_bid_ask", leg="X")
    assert ccr.cost_pct_of_premium_left(None, no_quote, D("5"), None).reason == no_quote


def test_state_cost_unknown_no_bid_ask_is_a_dash_with_that_reason():
    _, cols, ctx, before = build("ADJ-02")
    chain = [replace(r, bid=None, ask=None) for r in ctx.chain]
    cell = row(compare(cols, replace(ctx, chain=chain), before, True), "cost_pct").values["A-01"]
    assert cell.value is None and "has no bid or no ask" in cell.unavailable_reason


def test_state_max_profit_unlimited_either_side_is_a_dash_with_a_reason():
    reason = render_explanation("adjust_cmp_max_profit_unlimited")
    assert ccr.max_profit_change(UNLIMITED, D("5"), None, True).reason == reason
    assert ccr.max_profit_change(D("5"), UNLIMITED, None, True).reason == reason
    fig = ccr.max_profit_change(UNLIMITED, UNLIMITED, None, True)
    assert (fig.text, fig.value, fig.rank) == ("-", None, None)


def test_state_before_not_worked_out_is_a_dash_with_a_reason():
    _, cols, ctx, _ = build("ADJ-02")
    for before, known in ((None, True), (None, False)):
        cell = row(compare(cols, ctx, before, known), "max_profit_change").values["A-01"]
        assert cell.value is None
        assert cell.unavailable_reason == render_explanation("adjust_cmp_before_max_profit_unknown")


def test_state_no_trades_costs_zero_percent_and_changes_nothing():
    sc, cols, ctx, before = build("ADJ-02")
    cmp = compare(cols, ctx, before, True)
    pct, change = row(cmp, "cost_pct").values["A-36"], row(cmp, "max_profit_change").values["A-36"]
    assert (pct.value, pct.text) == (D("0.00"), "0.00%")
    assert change.value == D("0.00") and row(cmp, "cost").values["A-36"].breakdown is None
    assert sc["expected"]["compare_cost"]["A-36"]["cost"] == "0.00"


def test_breakdown_is_absent_without_rates_and_labels_are_catalogue_words():
    _, cols, ctx, before = build("ADJ-02")
    cell = row(compare(cols, replace(ctx, rates=None), before, True), "cost").values["A-01"]
    assert cell.breakdown is None
    lines = ccr.breakdown_lines((("sebi", D("0.02")), ("gst", D("15.91"))))
    assert [x["label"] for x in lines] == ["SEBI turnover fee", "GST"] and lines[1]["text"] == "₹15.91"
    assert set(ADJUSTMENT_CHARGE_LABEL_TEXT) == {c for c, _ in ccr.COMPONENTS} | {ccr.TOTAL_ID, ccr.SPREAD_ID}
