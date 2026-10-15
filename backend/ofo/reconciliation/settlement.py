"""Expiry is a settlement event (ADR-083, W-085): an expired leg is closed at the exchange settlement price.

Spec: ADR-083 ("a leg whose contract has expired is closed in the platform at the exchange settlement price, with a
timeline entry"; "a strategy with no legs left becomes Exited"); REQ-060 AC-2 (an expired leg is not a missing
platform position); REQ-039 AC-2 (Exited is a recorded transition); ADR-008 (money is exact Decimal; the engine's
``position_pnl`` is the one P&L formula).

Pure domain code. The settlement price comes from an injected ``settlement_source`` (contract -> per-unit price, or
None when it is not available yet). That source is UNPROVEN against the exchange's real settlement price
(ADR-083 consequences): this module never guesses a price. With no price, or no entry price to compute the realized
P&L against, the leg stays open and the strategy is flagged as awaiting settlement. Not here: the scheduler that
calls this after the close, and the screen.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Mapping

from ofo.engine.legs import Action, Leg, position_pnl, require_price
from ofo.strategy.definition import Contract, describe_contract
from ofo.strategy.versions import StrategyRecord
from ofo.timeline.catalogue import EntryType
from ofo.timeline.log import Timeline

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

#: Earliest time of day, on the expiry day itself, at which the platform treats a leg as expired. SENSEX options
#: traded until 15:39 on an expiry day (finding F-33, whose exact close is still an open point), later than the
#: 15:30 ``EXPIRY_CLOSE`` of the pricing model, so the later time is used: settling at 15:30 would close a leg that
#: can still trade. The days after expiry need no time of day.
EXPIRY_DAY_SETTLE_FROM = datetime.time(15, 39)

SettlementSource = Callable[[Contract], "Decimal | None"]


class SettlementError(ValueError):
    """The settlement source answered with something that is not a price, or an input is malformed."""


@dataclass(frozen=True)
class SettledLeg:
    contract: Contract
    units: int  # signed: long positive, short negative
    settlement_price: Decimal
    entry_price: Decimal
    realized_pnl: Decimal


@dataclass(frozen=True)
class SettlementResult:
    settled: tuple[SettledLeg, ...]
    awaiting: tuple[Contract, ...]  # expired legs left open: no settlement price (or no entry price) yet
    exited: bool  # the last leg settled and the strategy became Exited


def is_expired(contract: Contract, now: datetime.datetime) -> bool:
    """Expired: its expiry date is before ``now``'s trading date (IST), or is that date and the close has passed."""
    expiry = contract[3]
    local = now.astimezone(IST)
    today = local.date()
    return expiry < today or (expiry == today and local.time() >= EXPIRY_DAY_SETTLE_FROM)


def _checked_value(value: object, contract: Contract) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise SettlementError(f"settlement price for {describe_contract(contract)} must be a Decimal, got {value!r}")
    try:
        return require_price(value, "price")
    except ValueError as exc:
        raise SettlementError(f"settlement price for {describe_contract(contract)}: {exc}") from exc


def settle_expired_legs(
    strategy: StrategyRecord,
    now: datetime.datetime,
    settlement_source: SettlementSource,
    entry_prices: Mapping[Contract, Decimal],
    *,
    external_changes: Mapping[Contract, int] | None = None,
    timeline: Timeline | None = None,
    actor: str = "system",
) -> SettlementResult:
    """Close every expired leg of ``strategy`` that has a settlement price; flag the rest as awaiting settlement.

    ``entry_prices`` is the price each leg was entered at (a definition keeps none); the realized P&L is the engine's
    ``position_pnl`` at the settlement price. One timeline entry per settled leg (EXIT, contract / price / units /
    P&L), then, when no leg is left, a COMPLETION entry and the strategy's recorded transition to Exited. An exited
    strategy has nothing to settle. A strategy blocked by reconciliation, or with a proposal in flight, is refused
    (``VersionError``): settling would write over a position nobody has resolved.

    ``external_changes`` is ``unexplained_changes`` for the run (REQ-060 AC-4). A held, expired contract with an
    unexplained change is never settled over: the call raises ``SettlementError`` and changes nothing (the user's
    own exit in Zerodha would otherwise be booked at the settlement price, a wrong realized P&L). The settlement
    source must return None until the exchange's final price is published: there is no correction path after
    settling. The strategy's awaiting and settled sets are in memory only; persisting them is the next step.

    Atomic: the timeline entries are first written to a throwaway copy of the timeline; if that fails, nothing is
    changed. Only then are the legs closed and the real timeline written.
    """
    if not isinstance(strategy, StrategyRecord):
        raise SettlementError(f"strategy must be a StrategyRecord, got {strategy!r}")
    if not isinstance(now, datetime.datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise SettlementError(f"now must be a timezone-aware datetime, got {now!r}")
    if strategy.exited or strategy.active_version is None:
        return SettlementResult((), (), False)
    held = strategy.active_version.intended_position.as_dict()
    for contract, change in (external_changes or {}).items():
        if change and contract in held and is_expired(contract, now):
            raise SettlementError(
                f"{describe_contract(contract)} has an unexplained external change ({change:+d}); not settled")
    settled: list[SettledLeg] = []
    awaiting: list[Contract] = []
    for contract in sorted((c for c in held if is_expired(c, now)), key=lambda c: (c[3], c[1].value, c[2] or 0)):
        price = _checked_value(settlement_source(contract), contract)
        entry = entry_prices.get(contract)
        if price is None or entry is None:
            awaiting.append(contract)
            continue
        units = held[contract]
        leg = Leg(Action.BUY if units > 0 else Action.SELL, contract[1], contract[2], contract[3], abs(units), entry)
        settled.append(SettledLeg(contract, units, price, entry, position_pnl(leg, price)))
    reference = f"settled:{now.astimezone(IST).isoformat()}:{len(strategy.outcomes)}"
    exited = bool(settled) and len(settled) == len(held)
    entries = [
        (EntryType.EXIT, {
            "event": "leg_settled",
            "contract": describe_contract(leg.contract),
            "settlement_price": str(leg.settlement_price),
            "units": leg.units,
            "realized_pnl": str(leg.realized_pnl),
        }) for leg in settled
    ]
    if exited:
        entries.append((EntryType.COMPLETION, {"event": "all_legs_settled", "transition": "exited"}))

    def write(target: Timeline) -> None:
        for entry_type, detail in entries:
            target.append(entry_type, at=now, actor=actor, detail=detail)

    if timeline is not None and entries:
        write(Timeline.from_entries(timeline.strategy_id, timeline.entries, clock=timeline._clock))  # dry run
    contracts = [leg.contract for leg in settled]
    strategy.check_settlement(contracts, awaiting, at=now, reference=reference)  # every refusal, before any write
    if timeline is not None:
        write(timeline)  # the only step that can fail now (storage); the record is still untouched
    strategy.settle_legs(contracts, awaiting, at=now, reference=reference)  # in-memory, cannot fail after the check
    return SettlementResult(tuple(settled), tuple(awaiting), exited)
