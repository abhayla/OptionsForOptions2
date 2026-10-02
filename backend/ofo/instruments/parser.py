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

from ofo.instruments.models import ZERODHA, BrokerRef, Contract, ListedContract

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


def parse_instruments_rows(rows: Iterable[dict], *, seen_on: Optional[date] = None) -> Iterator[ListedContract]:
    """Parse dict rows (as from `csv.DictReader`) into `ListedContract` records.

    Raises `ValueError` on a row missing a required column or carrying an unparseable value
    (fail closed — never silently defaults a lot size, tick size, strike or identity). `seen_on` is the date
    Zerodha's list showed the row (the database stamps its own dates; the pure parser leaves it None unless given).
    """
    for row in rows:
        missing = [c for c in REQUIRED_COLUMNS if c not in row]
        if missing:
            raise ValueError(f"instrument row missing columns: {missing}")
        exchange = row["exchange"].strip()
        exchange_token = _parse_int(row["exchange_token"], "exchange_token")
        if not exchange or exchange_token <= 0:
            raise ValueError(f"instrument row has no exchange identity: exchange={exchange!r}, "
                             f"exchange_token={exchange_token!r}")
        yield zerodha_listed(
            instrument_token=_parse_int(row["instrument_token"], "instrument_token"),
            exchange_token=exchange_token,
            tradingsymbol=row["tradingsymbol"].strip(),
            name=row["name"].strip(),
            expiry=_parse_expiry(row["expiry"]),
            strike=_parse_decimal(row["strike"], "strike"),
            tick_size=_parse_decimal(row["tick_size"], "tick_size"),
            lot_size=_parse_int(row["lot_size"], "lot_size"),
            instrument_type=row["instrument_type"].strip(),
            segment=row["segment"].strip(),
            exchange=exchange,
            seen_on=seen_on,
        )


def zerodha_listed(*, instrument_token: int, exchange_token: int, tradingsymbol: str, name: str,
                   expiry: Optional[date], strike: Decimal, tick_size: Decimal, lot_size: int,
                   instrument_type: str, segment: str, exchange: str,
                   seen_on: Optional[date] = None) -> ListedContract:
    """One Zerodha instrument-list row, by its column names, as the contract plus Zerodha's own row (ADR-050).

    The contract keeps the exchange identity and terms; `instrument_token` and `tradingsymbol` go only into the
    `BrokerRef('zerodha', ...)` (REQ-054 AC-3), with Zerodha's lot and tick size dated `seen_on` (AC-4).
    """
    contract = Contract(exchange=exchange, exchange_token=exchange_token, name=name, expiry=expiry, strike=strike,
                        tick_size=tick_size, lot_size=lot_size, instrument_type=instrument_type, segment=segment)
    ref = BrokerRef(broker=ZERODHA, broker_token=str(instrument_token), broker_symbol=tradingsymbol,
                    broker_segment=segment, lot_size=lot_size, tick_size=tick_size, seen_on=seen_on)
    return ListedContract(contract=contract, broker_refs=(ref,))


def parse_instruments_stream(stream: TextIO, *, seen_on: Optional[date] = None) -> list[ListedContract]:
    """Parse an open CSV text stream (as downloaded from Zerodha) into `ListedContract` records."""
    reader = csv.DictReader(stream)
    return list(parse_instruments_rows(reader, seen_on=seen_on))


def parse_instruments_csv(path: str | Path, *, seen_on: Optional[date] = None) -> list[ListedContract]:
    """Parse a CSV file on disk (the instrument list, or a fixture slice of it)."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as f:
        return parse_instruments_stream(f, seen_on=seen_on)
