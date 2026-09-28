"""AC-2 tests: contract catalogue derived from a real Zerodha instrument-list slice.

Fixture: tests/fixtures/instruments/instruments_slice.csv — a real slice of
https://api.kite.trade/instruments captured 2026-09-29 (see that folder's README.md).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.instruments.catalogue import Catalogue
from ofo.instruments.eligibility import EligibilityRegistry, EligibilityStatus
from ofo.instruments.models import Contract
from ofo.instruments.parser import parse_instruments_csv

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "instruments_slice.csv"

NIFTY_NEAR_EXPIRY = date(2026, 9, 29)
NIFTY_FAR_EXPIRY = date(2026, 10, 6)
SENSEX_NEAR_EXPIRY = date(2026, 10, 1)
SENSEX_FAR_EXPIRY = date(2026, 10, 8)


@pytest.fixture()
def contracts() -> list[Contract]:
    return parse_instruments_csv(FIXTURE)


@pytest.fixture()
def catalogue(contracts: list[Contract]) -> Catalogue:
    cat = Catalogue()
    cat.load(contracts)
    return cat


def test_core_nifty_strike_gap_and_lot_size(catalogue: Catalogue) -> None:
    """AC-2 (core proof): the real fixture yields NIFTY strike gap 50 and lot size 65."""
    assert catalogue.strike_gap("NIFTY", NIFTY_NEAR_EXPIRY) == Decimal("50")
    assert catalogue.lot_size("NIFTY", NIFTY_NEAR_EXPIRY) == 65


def test_core_sensex_strike_gap_and_lot_size(catalogue: Catalogue) -> None:
    """AC-2 (core proof): the real fixture yields SENSEX strike gap 100 and lot size 20."""
    assert catalogue.strike_gap("SENSEX", SENSEX_NEAR_EXPIRY) == Decimal("100")
    assert catalogue.lot_size("SENSEX", SENSEX_NEAR_EXPIRY) == 20


def test_strike_gap_and_lot_size_hold_for_second_expiry(catalogue: Catalogue) -> None:
    """AC-2: the derived values are not a fluke of one expiry — the second nearest expiry agrees."""
    assert catalogue.strike_gap("NIFTY", NIFTY_FAR_EXPIRY) == Decimal("50")
    assert catalogue.lot_size("NIFTY", NIFTY_FAR_EXPIRY) == 65
    assert catalogue.strike_gap("SENSEX", SENSEX_FAR_EXPIRY) == Decimal("100")
    assert catalogue.lot_size("SENSEX", SENSEX_FAR_EXPIRY) == 20


def test_catalogue_filters_out_unrelated_instruments(catalogue: Catalogue, contracts: list[Contract]) -> None:
    """AC-2: the catalogue only holds NIFTY(NFO)/SENSEX(BFO) rows, not the whole instrument list."""
    total_rows = len(contracts)
    catalogue_rows = len(catalogue.all_entries())
    assert catalogue_rows < total_rows  # the fixture includes ~20 unrelated rows the catalogue must drop
    for entry in catalogue.all_entries():
        assert entry.contract.name in ("NIFTY", "SENSEX")
        assert entry.contract.exchange in ("NFO", "BFO")


def test_catalogue_includes_futures(catalogue: Catalogue) -> None:
    """AC-2: NIFTY/SENSEX futures are part of the catalogue too, not just options."""
    futures = [e.contract for e in catalogue.all_entries() if e.contract.is_future()]
    names = {c.name for c in futures}
    assert "NIFTY" in names
    assert "SENSEX" in names


def test_update_marks_missing_contract_not_listed_never_deletes(catalogue: Catalogue, contracts: list[Contract]) -> None:
    """AC-2: a contract absent from a newer list is marked not currently listed, never deleted."""
    before_count = len(catalogue.all_entries())

    # Simulate a refresh where one NIFTY contract from the near expiry has expired off the list.
    nifty_near = [
        c for c in contracts if c.name == "NIFTY" and c.expiry == NIFTY_NEAR_EXPIRY
    ]
    assert nifty_near, "fixture must contain NIFTY near-expiry rows"
    dropped_token = nifty_near[0].instrument_token
    newer_list = [c for c in contracts if c.instrument_token != dropped_token]

    result = catalogue.update(newer_list)

    after_count = len(catalogue.all_entries())
    assert after_count == before_count, "the entry must still be present (never deleted)"
    assert result.newly_unlisted == 1

    dropped_entry = next(
        e for e in catalogue.all_entries() if e.contract.instrument_token == dropped_token
    )
    assert dropped_entry.currently_listed is False


def test_update_relists_a_contract_that_reappears(catalogue: Catalogue, contracts: list[Contract]) -> None:
    """AC-2 negative case: a contract that disappears then reappears in a later list is relisted."""
    nifty_near = [c for c in contracts if c.name == "NIFTY" and c.expiry == NIFTY_NEAR_EXPIRY]
    token = nifty_near[0].instrument_token

    catalogue.update([c for c in contracts if c.instrument_token != token])
    entry = next(e for e in catalogue.all_entries() if e.contract.instrument_token == token)
    assert entry.currently_listed is False

    catalogue.update(contracts)  # full list again, including the previously dropped contract
    entry = next(e for e in catalogue.all_entries() if e.contract.instrument_token == token)
    assert entry.currently_listed is True


def test_catalogue_and_eligibility_are_separate_structures(catalogue: Catalogue) -> None:
    """AC-2: the catalogue never merges current eligibility into a contract record."""
    registry = EligibilityRegistry()
    some_entry = catalogue.all_entries()[0]
    token = some_entry.contract.instrument_token

    # Recording eligibility must not be reachable from, or reflected on, the catalogue entry.
    from datetime import datetime

    registry.record(
        EligibilityStatus(instrument_token=token, tradable=False, checked_at=datetime(2026, 9, 29))
    )

    assert not hasattr(some_entry.contract, "tradable")
    assert not hasattr(some_entry, "tradable")
    assert not hasattr(Catalogue, "eligibility")
    # The registry, not the catalogue, is the authority on current tradability.
    assert registry.is_tradable(token) is False


def test_lot_size_raises_for_underlying_with_no_contracts(catalogue: Catalogue) -> None:
    """AC-2 negative case: deriving a lot size for an underlying/expiry with no data fails closed."""
    with pytest.raises(ValueError):
        catalogue.lot_size("NIFTY", date(2099, 1, 1))


def test_strike_gap_raises_for_fewer_than_two_strikes() -> None:
    """AC-2 negative case: a single-strike expiry cannot yield a gap; must fail closed, not guess."""
    cat = Catalogue()
    contract = Contract(
        instrument_token=1,
        exchange_token=1,
        tradingsymbol="NIFTY26SEP23150CE",
        name="NIFTY",
        expiry=NIFTY_NEAR_EXPIRY,
        strike=Decimal("23150"),
        tick_size=Decimal("0.05"),
        lot_size=65,
        instrument_type="CE",
        segment="NFO-OPT",
        exchange="NFO",
    )
    cat.load([contract])
    with pytest.raises(ValueError):
        cat.strike_gap("NIFTY", NIFTY_NEAR_EXPIRY)
