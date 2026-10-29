"""GC-BP core proof (REQ-109 AC-2, AC-4; ADR-201 (2)): paper P&L splits into booked (exited legs, frozen at their exit
price) + unbooked (open legs at live prices) = total, all by the one engine (ofo.tracking.paper.paper_pnl).

Real numbers: live tracked strategy 48 on 2026-10-28, a NIFTY 3 Nov iron condor, 65 units a leg. Entries BUY 22300 PE
114.25, SELL 22400 PE 150.30, SELL 22600 CE 166.90, BUY 22700 CE 126.00; LTPs 113.60 / 151.05 / 166.80 / 126.45.
By hand: (113.60 - 114.25) x 65 = -42.25; (150.30 - 151.05) x 65 = -48.75; (166.90 - 166.80) x 65 = +6.50;
(126.45 - 126.00) x 65 = +29.25 -> total -55.25. Exit the SELL 22600 CE (leg 2) at 166.80: booked +6.50,
unbooked -42.25 - 48.75 + 29.25 = -61.75, total -55.25.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.engine.legs import Action, Instrument
from ofo.tracking import paper

D = Decimal
EXPIRY = datetime.date(2026, 11, 3)
AT = datetime.datetime(2026, 10, 28, 5, 0, tzinfo=datetime.UTC)
S48 = [paper.TrackedLeg("NSE_FO:1", Action.BUY, Instrument.PE, D("22300"), EXPIRY, 65, D("114.25"), AT),
       paper.TrackedLeg("NSE_FO:2", Action.SELL, Instrument.PE, D("22400"), EXPIRY, 65, D("150.30"), AT),
       paper.TrackedLeg("NSE_FO:3", Action.SELL, Instrument.CE, D("22600"), EXPIRY, 65, D("166.90"), AT),
       paper.TrackedLeg("NSE_FO:4", Action.BUY, Instrument.CE, D("22700"), EXPIRY, 65, D("126.00"), AT)]
LTP = [D("113.60"), D("151.05"), D("166.80"), D("126.45")]


def test_core_strategy_48_total_before_any_exit_is_minus_55_25():
    assert paper.paper_pnl(S48, LTP) == D("-55.25")


def test_core_exit_of_the_sell_22600_ce_books_6_50_and_leaves_minus_61_75_unbooked():
    split = paper.pnl_split(S48, {0: LTP[0], 1: LTP[1], 3: LTP[3]}, {2: D("166.80")})
    assert (split.booked, split.unbooked, split.total) == (D("6.50"), D("-61.75"), D("-55.25"))


def test_booked_is_frozen_at_the_exit_price_whatever_the_leg_trades_at_later():
    """After the exit the 22600 CE trades at 200.00: booked stays +6.50 (its exit price), never (166.90 - 200) x 65."""
    assert paper.booked_pnl(S48, {2: D("166.80")}) == D("6.50")
    assert paper.pnl_split(S48, {0: LTP[0], 1: LTP[1], 3: LTP[3]}, {2: D("166.80")}).booked == D("6.50")


def test_nothing_exited_books_zero_and_everything_exited_has_no_unbooked_part():
    none = paper.pnl_split(S48, dict(enumerate(LTP)), {})
    assert (none.booked, none.unbooked, none.total) == (D("0"), D("-55.25"), D("-55.25"))
    every = paper.pnl_split(S48, {}, dict(enumerate(LTP)))
    assert (every.booked, every.unbooked, every.total) == (D("-55.25"), D("0"), D("-55.25"))


def test_an_open_leg_without_a_live_price_leaves_unbooked_and_total_unknown_booked_still_known():
    split = paper.pnl_split(S48, {0: LTP[0], 3: LTP[3]}, {2: D("166.80")})  # leg 1 open, no price
    assert (split.booked, split.unbooked, split.total) == (D("6.50"), None, None)


def test_a_leg_both_open_and_exited_or_unknown_is_refused():
    with pytest.raises(ValueError, match="once"):
        paper.pnl_split(S48, dict(enumerate(LTP)), {2: D("166.80")})
    with pytest.raises(ValueError, match="leg"):
        paper.booked_pnl(S48, {9: D("1.00")})
