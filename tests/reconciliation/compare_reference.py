"""Frozen oracle for W-037's equivalence test: the comparison logic of ``ofo.reconciliation.compare`` exactly as it was
on origin/main at b844ad5 (before W-037 indexed strategies by contract), copied verbatim apart from the names below.

Test-only. It reuses the module's validated input readers and result types (``units_map``, ``_records``,
``require_time``, ``Mismatch``, ``ReconciliationReport``, the next-action table), so the only thing that differs from
the product module is HOW holders, expected units, breakdowns and shares are found -- which is what the equivalence
test compares. Do not "fix" this file: it is the pre-refactor behaviour the new code must reproduce.
"""
from __future__ import annotations

import datetime
from typing import Callable, Mapping

from ofo.reconciliation.compare import (
    _NEXT_ACTION, STANDALONE, Mismatch, MismatchKind, ReconciliationError, ReconciliationReport, _records, _utc_now,
    require_time, units_map,
)
from ofo.strategy.definition import Contract, contract_sort_key
from ofo.strategy.versions import Position, StrategyRecord, VersionError


def active_units(record: StrategyRecord) -> dict[Contract, int]:
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
    return tuple(sorted(
        sid for sid in actives
        if contract in actives[sid] or contract in (proposals.get(sid) or {})
    ))


def compare_reference(
    broker_net: object,
    strategies: object,
    standalone: object = None,
    *,
    at: datetime.datetime,
    external: object = None,
    clock: Callable[[], datetime.datetime] = _utc_now,
) -> ReconciliationReport:
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
        owners = tuple(sorted({sid for contract in contracts for sid in held[contract]}))
        if owners:
            anchor = next(contract for contract in contracts if held[contract])
            kind = kind_hint or _classify_held(anchor, owners, broker, alone, actives, proposals, outside)
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

    covered = sorted(sid for sid, record in records.items() if not record.exited)
    shares = tuple((sid, broker_share(sid, broker, alone, actives, proposals, mismatches)) for sid in covered)
    broker_lines = tuple(sorted(broker.items(), key=lambda item: contract_sort_key(item[0])))
    return ReconciliationReport(at, broker_lines, tuple(mismatches), shares)


def _pair_moved_contracts(
    differing: list[Contract], diff: Mapping[Contract, int], held: Mapping[Contract, tuple[str, ...]]
) -> list[tuple[tuple[Contract, ...], MismatchKind | None]]:
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
    units = dict(actives[sid])
    involved = {c for m in mismatches if sid in m.strategy_ids for c, _ in m.difference}
    for contract in involved:
        units[contract] = broker.get(contract, 0) - alone.get(contract, 0) - _others_units(sid, contract, actives)
    try:
        return Position.of(units)
    except VersionError as exc:
        raise ReconciliationError(f"strategy {sid!r}: broker share is not a valid position: {exc}") from exc
