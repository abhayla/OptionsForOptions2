# ruff: noqa: C408, PLR0913, RUF001, PLC0415
"""REQ-085 (ADR-185): Builder warnings as engine codes on measured conditions.

AC-2 strategy-level unhedged_short per direction; AC-3 weekend/holiday decay; AC-4 liquidity (spread, no trade, no
bid/offer, liquidity unknown); AC-8 an empty list is the "No warnings" label; the not-live paths carry no list at all.
Legs are real NIFTY contracts (22,500 / 22,700 / 22,900 / 23,100 / 24,000 strikes, lot size 75)."""
from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ofo.engine.decay import decay_estimate
from ofo.engine.executable_price import Depth, DepthLevel
from ofo.engine.legs import Action, Instrument
from ofo.market_calendar import CalendarError, next_open
from ofo.outcome.service import OutcomeLeg
from ofo.outcome.snapshot import LegLiquidity
from ofo.outcome.warnings import LiquiditySettings, WarningCode, no_warnings_label, strategy_warnings
from ofo.rules.inputs import DataHealth
from ofo.timeutil import IST

NOW = datetime.datetime(2026, 10, 9, 11, 0, tzinfo=IST)  # a Friday
LOT = 75
THIS_WEEK = datetime.date(2026, 10, 13)
NEXT_MONTH = datetime.date(2026, 11, 24)
SETTINGS = LiquiditySettings()


def leg(action, kind, strike, lots=1, expiry=THIS_WEEK, iid=None):
    iid = iid or f"{action.value}-{kind.value}-{strike}-{expiry}"
    return OutcomeLeg(iid, f"NIFTY{strike}{kind.value}", action, kind, Decimal(strike), expiry, lots, LOT, lots * LOT,
                      Decimal(10), NOW, Decimal(10), Decimal("0.15"), DataHealth.AVAILABLE, None)


def snap(legs, depth=None, health=DataHealth.AVAILABLE, trade_seconds_ago=60, missing=False):
    """A snapshot holding the same depth for every leg (None = no depth held)."""
    ts = int((NOW - datetime.timedelta(seconds=trade_seconds_ago)).timestamp())
    held = {} if missing else {x.instrument_id: LegLiquidity(depth, ts) for x in legs}
    return SimpleNamespace(underlying="NIFTY", liquidity=held,
                           legs={x.instrument_id: SimpleNamespace(quote=SimpleNamespace(health=health)) for x in legs})


def book(bid, ask):
    return Depth(tuple(DepthLevel(Decimal(bid), 100) for _ in [0]) if bid else (),
                 tuple(DepthLevel(Decimal(ask), 100) for _ in [0]) if ask else ())


def run(legs, snapshot=None, theta=None, calendar=lambda now: None, settings=SETTINGS, valuation=NOW):
    return strategy_warnings(SimpleNamespace(underlying="NIFTY"), legs, snapshot or snap(legs, book("10", "10.05")),
                             valuation, totals_theta=theta, calendar=calendar, liquidity_settings=settings)


def unhedged(legs):
    out, _ = run(legs)
    return [w.text for w in out if w.code is WarningCode.UNHEDGED_SHORT]


def directions(legs):
    texts = unhedged(legs)
    return ("rises" in " ".join(texts), "falls" in " ".join(texts), len(texts))


# ---- AC-2 --------------------------------------------------------------------------------------------------------

def test_strangle_warns_rising_and_falling_once_each_and_never_per_leg():
    legs = [leg(Action.SELL, Instrument.PE, 22700), leg(Action.SELL, Instrument.CE, 22900)]
    assert directions(legs) == (True, True, 2)
    _, per_leg = run(legs)
    assert all(w.code is not WarningCode.UNHEDGED_SHORT for ws in per_leg.values() for w in ws)


def test_buying_a_lower_put_clears_the_falling_warning_only():
    legs = [leg(Action.SELL, Instrument.PE, 22700), leg(Action.SELL, Instrument.CE, 22900),
            leg(Action.BUY, Instrument.PE, 22500)]
    assert directions(legs) == (True, False, 1)


def test_calendar_with_a_later_expiry_bought_call_is_not_warned():
    legs = [leg(Action.SELL, Instrument.CE, 24000), leg(Action.BUY, Instrument.CE, 24000, expiry=NEXT_MONTH)]
    assert directions(legs) == (False, False, 0)


def test_two_to_one_call_ratio_warns_rising():
    legs = [leg(Action.SELL, Instrument.CE, 22900, lots=2), leg(Action.BUY, Instrument.CE, 23100, lots=1)]
    assert directions(legs) == (True, False, 1)


def test_lone_bought_future_warns_falling_only():
    legs = [leg(Action.BUY, Instrument.FUT, 0, iid="fut")]
    assert directions(legs) == (False, True, 1)


def test_sold_call_with_an_equal_bought_future_clears_the_rising_warning():
    # the bought future covers the sold call's rising loss; its own falling loss (a lone bought future warns falling)
    # stays, because nothing bought covers it - so the covered call warns falling only
    legs = [leg(Action.SELL, Instrument.CE, 22900), leg(Action.BUY, Instrument.FUT, 0, iid="fut")]
    assert directions(legs) == (False, True, 1)


def test_a_leg_without_a_lot_size_refuses_the_whole_list():
    broken = leg(Action.SELL, Instrument.CE, 22900)
    broken = OutcomeLeg(*(*[getattr(broken, f) for f in broken.__dataclass_fields__][:7], None, None,
                          *[getattr(broken, f) for f in broken.__dataclass_fields__][9:]))
    assert run([broken]) is None


# ---- AC-3 --------------------------------------------------------------------------------------------------------

def decay(theta, valuation=NOW, calendar=next_open):
    legs = [leg(Action.BUY, Instrument.CE, 22900)]
    out, _ = run(legs, theta=theta, calendar=calendar, valuation=valuation)
    return [w for w in out if w.code is WarningCode.WEEKEND_HOLIDAY_DECAY]


def test_friday_to_monday_is_three_days_with_a_decimal_rupee_estimate():
    (w,) = decay(Decimal("-413.3333"))
    assert "Over the 3 days to Monday" in w.text and "₹1,240.00" in w.text.replace("−", "")  # 413.3333 x 3 = 1240
    assert decay_estimate(Decimal("-413.3333"), 3) == Decimal(-1240)


def test_a_midweek_evening_is_one_day_and_no_code():
    assert decay(Decimal("-400"), valuation=datetime.datetime(2026, 10, 14, 20, 0, tzinfo=IST)) == []


def test_a_holiday_makes_it_a_decay_weekend():
    # Thursday 2026-10-22 evening: Friday 2026-10-23 open -> one day -> none; treat a holiday through a stub calendar
    stub = lambda now: datetime.datetime(2026, 10, 15, 9, 15, tzinfo=IST)  # noqa: E731 - Thursday 15th (2 days from Tue)
    assert len(decay(Decimal("-400"), valuation=datetime.datetime(2026, 10, 13, 20, 0, tzinfo=IST), calendar=stub)) == 1


def test_zero_or_absent_theta_gives_no_decay_code():
    assert decay(Decimal(0)) == [] and decay(None) == []


def test_a_missing_calendar_year_gives_no_decay_code():
    def raising(now):
        raise CalendarError("no data")
    assert decay(Decimal("-400"), calendar=raising) == []
    assert decay(Decimal("-400"), calendar=lambda now: None) == []


# ---- AC-4 --------------------------------------------------------------------------------------------------------

def liquidity(snapshot_kwargs, settings=SETTINGS):
    legs = [leg(Action.BUY, Instrument.PE, 21000)]
    _, per_leg = run(legs, snap(legs, **snapshot_kwargs), settings=settings)
    return [(w.code, str(w.text)) for w in per_leg[legs[0].instrument_id] if w.code is not WarningCode.EXPIRY_DAY]


def test_far_put_with_bid_040_ask_060_is_flagged_as_40_percent_of_mid():
    (code, text), = liquidity(dict(depth=book("0.40", "0.60")))
    assert code is WarningCode.LOW_LIQUIDITY and "40.0%" in text


def test_spread_exactly_ten_percent_is_not_flagged_and_just_above_is():
    assert liquidity(dict(depth=book("9.5", "10.5"))) == []  # (1.0 / 10.0) = exactly 10% of mid
    assert len(liquidity(dict(depth=book("9.49", "10.5")))) == 1


def test_no_bid_or_no_offer_is_flagged():
    assert liquidity(dict(depth=book(None, "0.60")))[0][1] == "No bid or no offer."
    assert liquidity(dict(depth=book("0.40", None)))[0][1] == "No bid or no offer."


def test_no_depth_or_stale_quote_or_nothing_held_is_unknown_never_low_liquidity():
    for kw in (dict(depth=None), dict(depth=book("10", "10.05"), health=DataHealth.STALE),
               dict(depth=book("10", "10.05"), missing=True)):
        assert liquidity(kw) == [(WarningCode.LIQUIDITY_UNKNOWN, "Liquidity unknown - no live depth.")]


def test_no_trade_for_six_minutes_is_flagged_and_four_is_not():
    assert len(liquidity(dict(depth=book("10", "10.05"), trade_seconds_ago=360))) == 1
    assert liquidity(dict(depth=book("10", "10.05"), trade_seconds_ago=240)) == []


def test_exactly_five_minutes_since_the_last_trade_is_not_flagged():
    assert liquidity(dict(depth=book("10", "10.05"), trade_seconds_ago=300)) == []


def test_settings_change_the_thresholds():
    assert liquidity(dict(depth=book("9.5", "10.5")), LiquiditySettings(5, Decimal(9))) != []
    assert liquidity(dict(depth=book("10", "10.05"), trade_seconds_ago=240), LiquiditySettings(3, Decimal(10))) != []


# ---- expiry day / AC-8 / absent paths ----------------------------------------------------------------------------

def test_expiry_day_reuses_the_w086_wording_for_a_leg_expiring_today():
    today_leg = leg(Action.SELL, Instrument.CE, 22900, expiry=NOW.date())
    _, per_leg = run([today_leg])
    (w,) = [w for w in per_leg[today_leg.instrument_id] if w.code is WarningCode.EXPIRY_DAY]
    assert "expires today" in w.text


def test_no_warning_reads_as_the_server_label_and_an_empty_list():
    legs = [leg(Action.BUY, Instrument.CE, 22900)]
    out, per_leg = run(legs)
    assert out == [] and per_leg[legs[0].instrument_id] == []
    assert no_warnings_label() == "No warnings for this strategy"


def test_market_event_is_never_emitted():
    legs = [leg(Action.SELL, Instrument.CE, 22900), leg(Action.SELL, Instrument.PE, 22700)]
    out, per_leg = run(legs, theta=Decimal("-300"), calendar=next_open)
    assert WarningCode.MARKET_EVENT not in {w.code for w in out} | {w.code for ws in per_leg.values() for w in ws}


def test_the_not_live_paths_never_call_the_warnings():
    import inspect

    from ofo.outcome import service
    for fn in (service.not_connected, service.not_live, service.waiting_first_price, service.from_entries,
               service._refused):
        assert "strategy_warnings" not in inspect.getsource(fn) and "_with_warnings" not in inspect.getsource(fn)
    assert inspect.getsource(service.build_outcome).count("_with_warnings(") == 1
    assert inspect.getsource(service).count("strategy_warnings(") == 1


@pytest.mark.parametrize("bad", [1.5, "1", None])
def test_decay_estimate_refuses_a_non_decimal_theta(bad):
    with pytest.raises(ValueError):
        decay_estimate(bad, 3)
