"""Compare Zerodha's net quantity per contract with the strategies' active versions plus recorded standalones.

Spec: REQ-060 AC-2, AC-3, AC-4, AC-7; ADR-016 (Zerodha is the authority on actual positions); ADR-018 (Q196 "on
difference ... stop assuming"; Q197 outside changes recorded as an external change; Q199 a mismatch blocks
execution); ADR-019 Q200 (Partially Executed, Reconciliation Required, Exited).

Pure: the broker's net positions are an INPUT (contract -> signed units, long positive, short negative). Nothing
here calls the broker or changes a strategy record; ``resolution.record_report`` applies a report.

Allocation rule (REQ-060 AC-7, "compares Zerodha's net quantity per contract with the strategy legs plus the
recorded standalone quantity"; "a mismatch blocks only the strategy whose contract quantity disagrees"):

- expected[c] = recorded standalone units on c + the sum of every non-exited strategy's ACTIVE-version units on c.
- difference[c] = broker[c] - expected[c]. A contract with difference 0 is no mismatch, whoever holds it.
- A non-zero difference on a contract is attributed to EVERY strategy holding that contract (in its active version
  or its pending proposed version), and blocks each of them. Fail closed: the broker reports one net number per
  contract, so it cannot say which holder (or the standalone) moved; blocking only one holder could leave the real
  one executing on a wrong picture. Example (AC-7): strategy SELL 25,000 CE x 50 plus standalone x 25 -> expected
  -75; Zerodha -75: no mismatch; Zerodha -50: that strategy is blocked.
- A non-zero difference on a contract NO strategy holds blocks no strategy: it is an unexpected broker position
  (offer the grouping choice, Q24) or a change to a recorded standalone.

A strategy's "broker share" of a contract is broker[c] - standalone[c] - the other holders' active units on c.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping

from ofo.strategy.definition import MAX_TEXT, Contract, contract_sort_key, describe_contract
from ofo.strategy.versions import MAX_FUTURE_SKEW, MAX_UNITS, Position, StrategyRecord, VersionError, check_contract

#: An account's net-position map and a recorded-standalone map are capped (absurd-size guard, fail closed).
MAX_CONTRACTS = 1_000
MAX_STRATEGIES = 1_000

#: The holder label used for the recorded standalone quantity in a mismatch's platform breakdown.
STANDALONE = "standalone"


class ReconciliationError(ValueError):
    """Invalid reconciliation input, or a resolution that is not allowed in the current state."""


class MismatchKind(Enum):
    """AC-2's list, plus a change to a recorded standalone (AC-7: recorded, never blocking)."""

    MISSING_PLATFORM_POSITION = "missing platform position"  # a strategy holds it; the broker shows none of it
    UNEXPECTED_BROKER_POSITION = "unexpected broker position"  # the broker holds it; no strategy, no standalone
    QUANTITY_MISMATCH = "quantity mismatch"
    STRIKE_MISMATCH = "strike mismatch"
    SIDE_MISMATCH = "side mismatch"
    EXPIRY_MISMATCH = "expiry mismatch"
    EXTERNAL_MODIFICATION = "external broker modification"  # a change no platform order/fill explains (AC-4)
    PARTIAL_EXECUTION = "partially executed strategy"
    STANDALONE_CHANGED = "standalone position changed"


_NEXT_ACTION = {
    MismatchKind.MISSING_PLATFORM_POSITION: "Reconcile this strategy: adopt the broker position, prepare a closing or "
    "restoring order, mark as requiring attention, or (if the broker is flat) mark the strategy exited.",
    MismatchKind.QUANTITY_MISMATCH: "Reconcile this strategy: adopt the broker position, prepare a closing or "
    "restoring order, or mark as requiring attention.",
    MismatchKind.EXTERNAL_MODIFICATION: "Review the change made outside the platform, then reconcile: adopt the "
    "broker position, prepare a closing or restoring order, or mark as requiring attention.",
    MismatchKind.PARTIAL_EXECUTION: "Partially executed: Complete Strategy, Retry Failed Leg, Review Manually or "
    "Close Partial Strategy.",
    MismatchKind.UNEXPECTED_BROKER_POSITION: "Choose how to group it: add to an existing strategy, create a new "
    "strategy, or leave it standalone. No strategy is blocked.",
    MismatchKind.STANDALONE_CHANGED: "Review the standalone position and update its recorded quantity. No strategy "
    "is blocked.",
}
for _kind in (MismatchKind.STRIKE_MISMATCH, MismatchKind.SIDE_MISMATCH, MismatchKind.EXPIRY_MISMATCH):
    _NEXT_ACTION[_kind] = _NEXT_ACTION[MismatchKind.QUANTITY_MISMATCH]


@dataclass(frozen=True)
class Mismatch:
    """One recorded mismatch (AC-3): time, broker state, platform state, difference and required next action."""

    kind: MismatchKind
    strategy_ids: tuple[str, ...]  # every strategy it blocks; empty = blocks none
    at: datetime.datetime
    broker_state: tuple[tuple[Contract, int], ...]  # the broker's net units on each contract involved
    platform_state: tuple[tuple[Contract, int], ...]  # expected units (strategies' active versions + standalone)
    platform_breakdown: tuple[tuple[str, Contract, int], ...]  # (strategy id or "standalone", contract, units)
    difference: tuple[tuple[Contract, int], ...]  # broker minus expected, per contract
    next_action: str

    @property
    def blocks(self) -> bool:
        return bool(self.strategy_ids)

    def describe(self) -> str:
        diff = ", ".join(f"{describe_contract(c)} {units:+d}" for c, units in self.difference)
        return f"{self.kind.value}: {diff}"


@dataclass(frozen=True)
class ReconciliationReport:
    """The result of one comparison run. ``mismatches`` is empty when the broker agrees on every contract."""

    at: datetime.datetime
    broker: tuple[tuple[Contract, int], ...]  # the broker's whole net-position map as compared
    mismatches: tuple[Mismatch, ...]
    shares: tuple[tuple[str, Position], ...]  # each blocked strategy's broker share (what adopting would adopt)

    @property
    def blocked_strategy_ids(self) -> frozenset[str]:
        return frozenset(sid for m in self.mismatches for sid in m.strategy_ids)

    def share(self, strategy_id: str) -> Position:
        for sid, position in self.shares:
            if sid == strategy_id:
                return position
        raise ReconciliationError(f"strategy {strategy_id!r} has no mismatch in this report")


# ---- input validation ----------------------------------------------------------------------------------------

def units_map(value: object, label: str) -> dict[Contract, int]:
    """A Position or a contract -> signed-units mapping, validated; zero lines dropped. Fail closed on anything else."""
    if isinstance(value, Position):
        return value.as_dict()
    if not isinstance(value, Mapping):
        raise ReconciliationError(f"{label} must be a Position or a mapping of contract -> signed units, got {value!r}")
    if len(value) > MAX_CONTRACTS:
        raise ReconciliationError(f"{label} has {len(value)} contracts; at most {MAX_CONTRACTS}")
    result: dict[Contract, int] = {}
    for contract, units in value.items():
        try:
            check_contract(contract)
        except VersionError as exc:
            raise ReconciliationError(f"{label}: {exc}") from exc
        if isinstance(units, bool) or not isinstance(units, int) or abs(units) > MAX_UNITS:
            raise ReconciliationError(f"{label}: units must be an int within +/-{MAX_UNITS}, got {units!r}")
        if units:
            result[contract] = units
    return result


def require_time(at: object, clock: Callable[[], datetime.datetime]) -> datetime.datetime:
    if not isinstance(at, datetime.datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ReconciliationError(f"reconciliation time must be a timezone-aware datetime, got {at!r}")
    if at > clock() + MAX_FUTURE_SKEW:
        raise ReconciliationError(f"reconciliation time {at.isoformat()} is in the future")
    return at


def require_id(value: object, label: str = "strategy id") -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT or value == STANDALONE:
        raise ReconciliationError(f"{label} must be a non-empty string of at most {MAX_TEXT} chars (not "
                                  f"{STANDALONE!r}), got {value!r}")
    return value


def _records(strategies: object) -> dict[str, StrategyRecord]:
    if not isinstance(strategies, Mapping):
        raise ReconciliationError(f"strategies must be a mapping of strategy id -> StrategyRecord, got {strategies!r}")
    if len(strategies) > MAX_STRATEGIES:
        raise ReconciliationError(f"{len(strategies)} strategies; at most {MAX_STRATEGIES}")
    seen: set[int] = set()
    for sid, record in strategies.items():
        require_id(sid)
        if not isinstance(record, StrategyRecord):
            raise ReconciliationError(f"strategy {sid!r} must be a StrategyRecord, got {record!r}")
        if id(record) in seen:
            raise ReconciliationError(f"strategy {sid!r} is the same record as another id; one record, one id")
        seen.add(id(record))
    return dict(strategies)


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# ---- comparison ---------------------------------------------------------------------------------------------

def active_units(record: StrategyRecord) -> dict[Contract, int]:
    """The strategy's platform position: its active version's intended units; none once exited or never active."""
    active = record.active_version
    if record.exited or active is None:
        return {}
    return active.intended_position.as_dict()


def _proposed_units(record: StrategyRecord) -> dict[Contract, int] | None:
    proposal = record.proposed_version
    if record.exited or proposal is None:
        return None
    return proposal.intended_position.as_dict()


def expected_units(
    actives: Mapping[str, Mapping[Contract, int]], standalone: Mapping[Contract, int]
) -> dict[Contract, int]:
    """Allocation rule: expected = recorded standalone + the sum of every strategy's active units, per contract."""
    expected = dict(standalone)
    for units in actives.values():
        for contract, value in units.items():
            expected[contract] = expected.get(contract, 0) + value
    return {c: v for c, v in expected.items() if v}


def holders_of(
    contract: Contract,
    actives: Mapping[str, Mapping[Contract, int]],
    proposals: Mapping[str, Mapping[Contract, int] | None],
) -> tuple[str, ...]:
    """Every strategy holding ``contract`` in its active version or its pending proposed version."""
    return tuple(sorted(
        sid for sid in actives
        if contract in actives[sid] or contract in (proposals.get(sid) or {})
    ))


def compare(
    broker_net: object,
    strategies: object,
    standalone: object = None,
    *,
    at: datetime.datetime,
    external: object = None,
    clock: Callable[[], datetime.datetime] = _utc_now,
) -> ReconciliationReport:
    """Compare the broker's net units per contract with strategies + recorded standalone (REQ-060 AC-2/3/4/7).

    ``external`` is the per-contract change no platform order or fill explains (``unexplained_changes``); a
    strategy contract with such a change is reported as an EXTERNAL_MODIFICATION.
    """
    broker = units_map(broker_net, "broker net positions")
    alone = units_map({} if standalone is None else standalone, "standalone quantities")
    outside = units_map({} if external is None else external, "external changes")
    records = _records(strategies)
    require_time(at, clock)

    actives = {sid: active_units(record) for sid, record in records.items()}
    proposals = {sid: _proposed_units(record) for sid, record in records.items()}
    expected = expected_units(actives, alone)
    differing = sorted(
        (c for c in broker.keys() | expected.keys() if broker.get(c, 0) != expected.get(c, 0)), key=contract_sort_key
    )
    diff = {c: broker.get(c, 0) - expected.get(c, 0) for c in differing}
    held = {c: holders_of(c, actives, proposals) for c in differing}

    groups = _pair_moved_contracts(differing, diff, held)
    mismatches = []
    for contracts, kind_hint in groups:
        owners = held[contracts[0]]
        if owners:
            kind = kind_hint or _classify_held(contracts[0], owners, broker, alone, actives, proposals, outside)
        else:
            kind = MismatchKind.STANDALONE_CHANGED if alone.get(contracts[0]) else MismatchKind.UNEXPECTED_BROKER_POSITION
        if owners and any(outside.get(c) for c in contracts):
            kind = MismatchKind.EXTERNAL_MODIFICATION
        breakdown = tuple(
            (holder, c, units)
            for c in contracts
            for holder, units in [(STANDALONE, alone.get(c, 0))] + [(sid, actives[sid].get(c, 0)) for sid in sorted(actives)]
            if units
        )
        mismatches.append(Mismatch(
            kind=kind,
            strategy_ids=owners,
            at=at,
            broker_state=tuple((c, broker.get(c, 0)) for c in contracts),
            platform_state=tuple((c, expected.get(c, 0)) for c in contracts),
            platform_breakdown=breakdown,
            difference=tuple((c, diff[c]) for c in contracts),
            next_action=_NEXT_ACTION[kind],
        ))

    blocked = sorted({sid for m in mismatches for sid in m.strategy_ids})
    shares = tuple((sid, broker_share(sid, broker, alone, actives, proposals, mismatches)) for sid in blocked)
    broker_lines = tuple(sorted(broker.items(), key=lambda item: contract_sort_key(item[0])))
    return ReconciliationReport(at, broker_lines, tuple(mismatches), shares)


def _pair_moved_contracts(
    differing: list[Contract], diff: Mapping[Contract, int], held: Mapping[Contract, tuple[str, ...]]
) -> list[tuple[tuple[Contract, ...], MismatchKind | None]]:
    """Group a held contract with the ONE unheld contract its quantity moved to (strike or expiry changed).

    Pairs only when exactly one unheld contract has the same underlying and instrument, the opposite difference,
    and differs in strike only (STRIKE) or expiry only (EXPIRY). Anything ambiguous stays separate, so an unheld
    contract is never silently attributed to a strategy it may not belong to.
    """
    used: set[Contract] = set()
    groups: list[tuple[tuple[Contract, ...], MismatchKind | None]] = []
    unheld = [c for c in differing if not held[c]]
    for contract in differing:
        if contract in used or not held[contract]:
            continue
        candidates = []
        for other in unheld:
            if other in used or other[:2] != contract[:2] or diff[other] != -diff[contract]:
                continue
            if other[3] == contract[3] and other[2] != contract[2]:
                candidates.append((other, MismatchKind.STRIKE_MISMATCH))
            elif other[2] == contract[2] and other[3] != contract[3]:
                candidates.append((other, MismatchKind.EXPIRY_MISMATCH))
        if len(candidates) == 1:
            other, kind = candidates[0]
            used.update((contract, other))
            groups.append((tuple(sorted((contract, other), key=contract_sort_key)), kind))
        else:
            used.add(contract)
            groups.append(((contract,), None))
    groups.extend(((c,), None) for c in differing if c not in used)
    return groups


def _others_units(sid: str, contract: Contract, actives: Mapping[str, Mapping[Contract, int]]) -> int:
    return sum(units.get(contract, 0) for other, units in actives.items() if other != sid)


def _classify_held(
    contract: Contract,
    owners: tuple[str, ...],
    broker: Mapping[Contract, int],
    alone: Mapping[Contract, int],
    actives: Mapping[str, Mapping[Contract, int]],
    proposals: Mapping[str, Mapping[Contract, int] | None],
    outside: Mapping[Contract, int],
) -> MismatchKind:
    """Kind of a mismatch on a strategy contract whose quantity moved (not to another strike or expiry)."""
    for sid in owners:
        proposal = proposals.get(sid)
        if proposal is None:
            continue
        share = broker.get(contract, 0) - alone.get(contract, 0) - _others_units(sid, contract, actives)
        low, high = sorted((actives[sid].get(contract, 0), proposal.get(contract, 0)))
        if low <= share <= high:
            return MismatchKind.PARTIAL_EXECUTION
    strategies_part = sum(actives[sid].get(contract, 0) for sid in owners)
    broker_part = broker.get(contract, 0) - alone.get(contract, 0)
    if broker_part == 0:
        return MismatchKind.MISSING_PLATFORM_POSITION
    reference = strategies_part or next(
        ((proposals.get(sid) or {}).get(contract, 0) for sid in owners if (proposals.get(sid) or {}).get(contract)), 0
    )
    if reference and (broker_part > 0) != (reference > 0):
        return MismatchKind.SIDE_MISMATCH
    return MismatchKind.QUANTITY_MISMATCH


def broker_share(
    sid: str,
    broker: Mapping[Contract, int],
    alone: Mapping[Contract, int],
    actives: Mapping[str, Mapping[Contract, int]],
    proposals: Mapping[str, Mapping[Contract, int] | None],
    mismatches: tuple[Mismatch, ...] | list[Mismatch],
) -> Position:
    """The strategy's broker share: its active units where the broker agrees; elsewhere broker minus the rest."""
    units = dict(actives[sid])
    involved = {c for m in mismatches if sid in m.strategy_ids for c, _ in m.difference}
    for contract in involved:
        units[contract] = broker.get(contract, 0) - alone.get(contract, 0) - _others_units(sid, contract, actives)
    try:
        return Position.of(units)
    except VersionError as exc:
        raise ReconciliationError(f"strategy {sid!r}: broker share is not a valid position: {exc}") from exc


def unexplained_changes(previous: object, current: object, platform_fills: object) -> dict[Contract, int]:
    """AC-4: per contract, the broker change since the last snapshot that the platform's own fills do not explain.

    ``previous`` and ``current`` are broker net-position snapshots; ``platform_fills`` is the net signed units the
    platform's own orders filled between them (all strategies). A non-zero result is a change made in Zerodha.
    """
    before = units_map(previous, "previous broker positions")
    now = units_map(current, "current broker positions")
    fills = units_map(platform_fills, "platform fills")
    changes = {}
    for contract in before.keys() | now.keys() | fills.keys():
        unexplained = now.get(contract, 0) - before.get(contract, 0) - fills.get(contract, 0)
        if unexplained:
            changes[contract] = unexplained
    return changes
