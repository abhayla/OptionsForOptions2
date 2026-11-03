"""ADR-241: an adjustment approach trade is priced at the live bid-ask mid first (the ADR-172 rule of
``ofo.engine.model.iv_price``, health gate included), else the LTP, else none. Answer states (B4 (d)): live book /
stale book / one side missing / ask below bid (crossed) / no LTP and no live book."""
from __future__ import annotations

import datetime
import inspect
from decimal import Decimal as D

import pytest

from ofo.adjustment import approaches
from ofo.adjustment.approaches import ChainRow, planned_price
from ofo.engine import model
from ofo.rules.inputs import DataHealth

EXP = datetime.date(2026, 12, 29)


def row(ltp: str | None, bid: str | None, ask: str | None, health: DataHealth | None) -> ChainRow:
    return ChainRow(D("25250"), "CE", EXP, "NIFTY26DEC25250CE", None if ltp is None else D(ltp),
                    None if bid is None else D(bid), None if ask is None else D(ask), health=health)


def test_live_book_mid_beats_a_stale_ltp() -> None:
    """The real case of ADR-241 (2026-11-03): LTP 117.75, live book 72.00 / 75.30 -> 73.65, never 117.75."""
    assert planned_price(row("117.75", "72.00", "75.30", DataHealth.AVAILABLE)) == D("73.65")


@pytest.mark.parametrize("health", [DataHealth.STALE, DataHealth.DELAYED, DataHealth.UNHEALTHY,
                                    DataHealth.UNAVAILABLE, None])
def test_book_not_live_uses_the_ltp(health: DataHealth | None) -> None:
    """Health gate: after hours (STALE) or any non-AVAILABLE / unknown book, the closing LTP (ADR-172 / ADR-197)."""
    assert planned_price(row("117.75", "72.00", "75.30", health)) == D("117.75")


@pytest.mark.parametrize(("bid", "ask"), [(None, "75.30"), ("72.00", None), ("0", "75.30"), ("72.00", "0")])
def test_one_side_missing_uses_the_ltp(bid: str | None, ask: str | None) -> None:
    assert planned_price(row("117.75", bid, ask, DataHealth.AVAILABLE)) == D("117.75")


def test_crossed_book_uses_the_ltp() -> None:
    assert planned_price(row("117.75", "75.30", "72.00", DataHealth.AVAILABLE)) == D("117.75")


def test_locked_book_is_live() -> None:
    """Ask equal to the bid is a live book (ADR-172: ask at or above bid)."""
    assert planned_price(row("117.75", "73.00", "73.00", DataHealth.AVAILABLE)) == D("73.00")


def test_no_ltp_and_no_live_book_is_none() -> None:
    assert planned_price(row(None, "72.00", "75.30", DataHealth.STALE)) is None
    assert planned_price(row(None, None, None, DataHealth.AVAILABLE)) is None
    assert planned_price(row("0", None, None, DataHealth.AVAILABLE)) is None
    assert planned_price(None) is None


def test_no_ltp_live_book_is_the_mid() -> None:
    assert planned_price(row(None, "72.00", "75.30", DataHealth.AVAILABLE)) == D("73.65")


def test_mid_is_rounded_half_up_to_the_paisa() -> None:
    """72.00 / 75.31 -> 73.655 -> 73.66; 72.00 / 75.25 -> 73.625 -> 73.63 (half-up, as the planned price always
    was; half-even would give 73.62)."""
    assert planned_price(row("117.75", "72.00", "75.31", DataHealth.AVAILABLE)) == D("73.66")
    assert planned_price(row("117.75", "72.00", "75.25", DataHealth.AVAILABLE)) == D("73.63")


def test_ltp_rounded_to_the_paisa_when_book_not_live() -> None:
    assert planned_price(row("117.755", None, None, None)) == D("117.76")


def test_one_rule_shared_with_iv_price() -> None:
    """Attack 4: the builder and iv_price call the engine's one live-book rule; no second copy of the gate."""
    assert "live_book(" in inspect.getsource(approaches.planned_price)
    assert "DataHealth.AVAILABLE" not in inspect.getsource(approaches)
    assert "live_book(" in inspect.getsource(model.iv_price)
