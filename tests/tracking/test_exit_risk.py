"""GC-ICFIX Issue 10 (ADR-256, ADR-143, ADR-008): an exit that leaves a sold leg without its protecting bought leg.

Real shape: user-test trade 139 "IC exit test" (NIFTY 23 Nov condor, 1 lot of 65): B 25000 PE, S 25100 PE, S 25300 CE,
B 25400 CE at the paper fills 162.55 / 201.50 / 218.35 / 176.40. Closing the bought 25400 CE alone turns a limited-loss
condor into one with no fixed maximum loss. The one engine (ofo.engine.extremes.exit_risk) answers before / after.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from ofo.engine.extremes import UNLIMITED, ContractTerms, exit_risk
from ofo.engine.legs import Instrument
from ofo.engine.orderbook import PaperOrder

D = Decimal
EXPIRY = datetime.date(2026, 11, 23)
T0 = datetime.datetime(2026, 11, 13, 4, 48, tzinfo=datetime.UTC)
T1 = datetime.datetime(2026, 11, 13, 5, 30, tzinfo=datetime.UTC)
TERMS = {"1": ContractTerms(Instrument.PE, D(25000), EXPIRY), "2": ContractTerms(Instrument.PE, D(25100), EXPIRY),
         "3": ContractTerms(Instrument.CE, D(25300), EXPIRY), "4": ContractTerms(Instrument.CE, D(25400), EXPIRY)}
BOOK = [PaperOrder("1", "BUY", 65, D("162.55"), "open", T0), PaperOrder("2", "SELL", 65, D("201.50"), "open", T0),
        PaperOrder("3", "SELL", 65, D("218.35"), "open", T0), PaperOrder("4", "BUY", 65, D("176.40"), "open", T0)]


def _exit(*legs: tuple[str, str, str]) -> list[PaperOrder]:
    return [PaperOrder(cid, side, 65, D(price), "exit", T1) for cid, side, price in legs]


def test_protective_bought_leg_closed_alone_has_no_fixed_maximum_loss_after() -> None:
    got = exit_risk(BOOK, _exit(("4", "SELL", "170.00")), TERMS)
    assert got.widens is True
    assert got.max_loss_after is UNLIMITED
    assert got.max_loss_before is not UNLIMITED and got.max_loss_before < 0


def test_closing_a_sold_leg_alone_does_not_warn() -> None:
    got = exit_risk(BOOK, _exit(("3", "BUY", "210.00")), TERMS)
    assert got.widens is False


def test_closing_everything_does_not_warn() -> None:
    got = exit_risk(BOOK, _exit(("1", "SELL", "150.00"), ("2", "BUY", "210.00"), ("3", "BUY", "230.00"),
                                ("4", "SELL", "160.00")), TERMS)
    assert got.widens is False


def test_closing_one_whole_spread_at_a_loss_does_not_warn_and_shows_no_figures() -> None:
    # the remaining put spread is unchanged; the loss booked on the closed call spread makes the book's Max Loss figure
    # fall, which is not a wider structure: the flag and the figures come from one result, so no figures either
    got = exit_risk(BOOK, _exit(("3", "BUY", "260.00"), ("4", "SELL", "120.00")), TERMS)
    assert got.widens is False
    assert got.max_loss_before is None and got.max_loss_after is None


def test_a_warning_always_carries_figures_that_agree_with_it() -> None:
    got = exit_risk(BOOK, _exit(("1", "SELL", "150.00")), TERMS)  # the bought put closed alone: wider, not unlimited
    assert got.widens is True
    assert got.max_loss_after is not UNLIMITED and got.max_loss_after < got.max_loss_before < 0


def test_a_flag_whose_figures_would_disagree_shows_no_figures() -> None:
    # absurd 30000 sale price: the booked gain outweighs the wider structure, so "after" would not read worse
    got = exit_risk(BOOK, _exit(("1", "SELL", "30000.00")), TERMS)
    assert got.widens is True
    assert got.max_loss_before is None and got.max_loss_after is None
