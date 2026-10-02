"""Parse Zerodha's public instrument list (CSV) into `ListedContract` records.

Each row becomes the contract (identity = exchange, exchange_token; ADR-050) plus Zerodha's own row for it
(`BrokerRef('zerodha', instrument_token, tradingsymbol, segment, lot_size, tick_size)`, REQ-054 AC-3/AC-4).

Adapted in structure (never-delete-on-refresh, underlying extraction) from
abhayla/algochanakya@2a868db (origin/main surveyed 2026-09-29)
backend/app/services/instrument_master.py — that module is SQLAlchemy/Redis/DB-backed and
downloads from a broker adapter; this module is a stdlib-only, pure parser (no DB, no network)
matching this project's stack rules (CLAUDE.md, ADR-043).

Zerodha publishes this list without authentication at https://api.kite.trade/instruments — see
`ofo.instruments.sources` for the cited source + capture date of any rule derived from it.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Iterator, Optional, TextIO

from ofo.instruments.models import BSE_FO, NSE_FO, ZERODHA, BrokerRef, Contract, ListedContract

REQUIRED_COLUMNS = (
    "instrument_token",
    "exchange_token",
    "tradingsymbol",
    "name",
    "last_price",
    "expiry",
    "strike",
    "tick_size",
    "lot_size",
    "instrument_type",
    "segment",
    "exchange",
)


def _parse_expiry(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"unparseable expiry date: {raw!r}") from exc


def _parse_decimal(raw: str, field: str) -> Decimal:
    raw = raw.strip()
    if raw == "":
        raise ValueError(f"empty {field}: decimal fields must never be blank")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"unparseable {field}: {raw!r}") from exc


def _parse_int(raw: str, field: str) -> int:
    raw = raw.strip()
    if raw == "":
        raise ValueError(f"empty {field}: integer fields must never be blank")
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"unparseable {field}: {raw!r}") from exc


#: Zerodha's `exchange` column -> the platform's exchange segment (REQ-054 "Exchange segment vocabulary"). Any other
#: value (NSE, BSE, MCX, CDS, NCO, BCD ...) is outside V1: the row is skipped and counted, never an error (F-10).
ZERODHA_EXCHANGE_TO_SEGMENT: dict[str, str] = {"NFO": NSE_FO, "BFO": BSE_FO}


class ParsedInstruments(list):
    """The listed contracts of one instrument list, plus how many rows were outside V1 and skipped."""

    def __init__(self, rows: Iterable[ListedContract] = (), skipped_outside_v1: int = 0) -> None:
        super().__init__(rows)
        self.skipped_outside_v1 = skipped_outside_v1


def zerodha_segment(exchange: str) -> str | None:
    """The platform segment for Zerodha's `exchange` value, or None when it is outside V1."""
    return ZERODHA_EXCHANGE_TO_SEGMENT.get(exchange.strip())


def _parse_rows(rows: Iterable[dict], seen_on: Optional[date], skipped: list[int]) -> Iterator[ListedContract]:
    for row in rows:
        missing = [c for c in REQUIRED_COLUMNS if c not in row]
        if missing:
            raise ValueError(f"instrument row missing columns: {missing}")
        if zerodha_segment(row["exchange"]) is None:
            skipped[0] += 1  # outside V1: not parsed further, so its other columns can never stop the load
            continue
        yield zerodha_listed(
            instrument_token=_parse_int(row["instrument_token"], "instrument_token"),
            exchange_token=_parse_int(row["exchange_token"], "exchange_token"),
            tradingsymbol=row["tradingsymbol"].strip(),
            name=row["name"].strip(),
            expiry=_parse_expiry(row["expiry"]),
            strike=_parse_decimal(row["strike"], "strike"),
            tick_size=_parse_decimal(row["tick_size"], "tick_size"),
            lot_size=_parse_int(row["lot_size"], "lot_size"),
            instrument_type=row["instrument_type"].strip(),
            segment=row["segment"].strip(),
            exchange=row["exchange"].strip(),
            seen_on=seen_on,
        )


def parse_instruments_rows(rows: Iterable[dict], *, seen_on: Optional[date] = None) -> Iterator[ListedContract]:
    """Parse dict rows (as from `csv.DictReader`) into `ListedContract` records; rows outside V1 are skipped.

    Raises `ValueError` on a row missing a required column or a V1 row carrying an unparseable value (fail closed -
    never silently defaults a lot size, tick size, strike or identity). `seen_on` is the date Zerodha's list showed the
    row (the database stamps its own dates; the pure parser leaves it None unless given).
    """
    return _parse_rows(rows, seen_on, [0])


def zerodha_listed(*, instrument_token: int, exchange_token: int, tradingsymbol: str, name: str,
                   expiry: Optional[date], strike: Decimal, tick_size: Decimal, lot_size: int,
                   instrument_type: str, segment: str, exchange: str,
                   seen_on: Optional[date] = None) -> ListedContract:
    """One Zerodha instrument-list row, by its column names, as the contract plus Zerodha's own row (ADR-050).

    The contract keeps the exchange identity (segment mapped from Zerodha's `exchange`, REQ-054) and terms;
    `instrument_token`, `tradingsymbol` and Zerodha's `segment` code go only into the `BrokerRef('zerodha', ...)`
    (REQ-054 AC-3), with Zerodha's lot and tick size dated `seen_on` (AC-4). Raises ValueError for an exchange outside
    V1 or a non-positive exchange token.
    """
    exchange_segment = zerodha_segment(exchange)
    if exchange_segment is None:
        raise ValueError(f"Zerodha exchange {exchange!r} is outside V1 (segments {sorted(ZERODHA_EXCHANGE_TO_SEGMENT)})")
    if isinstance(exchange_token, bool) or not isinstance(exchange_token, int) or exchange_token <= 0:
        raise ValueError(f"instrument row has no exchange identity: exchange_token={exchange_token!r}")
    contract = Contract(exchange_segment=exchange_segment, exchange_token=exchange_token, name=name, expiry=expiry,
                        strike=strike, tick_size=tick_size, lot_size=lot_size, instrument_type=instrument_type)
    ref = BrokerRef(broker=ZERODHA, broker_token=str(instrument_token), broker_symbol=tradingsymbol,
                    broker_segment=segment, lot_size=lot_size, tick_size=tick_size, seen_on=seen_on)
    return ListedContract(contract=contract, broker_refs=(ref,))


def parse_instruments_stream(stream: TextIO, *, seen_on: Optional[date] = None) -> ParsedInstruments:
    """Parse an open CSV text stream (as downloaded from Zerodha) into `ListedContract` records."""
    skipped = [0]
    rows = list(_parse_rows(csv.DictReader(stream), seen_on, skipped))
    return ParsedInstruments(rows, skipped_outside_v1=skipped[0])


def parse_instruments_csv(path: str | Path, *, seen_on: Optional[date] = None) -> ParsedInstruments:
    """Parse a CSV file on disk (the instrument list, or a fixture slice of it)."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as f:
        return parse_instruments_stream(f, seen_on=seen_on)
