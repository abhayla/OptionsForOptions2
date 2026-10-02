"""W-056: a contract's identity is the exchange's (exchange, exchange_token); Zerodha's ids are only broker data.

Spec basis: REQ-054 AC-3 "Each broker's own token, trading symbol and segment code for a contract are stored in a
per-broker table keyed to the contract's identity (exchange segment, exchange token), with one broker code
vocabulary; a contract with no row for a broker cannot be traded at that broker - no symbol is guessed or derived.";
AC-4 "Lot size, tick size and freeze limit are stored per broker with the date the broker's list showed them.";
ADR-050. Expected values are read from the real fixture row (Zerodha's list, captured 2026-09-29), not from the code:
``18920450,73908,NIFTY26SEP23150CE,NIFTY,0,2026-09-29,23150,0.05,65,CE,NFO-OPT,NFO``.
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.instruments import (
    BROKER_CODES,
    BrokerRef,
    Catalogue,
    Contract,
    EligibilityRegistry,
    EligibilityStatus,
    InstrumentId,
    ListedContract,
    MissingBrokerRef,
)
from ofo.instruments.parser import parse_instruments_csv, parse_instruments_rows

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "instruments_slice.csv"
IST = timezone(timedelta(hours=5, minutes=30))
NIFTY_23150_CE = InstrumentId("NSE_FO", 73908)


@pytest.fixture()
def rows() -> list[ListedContract]:
    return parse_instruments_csv(FIXTURE, seen_on=date(2026, 9, 29))


@pytest.fixture()
def catalogue(rows: list[ListedContract]) -> Catalogue:
    cat = Catalogue()
    cat.load(rows)
    return cat


def test_the_contract_holds_no_broker_id_field() -> None:
    """AC-3: the contract type cannot hold Zerodha's token or symbol; identity is (exchange, exchange_token)."""
    names = {f.name for f in dataclasses.fields(Contract)}
    assert "instrument_token" not in names and "tradingsymbol" not in names
    assert {"exchange_segment", "exchange_token"} <= names


def test_real_row_parses_to_exchange_identity_plus_a_zerodha_row(rows: list[ListedContract]) -> None:
    (row,) = [r for r in rows if r.id == NIFTY_23150_CE]
    c = row.contract
    assert (c.exchange_segment, c.name, c.expiry, c.strike, c.instrument_type) == (
        "NSE_FO", "NIFTY", date(2026, 9, 29), Decimal("23150"), "CE")
    ref = row.ref("zerodha")
    assert ref == BrokerRef(broker="zerodha", broker_token="18920450", broker_symbol="NIFTY26SEP23150CE",
                            broker_segment="NFO-OPT", lot_size=65, tick_size=Decimal("0.05"),
                            seen_on=date(2026, 9, 29), freeze_limit=None)


def test_lookup_is_by_instrument_id_not_by_zerodha_token(catalogue: Catalogue) -> None:
    entry = catalogue.get(NIFTY_23150_CE)
    assert entry is not None and entry.ref("zerodha").broker_symbol == "NIFTY26SEP23150CE"
    with pytest.raises(TypeError):
        catalogue.get(18920450)  # Zerodha's instrument_token is not a key
    assert catalogue.get(InstrumentId("BSE_FO", 73908)) is None  # same token in another segment is another contract


def test_one_broker_code_vocabulary_unknown_codes_refused(catalogue: Catalogue) -> None:
    assert BROKER_CODES == frozenset({"zerodha"})
    entry = catalogue.get(NIFTY_23150_CE)
    for code in ("upstox", "Zerodha", "kite", "", None):
        with pytest.raises(MissingBrokerRef):
            entry.ref(code)  # type: ignore[arg-type]
    with pytest.raises(MissingBrokerRef):
        BrokerRef("upstox", "1", "X", "NFO-OPT", 65, Decimal("0.05"), None)


def test_a_contract_with_no_zerodha_row_has_no_symbol(rows: list[ListedContract]) -> None:
    """AC-3: no row for the broker -> refused; nothing is derived from the contract's own fields."""
    (row,) = [r for r in rows if r.id == NIFTY_23150_CE]
    cat = Catalogue()
    cat.load([row.contract])  # bare contract: no broker row
    entry = cat.get(NIFTY_23150_CE)
    assert entry.has_ref("zerodha") is False
    with pytest.raises(MissingBrokerRef, match="has no zerodha row"):
        entry.ref("zerodha")


def test_a_newer_list_replaces_zerodha_row_with_its_new_date_and_lot(rows: list[ListedContract]) -> None:
    """AC-4: the broker's terms follow its newest list, dated by that list."""
    cat = Catalogue()
    cat.load(rows)
    revised = [dataclasses.replace(r, broker_refs=tuple(dataclasses.replace(b, lot_size=75, seen_on=date(2026, 9, 30))
                                                         for b in r.broker_refs))
               if r.id == NIFTY_23150_CE else r for r in rows]
    cat.update(revised, as_of=datetime(2026, 9, 29, 10, 0, tzinfo=IST))
    ref = cat.get(NIFTY_23150_CE).ref("zerodha")
    assert (ref.lot_size, ref.seen_on) == (75, date(2026, 9, 30))


def test_eligibility_is_keyed_by_instrument_id(catalogue: Catalogue) -> None:
    reg = EligibilityRegistry()
    reg.record(EligibilityStatus(NIFTY_23150_CE, True, datetime(2026, 9, 29, 10, 0, tzinfo=IST)))
    assert reg.is_tradable(NIFTY_23150_CE) and not reg.is_tradable(InstrumentId("NSE_FO", 73909))
    with pytest.raises(TypeError):
        reg.record(EligibilityStatus(18920450, True, datetime(2026, 9, 29, 10, 0, tzinfo=IST)))  # type: ignore[arg-type]


def test_a_row_without_an_exchange_identity_stops_the_load() -> None:
    good = {"instrument_token": "18920450", "exchange_token": "73908", "tradingsymbol": "NIFTY26SEP23150CE",
            "name": "NIFTY", "last_price": "0", "expiry": "2026-09-29", "strike": "23150", "tick_size": "0.05",
            "lot_size": "65", "instrument_type": "CE", "segment": "NFO-OPT", "exchange": "NFO"}
    for field, bad in (("exchange_token", "0"), ("exchange_token", ""), ("exchange_token", "x1")):
        with pytest.raises(ValueError):
            list(parse_instruments_rows([{**good, field: bad}]))


def test_two_rows_with_one_identity_refuse_the_list(rows: list[ListedContract]) -> None:
    """Fail closed: the same (exchange, exchange_token) twice in one list is refused, nothing changes."""
    (row,) = [r for r in rows if r.id == NIFTY_23150_CE]
    twin = dataclasses.replace(row, broker_refs=(dataclasses.replace(row.ref("zerodha"), broker_token="1"),))
    cat = Catalogue()
    with pytest.raises(ValueError, match="share the identity NSE_FO:73908"):
        cat.load(rows + [twin])
    assert cat.all_entries() == []
