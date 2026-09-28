"""Parse Zerodha's public instrument list (CSV) into `Contract` records.

Adapted in structure (never-delete-on-refresh, underlying extraction) from
abhayla/algochanakya@<checkout HEAD> backend/app/services/instrument_master.py — that module is
SQLAlchemy/Redis/DB-backed and downloads from a broker adapter; this module is a stdlib-only,
pure parser (no DB, no network) matching this project's stack rules (CLAUDE.md, ADR-043).

Zerodha publishes this list without authentication at https://api.kite.trade/instruments — see
`ofo.instruments.sources` for the cited source + capture date of any rule derived from it.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Iterator, TextIO

from ofo.instruments.models import Contract

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


def parse_instruments_rows(rows: Iterable[dict]) -> Iterator[Contract]:
    """Parse dict rows (as from `csv.DictReader`) into `Contract` records.

    Raises `ValueError` on a row missing a required column or carrying an unparseable value
    (fail closed — never silently defaults a lot size, tick size or strike).
    """
    for row in rows:
        missing = [c for c in REQUIRED_COLUMNS if c not in row]
        if missing:
            raise ValueError(f"instrument row missing columns: {missing}")

        yield Contract(
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
        )


def parse_instruments_stream(stream: TextIO) -> list[Contract]:
    """Parse an open CSV text stream (as downloaded from Zerodha) into `Contract` records."""
    reader = csv.DictReader(stream)
    return list(parse_instruments_rows(reader))


def parse_instruments_csv(path: str | Path) -> list[Contract]:
    """Parse a CSV file on disk (the instrument list, or a fixture slice of it)."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as f:
        return parse_instruments_stream(f)
