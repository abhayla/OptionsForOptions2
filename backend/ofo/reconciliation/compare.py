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
  or its pending proposed version), and blocks each of them. ORCHESTRATOR DEFAULT (W-021 fix round, 2026-09-29;
  not an owner decision): AC-7 says "a mismatch blocks only the strategy whose contract quantity disagrees", but
  when two strategies share a contract the broker's single net number cannot show which one's quantity moved, so
  both are treated as disagreeing and both are blocked (fail closed): blocking only one could leave the real one
  executing on a wrong picture. Example (AC-7): strategy SELL 25,000 CE x 50 plus standalone x 25 -> expected
  -75; Zerodha -75: no mismatch; Zerodha -50: that strategy is blocked.
- A non-zero difference on a contract NO strategy holds blocks no strategy: it is an unexpected broker position
  (offer the grouping choice, Q24) or a change to a recorded standalone.

A strategy's "broker share" of a contract is broker[c] - standalone[c] - the other holders' active units on c.
"""
from __future__ import annotations

from ofo.errors.user_facing import UserFacing

import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping

from ofo.errors import CATALOGUE, UserFacingError, display_text, render
from ofo.strategy.definition import MAX_TEXT, Contract, contract_sort_key, describe_contract
from ofo.strategy.versions import MAX_FUTURE_SKEW, MAX_UNITS, Position, StrategyRecord, VersionError, check_contract

#: An account's net-position map and a recorded-standalone map are capped (absurd-size guard, fail closed).
MAX_CONTRACTS = 1_000
MAX_STRATEGIES = 1_000

#: The holder label used for the recorded standalone quantity in a mismatch's platform breakdown.
STANDALONE = "standalone"


class ReconciliationError(UserFacing, ValueError):
    """Invalid reconciliation input, or a resolution that is not allowed in the current state.

    ``str(error)`` is the developer detail (a malformed input, named with its value); it is never shown to a user.
    When an error does reach a user, ``message`` is the four-part ``UserFacingError`` from ``ofo.errors.render()``
    (W-024 round 9); the detail stays beside it for the log."""

    def __init__(self, detail: str = "", *, message: object | None = None) -> None:
        super().__init__(detail)
        if message is not None and type(message) is not UserFacingError:
            raise TypeError(f"ReconciliationError.message must come from render(), got {type(message).__name__}")
        self.message = message


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


#: The catalogue template for each kind (ofo.errors.templates): the user's four-part text comes only from render().
_KIND_TEMPLATE = {
    MismatchKind.MISSING_PLATFORM_POSITION: "recon_missing_platform_position",
    MismatchKind.UNEXPECTED_BROKER_POSITION: "recon_unexpected_broker_position",
    MismatchKind.QUANTITY_MISMATCH: "recon_quantity_mismatch",
    MismatchKind.STRIKE_MISMATCH: "recon_strike_mismatch",
    MismatchKind.SIDE_MISMATCH: "recon_side_mismatch",
    MismatchKind.EXPIRY_MISMATCH: "recon_expiry_mismatch",
    MismatchKind.EXTERNAL_MODIFICATION: "recon_external_modification",
    MismatchKind.PARTIAL_EXECUTION: "recon_partial_execution",
    MismatchKind.STANDALONE_CHANGED: "recon_standalone_changed",
}
#: The next-action part of each kind's template: what the audit record keeps (``Mismatch.next_action``).
_NEXT_ACTION = {kind: CATALOGUE[template_id].next_action for kind, template_id in _KIND_TEMPLATE.items()}


def _check_aware_datetime(value: object, label: str) -> None:
    if not isinstance(value, datetime.datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ReconciliationError(detail=f"{label} must be a timezone-aware datetime, got {value!r}")


def _check_units(value: object, label: str) -> None:
    """Units are a domain quantity (lots x lot size), always a plain int -- never Decimal/float/str.

    This is a DOMAIN rule, not an audit-storage limit: the audit CAN store a Decimal (tagged ``{"$decimal": ...}``)
    or a float (json.dumps serialises it, lossily). Money is exact Decimal by ADR-008, but a reconciliation
    quantity is not money, and keeping it a plain int end to end (never re-typed to Decimal by a reload path) is
    what lets every downstream int arithmetic (differences, shares) stay exact and comparable.
    """
    if isinstance(value, bool) or not isinstance(value, int) or abs(value) > MAX_UNITS:
        raise ReconciliationError(detail=f"{label} must be an int within +/-{MAX_UNITS}, got {value!r}")


def _check_contract_pairs(value: object, label: str) -> None:
    if not isinstance(value, tuple):
        raise ReconciliationError(detail=f"{label} must be a tuple of (contract, units) pairs, got {value!r}")
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ReconciliationError(detail=f"{label}: each entry must be a (contract, units) pair, got {item!r}")
        contract, units = item
        try:
            check_contract(contract)
        except VersionError as exc:
            raise ReconciliationError(detail=f"{label}: {exc}") from exc
        _check_units(units, f"{label} units")


def _check_breakdown(value: object, label: str) -> None:
    if not isinstance(value, tuple):
        raise ReconciliationError(detail=f"{label} must be a tuple of (holder, contract, units) triples, got {value!r}")
    for item in value:
        if not isinstance(item, tuple) or len(item) != 3:
            raise ReconciliationError(detail=f"{label}: each entry must be a (holder, contract, units) triple, got {item!r}")
        holder, contract, units = item
        if not isinstance(holder, str) or not holder.strip():
            raise ReconciliationError(detail=f"{label}: holder must be a non-empty string, got {holder!r}")
        try:
            check_contract(contract)
        except VersionError as exc:
            raise ReconciliationError(detail=f"{label}: {exc}") from exc
        _check_units(units, f"{label} units")


@dataclass(frozen=True)
class Mismatch(UserFacing):
    """One recorded mismatch (AC-3): time, broker state, platform state, difference and required next action.

    Validated on construction (W-021 fix round, class: an audit write not validated before commit) so a hand-built
    or reloaded Mismatch carrying a wrong-typed field (a Decimal/float/str where a unit must be a plain int -- a
    domain rule, not an audit-storage limit; see ``_check_units`` -- a malformed contract, an empty holder) is
    refused HERE, immediately, rather than surfacing later as a ``PayloadValidationError`` mid-way through writing
    several audit events.
    """

    kind: MismatchKind
    strategy_ids: tuple[str, ...]  # every strategy it blocks; empty = blocks none
    at: datetime.datetime
    broker_state: tuple[tuple[Contract, int], ...]  # the broker's net units on each contract involved
    platform_state: tuple[tuple[Contract, int], ...]  # expected units (strategies' active versions + standalone)
    platform_breakdown: tuple[tuple[str, Contract, int], ...]  # (strategy id or "standalone", contract, units)
    difference: tuple[tuple[Contract, int], ...]  # broker minus expected, per contract
    next_action: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, MismatchKind):
            raise ReconciliationError(detail=f"mismatch kind must be a MismatchKind, got {self.kind!r}")
        if not isinstance(self.strategy_ids, tuple) or not all(
            isinstance(sid, str) and sid.strip() for sid in self.strategy_ids
        ):
            raise ReconciliationError(detail=f"mismatch strategy_ids must be a tuple of non-empty strings, got "
                                      f"{self.strategy_ids!r}")
        if len(set(self.strategy_ids)) != len(self.strategy_ids):
            raise ReconciliationError(detail=f"mismatch strategy_ids has duplicates: {self.strategy_ids!r}")
        _check_aware_datetime(self.at, "mismatch at")
        _check_contract_pairs(self.broker_state, "mismatch broker_state")
        _check_contract_pairs(self.platform_state, "mismatch platform_state")
        _check_contract_pairs(self.difference, "mismatch difference")
        _check_breakdown(self.platform_breakdown, "mismatch platform_breakdown")
        if not isinstance(self.next_action, str) or not self.next_action.strip() or len(self.next_action) > MAX_TEXT:
            raise ReconciliationError(detail=f"mismatch next_action must be a non-empty string of at most {MAX_TEXT} "
                                      f"chars, got {self.next_action!r}")

    @property
    def blocks(self) -> bool:
        return bool(self.strategy_ids)

    @property
    def message(self) -> UserFacingError:
        """The four-part text for this mismatch (REQ-065 AC-2), from the catalogue template of its kind."""
        return render(_KIND_TEMPLATE[self.kind], contracts=len(self.difference))

    @property
    def reason(self) -> str:
        """The what-happened part."""
        return self.message.what_happened

    @property
    def text(self) -> str:
        """What the user is shown: all four parts."""
        return display_text(self.message)

    def describe(self) -> str:
        diff = ", ".join(f"{describe_contract(c)} {units:+d}" for c, units in self.difference)
        return f"{self.kind.value}: {diff}"


@dataclass(frozen=True)
class ReconciliationReport:
    """The result of one comparison run. ``mismatches`` is empty when the broker agrees on every contract.

    Validated on construction, same class as ``Mismatch`` above: a hand-built or reloaded report with a wrong-typed
    field is refused here, not partway through recording it.
    """

    at: datetime.datetime
    broker: tuple[tuple[Contract, int], ...]  # the broker's whole net-position map as compared
    mismatches: tuple[Mismatch, ...]
    shares: tuple[tuple[str, Position], ...]  # EVERY covered strategy's broker share, blocked or not

    def __post_init__(self) -> None:
        _check_aware_datetime(self.at, "report at")
        _check_contract_pairs(self.broker, "report broker")
        if not isinstance(self.mismatches, tuple) or not all(isinstance(m, Mismatch) for m in self.mismatches):
            raise ReconciliationError(detail=f"report mismatches must be a tuple of Mismatch, got {self.mismatches!r}")
        if not isinstance(self.shares, tuple):
            raise ReconciliationError(detail=f"report shares must be a tuple of (strategy id, Position), got {self.shares!r}")
        seen: set[str] = set()
        for item in self.shares:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ReconciliationError(detail=f"report shares: each entry must be (strategy id, Position), got {item!r}")
            sid, position = item
            if not isinstance(sid, str) or not sid.strip():
                raise ReconciliationError(detail=f"report shares: strategy id must be a non-empty string, got {sid!r}")
            if sid in seen:
                raise ReconciliationError(detail=f"report shares has duplicate strategy id {sid!r}")
            seen.add(sid)
            if not isinstance(position, Position):
                raise ReconciliationError(detail=f"report shares[{sid!r}] must be a Position, got {position!r}")
        # Not a field (no effect on equality or repr): a per-strategy lookup, so recording a run that covers every
        # strategy reads each share once instead of scanning all shares per strategy (W-037).
        object.__setattr__(self, "_share_by_id", dict(self.shares))

    @property
    def blocked_strategy_ids(self) -> frozenset[str]:
        return frozenset(sid for m in self.mismatches for sid in m.strategy_ids)

    @property
    def covered_strategy_ids(self) -> frozenset[str]:
        """Every (non-exited) strategy this run compared; each one's broker picture is refreshed from it."""
        return frozenset(sid for sid, _ in self.shares)

    def share(self, strategy_id: str) -> Position:
        """The strategy's broker position according to THIS run (what a resolution's premise is checked against)."""
        position = self._share_by_id.get(strategy_id) if isinstance(strategy_id, str) else None
        if position is not None:
            return position
        raise ReconciliationError(detail=f"strategy {strategy_id!r} was not covered by this reconciliation run")


# ---- input validation ----------------------------------------------------------------------------------------

def units_map(value: object, label: str) -> dict[Contract, int]:
    """A Position or a contract -> signed-units mapping, validated; zero lines dropped. Fail closed on anything else."""
    if isinstance(value, Position):
        return value.as_dict()
    if not isinstance(value, Mapping):
        raise ReconciliationError(detail=f"{label} must be a Position or a mapping of contract -> signed units, got {value!r}")
    if len(value) > MAX_CONTRACTS:
        raise ReconciliationError(detail=f"{label} has {len(value)} contracts; at most {MAX_CONTRACTS}")
    result: dict[Contract, int] = {}
    for contract, units in value.items():
        try:
            check_contract(contract)
        except VersionError as exc:
            raise ReconciliationError(detail=f"{label}: {exc}") from exc
        if isinstance(units, bool) or not isinstance(units, int) or abs(units) > MAX_UNITS:
            raise ReconciliationError(detail=f"{label}: units must be an int within +/-{MAX_UNITS}, got {units!r}")
        if units:
            result[contract] = units
    return result


def require_time(at: object, clock: Callable[[], datetime.datetime]) -> datetime.datetime:
    if not isinstance(at, datetime.datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ReconciliationError(detail=f"reconciliation time must be a timezone-aware datetime, got {at!r}")
    if at > clock() + MAX_FUTURE_SKEW:
        raise ReconciliationError(detail=f"reconciliation time {at.isoformat()} is in the future")
    return at


def require_id(value: object, label: str = "strategy id") -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT or value == STANDALONE:
        raise ReconciliationError(detail=f"{label} must be a non-empty string of at most {MAX_TEXT} chars (not "
                                  f"{STANDALONE!r}), got {value!r}")
    return value


def _records(strategies: object) -> dict[str, StrategyRecord]:
    if not isinstance(strategies, Mapping):
        raise ReconciliationError(detail=f"strategies must be a mapping of strategy id -> StrategyRecord, got {strategies!r}")
    if len(strategies) > MAX_STRATEGIES:
        raise ReconciliationError(detail=f"{len(strategies)} strategies; at most {MAX_STRATEGIES}")
    seen: set[int] = set()
    for sid, record in strategies.items():
        require_id(sid)
        if not isinstance(record, StrategyRecord):
            raise ReconciliationError(detail=f"strategy {sid!r} must be a StrategyRecord, got {record!r}")
        if id(record) in seen:
            raise ReconciliationError(detail=f"strategy {sid!r} is the same record as another id; one record, one id")
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


def holders_by_contract(
    contracts: list[Contract],
    actives: Mapping[str, Mapping[Contract, int]],
    proposals: Mapping[str, Mapping[Contract, int] | None],
) -> dict[Contract, tuple[str, ...]]:
    """For each of ``contracts``: every strategy holding it in its active version or its pending proposed version.

    One pass over the strategies' lines (W-037, issue #64): work is linear in strategies + contracts, never a scan of
    every strategy per contract.
    """
    found: dict[Contract, set[str]] = {contract: set() for contract in contracts}
    for sid, units in actives.items():
        for contract in units.keys() | (proposals.get(sid) or {}).keys():
            if contract in found:
                found[contract].add(sid)
    return {contract: tuple(sorted(sids)) for contract, sids in found.items()}


@dataclass(frozen=True)
class _ActiveIndex:
    """The strategies' ACTIVE units on the differing contracts, built once per run (W-037).

    ``lines[c]``: (strategy id, units) for every strategy whose active version holds ``c``, sorted by id.
    ``totals[c]``: the sum of every strategy's active units on ``c`` (the strategies' part of ``expected``).
    Independent of ``holders_by_contract``: the breakdown and the shares read the active versions themselves.
    """

    lines: dict[Contract, list[tuple[str, int]]]
    totals: dict[Contract, int]

    @classmethod
    def build(cls, contracts: list[Contract], actives: Mapping[str, Mapping[Contract, int]]) -> "_ActiveIndex":
        lines: dict[Contract, list[tuple[str, int]]] = {contract: [] for contract in contracts}
        for sid in sorted(actives):
            for contract, value in actives[sid].items():
                if contract in lines:
                    lines[contract].append((sid, value))
        return cls(lines, {contract: sum(v for _, v in held) for contract, held in lines.items()})

    def others(self, sid: str, contract: Contract, actives: Mapping[str, Mapping[Contract, int]]) -> int:
        """Every OTHER strategy's active units on ``contract`` (``contract`` must be one the index was built for)."""
        return self.totals[contract] - actives[sid].get(contract, 0)


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
    held = holders_by_contract(differing, actives, proposals)
    index = _ActiveIndex.build(differing, actives)

    groups = _pair_moved_contracts(differing, diff, held)
    mismatches = []
    for contracts, kind_hint in groups:
        # A paired group's owners come from its HELD contract, wherever the pair sorts (the unheld one may sort first).
        owners = tuple(sorted({sid for contract in contracts for sid in held[contract]}))
        if owners:
            anchor = next(contract for contract in contracts if held[contract])
            kind = kind_hint or _classify_held(anchor, owners, broker, alone, actives, proposals, index)
        else:
            kind = MismatchKind.STANDALONE_CHANGED if alone.get(contracts[0]) else MismatchKind.UNEXPECTED_BROKER_POSITION
        if owners and any(outside.get(c) for c in contracts):
            kind = MismatchKind.EXTERNAL_MODIFICATION
        breakdown = tuple(
            (holder, c, units)
            for c in contracts
            for holder, units in [(STANDALONE, alone.get(c, 0))] + index.lines[c]
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
    involved: dict[str, set[Contract]] = {}
    for m in mismatches:
        for sid in m.strategy_ids:
            involved.setdefault(sid, set()).update(c for c, _ in m.difference)
    shares = tuple((sid, broker_share(sid, broker, alone, actives, involved.get(sid, set()), index)) for sid in covered)
    broker_lines = tuple(sorted(broker.items(), key=lambda item: contract_sort_key(item[0])))
    return ReconciliationReport(at, broker_lines, tuple(mismatches), shares)


def _pair_moved_contracts(
    differing: list[Contract], diff: Mapping[Contract, int], held: Mapping[Contract, tuple[str, ...]]
) -> list[tuple[tuple[Contract, ...], MismatchKind | None]]:
    """Group a held contract with the ONE unheld contract its quantity moved to (strike or expiry changed).

    Pairs only when exactly one unheld contract has the same underlying and instrument, the opposite difference,
    and differs in strike only (STRIKE) or expiry only (EXPIRY). Anything ambiguous stays separate, so an unheld
    contract is never silently attributed to a strategy it may not belong to.

    Candidates are looked up in two buckets built once (W-037): unheld contracts by (underlying, instrument,
    difference, expiry) -- a strike move -- and by (underlying, instrument, difference, strike) -- an expiry move. A
    bucket never holds the held contract itself (it is held), so every entry left in it differs in exactly the other
    field; a paired unheld contract is taken out of both buckets, exactly as it was skipped as "used" before.
    """
    used: set[Contract] = set()
    groups: list[tuple[tuple[Contract, ...], MismatchKind | None]] = []
    by_expiry: dict[tuple, dict[Contract, None]] = {}  # dict as an insertion-ordered set
    by_strike: dict[tuple, dict[Contract, None]] = {}
    for other in differing:
        if not held[other]:
            by_expiry.setdefault((other[:2], diff[other], other[3]), {})[other] = None
            by_strike.setdefault((other[:2], diff[other], other[2]), {})[other] = None
    for contract in differing:
        if contract in used or not held[contract]:
            continue
        strike_moves = by_expiry.get((contract[:2], -diff[contract], contract[3]), {})
        expiry_moves = by_strike.get((contract[:2], -diff[contract], contract[2]), {})
        if len(strike_moves) + len(expiry_moves) == 1:
            other, kind = ((next(iter(strike_moves)), MismatchKind.STRIKE_MISMATCH) if strike_moves
                           else (next(iter(expiry_moves)), MismatchKind.EXPIRY_MISMATCH))
            used.update((contract, other))
            del by_expiry[(other[:2], diff[other], other[3])][other]
            del by_strike[(other[:2], diff[other], other[2])][other]
            groups.append((tuple(sorted((contract, other), key=contract_sort_key)), kind))
        else:
            used.add(contract)
            groups.append(((contract,), None))
    groups.extend(((c,), None) for c in differing if c not in used)
    return groups


def _classify_held(
    contract: Contract,
    owners: tuple[str, ...],
    broker: Mapping[Contract, int],
    alone: Mapping[Contract, int],
    actives: Mapping[str, Mapping[Contract, int]],
    proposals: Mapping[str, Mapping[Contract, int] | None],
    index: _ActiveIndex,
) -> MismatchKind:
    """Kind of a mismatch on a strategy contract whose quantity moved (not to another strike or expiry)."""
    for sid in owners:
        proposal = proposals.get(sid)
        if proposal is None:
            continue
        share = broker.get(contract, 0) - alone.get(contract, 0) - index.others(sid, contract, actives)
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
    involved: set[Contract],
    index: _ActiveIndex,
) -> Position:
    """The strategy's broker share: its active units where the broker agrees; elsewhere broker minus the rest.

    ``involved`` is every contract of every mismatch that names this strategy (collected once per run, W-037).
    """
    units = dict(actives[sid])
    for contract in involved:
        units[contract] = broker.get(contract, 0) - alone.get(contract, 0) - index.others(sid, contract, actives)
    try:
        return Position.of(units)
    except VersionError as exc:
        raise ReconciliationError(detail=f"strategy {sid!r}: broker share is not a valid position: {exc}") from exc


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
