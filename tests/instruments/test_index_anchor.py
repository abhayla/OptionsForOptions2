"""ADR-148: the index anchor from NSE's F&O contract file, every answer state, on the real 16102026 file's NIFTY futures
(cut by scripts/cut_nse_future_fixture.py)."""
from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.instruments.freeze_file import (

    IndexAnchorUnavailable,
    index_anchor,
    parse_freeze_file,
    parse_freeze_rows,
)
from ofo.money import paise_to_rupees

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "nse-fo-16102026-nifty-futures.csv.gz"
FILE = parse_freeze_file(FIXTURE, nse_name="NSE_FO_contract_16102026.csv.gz")
REAL_OCT_BASE = Decimal("23119.20")  # NIFTY26OCTFUT BasePric 2311920 paise
MONDAY_AFTER = date(2026, 10, 19)  # real: 19102026 returned 404, 16102026 was the newest file
LAST_FRESH_DAY = date(2026, 10, 21)  # Fri 16th + 3 weekdays (Mon, Tue, Wed)
FIRST_STALE_DAY = date(2026, 10, 22)


def test_present_and_fresh_file_gives_the_near_month_base_price() -> None:
    assert index_anchor(FILE, "NIFTY", MONDAY_AFTER) == REAL_OCT_BASE
    assert index_anchor(FILE, "NIFTY", LAST_FRESH_DAY) == REAL_OCT_BASE


def test_an_expired_future_is_never_the_near_month() -> None:
    after_expiry = date(2026, 10, 28)  # the October future expired on the 27th; November's (23227.10) is next
    moved = dataclasses.replace(FILE, file_date=after_expiry)  # the same rows, as if read in a file of that day
    assert index_anchor(moved, "NIFTY", after_expiry) == Decimal("23227.10")


def test_absent_file_is_refused() -> None:
    with pytest.raises(IndexAnchorUnavailable, match="no NSE contract file was given"):
        index_anchor(None, "NIFTY", MONDAY_AFTER)


def test_stale_file_is_refused() -> None:
    with pytest.raises(IndexAnchorUnavailable, match="4 weekdays old, more than 3"):
        index_anchor(FILE, "NIFTY", FIRST_STALE_DAY)


def test_file_dated_after_the_update_is_refused() -> None:
    with pytest.raises(IndexAnchorUnavailable, match="after 2026-10-15"):
        index_anchor(FILE, "NIFTY", date(2026, 10, 15))


def test_no_future_row_for_the_index_is_refused() -> None:
    with pytest.raises(IndexAnchorUnavailable, match="no unexpired SENSEX future"):
        index_anchor(FILE, "SENSEX", MONDAY_AFTER)  # NSE's file carries no BSE index
    with pytest.raises(IndexAnchorUnavailable, match="no unexpired NIFTY future"):
        index_anchor(dataclasses.replace(FILE, rows=()), "NIFTY", MONDAY_AFTER)


def test_two_near_month_rows_are_refused() -> None:
    oct_row = next(r for r in FILE.rows if r.base_price == REAL_OCT_BASE)
    twin = dataclasses.replace(oct_row, exchange_token=oct_row.exchange_token + 1, base_price=Decimal("23000.00"))
    with pytest.raises(IndexAnchorUnavailable, match="2 NIFTY futures of 2026-10-27"):
        index_anchor(dataclasses.replace(FILE, rows=(*FILE.rows, twin)), "NIFTY", MONDAY_AFTER)


@pytest.mark.parametrize("price", ["abc", "", "-5", "1.5"])
def test_unparseable_price_is_refused(price: str) -> None:
    row = {"FinInstrmId": "48704", "FinInstrmNm": "FUTIDX", "TckrSymb": "NIFTY", "XpryDt": "1477578600",
           "StrkPric": "-1", "OptnTp": "XX", "MinLot": "65", "MaxTradQty": "3511", "BasePric": price}
    parsed = parse_freeze_rows([row], date(2026, 10, 16))
    with pytest.raises(IndexAnchorUnavailable, match="BasePric is missing or not a number"):
        index_anchor(parsed, "NIFTY", MONDAY_AFTER)


def test_paise_to_rupees_is_exact_and_int_only() -> None:
    assert paise_to_rupees(2311920) == REAL_OCT_BASE
    with pytest.raises(TypeError):
        paise_to_rupees(True)
