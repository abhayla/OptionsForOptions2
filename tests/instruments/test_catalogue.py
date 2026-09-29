"""AC-2 tests: contract catalogue derived from a real Zerodha instrument-list slice.

Fixture: tests/fixtures/instruments/instruments_slice.csv — a real slice of
https://api.kite.trade/instruments captured 2026-09-29 (see that folder's README.md).
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone
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


IST = timezone(timedelta(hours=5, minutes=30))
# The fixture was captured 2026-09-29; its earliest expiry is that same day.
ON_EXPIRY_DAY = datetime(2026, 9, 29, 15, 0, tzinfo=IST)
DAY_AFTER_EXPIRY = datetime(2026, 9, 30, 9, 0, tzinfo=IST)


def _snapshot(catalogue: Catalogue) -> dict[int, bool]:
    return {e.contract.instrument_token: e.currently_listed for e in catalogue.all_entries()}


def _entry(catalogue: Catalogue, token: int):
    return next(e for e in catalogue.all_entries() if e.contract.instrument_token == token)


def test_core_update_refuses_dropping_one_live_contract(catalogue: Catalogue, contracts: list[Contract]) -> None:
    """AC-2: removing ONE unexpired NIFTY option row is refused, naming it; nothing changes."""
    victim = next(c for c in contracts if c.name == "NIFTY" and c.instrument_type == "CE" and c.expiry == NIFTY_FAR_EXPIRY)
    before = _snapshot(catalogue)
    with pytest.raises(ValueError, match=victim.tradingsymbol):
        catalogue.update([c for c in contracts if c.instrument_token != victim.instrument_token], as_of=ON_EXPIRY_DAY)
    assert _snapshot(catalogue) == before, "a refused update must change nothing"


def test_update_refuses_the_verifier_75_percent_truncation(catalogue: Catalogue, contracts: list[Contract]) -> None:
    """AC-2: the W-006 verifier's truncation (first 75% of NIFTY rows, all else kept) was ACCEPTED
    under the old 50% rule; it must now be refused."""
    nifty = [c for c in contracts if c.name == "NIFTY"]
    kept_nifty = {c.instrument_token for c in nifty[: len(nifty) * 3 // 4]}
    truncated = [c for c in contracts if c.name != "NIFTY" or c.instrument_token in kept_nifty]
    before = _snapshot(catalogue)
    with pytest.raises(ValueError, match="refused"):
        catalogue.update(truncated, as_of=ON_EXPIRY_DAY)
    assert _snapshot(catalogue) == before


def test_update_accepts_roll_off_of_an_expired_expiry_never_deletes(
    catalogue: Catalogue, contracts: list[Contract]
) -> None:
    """AC-2: on 2026-09-30 IST every 2026-09-29 contract may roll off; they are marked not
    listed (never deleted) and the rest stay listed."""
    expired = {c.instrument_token for c in contracts if c.expiry == NIFTY_NEAR_EXPIRY}
    assert expired
    before_count = len(catalogue.all_entries())
    result = catalogue.update([c for c in contracts if c.instrument_token not in expired], as_of=DAY_AFTER_EXPIRY)
    assert len(catalogue.all_entries()) == before_count
    in_scope_expired = {t for t in expired if t in _snapshot(catalogue)}
    assert result.newly_unlisted == len(in_scope_expired) > 0
    assert all(not _entry(catalogue, t).currently_listed for t in in_scope_expired)
    assert all(e.currently_listed for e in catalogue.all_entries() if e.contract.expiry != NIFTY_NEAR_EXPIRY)


def test_update_refuses_roll_off_on_the_expiry_day_itself(catalogue: Catalogue, contracts: list[Contract]) -> None:
    """AC-2: a contract expiring on the update date has NOT yet passed; dropping it that day is
    refused (boundary), even at 23:59 IST."""
    expired = {c.instrument_token for c in contracts if c.expiry == NIFTY_NEAR_EXPIRY}
    late = datetime(2026, 9, 29, 23, 59, tzinfo=IST)
    with pytest.raises(ValueError):
        catalogue.update([c for c in contracts if c.instrument_token not in expired], as_of=late)


def test_update_date_is_judged_in_ist_not_utc(catalogue: Catalogue, contracts: list[Contract]) -> None:
    """AC-2: 2026-09-29 20:00 UTC is already 2026-09-30 01:30 IST, so the 09-29 expiry has
    passed and may roll off; the same instant read as a UTC date would refuse it."""
    expired = {c.instrument_token for c in contracts if c.expiry == NIFTY_NEAR_EXPIRY}
    as_of = datetime(2026, 9, 29, 20, 0, tzinfo=timezone.utc)
    catalogue.update([c for c in contracts if c.instrument_token not in expired], as_of=as_of)


def test_update_rejects_a_naive_as_of(catalogue: Catalogue, contracts: list[Contract]) -> None:
    """AC-2: a timezone-naive update time is rejected, not guessed."""
    with pytest.raises(ValueError, match="timezone-aware"):
        catalogue.update(contracts, as_of=datetime(2026, 9, 30, 9, 0))


def test_update_treats_a_contract_with_no_expiry_as_unexpired(contracts: list[Contract]) -> None:
    """AC-2: an in-scope contract with no expiry date can never be shown to have expired, so
    dropping it is refused (fail closed)."""
    odd = dataclasses.replace(next(c for c in contracts if c.name == "NIFTY"), expiry=None)
    cat = Catalogue()
    cat.load([odd])
    with pytest.raises(ValueError, match="refused"):
        cat.update([], as_of=DAY_AFTER_EXPIRY)


def test_update_refuses_empty_list_while_unexpired_contracts_are_listed(catalogue: Catalogue) -> None:
    """AC-2: an empty list would drop every live contract; refused, catalogue unchanged."""
    before = _snapshot(catalogue)
    with pytest.raises(ValueError):
        catalogue.update([], as_of=ON_EXPIRY_DAY)
    assert _snapshot(catalogue) == before


def test_update_accepts_new_expiries_being_added(catalogue: Catalogue, contracts: list[Contract]) -> None:
    """AC-2: additions never trip the guard: load only the far expiries, then update with all."""
    cat = Catalogue()
    cat.load([c for c in contracts if c.expiry != NIFTY_FAR_EXPIRY])
    result = cat.update(contracts, as_of=ON_EXPIRY_DAY)
    assert result.added > 0 and result.newly_unlisted == 0


def test_update_force_overrides_the_guard(catalogue: Catalogue, contracts: list[Contract]) -> None:
    """AC-2: force=True lets a real broker delisting through and marks (never deletes) the rows."""
    victim = next(c for c in contracts if c.name == "NIFTY" and c.expiry == NIFTY_FAR_EXPIRY)
    result = catalogue.update(
        [c for c in contracts if c.instrument_token != victim.instrument_token], as_of=ON_EXPIRY_DAY, force=True
    )
    assert result.newly_unlisted == 1
    assert _entry(catalogue, victim.instrument_token).currently_listed is False


def test_update_relists_a_contract_that_reappears(catalogue: Catalogue, contracts: list[Contract]) -> None:
    """AC-2: a force-delisted contract that reappears in a later list is relisted."""
    token = next(c for c in contracts if c.name == "NIFTY" and c.expiry == NIFTY_NEAR_EXPIRY).instrument_token
    catalogue.update([c for c in contracts if c.instrument_token != token], as_of=ON_EXPIRY_DAY, force=True)
    assert _entry(catalogue, token).currently_listed is False
    catalogue.update(contracts, as_of=ON_EXPIRY_DAY)
    assert _entry(catalogue, token).currently_listed is True


def test_update_normal_refresh_still_works(catalogue: Catalogue, contracts: list[Contract]) -> None:
    """AC-2: an identical list is accepted with nothing added or unlisted."""
    result = catalogue.update(contracts, as_of=ON_EXPIRY_DAY)
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
