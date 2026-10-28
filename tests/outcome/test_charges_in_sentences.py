"""REQ-034 AC-7 / ADR-082 (2) (W-075): the max-loss and max-profit sentences include the strategy's round-trip charges.

Core: the real 1-lot NIFTY iron condor of 2026-10-15 (SELL 23150 CE 53.30, BUY 23350 CE 17.30, SELL 22750 PE 65.15,
BUY 22550 PE 34.00, 65 units each, credit 67.15 x 65 = 4,364.75, max loss 8,635.25 before charges) gets round-trip
charges and the sentence "At most ₹<8,635.25 + charges> at expiry, including about ₹<charges> of charges and taxes."

Spec basis: ADR-082 "Every maximum-loss and maximum-profit sentence, and the expiry scenario values, include the
round-trip charges of the strategy at its planned prices (entry and exit), and the sentence says so"; W-075 decision
(a): round trip = each leg's entry order plus the OPPOSITE-side exit order of the same quantity at the same price.

The charges are hand-computed HERE from F-35's published rates (brokerage 20 per order; STT 0.15% on sell premium; NSE
0.03553%; SEBI 0.0001%; stamp 0.003% on buy premium; GST 18% on brokerage + SEBI + transaction), never read from the
calculator. Hand total for the 8 orders: premium 22,067.50 (11,033.75 each side) -> brokerage 160 + STT 16.550625 +
exchange 7.84058275 + SEBI 0.0220675 + stamp 0.3310125 + GST 30.215277045 = 214.959564795.
(ADR-082's "about 221.18" is twice Kite's 4 ENTRY rows, 110.5879, which puts STT on the exit buys too; the opposite-side
exits carry STT on the sold-back longs instead, so the exact figure is 214.96; shown as 214.95 since F-1:
parts rounded, total = their sum.) See the builder report.)
"""
import json
from datetime import date
from decimal import ROUND_HALF_UP
from decimal import Decimal as D
from pathlib import Path

import pytest
from ofo.charges import ChargeRates
from ofo.charges.round_trip import ChargesNotComputable, round_trip_charges
from ofo.engine.legs import Action, Instrument, Leg
from ofo.errors.explanations import render_explanation

ROOT = Path(__file__).resolve().parents[2]
KITE_ORDERS = ROOT / "docs" / "research" / "kite-proof-2026-10-07" / "rest-2026-10-15" / "charges_orders.json"
EXPIRY = date(2026, 10, 27)
Q = 65

RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=date(2026, 10, 15), source_url="https://zerodha.com/charges")

# (action, instrument, strike, price)
CONDOR = (
    (Action.SELL, Instrument.CE, "23150", "53.30"),
    (Action.BUY, Instrument.CE, "23350", "17.30"),
    (Action.SELL, Instrument.PE, "22750", "65.15"),
    (Action.BUY, Instrument.PE, "22550", "34.00"),
)
HAND_TOTAL = D("214.959564795")
HAND_PAISE = D("214.95")  # sum of the shown parts, each rounded half-up, GST on the rounded parts (F-1; was 214.96,
# the exact HAND_TOTAL rounded UP once, whose parts did not add up): the value the API carries
MAX_LOSS_BEFORE = D("8635.25")
MAX_PROFIT_BEFORE = D("4364.75")


def legs() -> tuple[Leg, ...]:
    return tuple(Leg(a, i, D(k), EXPIRY, Q, D(p)) for a, i, k, p in CONDOR)


def hand(side: str, price: D, qty: int = Q) -> dict:
    """One order from F-35's rates, written out (no calculator)."""
    premium = price * qty
    brokerage = D("20")
    stt = premium * D("0.0015") if side == "SELL" else D("0")
    txn = premium * D("0.0003553")
    sebi = premium * D("0.000001")
    stamp = premium * D("0.00003") if side == "BUY" else D("0")
    gst = (brokerage + sebi + txn) * D("0.18")
    return {"brokerage": brokerage, "stt": stt, "txn": txn, "sebi": sebi, "stamp": stamp, "gst": gst,
            "total": brokerage + stt + txn + sebi + stamp + gst}


def hand_round_trip(rows) -> D:
    total = D("0")
    for action, _i, _k, price in rows:
        entry = "BUY" if action is Action.BUY else "SELL"
        exit_ = "SELL" if entry == "BUY" else "BUY"
        total += hand(entry, D(price))["total"] + hand(exit_, D(price))["total"]
    return total


def hand_shown(orders) -> D:
    """F-1: the shown total of ``orders`` [(side, price)]: each component summed and rounded half-up to the paisa, GST =
    18% of the rounded brokerage + transaction + SEBI, rounded; total = sum of the rounded parts."""
    paisa = D("0.01")
    sums = {k: D("0") for k in ("brokerage", "stt", "txn", "sebi", "stamp")}
    for side, price in orders:
        h = hand(side, D(price))
        for k in sums:
            sums[k] += h[k]
    r = {k: v.quantize(paisa, rounding=ROUND_HALF_UP) for k, v in sums.items()}
    gst = ((r["brokerage"] + r["txn"] + r["sebi"]) * D("0.18")).quantize(paisa, rounding=ROUND_HALF_UP)
    return sum(r.values(), D("0")) + gst


def test_hand_computation_equals_the_literal_total():
    assert hand_round_trip(CONDOR) == HAND_TOTAL


def test_core_round_trip_charges_of_the_real_condor():
    assert round_trip_charges(legs(), "NIFTY", RATES) == HAND_PAISE


def test_entry_orders_match_kites_real_rows_except_stamp():
    rows = json.loads(KITE_ORDERS.read_text(encoding="utf-8"), parse_float=D)["reply"]["data"]
    assert len(rows) == KITE_ENTRY_ROWS
    for r in rows:
        h = hand(r["transaction_type"], r["price"], r["quantity"])
        c = r["charges"]
        for ours, theirs in ((h["stt"], c["transaction_tax"]), (h["txn"], c["exchange_turnover_charge"]),
                             (h["sebi"], c["sebi_turnover_charge"]), (h["gst"], c["gst"]["total"])):
            assert abs(ours - theirs) < D("0.0001")
        assert c["stamp_duty"] == 0 and abs(h["total"] - h["stamp"] - c["total"]) < D("0.0001")


def test_the_core_sentences():
    loss = MAX_LOSS_BEFORE + HAND_PAISE
    profit = MAX_PROFIT_BEFORE - HAND_PAISE
    assert (render_explanation("summary_lose_at_most_with_charges", amount=loss, charges=HAND_PAISE)
            == "At most ₹8,850.20 at expiry, including about ₹214.95 of charges and taxes.")
    assert (render_explanation("summary_make_at_most_with_charges", amount=profit, charges=HAND_PAISE)
            == "At most ₹4,149.80 at expiry, including about ₹214.95 of charges and taxes.")


# --- guards: each is red under its named mutation -------------------------------------------------------------------

def test_guard_each_leg_is_entry_plus_opposite_exit_at_the_same_price():
    one_leg = round_trip_charges(legs()[:1], "NIFTY", RATES)  # mutation: exit at another price / same side -> red
    assert one_leg == hand_shown([("SELL", "53.30"), ("BUY", "53.30")])
    one_buy = round_trip_charges(legs()[1:2], "NIFTY", RATES)
    assert one_buy == hand_shown([("BUY", "17.30"), ("SELL", "17.30")])


def test_guard_entries_only_is_half_a_round_trip():
    entries_only = sum(hand("BUY" if a is Action.BUY else "SELL", D(p))["total"] for a, _i, _k, p in CONDOR)
    assert round_trip_charges(legs(), "NIFTY", RATES) > entries_only * D("1.9")  # mutation: entries only -> red


def test_guard_sensex_uses_the_bse_rate_futures_zero_price_and_unknown_index_are_not_computable():
    assert round_trip_charges(legs(), "SENSEX", RATES) < HAND_PAISE  # 0.0325% < 0.03553% on the same premium
    fut = Leg(Action.BUY, Instrument.FUT, None, EXPIRY, Q, D("23000"))
    with pytest.raises(ChargesNotComputable):
        round_trip_charges((fut,), "NIFTY", RATES)
    with pytest.raises(ChargesNotComputable):
        round_trip_charges(legs(), "MIDCPNIFTY", RATES)
    with pytest.raises(ChargesNotComputable):
        round_trip_charges((Leg(Action.BUY, Instrument.CE, D("23000"), EXPIRY, Q, D("0")),), "NIFTY", RATES)


KITE_ENTRY_ROWS = 4
MIN_LEVELS = 10

# --- the engine's Summary on the real W-063 replay frames (a NIFTY 13-Oct condor, 65 units a leg) ------------------
import datetime  # noqa: E402

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402
from ofo.charges import round_trip as rt  # noqa: E402
from ofo.errors.explanations import join_explanations  # noqa: E402
from ofo.marketdata.kite_provider import IST  # noqa: E402
from ofo.outcome import OutcomeState, PlannedLeg, StrategyDefinition, build_outcome, read_snapshot  # noqa: E402
from ofo.outcome.service import exercise_stt_line  # noqa: E402
from ofo.scenario.views import View  # noqa: E402

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
REPLAY_CONDOR = (
    ("NSE_FO:44624", Action.SELL), ("NSE_FO:44632", Action.BUY), ("NSE_FO:44604", Action.SELL),
    ("NSE_FO:44595", Action.BUY),
)


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def outcome_of(provider, rates):
    d = StrategyDefinition("NIFTY", tuple(PlannedLeg(i, a, 1, provider.book.get(i, VALUATION).ltp, VALUATION)
                                          for i, a in REPLAY_CONDOR))
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, D("0.065"))
    return d, build_outcome(d, snap, VALUATION, rates=rates)


def test_summary_includes_the_hand_computed_round_trip(replayed):
    d, out = outcome_of(replayed, RATES)
    assert out.state is OutcomeState.COMPUTED, out.reason
    rows = [("SELL" if p.action is Action.SELL else "BUY", p.planned_entry) for p in d.legs]
    orders = []
    for side, price in rows:
        orders += [(side, price), ("SELL" if side == "BUY" else "BUY", price)]
    charges = hand_shown(orders)  # F-1: the API carries the sum of the shown parts
    s = out.summary
    assert s.charges == charges and not s.charges_unavailable
    assert s.max_loss == D("8245.25") + charges  # charges ADDED to the loss (mutation: subtracted -> red)
    assert s.max_profit == D("4754.75") - charges  # charges SUBTRACTED from the profit (mutation: added -> red)
    lose = render_explanation("summary_lose_at_most_with_charges", amount=s.max_loss, charges=charges)
    assert s.what_can_i_lose == lose + " " + EXERCISE_STT_LINE  # the condor holds bought options (round 4)
    make = render_explanation("summary_make_at_most_with_charges", amount=s.max_profit, charges=charges)
    assert s.what_can_i_make == make
    assert "including about ₹" in s.what_can_i_lose and "before charges" not in s.what_can_i_lose


PAISE_EXPONENT = D("0.01").as_tuple().exponent  # test-local: the exponent of a two-decimal paise string


def _is_paise(value) -> bool:
    return value.as_tuple().exponent == PAISE_EXPONENT


def test_every_charges_derived_decimal_has_two_places(replayed):
    """Class: no money value derived from the unrounded charges total may leak extra decimals into the API."""
    _, out = outcome_of(replayed, RATES)
    s = out.summary
    money = [s.charges, s.max_profit, s.max_loss, *out.scenario.totals, out.scenario.charges,
             *(p[1] for p in out.payoff_points)]
    assert len(money) > len(out.scenario.totals) and all(_is_paise(m) for m in money), money
    for row in out.table.rows:
        if row.row_id == "TOTAL":
            for cell in row.cells.values():
                if cell.kind.value == "money" and isinstance(cell.value, D):
                    assert _is_paise(cell.value), (row.row_id, cell.value)


def test_guard_breakevens_and_zero_columns_do_not_move_with_charges(replayed):
    _, with_rates = outcome_of(replayed, RATES)
    _, without = outcome_of(replayed, None)
    a, b = with_rates.summary, without.summary
    assert (a.breakevens, a.lower_be, a.upper_be, a.risk_boundaries) == (b.breakevens, b.lower_be, b.upper_be,
                                                                          b.risk_boundaries)
    assert with_rates.level_set.levels == without.level_set.levels


def test_guard_no_rates_keeps_the_old_phrase_flags_it_and_never_shows_zero_charges(replayed):
    _, out = outcome_of(replayed, None)
    s = out.summary
    assert s.charges is None and s.charges_unavailable
    assert s.what_can_i_lose == "At most ₹8,245.25 at expiry, before charges and taxes."
    assert s.what_can_i_make == "At most ₹4,754.75 at expiry, before charges and taxes."
    assert "₹0.00 of charges" not in s.what_can_i_lose


def test_guard_charges_that_wipe_out_the_profit_read_cannot_make_money(replayed):
    huge = ChargeRates(brokerage_per_order=D("5000"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
                       transaction_rates=RATES.transaction_rates, sebi_rate=D("0.000001"),
                       stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=date(2026, 10, 15),
                       source_url="https://zerodha.com/charges")
    _, out = outcome_of(replayed, huge)
    assert out.summary.what_can_i_make == "This strategy cannot make money at expiry."


# --- round 2: a leg the rate table cannot price falls back to ADR-071's phrase and never shows zero charges ----------

def _assert_old_phrase_and_flag(out, provider):
    s = out.summary
    assert out.state is OutcomeState.COMPUTED, out.reason
    assert s.charges is None and s.charges_unavailable  # mutant `charges = Decimal(0)` -> charges == 0, flag False: red
    assert s.what_can_i_lose == "At most ₹8,245.25 at expiry, before charges and taxes."
    assert s.what_can_i_make == "At most ₹4,754.75 at expiry, before charges and taxes."
    assert "about ₹" not in s.what_can_i_lose + s.what_can_i_make
    assert out.scenario.charges is None  # the breakdown figure is absent: scenario_values got no rates
    assert out.scenario.totals == outcome_of(provider, None)[1].scenario.totals  # same curve as with no rates at all


def test_guard_an_index_with_no_exchange_segment_falls_back(replayed, monkeypatch):
    monkeypatch.delitem(rt.SEGMENT_BY_UNDERLYING, "NIFTY")
    _, out = outcome_of(replayed, RATES)
    _assert_old_phrase_and_flag(out, replayed)


def test_guard_a_zero_planned_price_leg_falls_back(replayed):
    d = StrategyDefinition("NIFTY", tuple(PlannedLeg(i, a, 1, D("0") if n == 1 else replayed.book.get(i, VALUATION).ltp,
                                                     VALUATION) for n, (i, a) in enumerate(REPLAY_CONDOR)))
    snap = read_snapshot(replayed, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, D("0.065"))
    out = build_outcome(d, snap, VALUATION, rates=RATES)
    assert out.state is OutcomeState.COMPUTED, out.reason
    assert out.summary.charges is None and out.summary.charges_unavailable
    assert "about ₹" not in out.summary.what_can_i_lose + out.summary.what_can_i_make
    assert out.scenario.charges is None


# --- ADR-167: the table has no charges row; the legs sum to TOTAL in every column, before charges --------------------

CHARGES_ROW = "CHARGES"


def _rows(out):
    return {r.row_id: r for r in out.table.rows}


def test_table_has_no_charges_row_and_the_legs_sum_to_total_in_every_column(replayed):
    _, out = outcome_of(replayed, RATES)
    rows = _rows(out)
    assert [r.row_id for r in out.table.rows] == ["1", "2", "3", "4", "TOTAL"]  # mutant: re-added row -> red
    levels = out.level_set.levels
    assert len(levels) >= MIN_LEVELS
    for level in levels:
        legs_sum = sum((rows[str(i)].cell(level).value for i in range(1, 5)), D("0"))
        assert legs_sum == rows["TOTAL"].cell(level).value, level  # exact; mutant: `- charges` in views.py -> red


def test_guard_the_total_at_each_breakeven_column_is_zero_before_charges(replayed):
    _, out = outcome_of(replayed, RATES)
    total = _rows(out)["TOTAL"]
    assert out.summary.breakevens
    for be in out.summary.breakevens:
        assert total.cell(be).value == 0, be  # today (before the fix) this was minus the charges


def test_guard_the_curve_and_totals_equal_the_no_rates_answer_while_max_loss_adds_charges(replayed):
    _, with_rates = outcome_of(replayed, RATES)
    _, without = outcome_of(replayed, None)
    assert with_rates.scenario.totals == without.scenario.totals
    assert with_rates.payoff_points == without.payoff_points
    s = with_rates.summary
    assert s.max_loss == without.summary.max_loss + s.charges  # the sentence figure is not read off the curve
    assert s.max_profit == without.summary.max_profit - s.charges
    assert min(with_rates.scenario.totals) == -without.summary.max_loss


def test_table_has_no_charges_row_without_rates_and_in_estimated_now(replayed):
    _, none_out = outcome_of(replayed, None)
    assert CHARGES_ROW not in _rows(none_out)
    d = StrategyDefinition("NIFTY", tuple(PlannedLeg(i, a, 1, replayed.book.get(i, VALUATION).ltp, VALUATION)
                                          for i, a in REPLAY_CONDOR))
    snap = read_snapshot(replayed, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, D("0.065"))
    est = build_outcome(d, snap, VALUATION, rates=RATES, view=View.ESTIMATED_NOW)
    assert CHARGES_ROW not in _rows(est)


# --- round 4 (owner OQ-4 a): one line under the max-loss sentence when the strategy holds a bought option --------

EXERCISE_STT_LINE = (
    "Holding a bought option to expiry in the money adds STT on its value; squaring off before expiry avoids it.")


def _summary_of_legs(provider, picks, rates=RATES):
    d = StrategyDefinition("NIFTY", tuple(PlannedLeg(i, a, 1, provider.book.get(i, VALUATION).ltp, VALUATION)
                                          for i, a in picks))
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, D("0.065"))
    out = build_outcome(d, snap, VALUATION, rates=rates)
    assert out.state is OutcomeState.COMPUTED, out.reason
    return out.summary


def test_the_real_15_oct_condor_sentence_then_the_line():
    sentence = render_explanation("summary_lose_at_most_with_charges", amount=MAX_LOSS_BEFORE + HAND_PAISE,
                                  charges=HAND_PAISE)
    line = exercise_stt_line(legs())
    assert line == EXERCISE_STT_LINE
    assert join_explanations([sentence, line], " ") == (
        f"At most ₹8,850.20 at expiry, including about ₹214.95 of charges and taxes. {EXERCISE_STT_LINE}")


def test_the_replay_condor_max_loss_sentence_is_followed_by_the_line(replayed):
    s = outcome_of(replayed, RATES)[1].summary
    first = render_explanation("summary_lose_at_most_with_charges", amount=s.max_loss, charges=s.charges)
    assert s.what_can_i_lose == f"{first} {EXERCISE_STT_LINE}"
    assert "including about ₹" in first and first.startswith("At most ₹")  # the existing sentence is unchanged
    assert s.what_can_i_make == render_explanation("summary_make_at_most_with_charges", amount=s.max_profit,
                                                   charges=s.charges)  # the profit sentence gets no line
    assert "you should" not in s.what_can_i_lose.lower()


def test_guard_no_bought_option_no_line(replayed):
    s = _summary_of_legs(replayed, (("NSE_FO:44604", Action.SELL),))  # one short put: loss is limited, nothing bought
    assert not s.max_loss_unlimited and s.charges is not None
    assert s.what_can_i_lose == render_explanation("summary_lose_at_most_with_charges", amount=s.max_loss,
                                                   charges=s.charges)
    assert "STT" not in s.what_can_i_lose


def test_guard_unlimited_max_loss_has_no_line_even_with_a_bought_option(replayed):
    s = _summary_of_legs(replayed, (("NSE_FO:44624", Action.SELL), ("NSE_FO:44595", Action.BUY)))
    assert s.max_loss_unlimited
    assert "STT" not in s.what_can_i_lose
