"""REQ-081 (W-154): the Builder money figures (ofo.outcome.money) on the real 2026-10-15 condor and the AC-3 example.

Core: net premium Get 4364.75 (67.15 per unit), max profit 4149.79 / max loss 8850.21 with charges 214.96, Reward/Risk
0.47 and Risk/Reward 2.13 on the recorded condor of tests/outcome/test_charges_in_sentences.py.
Proof: test_core_figures_of_the_real_condor below; the expected numbers are the spec's (REQ-081 AC-1, AC-4).
"""
import datetime
import sys
from dataclasses import dataclass
from decimal import Decimal as D
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from ofo.charges.round_trip import round_trip_charges
from ofo.engine import Strategy, strategy_metrics
from ofo.engine.legs import Action, Instrument, Leg
from ofo.errors.explanations import EXPLANATIONS
from ofo.outcome import money
from ofo.table import ColumnId
from test_charges_in_sentences import (
    EXPIRY,
    HAND_PAISE,
    MAX_LOSS_BEFORE,
    MAX_PROFIT_BEFORE,
    RATES,
    legs,
    outcome_of,
)

Q = 65
FUNDS = D("50000")
CHECKED_AT = datetime.datetime(2026, 10, 26, 10, 36, tzinfo=datetime.UTC)


@dataclass
class FakeMargin:
    state: str = "CHECKED"
    available: object = FUNDS
    checked_at: object = CHECKED_AT


def leg(action, kind, strike, price, ltp=None, qty=Q, expiry=EXPIRY):  # noqa: PLR0913
    return Leg(action, kind, None if kind is Instrument.FUT else D(strike), expiry, qty, D(price),
               None if ltp is None else D(ltp))


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def test_core_figures_of_the_real_condor():
    net = money.net_premium(legs())
    assert (net.amount, net.side, net.per_unit, net.text) == (D("4364.75"), "get", D("67.15"), "Get ₹4,364.75")
    charges = round_trip_charges(legs(), "NIFTY", RATES)
    assert charges == HAND_PAISE
    m = strategy_metrics(Strategy(legs()))
    assert (m.max_profit, m.max_loss) == (MAX_PROFIT_BEFORE, MAX_LOSS_BEFORE)
    rr = money.reward_risk(m.max_profit - charges, m.max_loss + charges)
    assert (rr.reward_risk, rr.risk_reward, rr.reason) == (D("0.47"), D("2.13"), None)  # 4149.79/8850.21, inverse


# --- net premium (attack 1) -------------------------------------------------------------------------------------

def test_debit_is_pay_with_per_unit_and_zero_is_neither():
    debit = (leg(Action.BUY, Instrument.CE, "23000", "100.00"), leg(Action.SELL, Instrument.CE, "23200", "48.50"))
    n = money.net_premium(debit)
    assert (n.amount, n.side, n.per_unit, n.text) == (D("3347.50"), "pay", D("51.50"), "Pay ₹3,347.50")
    flat = (leg(Action.BUY, Instrument.CE, "23000", "50.00"), leg(Action.SELL, Instrument.CE, "23200", "50.00"))
    z = money.net_premium(flat)
    assert (z.amount, z.side, z.reason) == (D("0.00"), None, None)


def test_different_quantities_have_a_total_but_no_per_unit():
    sell = leg(Action.SELL, Instrument.CE, "23000", "100.00", qty=65)  # 6500 in
    buy = leg(Action.BUY, Instrument.CE, "23200", "40.00", qty=130)  # 5200 out
    n = money.net_premium((sell, buy))
    assert (n.amount, n.side, n.per_unit) == (D("1300.00"), "get", None)


def test_a_futures_leg_shows_the_reason_and_no_amount():
    n = money.net_premium((leg(Action.BUY, Instrument.FUT, None, "23000"), *legs()[:1]))
    assert (n.amount, n.side, n.per_unit, n.text) == (None, None, None, None)
    assert n.reason == "premium and futures value cannot be added"


def test_a_leg_without_a_planned_price_gives_no_partial_sum():
    @dataclass
    class Unpriced:
        action: Action = Action.BUY
        instrument: Instrument = Instrument.CE
        entry_price: object = None
        quantity: int = Q

    n = money.net_premium((*legs(), Unpriced()))
    assert n.amount is None and n.reason == "a planned price is missing for at least one leg"
    assert money.net_premium(()) is None  # no legs: no block


def test_net_premium_rule_is_the_tables_total_entry_value(replayed):
    _d, out = outcome_of(replayed, RATES)
    cell = out.table.rows[-1].cells[ColumnId.ENTRY_VALUE]
    engine = tuple(Leg(x.action, x.instrument, x.strike, x.expiry, x.quantity, x.planned_entry) for x in out.legs)
    n = money.net_premium(engine)
    assert (cell.value, {"get": "Cr", "pay": "Dr"}[n.side]) == (n.amount, cell.side)
    assert out.summary.net_premium == n


# --- intrinsic and time value (attack 5) ------------------------------------------------------------------------

def test_ac3_bought_call_intrinsic_and_time():
    v = money.time_and_intrinsic((leg(Action.BUY, Instrument.CE, "22900", "150.00", ltp="150.00"),), D("22976.85"))
    label = "value of the options, not P&L"
    assert (v.intrinsic, v.time, v.label, v.reason) == (D("4995.25"), D("4754.75"), label, None)


def test_a_sold_leg_flips_the_sign_and_a_put_uses_strike_minus_spot():
    sold_put = leg(Action.SELL, Instrument.PE, "23000", "90.00", ltp="90.00")
    v = money.time_and_intrinsic((sold_put,), D("22950"))  # intrinsic 50 per unit, time 40
    assert (v.intrinsic, v.time) == (D("-3250.00"), D("-2600.00"))


def test_a_leg_with_no_ltp_or_no_spot_makes_both_absent_with_the_reason():
    ltp_less = leg(Action.BUY, Instrument.CE, "22900", "150.00")
    for given, spot in (((ltp_less,), D("22976.85")), ((leg(Action.BUY, Instrument.CE, "22900", "1", ltp="1"),), None)):
        v = money.time_and_intrinsic(given, spot)
        assert (v.intrinsic, v.time, v.label) == (None, None, None)
        assert v.reason == "a live price is missing for at least one leg or for the index"


def test_summary_of_the_real_replay_carries_the_split(replayed):
    _d, out = outcome_of(replayed, RATES)
    s = out.summary
    assert s.value_label == "value of the options, not P&L" and s.value_reason is None
    assert s.intrinsic_value is not None and s.time_value is not None
    assert out.charges_breakdown.total == s.charges


# --- Reward/Risk (attack 2) -------------------------------------------------------------------------------------

@pytest.mark.parametrize(("profit", "loss", "reason"), [
    (None, D("100"), "No fixed maximum"), (D("100"), None, "No fixed maximum"),
    (D("100"), D("0"), "max loss is 0"), (D("-5"), D("100"), "This strategy cannot make money at expiry."),
])
def test_ratio_is_absent_with_a_reason(profit, loss, reason):
    rr = money.reward_risk(profit, loss)
    assert (rr.reward_risk, rr.risk_reward, rr.reason) == (None, None, reason)


def test_two_expiries_have_no_worst_case_and_never_raise():
    other = datetime.date(2026, 11, 24)
    near = leg(Action.BUY, Instrument.CE, "23000", "100")
    far = leg(Action.SELL, Instrument.CE, "23000", "90", expiry=other)
    two = Strategy((near, far))
    assert not two.is_single_expiry
    rr = money.reward_risk(D("1"), D("1"), single_expiry=two.is_single_expiry)
    assert rr.reason == "no worst case for legs on different expiries" and rr.reward_risk is None


def test_ratio_rounds_half_even_to_two_places():
    assert money.reward_risk(D("1"), D("8")).reward_risk == D("0.12")  # 0.125 -> 0.12
    assert money.reward_risk(D("3"), D("8")).reward_risk == D("0.38")  # 0.375 -> 0.38


# --- funds percentages (attack 3) -------------------------------------------------------------------------------

@dataclass(frozen=True)
class MiniSummary:
    max_profit: object
    max_loss: object
    funds_share: object = None


def summary_of(profit, loss):
    return MiniSummary(profit, loss)


def test_adr164_example_percentages():
    f = money.funds_share(D("4500"), D("9222"), FakeMargin())
    assert (f.max_profit_percent, f.max_loss_percent) == (D("9"), D("18"))
    assert (f.max_profit_text, f.max_loss_text) == ("9% of funds", "18% of funds")
    assert (f.funds, f.read_at) == (FUNDS, CHECKED_AT)


@pytest.mark.parametrize("margin", [
    FakeMargin(state="NOT_AVAILABLE_YET"), FakeMargin(state="UNREADABLE"), FakeMargin(state="NO_BASKET"),
    FakeMargin(available=D("0")), FakeMargin(available=D("-5")), FakeMargin(available="50000"),
    FakeMargin(available=D("NaN")), FakeMargin(available=None), FakeMargin(checked_at=None),
])
def test_no_percentage_unless_checked_with_positive_decimal_funds(margin):
    assert money.funds_share(D("4500"), D("9222"), margin) is None
    summary = summary_of(D("4500"), D("9222"))
    assert money.with_funds(summary, margin) is summary  # the rupee figures stay, nothing added


def test_unlimited_side_has_no_percentage_and_small_ones_say_less_than_one():
    f = money.funds_share(None, D("100"), FakeMargin())
    assert (f.max_profit_percent, f.max_profit_text) == (None, None) and f.max_loss_text == "less than 1% of funds"
    assert money.funds_share(D("0"), D("500"), FakeMargin()).max_profit_text == "0% of funds"
    assert money.funds_share(D("-1"), D("500"), FakeMargin()).max_profit_text is None


def test_with_funds_sets_the_share_on_a_summary():
    out = money.with_funds(summary_of(D("4500"), D("9222")), FakeMargin())
    assert out.funds_share.max_loss_percent == D("18")


def test_catalogue_wording_has_none_of_the_advice_words():
    texts = [t.text.lower() for tid, t in EXPLANATIONS.items() if tid.startswith("money_")]
    assert texts and not [w for t in texts for w in ("return", "gain", "expected", "promise") if w in t]
