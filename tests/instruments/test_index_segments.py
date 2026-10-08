"""REQ-072 AC-1 (W-060): NSE_INDEX and BSE_INDEX for the NIFTY 50 and SENSEX rows only; identity (segment, exchange
token); never mixed with Zerodha's NSE cash rows that share numbers (F-10).

Rows are copied from Zerodha's real instrument list (tests/fixtures/kite_ws, 2026-10-08; F-10's NSE / 1001 pair).
"""
from __future__ import annotations

import datetime
import io
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.instruments import Catalogue, InstrumentId
from ofo.instruments.models import (BSE_INDEX, EXCHANGE_SEGMENTS, INDEX_ROWS, INDEX_SEGMENTS, NSE_INDEX, ZERODHA)
from ofo.instruments.parser import parse_instruments_csv, parse_instruments_stream
from ofo.marketdata.kite_frames import RawTick
from ofo.marketdata.kite_provider import IST, KiteProvider

KITE_CSV = Path(__file__).resolve().parents[1] / "fixtures" / "kite_ws" / "instruments-2026-10-08-subscribed.csv"
HEADER = ("instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,"
          "instrument_type,segment,exchange\n")
NIFTY_INDEX_ROW = "256265,1001,NIFTY 50,NIFTY 50,0,,0,0,0,EQ,INDICES,NSE\n"
CASH_1001_ROW = "256266,1001,94SFL28-YL,94SFL28,0,,0,0.01,1,EQ,NSE,NSE\n"  # F-10: same exchange token, cash
AT = datetime.datetime(2026, 10, 8, 9, 20, tzinfo=IST)


def test_the_vocabulary_gains_exactly_the_two_index_segments_for_two_rows():
    assert INDEX_SEGMENTS == {"NSE_INDEX", "BSE_INDEX"} and INDEX_SEGMENTS <= EXCHANGE_SEGMENTS
    assert INDEX_ROWS == {("NSE_INDEX", 1001): ("NIFTY 50", "NIFTY"), ("BSE_INDEX", 1): ("SENSEX", "SENSEX")}


def test_the_real_list_yields_nifty_50_and_sensex_only_and_never_india_vix():
    rows = parse_instruments_csv(KITE_CSV)
    index = sorted((r.contract.exchange_segment, r.contract.exchange_token, r.contract.name, r.ref(ZERODHA).broker_token)
                   for r in rows if r.contract.is_index())
    assert index == [("BSE_INDEX", 1, "SENSEX", "265"), ("NSE_INDEX", 1001, "NIFTY 50", "256265")]
    assert rows.skipped_outside_v1 == 1  # INDIA VIX (NSE INDICES, exchange token 1035): not in AC-1
    for r in rows:
        if r.contract.is_index():
            assert not r.contract.is_option() and not r.contract.is_future() and r.contract.expiry is None


@pytest.mark.parametrize("order", ["index first", "cash first"])
def test_nse_cash_row_sharing_1001_stays_a_different_contract(order):
    body = NIFTY_INDEX_ROW + CASH_1001_ROW if order == "index first" else CASH_1001_ROW + NIFTY_INDEX_ROW
    parsed = parse_instruments_stream(io.StringIO(HEADER + body))
    assert [r.id for r in parsed] == [InstrumentId(NSE_INDEX, 1001)] and parsed.skipped_outside_v1 == 1
    cat = Catalogue()
    assert cat.load(parsed) == 1
    (entry,) = cat.all_entries()
    assert entry.ref(ZERODHA).broker_token == "256265" and entry.ref(ZERODHA).broker_symbol == "NIFTY 50"
    # the cash row's own token never reaches NIFTY 50: a tick for it is unmapped, the index tick maps
    provider = KiteProvider(parsed, clock=lambda: AT)
    assert provider.normalise(RawTick(token=256266, kind="quote", ltp=Decimal("99.00")), AT) is None
    q = provider.normalise(RawTick(token=256265, kind="index", ltp=Decimal("22533.25")), AT)
    assert (q.instrument_id, q.segment, q.underlying, q.ltp) == ("NSE_INDEX:1001", "NSE_INDEX", "NIFTY",
                                                              Decimal("22533.25"))


@pytest.mark.parametrize("row", [
    "256266,1001,94SFL28-YL,NIFTY 50,0,,0,0,0,EQ,INDICES,NSE\n",  # INDICES + 1001 but not the NIFTY 50 symbol
    "256266,1001,NIFTY 50,NIFTY 50,0,,0,0.01,1,EQ,NSE,NSE\n",  # NIFTY 50 symbol on a cash row
    "265,1,SENSEX,SENSEX,0,,0,0,0,EQ,INDICES,NSE\n",  # SENSEX's token on the wrong exchange
])
def test_a_row_that_only_looks_like_an_index_is_not_one(row):
    parsed = parse_instruments_stream(io.StringIO(HEADER + row))
    assert list(parsed) == [] and parsed.skipped_outside_v1 == 1


def test_sensex_identity_is_bse_index_1():
    parsed = parse_instruments_stream(io.StringIO(HEADER + "265,1,SENSEX,SENSEX,0,,0,0,0,EQ,INDICES,BSE\n"))
    assert [r.id for r in parsed] == [InstrumentId(BSE_INDEX, 1)]
