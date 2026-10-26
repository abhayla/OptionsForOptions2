"""REQ-135 AC-4 (W-155): a strategy whose only leg is a futures leg, on the real engine and the real 2026-10-08 frames.

Core: strategy_metrics and the outcome service on one BUY and one SELL futures leg. The recorded frames hold options
only, so the futures rows come from the real instrument-list slice (listed, no quote of their own).
Proof: the summary body of a lone BUY / SELL future is asserted field by field below.
"""
import datetime
from decimal import Decimal

import pytest
from marketdata._kite_fixture import all_instrument_ids, new_provider, new_provider_with_futures, replay

from ofo.engine import UNLIMITED, Action, Instrument, Leg, Strategy, strategy_metrics
from ofo.marketdata.kite_provider import IST
from ofo.outcome import OutcomeState, PlannedLeg, StrategyDefinition, build_outcome, read_snapshot

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = Decimal("0.065")
ENTRY = Decimal("24000")
NO_FIXED_MAXIMUM = "No fixed maximum"
PAISE_ZERO = "0.00"
# the real NIFTY condor of the recorded frames (bounded on both sides)
CONDOR = (("NSE_FO:44624", Action.SELL), ("NSE_FO:44632", Action.BUY), ("NSE_FO:44604", Action.SELL),
          ("NSE_FO:44595", Action.BUY))
CALL_ID = "NSE_FO:44632"  # the recorded NIFTY 13-Oct 23000 CE


@pytest.fixture(scope="module")
def futures_provider():
    provider, clock, items, futures = new_provider_with_futures("NIFTY")
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider, futures


def summary_of(provider, legs):
    d = StrategyDefinition("NIFTY", tuple(PlannedLeg(iid, action, 1, entry, VALUATION) for iid, action, entry in legs))
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    out = build_outcome(d, snap, VALUATION)
    assert out.state is OutcomeState.COMPUTED, out.reason
    return out.summary


def future_id(futures):
    c = futures[1].contract  # NIFTY 27 Oct 2026 futures, lot 65
    return f"{c.exchange_segment}:{c.exchange_token}"


def test_the_engine_answers_both_max_sides_of_a_lone_future():
    leg = lambda action: Leg(action, Instrument.FUT, None, datetime.date(2026, 10, 27), 75, ENTRY)  # noqa: E731
    buy = strategy_metrics(Strategy((leg(Action.BUY),)))
    sell = strategy_metrics(Strategy((leg(Action.SELL),)))
    assert (buy.max_profit, buy.max_loss) == (UNLIMITED, Decimal("1800000"))
    assert (sell.max_profit, sell.max_loss) == (Decimal("1800000"), UNLIMITED)


def test_lone_buy_future_unlimited_profit_finite_loss_no_ratio_zero_values(futures_provider):
    provider, futures = futures_provider
    s = summary_of(provider, [(future_id(futures), Action.BUY, ENTRY)])
    assert s.max_profit_unlimited is True and s.max_profit is None
    assert s.max_loss_unlimited is False and s.max_loss == Decimal("1560000")
    assert s.reward_risk is None and s.reward_risk_reason == NO_FIXED_MAXIMUM
    assert str(s.time_value) == PAISE_ZERO and str(s.intrinsic_value) == PAISE_ZERO


def test_lone_sell_future_mirrors_it(futures_provider):
    provider, futures = futures_provider
    s = summary_of(provider, [(future_id(futures), Action.SELL, ENTRY)])
    assert s.max_loss_unlimited is True and s.max_loss is None
    assert s.max_profit_unlimited is False and s.max_profit == Decimal("1560000")
    assert s.reward_risk is None and s.reward_risk_reason == NO_FIXED_MAXIMUM
    assert str(s.time_value) == PAISE_ZERO and str(s.intrinsic_value) == PAISE_ZERO


def test_an_unlimited_option_strategy_has_no_ratio_but_its_time_and_intrinsic_value():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    entry = provider.book.get(CALL_ID, VALUATION).ltp
    s = summary_of(provider, [(CALL_ID, Action.BUY, entry)])  # a long call: profit unlimited
    assert s.max_profit_unlimited is True
    assert s.reward_risk is None and s.reward_risk_reason == NO_FIXED_MAXIMUM
    assert s.time_value + s.intrinsic_value == entry * 65  # REQ-081 AC-3 (row 26b): premium paid = intrinsic + time


def test_a_bounded_strategy_reads_its_ratio_from_the_summary_maximums_row_26b():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    legs = [(iid, action, provider.book.get(iid, VALUATION).ltp) for iid, action in CONDOR]
    s = summary_of(provider, legs)
    assert s.max_profit_unlimited is False and s.max_loss_unlimited is False
    assert (s.max_profit, s.max_loss) == (Decimal("4754.75"), Decimal("8245.25"))  # no rates here: before charges
    # 4754.75 / 8245.25 = 0.5766 and 8245.25 / 4754.75 = 1.7341 (hand division), two decimals
    assert (s.reward_risk, s.risk_reward, s.reward_risk_reason) == (Decimal("0.58"), Decimal("1.73"), None)
    assert s.time_value is not None and s.intrinsic_value is not None
