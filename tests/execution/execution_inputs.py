"""Shared inputs for the pre-execution gate tests (W-014, REQ-059).

The catalogue is the REAL Zerodha instrument-list slice (tests/fixtures/instruments/, captured 2026-09-29). The
strategy is the golden Iron Condor of scenario-calculations.md §6 (same strikes, sides and prices), placed on the
fixture's NIFTY 2026-10-06 expiry with one real lot (65 units) so every contract exists in the real list.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
from collections.abc import Iterable, Mapping
from typing import Any, Callable

import pytest

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.engine.product import Product
from ofo.execution.context import product_key
from ofo.execution import (
    DataHealth,
    DataInput,
    ExecutionAction,
    ExecutionContext,
    SafetyResult,
    VersionState,
    active_legs_hash,
    check_pre_execution,
)
from ofo.instruments import Catalogue, InstrumentId, ZerodhaEligibility, parse_instruments_csv
from ofo.instruments.eligibility import apply_margin_refusals, list_state_from_row, registry_from_list

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "instruments_slice.csv"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
EXPIRY = datetime.date(2026, 10, 6)
LOT = 65
AS_OF = datetime.datetime(2026, 9, 29, 10, 0, tzinfo=IST)


def condor_legs(quantity: int = LOT, expiry: datetime.date = EXPIRY) -> tuple[Leg, ...]:
    return (
        Leg(Action.BUY, Instrument.PE, D("22800"), expiry, quantity, D("42.50")),
        Leg(Action.SELL, Instrument.PE, D("23000"), expiry, quantity, D("86.00")),
        Leg(Action.SELL, Instrument.CE, D("23400"), expiry, quantity, D("91.50")),
        Leg(Action.BUY, Instrument.CE, D("23600"), expiry, quantity, D("44.00")),
    )


@pytest.fixture()
def condor() -> Strategy:
    return Strategy(condor_legs())


@pytest.fixture()
def catalogue() -> Catalogue:
    cat = Catalogue()
    cat.load(parse_instruments_csv(FIXTURE))
    return cat


def zerodha_eligibility(catalogue: Catalogue, *, at: datetime.datetime = AS_OF, today: datetime.date | None = None,
                        omit: Iterable[InstrumentId] = (),
                        refused: Mapping[InstrumentId, str] | None = None) -> ZerodhaEligibility:
    """THE one test path to eligibility (W-092 round 2): synthetic list rows (every catalogue contract listed with a
    Zerodha row, except ``omit``) through the same minting functions production uses - ``list_state_from_row`` ->
    ``registry_from_list`` -> ``apply_margin_refusals``. The gate accepts nothing else, so a test cannot hand-make one.
    ``today`` defaults to the India date of ``at`` (the load time); ``refused`` = margin-reply refusals."""
    skip = set(omit)
    states = [list_state_from_row(SimpleNamespace(
        exchange_segment=e.contract.id.exchange_segment, exchange_token=e.contract.id.exchange_token,
        instrument_type=e.contract.instrument_type, expiry=e.contract.expiry, currently_listed=True, retired=False,
        delisted=False, has_zerodha_row=True)) for e in catalogue.all_entries() if e.contract.id not in skip]
    minted = registry_from_list(states, today=today or at.date(), loaded_at=at)
    return apply_margin_refusals(minted, refused, refused_at=at) if refused else minted


def refuse(eligibility: ZerodhaEligibility, *instrument_ids: InstrumentId, text: str = "OI limit reached",
           at: datetime.datetime = AS_OF) -> ZerodhaEligibility:
    """A NEW eligibility with these contracts refused by the margin reply (the sealed input is never changed)."""
    return apply_margin_refusals(eligibility, dict.fromkeys(instrument_ids, text), refused_at=at)


@pytest.fixture()
def eligibility(catalogue: Catalogue) -> ZerodhaEligibility:
    """Every catalogue contract confirmed tradable (as Zerodha's list load would leave it)."""
    return zerodha_eligibility(catalogue)


class AnyBand(Mapping):
    """A price band for every leg: 0.05 to 1,000,000 (test default; the real band is read from the quote)."""

    def __getitem__(self, key):  # noqa: ANN001, ANN204
        return (D("0.05"), D("1000000"))

    def __iter__(self):  # noqa: ANN204
        return iter(())

    def __len__(self) -> int:
        return 0


class AnyPrice(Mapping):
    """An adjustment order price for every leg (test default): a real, in-band 50.00."""

    def __getitem__(self, key):  # noqa: ANN001, ANN204
        return D("50.00")

    def __iter__(self):  # noqa: ANN204
        return iter(())

    def __len__(self) -> int:
        return 0


def all_true_context(**overrides: Any) -> ExecutionContext:
    base = ExecutionContext(
        strategy_id="S-1",
        version_id="V-3",
        actor="user:U-42",
        underlying="NIFTY",
        action=ExecutionAction.NEW_ENTRY,
        as_of=AS_OF,
        market_open=True,
        platform_paused=False,
        broker_connected=True,
        session_valid=True,
        pro_entitled=True,
        version_state=VersionState.ACTIVE,
        rules_valid=True,
        dependencies_satisfied=True,
        data_health={d: DataHealth.HEALTHY for d in DataInput},
        margin_available=D("150000.00"),
        margin_required=D("48210.75"),
        reconciliation_blocked_strategy_ids=frozenset({"S-OTHER"}),
        charges_estimate=D("236.40"),
    )
    overrides.setdefault("price_bands", AnyBand())
    overrides.setdefault("order_prices", AnyPrice())  # a band wide enough for any test price; tests override or pass None
    if overrides.get("action") is ExecutionAction.EXIT and overrides.get("active_legs") is not None:
        # an EXIT whose position and order products both read NRML, unless a test says otherwise (explicit None blocks)
        held = {product_key(leg): Product.NRML for leg in overrides["active_legs"]}
        overrides.setdefault("active_products", held)
        overrides.setdefault("exit_products", held)
    active = overrides.get("active_legs")
    # The active version as the store would give it, unless a test overrides the tie; malformed legs pass straight
    # through so the context's own validation refuses them.
    if active is not None and all(isinstance(leg, Leg) for leg in active):
        overrides.setdefault("active_version_id", ACTIVE_VERSION_ID)
        overrides.setdefault("active_futures_entry_known", True)  # hand-built legs carry real entries
        overrides.setdefault("active_legs_hash", active_legs_hash(
            overrides.get("strategy_id", STRATEGY_ID), overrides["active_version_id"], active))
    return dataclasses.replace(base, **overrides)


ACTIVE_VERSION_ID = "V-2"


@pytest.fixture()
def make_context() -> Callable[..., ExecutionContext]:
    return all_true_context


STRATEGY_ID = "S-1"


def check(
    strategy: Strategy, ctx: ExecutionContext, catalogue: Catalogue, eligibility: ZerodhaEligibility,
    strategy_id: str = STRATEGY_ID,
) -> SafetyResult:
    """Run the gate for a strategy whose own id is ``strategy_id`` (every test strategy is S-1 unless stated)."""
    return check_pre_execution(strategy, ctx, catalogue, eligibility, strategy_id=strategy_id)


def closing_orders(legs: tuple[Leg, ...]) -> tuple[Leg, ...]:
    """The orders that close ``legs``: same contract and quantity, opposite side."""
    flip = {Action.BUY: Action.SELL, Action.SELL: Action.BUY}
    return tuple(dataclasses.replace(leg, action=flip[leg.action]) for leg in legs)


def find_token(catalogue: Catalogue, instrument_type: str, strike: str, expiry: datetime.date = EXPIRY):
    (contract,) = [
        c for c in catalogue.contracts_for("NIFTY", expiry, frozenset({instrument_type})) if c.strike == D(strike)
    ]
    return contract.id  # the exchange identity (ADR-050)
