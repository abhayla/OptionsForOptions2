"""W-108: attribute before compare (ADR-109 (2) and its first consequence; REQ-060 AC-4, AC-6, AC-7; ADR-105; Q224).

A strategy owns exactly the fills of orders this app placed (ADR-109 (2)); what it holds is ``execute_plan.held_units``
over ALL its stored plans (ADR-105). Per contract, the expected quantity is every strategy's held units plus the
recorded standalone quantity (AC-7). A same-direction surplus of Zerodha's net beyond that is reported as OUTSIDE lots
and removed before ``ofo.reconciliation.compare`` runs; compare itself is unchanged, and the result keeps Zerodha's raw
net beside the stripped one. Examples (ADR-109): strategy BUY 65 CE, Zerodha 130 -> not blocked, 65 outside; strategy
65 + standalone 25, Zerodha 90 -> no mismatch; Zerodha 0 -> blocked.

Attribution rule, per contract ``c`` (``b`` = Zerodha's net, ``e`` = expected; signed units, BUY +, SELL -):

- No strategy and no standalone holds ``c``: all of ``b`` is outside (AC-7: "a broker position in no strategy and not
  recorded as standalone ... blocks no strategy").
- Every holder (each strategy's held units and the standalone quantity) is on ONE side ``s``: when ``b`` is on side
  ``s`` too and ``|b| > |e|``, ``b - e`` is outside and ``e`` is compared. Anything else (a shortfall, Zerodha flat, the
  opposite side) is compared as read, so compare blocks it (AC-6, Q199).
- Holders on BOTH sides of ``c``: nothing is stripped. A surplus over the sum is then a shortfall against the
  opposite-side holder's own fills (Kite nets the contract to one number; ADR-109 (2): "sold app lots, or an opposite
  outside trade that nets them away, cannot be told apart"), so it reaches compare and Q224 blocks every holder.

Inputs are read by this module itself (finding ``caller-supplied-verdict-trusted``): the stored plans (held units are
computed here, never accepted), the positions reply's ``data`` (parsed here by ``kite_replies.positions_from_reply``),
and the catalogue. A strategy that holds nothing (no fills, or every fill closed) has no active position and is not
passed to compare. No route is wired here (GC-3F).
"""
from __future__ import annotations

import datetime
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ofo.engine import Action
from ofo.execution.basket import parse_tag
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import InstrumentId
from ofo.reconciliation.compare import MAX_STRATEGIES, ReconciliationReport, compare, units_map
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo.strategy.versions import StrategyRecord

from ofo_app import execute_plan as ep
from ofo_app.execution_plan_store import StoredPlan
from ofo_app.kite_replies import ContractIndex, positions_from_reply

ContractKey = tuple  # (underlying, Instrument, strike | None, expiry): the reconcile key (execute_plan.contract_key)

#: The actor recorded on the in-memory record compare reads (never stored; the record lives for one comparison).
_ACTOR = "reconcile_attribution"


class AttributionError(ValueError):
    """An input the attribution cannot read exactly; nothing is guessed (fail closed)."""


@dataclass(frozen=True)
class StrategyPlans:
    """One strategy's stored underlying and ALL its stored plans (``execution_plan_store.StoredPlan``)."""

    underlying: str
    plans: tuple[StoredPlan, ...]


@dataclass(frozen=True)
class Sources:
    """Where keys and time come from: the catalogue (stored instrument ids), the contract index (Kite's position rows)
    and the platform clock compare checks ``at`` against."""

    catalogue: Catalogue
    index: ContractIndex
    clock: Callable[[], datetime.datetime]


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


def _check_plans(strategy_id: int, plans: StrategyPlans) -> None:
    """Every plan is this strategy's, numbered once, and every order's tag decodes to this strategy and plan."""
    if not isinstance(plans, StrategyPlans) or not isinstance(plans.plans, tuple):
        raise AttributionError(f"strategy {strategy_id}: plans must be a StrategyPlans of a tuple, got {plans!r}")
    numbers: set[int] = set()
    for plan in plans.plans:
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


def _held_by_key(strategy_id: int, plans: StrategyPlans, catalogue: Catalogue) -> dict[ContractKey, int]:
    _check_plans(strategy_id, plans)
    held: dict[ContractKey, int] = {}
    for instrument_id, units in ep.held_units(plans.plans).items():
        key = instrument_key(catalogue, instrument_id, plans.underlying)
        held[key] = held.get(key, 0) + units
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
        holdings = [units.get(contract, 0) for units in held.values()] + [standalone.get(contract, 0)]
        sides = {units > 0 for units in holdings if units}
        expected = sum(holdings)
        if not sides:
            surplus = broker  # in no strategy and not standalone: all of it is outside
        elif sides == {True, False}:
            surplus = 0  # holders on both sides: a surplus is a shortfall for one of them (Q224 blocks all)
        elif (broker > 0) == (expected > 0) and abs(broker) > abs(expected):
            surplus = broker - expected  # same side, beyond the app's own fills + standalone
        else:
            surplus = 0  # shortfall, flat or opposite side: compare decides (AC-6)
        if surplus:
            outside[contract] = surplus
    return outside


def attribute_and_compare(
    strategies: Mapping[int, StrategyPlans],
    standalone: Mapping[ContractKey, int],
    positions_data: Mapping[str, object],
    sources: Sources,
    *,
    at: datetime.datetime,
) -> Attribution:
    """Read Zerodha's positions, compute every strategy's held units, set the outside lots apart, then run compare.

    ``strategies``: strategy id -> its plans (every non-exited strategy of the account on these contracts; a strategy
    left out is not expected). ``standalone``: the recorded standalone units per contract. ``positions_data``: the
    ``data`` of Kite's positions reply. Any unreadable input raises ``ValueError`` (``AttributionError``,
    ``KiteReplyError``, ``ReconciliationError``); a guessed zero never reaches compare."""
    if not isinstance(strategies, Mapping) or len(strategies) > MAX_STRATEGIES:
        raise AttributionError(f"strategies must be a mapping of at most {MAX_STRATEGIES} ids, got {strategies!r}")
    if not isinstance(sources, Sources):
        raise AttributionError(f"sources must be a Sources, got {sources!r}")
    catalogue, clock = sources.catalogue, sources.clock
    alone = units_map(standalone, "standalone quantities")
    raw_net = dict(positions_from_reply(positions_data, sources.index).net)
    seen: set[int] = set()
    held: dict[str, dict[ContractKey, int]] = {}
    records: dict[str, StrategyRecord] = {}
    for strategy_id, plans in strategies.items():
        if isinstance(strategy_id, bool) or not isinstance(strategy_id, int) or strategy_id <= 0:
            raise AttributionError(f"a strategy id must be a positive int, got {strategy_id!r}")
        if id(plans) in seen:
            raise AttributionError(f"strategy {strategy_id}: the same plans object is given for two strategies")
        seen.add(id(plans))
        units = _held_by_key(strategy_id, plans, catalogue)
        if units:
            held[str(strategy_id)] = units
            records[str(strategy_id)] = _record(plans.underlying, units, at, clock)
    outside = split_outside(raw_net, held, alone)
    compared = {c: units - outside.get(c, 0) for c, units in raw_net.items() if units - outside.get(c, 0)}
    report = compare(compared, records, alone, at=at, clock=clock)
    return Attribution(report, MappingProxyType(raw_net), MappingProxyType(compared), MappingProxyType(outside),
                       MappingProxyType({sid: MappingProxyType(u) for sid, u in held.items()}))


__all__ = ["Attribution", "AttributionError", "Sources", "StrategyPlans", "attribute_and_compare", "instrument_key",
           "split_outside"]
