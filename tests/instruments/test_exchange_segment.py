"""W-056 stage 2: identity uses the platform's exchange segment, never Zerodha's `exchange` column (REQ-054, F-10).

Spec basis: REQ-054 section "Exchange segment vocabulary": V1 values NSE_FO and BSE_FO; Zerodha NFO -> NSE_FO,
BFO -> BSE_FO; any other row is outside V1 and not loaded. F-10: on Zerodha's 2026-10-02 list 30 NSE INDICES/cash pairs
share an exchange token (e.g. NSE / 1001 = NIFTY 50 and 94SFL28-YL). Rows below are copied from the real list.
"""
from __future__ import annotations

import dataclasses
import io
from pathlib import Path

import pytest

from ofo.instruments import EXCHANGE_SEGMENTS, Catalogue, Contract, InstrumentId
from ofo.instruments.parser import ZERODHA_EXCHANGE_TO_SEGMENT, parse_instruments_csv, parse_instruments_stream

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "instruments_slice.csv"
HEADER = ("instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,"
          "instrument_type,segment,exchange\n")
COLLISION_ROWS = (
    "256265,1001,NIFTY 50,NIFTY 50,0,,0,0,0,EQ,INDICES,NSE\n"
    "256266,1001,94SFL28-YL,94SFL28,0,,0,0.01,1,EQ,NSE,NSE\n"
    "18920450,73908,NIFTY26SEP23150CE,NIFTY,0,2026-09-29,23150,0.05,65,CE,NFO-OPT,NFO\n"
)


def test_segment_vocabulary_is_closed_and_zerodha_exchange_maps_into_it() -> None:
    assert EXCHANGE_SEGMENTS == frozenset({"NSE_FO", "BSE_FO"})
    assert ZERODHA_EXCHANGE_TO_SEGMENT == {"NFO": "NSE_FO", "BFO": "BSE_FO"}
    for bad in ("NFO", "BFO", "NSE", "nse_fo", "", None):
        with pytest.raises(ValueError):
            InstrumentId(bad, 40559)  # type: ignore[arg-type]
    names = {f.name for f in dataclasses.fields(Contract)}
    assert "exchange" not in names and "segment" not in names and "exchange_segment" in names


def test_the_real_nse_1001_collision_rows_are_skipped_as_outside_v1_never_loaded() -> None:
    parsed = parse_instruments_stream(io.StringIO(HEADER + COLLISION_ROWS))
    assert parsed.skipped_outside_v1 == 2
    assert [r.id for r in parsed] == [InstrumentId("NSE_FO", 73908)]
    cat = Catalogue()
    assert cat.load(parsed) == 1
    assert [e.ref("zerodha").broker_symbol for e in cat.all_entries()] == ["NIFTY26SEP23150CE"]


def test_an_outside_v1_row_with_garbage_never_stops_the_load_but_an_in_scope_one_does() -> None:
    garbage_nse = "x,y,Z,Z,0,not-a-date,abc,,,EQ,NSE,NSE\n"
    parsed = parse_instruments_stream(io.StringIO(HEADER + garbage_nse + COLLISION_ROWS))
    assert parsed.skipped_outside_v1 == 3 and len(parsed) == 1
    broken_nfo = "18920451,,NIFTY26SEP23200CE,NIFTY,0,2026-09-29,23200,0.05,65,CE,NFO-OPT,NFO\n"
    with pytest.raises(ValueError, match="exchange_token"):
        parse_instruments_stream(io.StringIO(HEADER + broken_nfo))


def test_fixture_slice_maps_nfo_and_bfo_rows_to_their_segments() -> None:
    rows = parse_instruments_csv(FIXTURE)
    assert {r.contract.exchange_segment for r in rows} == {"NSE_FO", "BSE_FO"}
    assert {(r.contract.exchange_segment, r.ref("zerodha").broker_segment.split("-")[0]) for r in rows} == {
        ("NSE_FO", "NFO"), ("BSE_FO", "BFO")}
