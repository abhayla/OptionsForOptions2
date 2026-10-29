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
from ofo.outcome.serialize import outcome_to_dict
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
FUNDS = D("50000")  # available funds: never the percent basis since ADR-207 (8)
NEEDED = D("61163")  # F-70: strategy 63's margin needed (Zerodha's basket figure)
CHECKED_AT = datetime.datetime(2026, 10, 26, 10, 36, tzinfo=datetime.UTC)


@dataclass
class FakeMargin:
    state: str = "CHECKED"
    available: object = FUNDS
    needed: object = NEEDED
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


def test_f70_strategy_63_percentages_are_of_the_margin_needed():
    # REQ-081 AC-9 (ADR-207 (8)): max profit 4,274 and max loss 2,226 with margin needed 61,163 -> 7.0% and 3.6%
    # (of the 50,000 available funds they would read 8.5% and 4.5%: the basis is the margin needed, never funds)
    f = money.funds_share(D("4274"), D("2226"), FakeMargin())
    assert (f.max_profit_percent, f.max_loss_percent) == (D("7.0"), D("3.6"))
    assert (f.max_profit_text, f.max_loss_text) == ("7.0% of margin needed", "3.6% of margin needed")
    assert (f.margin_needed, f.read_at) == (NEEDED, CHECKED_AT)


def test_available_funds_play_no_part():
    assert money.funds_share(D("4274"), D("2226"), FakeMargin(available=None)).max_profit_percent == D("7.0")
    assert money.funds_share(D("4274"), D("2226"), FakeMargin(needed=None)) is None  # funds read, margin not: absent


@pytest.mark.parametrize("margin", [
    FakeMargin(state="NOT_AVAILABLE_YET"), FakeMargin(state="UNREADABLE"), FakeMargin(state="NO_BASKET"),
    FakeMargin(needed=D("0")), FakeMargin(needed=D("-5")), FakeMargin(needed="61163"),
    FakeMargin(needed=D("NaN")), FakeMargin(needed=None), FakeMargin(checked_at=None),
])
def test_no_percentage_unless_checked_with_a_positive_decimal_margin_needed(margin):
    assert money.funds_share(D("4500"), D("9222"), margin) is None
    summary = summary_of(D("4500"), D("9222"))
    assert money.with_funds(summary, margin) is summary  # the rupee figures stay, nothing added


def test_unlimited_side_has_no_percentage_and_small_ones_say_less_than_a_tenth():
    f = money.funds_share(None, D("50"), FakeMargin())  # 50 / 61,163 = 0.08%
    assert (f.max_profit_percent, f.max_profit_text) == (None, None)
    assert f.max_loss_text == "less than 0.1% of margin needed"
    assert money.funds_share(D("0"), D("500"), FakeMargin()).max_profit_text == "0.0% of margin needed"
    assert money.funds_share(D("-1"), D("500"), FakeMargin()).max_profit_text is None


def test_with_funds_sets_the_share_on_a_summary():
    out = money.with_funds(summary_of(D("4274"), D("2226")), FakeMargin())
    assert out.funds_share.max_loss_percent == D("3.6")


def test_catalogue_wording_has_none_of_the_advice_words():
    texts = [t.text.lower() for tid, t in EXPLANATIONS.items() if tid.startswith("money_")]
    assert texts and not [w for t in texts for w in ("return", "gain", "expected", "promise") if w in t]


# --- row 26b fix 1: ratios only with charges (REQ-081 AC-4), killing mutants M1 / M1b ---------------------------------

NO_CHARGES_REASON = "the charges could not be priced, so the ratio is not shown"


def test_replay_condor_without_rates_has_no_ratio_and_with_rates_keeps_054_186(replayed):
    """Core: the same replay condor, rates absent -> None + reason (was 0.58 / 1.73); rates present -> 0.54 / 1.86."""
    _d, bare = outcome_of(replayed, None)
    s = bare.summary
    assert (s.reward_risk, s.risk_reward, s.reward_risk_reason) == (None, None, NO_CHARGES_REASON)
    assert s.charges is None and s.charges_unavailable
    _d, priced = outcome_of(replayed, RATES)
    p = priced.summary
    assert (p.reward_risk, p.risk_reward, p.reward_risk_reason) == (D("0.54"), D("1.86"), None)
    # hand: 4539.65 / 8460.35 = 0.5366 -> 0.54 ; inverse 1.8636 -> 1.86
    # these replay prices give the exact round trip rounded UP, 215.10 (ADR-082 line 39)
    assert (p.max_profit, p.max_loss) == (D("4754.75") - D("215.10"), D("8245.25") + D("215.10"))


def test_ratio_is_never_taken_from_the_figures_before_charges(replayed):
    _d, priced = outcome_of(replayed, RATES)
    before = money.reward_risk(D("4754.75"), D("8245.25"))
    assert (before.reward_risk, before.risk_reward) == (D("0.58"), D("1.73"))
    assert priced.summary.reward_risk != before.reward_risk and priced.summary.risk_reward != before.risk_reward


# --- M2 / M5 and the shares (attack 4, 5) ----------------------------------------------------------------------


def test_one_priced_and_one_unpriced_leg_gives_no_partial_value_split():
    priced = leg(Action.BUY, Instrument.CE, "22900", "150.00", ltp="150.00")
    unpriced = leg(Action.SELL, Instrument.PE, "23000", "90.00")  # no live price
    v = money.time_and_intrinsic((priced, unpriced), D("22976.85"))
    assert (v.intrinsic, v.time, v.label) == (None, None, None)
    assert v.reason == "a live price is missing for at least one leg or for the index"


def test_time_value_uses_the_live_price_not_the_planned_entry():
    bought = leg(Action.BUY, Instrument.CE, "22900", "150.00", ltp="180.00")  # planned 150, live 180
    v = money.time_and_intrinsic((bought,), D("22976.85"))
    # per unit: intrinsic 22976.85 - 22900 = 76.85, time 180 - 76.85 = 103.15 (planned 150 would give 73.15); x 65
    assert (v.intrinsic, v.time) == (D("4995.25"), D("6704.75"))


def test_a_share_under_a_tenth_of_a_percent_sends_percent_null_with_the_text():
    f = money.funds_share(D("10"), D("20"), FakeMargin())  # 0.016% and 0.033% of 61,163
    assert (f.max_profit_percent, f.max_loss_percent) == (None, None)
    assert f.max_profit_text == f.max_loss_text == "less than 0.1% of margin needed"


def test_one_decimal_percent_rounds_half_up():
    # 0.25 -> 0.3, 0.85 -> 0.9 (half-even would give 0.2, 0.8)
    f = money.funds_share(D("2.5"), D("8.5"), FakeMargin(needed=D("1000")))
    assert (f.max_profit_percent, f.max_loss_percent) == (D("0.3"), D("0.9"))


def test_the_sentences_and_ratios_use_the_one_shown_total(replayed):
    _d, out = outcome_of(replayed, RATES)
    body = outcome_to_dict(out)
    b = body["charges_breakdown"]
    items = sum((D(b[k]) for k in ("brokerage", "stt", "exchange_transaction", "sebi", "stamp", "gst")), D(0))
    assert D(b["total"]) == out.summary.charges == D("215.10")  # exact sum rounded UP; items may differ by paise
    assert abs(items - D(b["total"])) <= 2 * D("0.01")
    assert "about ₹215.10 of" in out.summary.what_can_i_lose and "about ₹215.10 of" in out.summary.what_can_i_make
    assert D(body["summary"]["max_loss"]) == D("8245.25") + D(b["total"])


def test_the_breakdown_names_exercise_stt_with_rate_and_condition_but_no_figure(replayed):
    _d, out = outcome_of(replayed, RATES)
    b = outcome_to_dict(out)["charges_breakdown"]
    assert b["exercise_stt_rate"] == "0.0015"
    assert b["exercise_stt_note"] == ("STT on exercise: 0.15% of the value of a bought option that finishes in the "
                                      "money. It depends on where the index settles, so it is not in this total.")
    assert "exercise_stt_amount" not in b and b["total"] == "215.10"
