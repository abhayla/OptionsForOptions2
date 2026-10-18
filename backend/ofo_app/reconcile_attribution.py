"""W-108: attribute before compare (ADR-109 (2) and its first consequence; REQ-060 AC-4, AC-6, AC-7; ADR-105; Q224).

A strategy owns exactly the fills of orders this app placed (ADR-109 (2)); what it holds is ``execute_plan.held_units``
over ALL its stored plans (ADR-105). Per contract, the expected quantity is every strategy's held units plus the
recorded standalone quantity (AC-7). A same-direction surplus of Zerodha's net beyond that is reported as OUTSIDE lots
and removed before ``ofo.reconciliation.compare`` runs; compare itself is unchanged, and the result keeps Zerodha's raw
net beside the stripped one. Examples (ADR-109): strategy BUY 65 CE, Zerodha 130 -> not blocked, 65 outside; strategy
65 + standalone 25, Zerodha 90 -> no mismatch; Zerodha 0 -> blocked.

Attribution rule, per contract ``c`` (``b`` = Zerodha's net, signed units, BUY +, SELL -):

- ``e`` (expected) = every strategy's held units + the recorded standalone quantity (the standalone only ADDS to ``e``).
- No strategy and no standalone holds ``c``: all of ``b`` is outside (AC-7: "a broker position in no strategy and not
  recorded as standalone ... blocks no strategy").
- The direction ``s`` is decided by the STRATEGY holders only (fix round 1: a standalone on the other side must not turn
  a single-holder contract into a both-sides one; Q224 leaves single-holder contracts unchanged); with no strategy
  holder, by the standalone. When ``b - e`` lies on side ``s`` (Zerodha holds MORE in that direction than expected),
  ``b - e`` is outside and ``e`` is compared. Anything else (a shortfall, Zerodha flat, the opposite side) is compared
  as read, so compare blocks it (AC-6, Q199). Example: own +65, standalone -25 (``e`` = 40): Zerodha 40 agrees; 65 ->
  25 outside; 130 -> 90 outside; 0 -> blocked.
- Strategy holders on BOTH sides of ``c``: nothing is stripped. A surplus over the sum is then a shortfall against the
  opposite-side holder's own fills (Kite nets the contract to one number; ADR-109 (2): "sold app lots, or an opposite
  outside trade that nets them away, cannot be told apart"), so it reaches compare and Q224 blocks every holder.

Inputs (finding ``caller-supplied-verdict-trusted``, run-discipline B8): the caller passes only the account (database
connection + user), Zerodha's net, the standalone map and ``at``. EVERY strategy of the account and ALL of each one's
stored plans are read HERE through the store reader (``strategy_store.list_strategies`` +
``execution_plan_store.plans_for``), so no plan or strategy can be left out by a caller (an omitted plan or strategy
would hide a shortfall); held units are computed HERE, never accepted; compare is called HERE. Zerodha's net is what
the reply adapter parsed (``kite_replies.positions_from_reply(...).net``), validated again by ``compare.units_map``;
this module imports no Kite module (REQ-063 AC-1). A strategy that holds nothing (no fills, every fill closed, exited)
has no active position and is not passed to compare. No route is wired here (GC-3F).
"""
from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from ofo.engine import Action
from ofo.execution.basket import parse_tag
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import InstrumentId
from ofo.reconciliation.compare import MAX_STRATEGIES, ReconciliationReport, compare, units_map
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo.strategy.versions import StrategyRecord

from ofo_app import execute_plan as ep
from ofo_app import execution_plan_store, strategy_store
from ofo_app.execution_plan_store import StoredPlan
from ofo_app.strategy_store import StrategySummary

ContractKey = tuple  # (underlying, Instrument, strike | None, expiry): the reconcile key (execute_plan.contract_key)
ListStrategies = Callable[[object, str], Awaitable[Sequence[StrategySummary]]]
PlansFor = Callable[[object, str, int], Awaitable[Sequence[StoredPlan]]]

#: The actor recorded on the in-memory record compare reads (never stored; the record lives for one comparison).
_ACTOR = "reconcile_attribution"


class AttributionError(ValueError):
    """An input the attribution cannot read exactly; nothing is guessed (fail closed)."""


@dataclass(frozen=True)
class StoreReader:
    """The read seam: every strategy of a user, and every stored plan of one strategy. The defaults are the stores the
    routes use; a test injects a fake with the same two calls."""

    list_strategies: ListStrategies = strategy_store.list_strategies
    plans_for: PlansFor = execution_plan_store.plans_for


@dataclass(frozen=True)
class Account:
    """Whose strategies are read: the database connection and the user."""

    conn: object
    user_ref: str


@dataclass(frozen=True)
class Sources:
    """Where keys, time and the stored plans come from: the catalogue (stored instrument ids -> contract keys), the
    platform clock compare checks ``at`` against, and the store reader."""

    catalogue: Catalogue
    clock: Callable[[], datetime.datetime]
    reader: StoreReader = field(default_factory=StoreReader)


@dataclass(frozen=True)
class Attribution:
    """The comparison and what was set apart before it.

    ``raw_net``: Zerodha's net units per contract, as read (flat rows dropped). ``compared_net``: what compare was
    given (``raw_net`` minus ``outside``). ``outside``: the outside lots per contract, signed. ``held``: each holding
    strategy's own units per contract (``held_units``), by strategy id (text, compare's id). ``report``: compare's
    report on ``compared_net``."""

    report: ReconciliationReport
    raw_net: Mapping[ContractKey, int]
    compared_net: Mapping[ContractKey, int]
    outside: Mapping[ContractKey, int]
    held: Mapping[str, Mapping[ContractKey, int]]


def instrument_key(catalogue: Catalogue, instrument_id: str, underlying: str) -> ContractKey:
    """A stored plan order's ``instrument_id`` text ("NSE_FO:47189") -> the reconcile key, through the catalogue.

    Refused: text that is not exactly ``segment:token`` with a plain positive token, an id the catalogue does not
    hold, and a contract of another underlying than the strategy's."""
    segment, colon, token = instrument_id.partition(":") if isinstance(instrument_id, str) else ("", "", "")
    if not colon or not token.isascii() or not token.isdigit() or token.startswith("0"):
        raise AttributionError(f"instrument_id must be 'segment:token', got {instrument_id!r}")
    try:
        iid = InstrumentId(segment, int(token))
    except ValueError as exc:
        raise AttributionError(f"instrument_id {instrument_id!r}: {exc}") from None
    entry = catalogue.get(iid)
    if entry is None:
        raise AttributionError(f"instrument_id {instrument_id!r} is not in the catalogue")
    if entry.contract.name != underlying:
        raise AttributionError(f"instrument_id {instrument_id!r} is {entry.contract.name}, not {underlying}")
    return ep.contract_key(catalogue, iid, underlying)


def _check_plans(strategy_id: int, plans: object) -> None:
    """Every plan is this strategy's, numbered once, and every order's tag decodes to this strategy and plan."""
    if not isinstance(plans, (tuple, list)):
        raise AttributionError(f"strategy {strategy_id}: the store must return a sequence of plans, got {plans!r}")
    numbers: set[int] = set()
    for plan in plans:
        if not isinstance(plan, StoredPlan):
            raise AttributionError(f"strategy {strategy_id}: a plan must be a StoredPlan, got {plan!r}")
        if plan.strategy_id != strategy_id:
            raise AttributionError(f"plan {plan.plan_number} belongs to strategy {plan.strategy_id}, not {strategy_id}")
        if plan.plan_number in numbers:
            raise AttributionError(f"strategy {strategy_id}: plan {plan.plan_number} appears twice")
        numbers.add(plan.plan_number)
        for order in plan.orders:
            try:
                tag = parse_tag(order.tag)
            except ValueError:
                raise AttributionError(f"strategy {strategy_id} plan {plan.plan_number}: {order.tag!r} is not an "
                                       "order tag of this app") from None
            if (tag.strategy_id, tag.plan_version) != (strategy_id, plan.plan_number):
                raise AttributionError(f"strategy {strategy_id} plan {plan.plan_number}: tag {order.tag!r} is another "
                                       "strategy's or plan's order")


def _held_by_key(strategy_id: int, underlying: str, plans: Sequence[StoredPlan],
                 catalogue: Catalogue) -> dict[ContractKey, int]:
    _check_plans(strategy_id, plans)
    held: dict[ContractKey, int] = {}
    for instrument_id, units in ep.held_units(plans).items():
        key = instrument_key(catalogue, instrument_id, underlying)
        held[key] = held.get(key, 0) + units  # two stored ids of ONE contract add up: Zerodha nets them as one
    return {key: units for key, units in held.items() if units}


def _record(underlying: str, held: Mapping[ContractKey, int], at: datetime.datetime,
            clock: Callable[[], datetime.datetime]) -> StrategyRecord:
    """An in-memory record whose ACTIVE version's intended position IS the held units (versions.py:156-157)."""
    legs = tuple(DefinitionLeg(Action.BUY if units > 0 else Action.SELL, kind, strike, expiry, abs(units))
                 for (_, kind, strike, expiry), units in held.items())
    return StrategyRecord.from_held(StrategyDefinition(underlying, legs), at=at, actor=_ACTOR, clock=clock)


def split_outside(raw_net: Mapping[ContractKey, int], held: Mapping[str, Mapping[ContractKey, int]],
                  standalone: Mapping[ContractKey, int]) -> dict[ContractKey, int]:
    """The outside lots per contract (module docstring rule). Pure; every input is signed units."""
    outside: dict[ContractKey, int] = {}
    for contract, broker in raw_net.items():
        own = [units.get(contract, 0) for units in held.values()]
        alone = standalone.get(contract, 0)
        expected = sum(own) + alone
        sides = {units > 0 for units in own if units} or ({alone > 0} if alone else set())
        excess = broker - expected
        if not sides:
            surplus = broker  # in no strategy and not standalone: all of it is outside
        elif sides == {True, False}:
            surplus = 0  # strategies on both sides: a surplus is a shortfall for one of them (Q224 blocks all)
        elif excess and (excess > 0) in sides:
            surplus = excess  # more than expected, in the holders' direction: outside lots
        else:
            surplus = 0  # shortfall, flat or opposite side: compare decides (AC-6)
        if surplus:
            outside[contract] = surplus
    return outside


async def attribute_and_compare(
    account: Account,
    standalone: Mapping[ContractKey, int],
    broker_net: Mapping[ContractKey, int],
    sources: Sources,
    *,
    at: datetime.datetime,
) -> Attribution:
    """Read every strategy of the account and all its plans, compute held units, set the outside lots of Zerodha's
    net apart, then run compare.

    ``standalone``: the recorded standalone units per contract. ``broker_net``: Zerodha's net units per contract from
    ``kite_replies.positions_from_reply`` (a flat row is absent: Zerodha holds 0; an unreadable reply raises there,
    before this runs). Any malformed input raises ``ValueError`` (``AttributionError``, ``ReconciliationError``); a
    guessed zero never reaches compare."""
    if not isinstance(account, Account) or not isinstance(account.user_ref, str) or not account.user_ref.strip():
        raise AttributionError(f"account must be an Account with a user, got {account!r}")
    if not isinstance(sources, Sources) or not isinstance(sources.reader, StoreReader):
        raise AttributionError(f"sources must be a Sources with a StoreReader, got {sources!r}")
    catalogue, clock, reader = sources.catalogue, sources.clock, sources.reader
    alone = units_map(standalone, "standalone quantities")
    raw_net = units_map(broker_net, "broker net positions")
    summaries = await reader.list_strategies(account.conn, account.user_ref)
    if not isinstance(summaries, (list, tuple)) or len(summaries) > MAX_STRATEGIES:
        raise AttributionError(f"the store must list at most {MAX_STRATEGIES} strategies, got {summaries!r}")
    held: dict[str, dict[ContractKey, int]] = {}
    records: dict[str, StrategyRecord] = {}
    seen: set[int] = set()
    for summary in summaries:
        if not isinstance(summary, StrategySummary):
            raise AttributionError(f"the store listed {summary!r}, not a StrategySummary")
        strategy_id = summary.id
        if isinstance(strategy_id, bool) or not isinstance(strategy_id, int) or strategy_id <= 0:
            raise AttributionError(f"a strategy id must be a positive int, got {strategy_id!r}")
        if strategy_id in seen:
            raise AttributionError(f"the store listed strategy {strategy_id} twice")
        seen.add(strategy_id)
        plans = await reader.plans_for(account.conn, account.user_ref, strategy_id)
        units = _held_by_key(strategy_id, summary.underlying, plans, catalogue)
        if units:
            held[str(strategy_id)] = units
            records[str(strategy_id)] = _record(summary.underlying, units, at, clock)
    outside = split_outside(raw_net, held, alone)
    compared = {c: units - outside.get(c, 0) for c, units in raw_net.items() if units - outside.get(c, 0)}
    report = compare(compared, records, alone, at=at, clock=clock)
    return Attribution(report, MappingProxyType(raw_net), MappingProxyType(compared), MappingProxyType(outside),
                       MappingProxyType({sid: MappingProxyType(u) for sid, u in held.items()}))


__all__ = ["Account", "Attribution", "AttributionError", "Sources", "StoreReader", "attribute_and_compare",
           "instrument_key", "split_outside"]
