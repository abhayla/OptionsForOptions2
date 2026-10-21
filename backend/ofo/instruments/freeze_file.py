"""NSE's daily F&O contract file as the source of the freeze limit (ADR-081, REQ-054 AC-4, findings F-36).

Zerodha publishes no freeze limit, so it is stored per exchange from the exchange's own file with the file's date.
For NSE that file is ``NSE_FO_contract_ddmmyyyy.csv(.gz)``. Meanings measured on the real 15 Oct 2026 file (F-36):
``FinInstrmId`` is the exchange token, ``MaxTradQty`` is the freeze limit (the largest allowed order is one less),
``XpryDt`` is seconds from 1980-01-01, ``StrkPric`` is in paise, ``MinLot`` is the lot size.

The header is an allow-list: the required columns must exist by name (never by position); the other ~120 columns of
the real file are not used and are ignored for that reason only. Standard library only; money stays ``Decimal``.
"""
from __future__ import annotations

import csv
import gzip
import io
import pathlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterable

from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS, Catalogue
from ofo.instruments.models import NSE_FO, InstrumentId
from ofo.money import paise_to_rupees

REQUIRED_COLUMNS: tuple[str, ...] = (
    "FinInstrmId", "FinInstrmNm", "TckrSymb", "XpryDt", "StrkPric", "OptnTp", "MinLot", "MaxTradQty",
)
_EPOCH = datetime(1980, 1, 1)
_NAME = re.compile(r"NSE_FO_contract_(\d{2})(\d{2})(\d{4})\.csv(\.gz)?")
#: the file's instrument kinds we keep -> our instrument type for futures (options use the file's CE/PE)
_KINDS = {"OPTIDX", "FUTIDX"}
_V1_NSE_UNDERLYINGS = frozenset(n for n, seg in SUPPORTED_UNDERLYINGS.items() if seg == NSE_FO)


@dataclass(frozen=True)
class FreezeRow:
    exchange_token: int
    underlying: str
    instrument_type: str  # CE, PE or FUT
    expiry: date
    strike: Decimal  # rupees; 0 for a future
    lot_size: int
    freeze_limit: int  # MaxTradQty: an order must be BELOW this (F-36)
    # ADR-148: a future's BasePric (paise -> rupees); None for an option, or when the column is absent or unparseable
    base_price: Decimal | None = None


@dataclass(frozen=True)
class FreezeFile:
    file_date: date
    rows: tuple[FreezeRow, ...]
    skipped: int  # rows outside V1 (other underlyings, stock derivatives)


@dataclass(frozen=True)
class FreezeMatch:
    instrument_id: InstrumentId
    freeze_limit: int


@dataclass(frozen=True)
class Disagreement:
    """A file row whose token is in the catalogue but whose lot, expiry, strike or type differs: not stored."""

    exchange_token: int
    fields: tuple[str, ...]  # the names of the fields that differ


@dataclass(frozen=True)
class FreezeJoin:
    matched: tuple[FreezeMatch, ...]
    disagreements: tuple[Disagreement, ...]  # reported, never stored
    not_in_catalogue: int


def file_date_from_name(name: str) -> date:
    """The ddmmyyyy of ``NSE_FO_contract_ddmmyyyy.csv[.gz]``; any other name, or an impossible date, is refused."""
    m = _NAME.fullmatch(pathlib.PurePath(str(name)).name)
    if m is None:
        raise ValueError(f"not an NSE F&O contract file name (NSE_FO_contract_ddmmyyyy.csv[.gz]): {name!r}")
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError as exc:
        raise ValueError(f"the date in the file name {name!r} is not a real date") from exc


def _int(text: str, column: str, token: str, *, positive: bool = True) -> int:
    try:
        d = Decimal(text.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"{column} of token {token} is not a number: {text!r}") from exc
    if not d.is_finite() or d != d.to_integral_value() or (positive and d <= 0):
        raise ValueError(f"{column} of token {token} must be a positive whole number, got {text!r}")
    return int(d)


def _row(raw: dict[str, str]) -> FreezeRow | None:
    kind = raw["FinInstrmNm"].strip()
    underlying = raw["TckrSymb"].strip()
    if kind not in _KINDS or underlying not in _V1_NSE_UNDERLYINGS:
        return None
    token_text = raw["FinInstrmId"].strip()
    token = _int(token_text, "FinInstrmId", token_text)
    seconds = _int(raw["XpryDt"], "XpryDt", token_text)
    expiry = (_EPOCH + timedelta(seconds=seconds)).date()
    base_price = None
    if kind == "FUTIDX":
        instrument_type, strike = "FUT", Decimal(0)
        base_price = _base_price(raw.get("BasePric"))
    else:
        instrument_type = raw["OptnTp"].strip()
        if instrument_type not in ("CE", "PE"):
            raise ValueError(f"OptnTp of token {token_text} must be CE or PE, got {instrument_type!r}")
        strike = Decimal(_int(raw["StrkPric"], "StrkPric", token_text)) / 100
    return FreezeRow(exchange_token=token, underlying=underlying, instrument_type=instrument_type, expiry=expiry,
                     strike=strike, lot_size=_int(raw["MinLot"], "MinLot", token_text),
                     freeze_limit=_int(raw["MaxTradQty"], "MaxTradQty", token_text), base_price=base_price)


def _base_price(text: str | None) -> Decimal | None:
    """ADR-148: BasePric in whole paise -> rupees; None (never a guess) when absent, not a positive whole number."""
    try:
        return paise_to_rupees(_int(text or "", "BasePric", "-"))
    except ValueError:
        return None


class IndexAnchorUnavailable(ValueError):
    """ADR-148: the NSE contract file cannot give an index's anchor level (the structural pass then refuses)."""


#: ADR-148: the newest NSE contract file may be at most this many weekdays older than the update date. Real case: on
#: Monday 2026-10-19 the 19102026 file returned 404 and Friday's 16102026 file was the newest (1 weekday); 3 allows a
#: late file across a weekend. Weekdays, not trading days (the repo has no holiday calendar), so a holiday makes the
#: limit stricter, never looser.
MAX_FILE_AGE_WEEKDAYS = 3


_SATURDAY = 5  # date.weekday(): Monday 0 ... Friday 4


def _weekdays_between(older: date, newer: date) -> int:
    return sum(1 for n in range(1, (newer - older).days + 1) if (older + timedelta(days=n)).weekday() < _SATURDAY)


def index_anchor(parsed: FreezeFile | None, underlying: str, update_date: date) -> Decimal:
    """ADR-148: the anchor level of ``underlying`` = the near-month index future's base price (the nearest FUT expiry on
    or after ``update_date``) from the NSE contract file. Raises IndexAnchorUnavailable for every other answer state:
    no file, a file dated after the update date or more than MAX_FILE_AGE_WEEKDAYS older, no future row, two
    near-month rows, or an unparseable price."""
    if parsed is None:
        raise IndexAnchorUnavailable("no NSE contract file was given (absent or not published, e.g. HTTP 404)")
    if parsed.file_date > update_date:
        raise IndexAnchorUnavailable(f"the NSE contract file is dated {parsed.file_date}, after {update_date}")
    age = _weekdays_between(parsed.file_date, update_date)
    if age > MAX_FILE_AGE_WEEKDAYS:
        raise IndexAnchorUnavailable(f"the NSE contract file of {parsed.file_date} is {age} weekdays old, more than "
                                     f"{MAX_FILE_AGE_WEEKDAYS}")
    futures = [r for r in parsed.rows
               if r.underlying == underlying and r.instrument_type == "FUT" and r.expiry >= update_date]
    if not futures:
        raise IndexAnchorUnavailable(f"the NSE contract file has no unexpired {underlying} future")
    near = min(r.expiry for r in futures)
    rows = [r for r in futures if r.expiry == near]
    if len(rows) != 1:
        raise IndexAnchorUnavailable(f"the NSE contract file has {len(rows)} {underlying} futures of {near}")
    if rows[0].base_price is None:
        raise IndexAnchorUnavailable(f"the {underlying} {near} future's BasePric is missing or not a number")
    return rows[0].base_price


def parse_freeze_rows(rows: Iterable[dict[str, str]], file_date: date) -> FreezeFile:
    """Parse dict rows of the contract file. Raises ``ValueError`` on a missing required column or a bad value."""
    kept: list[FreezeRow] = []
    skipped = 0
    seen: set[int] = set()
    for raw in rows:
        missing = [c for c in REQUIRED_COLUMNS if c not in raw]
        if missing:
            raise ValueError(f"contract file is missing required column(s): {missing}")
        short = [c for c in REQUIRED_COLUMNS if not isinstance(raw[c], str)]
        if short:
            raise ValueError(f"contract file row has no value for column(s) {short} (a short row)")
        row = _row(raw)
        if row is None:
            skipped += 1
            continue
        if row.exchange_token in seen:
            raise ValueError(f"exchange token {row.exchange_token} appears twice in the file")
        seen.add(row.exchange_token)
        kept.append(row)
    if not kept:
        raise ValueError(f"the contract file has no usable NIFTY row ({skipped} rows read): empty or the wrong file")
    return FreezeFile(file_date=file_date, rows=tuple(kept), skipped=skipped)


def parse_freeze_file(path: str | pathlib.Path, *, nse_name: str | None = None) -> FreezeFile:
    """Read ``NSE_FO_contract_ddmmyyyy.csv`` or ``.csv.gz``; the file date comes from the name.

    ``nse_name`` is for a copy kept under another name (a cut test fixture): the NSE name the rows came from."""
    p = pathlib.Path(path)
    file_date = file_date_from_name(nse_name or p.name)
    data = p.read_bytes()
    if p.name.endswith(".gz"):
        data = gzip.decompress(data)
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
    return parse_freeze_rows(reader, file_date)


def match_to_catalogue(parsed: FreezeFile, catalogue: Catalogue) -> FreezeJoin:
    """Join on (NSE_FO, exchange token) ONLY, then require lot, expiry, strike and type to agree with the catalogue.

    A disagreement is reported and the limit is not stored (identity data is never overwritten)."""
    matched: list[FreezeMatch] = []
    disagreements: list[Disagreement] = []
    absent = 0
    for row in parsed.rows:
        iid = InstrumentId(NSE_FO, row.exchange_token)
        entry = catalogue.get(iid)
        if entry is None:
            absent += 1
            continue
        c = entry.contract
        diffs = tuple(name for name, theirs, ours in (
            ("lot", row.lot_size, c.lot_size), ("expiry", row.expiry, c.expiry), ("strike", row.strike, c.strike),
            ("type", row.instrument_type, c.instrument_type)) if theirs != ours)
        if diffs:
            disagreements.append(Disagreement(row.exchange_token, diffs))
            continue
        matched.append(FreezeMatch(iid, row.freeze_limit))
    return FreezeJoin(tuple(matched), tuple(disagreements), absent)


__all__ = ["REQUIRED_COLUMNS", "Disagreement", "FreezeFile", "FreezeJoin", "FreezeMatch", "FreezeRow", "file_date_from_name",
           "match_to_catalogue", "parse_freeze_file", "parse_freeze_rows"]
