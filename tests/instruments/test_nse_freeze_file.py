"""AC-4 (REQ-054): the freeze limit is read from NSE's own contract file, joined on (NSE_FO, exchange token), with the
file's date. Real rows: tests/fixtures/exchange/NSE_FO_contract_15102026_sample.csv (cut unmodified; F-36 gives the
column meanings and the 3511 = 54 x 65 + 1 arithmetic that the expected values below come from)."""
from __future__ import annotations

import csv
import gzip
import pathlib
from datetime import date
from decimal import Decimal

import pytest

from ofo.instruments import NSE_FO
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.freeze_file import (
    FreezeRow, file_date_from_name, match_to_catalogue, parse_freeze_file, parse_freeze_rows,
)
from ofo.instruments.models import Contract

NSE_NAME = "NSE_FO_contract_15102026.csv.gz"  # the real file the fixture was cut from
FIXTURE = pathlib.Path(__file__).parent.parent / "fixtures" / "exchange" / "NSE_FO_contract_15102026_sample.csv"


def _by_token(parsed) -> dict[int, FreezeRow]:
    return {r.exchange_token: r for r in parsed.rows}


def test_core_real_row_gives_freeze_limit_3511_with_file_date() -> None:
    """AC-4 core: token 47185 (Zerodha's NIFTY26O1923550CE) has freeze limit 3511 on the file dated 2026-10-15."""
    parsed = parse_freeze_file(FIXTURE, nse_name=NSE_NAME)
    assert parsed.file_date == date(2026, 10, 15)
    row = _by_token(parsed)[47185]
    assert row.freeze_limit == 3511
    assert row.lot_size == 65
    assert row.underlying == "NIFTY"
    assert row.instrument_type == "CE"
    assert row.strike == Decimal("23550")
    assert row.expiry == date(2026, 10, 19)  # F-36: 1476887400 s after 1980-01-01 = 2026-10-19 14:30


def test_rows_counted_from_the_real_file() -> None:
    """AC-4: 82 NIFTY option rows + 3 NIFTY futures kept; the 3 BANKNIFTY rows are outside V1 and counted as skipped."""
    parsed = parse_freeze_file(FIXTURE, nse_name=NSE_NAME)
    assert len(parsed.rows) == 85
    assert parsed.skipped == 3
    assert {r.freeze_limit for r in parsed.rows} == {3511}
    futures = [r for r in parsed.rows if r.instrument_type == "FUT"]
    assert sorted(r.exchange_token for r in futures) == [48704, 58875, 61471]
    assert all(r.strike == Decimal(0) for r in futures)  # the file's -1 strike is "none"


def test_gz_file_reads_the_same(tmp_path: pathlib.Path) -> None:
    """AC-4: NSE serves the file as .csv.gz."""
    gz = tmp_path / "NSE_FO_contract_15102026.csv.gz"
    gz.write_bytes(gzip.compress(FIXTURE.read_bytes()))
    assert parse_freeze_file(gz).rows == parse_freeze_file(FIXTURE, nse_name=NSE_NAME).rows


def _real_rows() -> list[dict]:
    with FIXTURE.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_header_allow_list_renamed_column_fails() -> None:
    """AC-4: a renamed required column is an error; no column is guessed by position."""
    rows = _real_rows()
    renamed = [{("MaxTradQty2" if k == "MaxTradQty" else k): v for k, v in r.items()} for r in rows]
    with pytest.raises(ValueError, match="MaxTradQty"):
        parse_freeze_rows(renamed, date(2026, 10, 15))


def test_extra_unknown_columns_are_ignored_because_the_file_has_about_90_unused_columns() -> None:
    """AC-4: the real file has ~120 columns we do not use; only the required ones are read, the rest are ignored."""
    rows = _real_rows()
    assert len(rows[0]) > 100
    extra = [dict(r, SomeNewColumn="x") for r in rows]
    assert parse_freeze_rows(extra, date(2026, 10, 15)).rows == parse_freeze_file(FIXTURE, nse_name=NSE_NAME).rows


def test_non_integer_limit_is_refused() -> None:
    """AC-4: 3511.5 is not a freeze limit; refuse, never round."""
    rows = [dict(r) for r in _real_rows() if r["TckrSymb"] == "NIFTY"][:1]
    rows[0]["MaxTradQty"] = "3.511500E+03"
    with pytest.raises(ValueError, match="MaxTradQty"):
        parse_freeze_rows(rows, date(2026, 10, 15))
    rows[0]["MaxTradQty"] = ""
    with pytest.raises(ValueError, match="MaxTradQty"):
        parse_freeze_rows(rows, date(2026, 10, 15))
    rows[0]["MaxTradQty"] = "0"
    with pytest.raises(ValueError, match="MaxTradQty"):
        parse_freeze_rows(rows, date(2026, 10, 15))


def test_file_date_from_name() -> None:
    """AC-4: the date is the ddmmyyyy in the file name; a name that does not parse is refused."""
    assert file_date_from_name("NSE_FO_contract_15102026.csv.gz") == date(2026, 10, 15)
    assert file_date_from_name("/tmp/x/NSE_FO_contract_01012027.csv") == date(2027, 1, 1)
    for bad in ("qtyfreeze.xls", "NSE_FO_contract_32102026.csv", "NSE_FO_contract_2026.csv", "NSE_FO_contract_15102026.txt"):
        with pytest.raises(ValueError):
            file_date_from_name(bad)


def _catalogue(token: int, lot: int = 65, expiry=date(2026, 10, 19), strike="23550", kind="CE") -> Catalogue:
    cat = Catalogue()
    cat.load([Contract(exchange_segment=NSE_FO, exchange_token=token, name="NIFTY", expiry=expiry,
                       strike=Decimal(strike), tick_size=Decimal("0.05"), lot_size=lot, instrument_type=kind)])
    return cat


def test_join_on_token_stores_the_limit() -> None:
    """AC-4: a row joins on (NSE_FO, token) when lot, expiry and strike agree."""
    match = match_to_catalogue(parse_freeze_file(FIXTURE, nse_name=NSE_NAME), _catalogue(47185))
    assert [(m.instrument_id.exchange_token, m.freeze_limit) for m in match.matched] == [(47185, 3511)]
    assert match.disagreements == ()


@pytest.mark.parametrize("change, field", [({"lot": 75}, "lot"), ({"expiry": date(2026, 10, 26)}, "expiry"),
                                           ({"strike": "23600"}, "strike"), ({"kind": "PE"}, "type")])
def test_disagreeing_identity_is_reported_not_stored(change: dict, field: str) -> None:
    """AC-4: lot, expiry, strike or type differing from the catalogue -> reported, not stored."""
    match = match_to_catalogue(parse_freeze_file(FIXTURE, nse_name=NSE_NAME), _catalogue(47185, **change))
    assert match.matched == ()
    assert [(d.exchange_token, d.fields) for d in match.disagreements] == [(47185, (field,))]


def test_symbol_equal_but_token_different_does_not_join() -> None:
    """AC-4: the join is on the exchange token. A catalogue contract with the same strike/expiry/type under another
    token gets no limit, even though every other field agrees (a join on symbol would store it)."""
    match = match_to_catalogue(parse_freeze_file(FIXTURE, nse_name=NSE_NAME), _catalogue(99999))
    assert match.matched == ()
    assert match.disagreements == ()


def test_duplicate_token_in_one_file_is_refused() -> None:
    """AC-4: one token twice in a file is ambiguous (two limits for one contract): refuse the whole file."""
    row = next(r for r in _real_rows() if r["FinInstrmId"] == "47185")
    with pytest.raises(ValueError, match="47185"):
        parse_freeze_rows([row, dict(row)], date(2026, 10, 15))


def test_other_underlyings_and_kinds_are_skipped_not_parsed() -> None:
    """AC-4: a stock option row (not V1) with a junk limit does not stop the load; a V1 row with one does."""
    row = next(r for r in _real_rows() if r["FinInstrmId"] == "47185")
    stock = dict(row, TckrSymb="RELIANCE", MaxTradQty="junk")
    parsed = parse_freeze_rows([row, stock], date(2026, 10, 15))
    assert (len(parsed.rows), parsed.skipped) == (1, 1)
