"""AC-2 tests: contract catalogue derived from a real Zerodha instrument-list slice.

Fixture: tests/fixtures/instruments/instruments_slice.csv — a real slice of
https://api.kite.trade/instruments captured 2026-09-29 (see that folder's README.md).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.instruments.catalogue import Catalogue, ContractKind
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
    """AC-2 (core proof): the real fixture yields NIFTY strike gap 50 and option lot size 65."""
    assert catalogue.strike_gap("NIFTY", NIFTY_NEAR_EXPIRY) == Decimal("50")
    assert catalogue.lot_size("NIFTY", NIFTY_NEAR_EXPIRY, ContractKind.OPTION) == 65


def test_core_sensex_strike_gap_and_lot_size(catalogue: Catalogue) -> None:
    """AC-2 (core proof): the real fixture yields SENSEX strike gap 100 and option lot size 20."""
    assert catalogue.strike_gap("SENSEX", SENSEX_NEAR_EXPIRY) == Decimal("100")
    assert catalogue.lot_size("SENSEX", SENSEX_NEAR_EXPIRY, ContractKind.OPTION) == 20


def test_strike_gap_and_lot_size_hold_for_second_expiry(catalogue: Catalogue) -> None:
    """AC-2: the derived values are not a fluke of one expiry — the second nearest expiry agrees."""
    assert catalogue.strike_gap("NIFTY", NIFTY_FAR_EXPIRY) == Decimal("50")
    assert catalogue.lot_size("NIFTY", NIFTY_FAR_EXPIRY, ContractKind.OPTION) == 65
    assert catalogue.strike_gap("SENSEX", SENSEX_FAR_EXPIRY) == Decimal("100")
    assert catalogue.lot_size("SENSEX", SENSEX_FAR_EXPIRY, ContractKind.OPTION) == 20


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


# --- Fix round 1, defect 1: tick/lot size must never aggregate across option + future rows ---


def test_tick_size_differs_by_kind_on_real_fixture(catalogue: Catalogue) -> None:
    """AC-2 (real-data proof): NIFTY 2026-09-29 options tick 0.05, futures tick 0.1 — no exception,
    and the two kinds are NOT merged into one (inconsistent) aggregate."""
    option_tick = catalogue.tick_size("NIFTY", NIFTY_NEAR_EXPIRY, ContractKind.OPTION)
    future_tick = catalogue.tick_size("NIFTY", NIFTY_NEAR_EXPIRY, ContractKind.FUTURE)
    assert option_tick == Decimal("0.05")
    assert future_tick == Decimal("0.1")
    assert option_tick != future_tick


def test_tick_size_and_lot_size_hold_for_every_expiry_and_kind_in_fixture(
    catalogue: Catalogue, contracts: list[Contract]
) -> None:
    """AC-2 (real-data proof, class-level): loop every underlying+expiry+kind combination present
    in the real fixture — tick_size/lot_size must resolve without exception for each, proving the
    fix covers the whole class, not just the one NIFTY 2026-09-29 instance."""
    combos: set[tuple[str, date, ContractKind]] = set()
    for c in contracts:
        if c.name not in ("NIFTY", "SENSEX") or c.expiry is None:
            continue
        if c.is_option():
            combos.add((c.name, c.expiry, ContractKind.OPTION))
        elif c.is_future():
            combos.add((c.name, c.expiry, ContractKind.FUTURE))

    assert combos, "fixture must contain at least one NIFTY/SENSEX option or future row"

    for name, expiry, kind in combos:
        tick = catalogue.tick_size(name, expiry, kind)
        lot = catalogue.lot_size(name, expiry, kind)
        assert tick > 0
        assert lot > 0


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


# --- Fix round 1, defect 3: update() must refuse an empty or drastically incomplete source list ---


def _listedness_snapshot(catalogue: Catalogue) -> dict[int, bool]:
    return {e.contract.instrument_token: e.currently_listed for e in catalogue.all_entries()}


def test_update_refuses_empty_list(catalogue: Catalogue) -> None:
    """update() refuses an empty new list (would unlist everything); catalogue unchanged."""
    before = _listedness_snapshot(catalogue)
    with pytest.raises(ValueError):
        catalogue.update([])
    after = _listedness_snapshot(catalogue)
    assert after == before, "a refused update must change nothing"


def test_update_refuses_when_it_would_unlist_more_than_default_share(
    catalogue: Catalogue, contracts: list[Contract]
) -> None:
    """update() refuses a source list that would unlist more than 50% of currently listed
    contracts (an incomplete/truncated feed), and leaves the catalogue unchanged."""
    before = _listedness_snapshot(catalogue)
    # Keep only NIFTY near-expiry rows: far below half of everything currently listed.
    truncated = [c for c in contracts if c.name == "NIFTY" and c.expiry == NIFTY_NEAR_EXPIRY]
    assert truncated and len(truncated) < len(contracts) * 0.5

    with pytest.raises(ValueError):
        catalogue.update(truncated)

    after = _listedness_snapshot(catalogue)
    assert after == before, "a refused update must change nothing"


def test_update_force_overrides_the_unlist_share_guard(catalogue: Catalogue, contracts: list[Contract]) -> None:
    """force=True lets a legitimately drastic update (e.g. a real broker delisting wave) through."""
    truncated = [c for c in contracts if c.name == "NIFTY" and c.expiry == NIFTY_NEAR_EXPIRY]
    result = catalogue.update(truncated, force=True)
    assert result.newly_unlisted > 0


def test_update_normal_refresh_still_works(catalogue: Catalogue, contracts: list[Contract]) -> None:
    """A normal update (same list, or dropping a small minority) still succeeds without force."""
    result = catalogue.update(contracts)
    assert result.newly_unlisted == 0
    assert result.added == 0


def test_catalogue_and_eligibility_are_separate_structures(catalogue: Catalogue) -> None:
    """AC-2: the catalogue never merges current eligibility into a contract record."""
    registry = EligibilityRegistry()
    some_entry = catalogue.all_entries()[0]
    token = some_entry.contract.instrument_token

    # Recording eligibility must not be reachable from, or reflected on, the catalogue entry.
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
        catalogue.lot_size("NIFTY", date(2099, 1, 1), ContractKind.OPTION)


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
