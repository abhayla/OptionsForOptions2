"""AC-2 tests: contract catalogue derived from a real Zerodha instrument-list slice.

Fixture: tests/fixtures/instruments/instruments_slice.csv — a real slice of
https://api.kite.trade/instruments captured 2026-09-29 (see that folder's README.md).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.instruments.catalogue import DEFAULT_MAX_UNLIST_SHARE, Catalogue, ContractKind
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


def test_update_refuses_when_it_would_unlist_more_than_default_share_for_one_underlying(
    catalogue: Catalogue, contracts: list[Contract]
) -> None:
    """update() refuses a source list that would unlist more than 50% of ONE underlying's
    currently listed contracts, even with the OTHER underlying fully present (so this exercises
    the per-underlying SHARE guard specifically, not the zero-rows guard)."""
    before = _listedness_snapshot(catalogue)
    # Keep only NIFTY CE near-expiry rows (~29% of all NIFTY) plus every SENSEX row: NIFTY would
    # lose >50%, SENSEX loses nothing.
    nifty_small_slice = [
        c for c in contracts if c.name == "NIFTY" and c.instrument_type == "CE" and c.expiry == NIFTY_NEAR_EXPIRY
    ]
    sensex_full = [c for c in contracts if c.name == "SENSEX"]
    truncated = nifty_small_slice + sensex_full
    nifty_total = sum(1 for c in contracts if c.name == "NIFTY")
    assert nifty_small_slice and len(nifty_small_slice) < nifty_total * 0.5

    with pytest.raises(ValueError, match="NIFTY"):
        catalogue.update(truncated)

    after = _listedness_snapshot(catalogue)
    assert after == before, "a refused update must change nothing"


def test_update_refuses_a_nifty_less_slice_of_the_real_fixture(
    catalogue: Catalogue, contracts: list[Contract]
) -> None:
    """AC-2 fix round 3 (real-data proof): dropping ALL NIFTY rows from the real fixture must be
    refused per-underlying, even though NIFTY is only ~44% of the WHOLE catalogue (under the 50%
    global threshold that let this through before). Catalogue is unchanged after the refusal."""
    before = _listedness_snapshot(catalogue)
    nifty_less = [c for c in contracts if c.name != "NIFTY"]
    assert any(c.name == "SENSEX" for c in nifty_less)  # a real, non-empty, plausible feed

    with pytest.raises(ValueError, match="NIFTY"):
        catalogue.update(nifty_less)

    after = _listedness_snapshot(catalogue)
    assert after == before, "a refused update must change nothing"


def test_update_refuses_a_halfway_cut_of_the_real_fixture(
    catalogue: Catalogue, contracts: list[Contract]
) -> None:
    """AC-2 fix round 3 (real-data proof): the fixture cut at its halfway row (as the real full
    instrument list was, per the verifier's finding) drops NIFTY entirely — must be refused."""
    before = _listedness_snapshot(catalogue)
    half = len(contracts) // 2
    halfway_cut = contracts[:half]
    assert not any(c.name == "NIFTY" for c in halfway_cut), (
        "fixture ordering assumption: the first half must contain zero NIFTY rows for this to "
        "be the real scenario the verifier found"
    )

    with pytest.raises(ValueError):
        catalogue.update(halfway_cut)

    after = _listedness_snapshot(catalogue)
    assert after == before, "a refused update must change nothing"


def test_mutation_whole_catalogue_share_would_have_missed_dropping_all_nifty(
    catalogue: Catalogue, contracts: list[Contract]
) -> None:
    """Mutation-style: prove the fix DISCRIMINATES. On the real fixture, NIFTY is 481/1085 (~44%)
    of the whole catalogue — under the 50% default — so a whole-catalogue share check would NOT
    have refused dropping all NIFTY rows. The per-underlying check (100% of NIFTY specifically)
    correctly refuses it. If catalogue.update() ever reverts to a whole-catalogue share, this
    test's own precondition proves the bug would go undetected by the old check, while the
    refusal assertion below would then fail (the test goes red)."""
    total_listed = len(catalogue.all_entries())
    nifty_listed = sum(1 for e in catalogue.all_entries() if e.contract.name == "NIFTY")
    whole_catalogue_share_if_nifty_dropped = nifty_listed / total_listed
    assert whole_catalogue_share_if_nifty_dropped < DEFAULT_MAX_UNLIST_SHARE, (
        "precondition: dropping all NIFTY must be UNDER the global threshold, proving a "
        "whole-catalogue check would have missed it"
    )

    nifty_less = [c for c in contracts if c.name != "NIFTY"]
    with pytest.raises(ValueError):
        catalogue.update(nifty_less)  # the per-underlying check still catches it


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
