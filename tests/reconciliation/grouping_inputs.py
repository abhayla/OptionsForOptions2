"""Shared inputs for the W-083 position-grouping tests (REQ-061, ADR-084).

The catalogue is the REAL Zerodha instrument-list slice (tests/fixtures/instruments/, captured 2026-09-29), so every
symbol below is a real catalogue symbol. The POSITION rows are built to Kite's documented position shape
(`tradingsymbol`, `exchange`, `instrument_token`, `product`, `quantity`, `average_price`, `last_price`); the owner's
account held no positions on 2026-10-15, so the row shape is unproven on real data until the Stage 4b order (ADR-084).
The brief's 19-Oct / 26-Oct example expiries are not in the slice; the slice's NIFTY 2026-10-06 (condor) and NIFTY
2026-09-29 (second expiry) play those parts.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from pathlib import Path

from ofo.audit import AuditLog
from ofo.engine import Action, Instrument
from ofo.instruments import Catalogue, parse_instruments_csv
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo.strategy.loader import load_templates

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "instruments_slice.csv"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
EXP_CONDOR = datetime.date(2026, 10, 6)  # NIFTY weekly, lot 65
EXP_SECOND = datetime.date(2026, 9, 29)  # NIFTY monthly, lot 65
LOT = 65
SPOTS = {"NIFTY": D("23300"), "SENSEX": D("75600")}

CONDOR_SYMBOLS = ("NIFTY26O0622800PE", "NIFTY26O0623000PE", "NIFTY26O0623400CE", "NIFTY26O0623600CE")
IN_STRATEGY = "NIFTY26O0623200CE"  # already a leg of strategy S-1
SECOND_EXPIRY_CALL = "NIFTY26SEP24050CE"
SENSEX_PUT = "SENSEX26O0175600PE"

_catalogue: Catalogue | None = None


def catalogue() -> Catalogue:
    global _catalogue
    if _catalogue is None:
        cat = Catalogue()
        cat.load(parse_instruments_csv(FIXTURE))
        _catalogue = cat
    return _catalogue


def templates():
    return load_templates()


def token_of(symbol: str) -> str:
    (entry,) = catalogue().entries_for_broker_symbol("zerodha", symbol)
    return entry.broker_refs["zerodha"].broker_token


def instrument_id_of(symbol: str):
    (entry,) = catalogue().entries_for_broker_symbol("zerodha", symbol)
    return entry.id


def row(symbol: str, quantity: int, average_price: str, product: str = "NRML", *, exchange: str = "NFO",
        token: str | None = None, last_price: str = "50.00") -> dict:
    """A Kite position row (documented shape). ``token`` overrides the instrument token (a renamed-symbol row)."""
    return {
        "tradingsymbol": symbol,
        "exchange": exchange,
        "instrument_token": int(token if token is not None else token_of(symbol)),
        "product": product,
        "quantity": quantity,
        "average_price": D(average_price),
        "last_price": D(last_price),
    }


def seven_rows() -> list[dict]:
    """The core input: a 4-leg condor, a second-expiry short call, a SENSEX short put, and one in-strategy leg."""
    return [
        row("NIFTY26O0622800PE", LOT, "42.50", "NRML"),
        row("NIFTY26O0623000PE", -LOT, "86.00", "MIS"),
        row("NIFTY26O0623400CE", -LOT, "91.50", "NRML"),
        row("NIFTY26O0623600CE", LOT, "44.00", "NRML"),
        row(SECOND_EXPIRY_CALL, -LOT, "120.25", "NRML"),
        row(SENSEX_PUT, -20, "310.40", "NRML", exchange="BFO"),
        row(IN_STRATEGY, -LOT, "70.00", "NRML"),
    ]


def strategies() -> dict:
    """S-1 holds NIFTY 23200 CE 2026-10-06 (the in-strategy leg)."""
    return {"S-1": StrategyDefinition("NIFTY", (DefinitionLeg(Action.SELL, Instrument.CE, D("23200"), EXP_CONDOR, LOT),))}


def clock() -> datetime.datetime:
    return datetime.datetime(2026, 10, 1, 10, 0, tzinfo=IST)


def audit_log() -> AuditLog:
    return AuditLog()
