"""The execution plan: leg dependencies and the order sequence (REQ-056 AC-2, AC-3, AC-4; ADR-017 Q26).

Spec basis:
- REQ-056 AC-2 "an execution plan with leg dependencies and an order sequence based on protection, margin impact,
  dependencies and broker constraints"; AC-3 "protective/buy legs before the sell legs that depend on them, but 'all
  buys first' is never hard-coded for every strategy"; AC-4 "If a protective leg fails, the sell leg that depends on
  it is not submitted" (core invariant 21).
- ADR-017 Q26: "Strategy -> Execution Plan -> Leg Dependencies -> Execution Sequence -> Orders"; the user sees
  "Step 1 - Establish protection · Step 2 - Establish short positions"; "futures/naked strategies differ". The owner's
  reason (T1 #55): legs placed first free margin for the sells they hedge.

PROTECTION (``protects``). A leg protects a SOLD option when its payoff rises where the sold option loses, so it caps
that loss:
- a sold CE loses as the level rises: a BOUGHT CE (any strike) or a BOUGHT future protects it;
- a sold PE loses as the level falls: a BOUGHT PE (any strike) or a SOLD future protects it;
- expiry: the protector expires on or after the sold option (a protector that expires first leaves it naked).
Sources: same-expiry options of any strike - W-022 round 1, accepted by the verifier (payoff math). Later-expiry
options (calendar/diagonal) - mirrors W-014 rule 5d (``safety._closes_only_short_options``: in a multi-expiry strategy
closing only the SOLD options is open to every plan, i.e. the long leg is what protects the short). Futures - REQ-059
gate examples: "closing the long future of a covered call -> UNLIMITED (needs Pro)", i.e. the long future protects the
short call; the short future of a covered put is the mirror case. "Futures expiry on or after the option's" is an
orchestrator default (W-022 fix round).
Why not W-014's premium-free worst case (rule 5b) as the relation: measured 2026-09-29 with the engine, it rates a
covered put (SELL 23,000 PE + SELL future, 65 units) UNLIMITED, worse than the short put alone (-14,95,000), so the
short future would NOT count as protection, contradicting the covered-put case; and it cannot evaluate a calendar at
all (``MultiExpiryError``). The payoff-direction rule above covers every case both W-014 rules and REQ-059 name.
Nothing protects a futures leg in the spec; a futures leg that protects nothing is listed in ``undetermined``.

STEPS (ADR-017 Q26 display): step 1 "Establish protection" = every leg that protects some sold option; step 2
"Establish short positions" = every sold option that has a protector; step 3 = every other leg. Within a step the
order is the MARGIN tie-break, else the order the user confirmed (stable). A strategy with no dependency is therefore
never forced into "all buys first" (AC-3).

MARGIN IMPACT (orchestrator default, W-022 fix round; UNVERIFIED against real Zerodha margin behaviour, ADR-017 Q26):
with a ``MarginPlanner`` (engine interface), a leg's impact = margin(all legs) - margin(all legs without it); within a
step, legs with the lower impact (those that reduce margin most) go first, ties keep the user's order. No planner, or
a planner that fails: order by protection only and say "margin impact unknown - not used".

BROKER CONSTRAINTS (``BrokerConstraints``; the default values are UNVERIFIED placeholders, REQ-056 AC-10 verifies the
real ones at the Kite build): a leg above the freeze quantity is split into several orders of at most that many units;
orders are grouped into batches of at most ``max_orders_per_batch``; a batch never spans two steps, so every
protective slice is placed before any dependent slice.

LOTS (W-028, deferred #43; REQ-056 AC-9 "lot validity"): given the instrument ``catalogue``, every plan contract must
be a catalogue instrument, and every leg quantity and every quantity to order must be a whole number of that
instrument's catalogue lot size, else refused. ORCHESTRATOR DEFAULT (W-028, the spec is silent): a freeze quantity
that is not a whole number of lots is rounded DOWN to whole lots (freeze 200, lot 65 -> 195), so every slice is
lot-aligned; a freeze below one lot is refused.
ONE SLICING RULE (W-032, deferred #50): ``slice_quantity`` is the only place a leg is split at the freeze quantity;
the plan (Complete / Retry) and Close Partial Strategy (``exit_orders``, REQ-056 AC-10) both go through it.
REMAINING ORDERS (W-028): ``quantities`` names the units still to order per leg (Complete / Retry); steps, dependencies
and margin order stay those of the FULL plan, only the named legs get orders.

WITHHOLD (AC-4): a dependent is not submitted when ANY of its protectors failed or was itself withheld (one pass in
sequence order is the fixpoint, protectors always come earlier).
NAKED (``unprotected``): from the same relation. Sold options and their protectors are grouped into connected sets;
a set whose sold units exceed its protectors' units has that many naked units (units are fungible, no single sold leg
is singled out). A sold option with no protector is naked in full.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Final, Protocol

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.engine.interfaces import MarginPlanner, plan_margin
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.instruments import ZERODHA, Catalogue

_BUILDER_KEY: Final = object()
MARGIN_UNVERIFIED: Final = "unverified against real Zerodha margin behaviour (ADR-017 Q26)"
MARGIN_NOT_USED: Final = "margin impact unknown — not used"
MAX_SLICES_PER_LEG: Final = 50  # orchestrator default: refuse an absurd split rather than build it
MAX_BATCH_SIZE: Final = 100  # orchestrator default: sanity cap on a provider's answer

#: UNVERIFIED placeholders (REQ-056 AC-10 verifies the real values against Kite Connect at the Kite build).
#: 1,755 = 27 lots of 65, the largest one-lot multiple under NSE's historical NIFTY freeze of 1,800 units.
DEFAULT_FREEZE_UNITS: Final = 1755
DEFAULT_MAX_ORDERS_PER_BATCH: Final = 10


class BrokerConstraints(Protocol):
    """Broker limits the sequence must respect. ``freeze_quantity`` is lot-aligned units per order."""

    def freeze_quantity(self, contract: str) -> int: ...

    def max_orders_per_batch(self) -> int: ...


class UnverifiedDefaultConstraints:
    """The labelled, UNVERIFIED default (see DEFAULT_FREEZE_UNITS / DEFAULT_MAX_ORDERS_PER_BATCH)."""

    unverified = True

    def freeze_quantity(self, contract: str) -> int:
        return DEFAULT_FREEZE_UNITS

    def max_orders_per_batch(self) -> int:
        return DEFAULT_MAX_ORDERS_PER_BATCH


class StepKind(Enum):
    PROTECTION = "Establish protection"
    SHORT_POSITIONS = "Establish short positions"
    OTHER = "Legs with no protection relation"


@dataclass(frozen=True)
class PlanStep:
    kind: StepKind
    leg_refs: tuple[str, ...]


@dataclass(frozen=True)
class PlannedOrder:
    """One order to send: a whole leg, or one slice of a leg above the freeze quantity."""

    step: int
    batch: int  # 1-based, counted across the whole plan; a batch never spans two steps
    leg_ref: str
    slice_no: int
    quantity: int


@dataclass(frozen=True)
class Undetermined:
    leg_ref: str
    reason: str


@dataclass(frozen=True)
class Unprotected:
    """Sold units of one connected protection set that no protector covers: naked."""

    leg_refs: tuple[str, ...]
    units: int


@dataclass(frozen=True)
class Simulation:
    """What happens for a given set of failing legs: ``sent`` in sequence order (a failed leg was sent and refused),
    ``withheld`` = dependents never submitted (AC-4)."""

    sent: tuple[str, ...]
    failed: tuple[str, ...]
    withheld: tuple[str, ...]


@dataclass(frozen=True)
class OrderSequence:
    """Built only by :func:`sequence_plan`; a caller cannot hand one in with its own dependencies."""

    strategy_id: str
    steps: tuple[PlanStep, ...]
    dependencies: tuple[tuple[str, tuple[str, ...]], ...]  # (sold leg_ref, its protectors), plan order
    undetermined: tuple[Undetermined, ...]
    unprotected: tuple[Unprotected, ...]
    ordering_basis: str
    orders: tuple[PlannedOrder, ...] = ()
    margin_used: bool = False
    margin_note: str = MARGIN_NOT_USED
    _key: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._key is not _BUILDER_KEY:
            raise ValueError("an OrderSequence is built by sequence_plan(plan), never by hand")

    @property
    def sequence(self) -> tuple[str, ...]:
        return tuple(ref for step in self.steps for ref in step.leg_refs)

    def protectors_of(self, leg_ref: str) -> tuple[str, ...]:
        self._known(leg_ref)
        return dict(self.dependencies).get(leg_ref, ())

    def _known(self, leg_ref: str) -> None:
        if leg_ref not in self.sequence:
            raise ValueError(f"leg {leg_ref!r} is not in this plan")

    def simulate(self, failed: Iterable[str]) -> Simulation:
        """AC-4: walk the sequence; a leg whose protector failed or was withheld is not submitted (transitive)."""
        if isinstance(failed, str):
            raise ValueError("pass the failed legs as a collection of leg refs, not a single string")
        failing = tuple(failed)
        if len(set(failing)) != len(failing):
            raise ValueError(f"duplicate leg in the failed set: {failing}")
        for ref in failing:
            self._known(ref)
        deps = dict(self.dependencies)
        sent: list[str] = []
        refused: list[str] = []
        withheld: list[str] = []
        blocked: set[str] = set()  # failed or withheld
        for ref in self.sequence:  # protectors always come earlier in the sequence, so one pass is the fixpoint
            if any(p in blocked for p in deps.get(ref, ())):
                withheld.append(ref)
                blocked.add(ref)
                continue
            sent.append(ref)
            if ref in failing:
                refused.append(ref)
                blocked.add(ref)
        return Simulation(tuple(sent), tuple(refused), tuple(withheld))

    def simulate_slices(self, failed: Iterable[tuple[str, int]]) -> Simulation:
        """AC-4 per slice (W-028): a failed slice ``(leg_ref, slice_no)`` of this sequence's orders counts as a failed
        leg, so every dependent of that leg is withheld."""
        failing = tuple(failed)
        known = {(o.leg_ref, o.slice_no) for o in self.orders}
        for item in failing:
            if not isinstance(item, tuple) or len(item) != 2 or isinstance(item[1], bool) or item not in known:
                raise ValueError(f"{item!r} is not a (leg_ref, slice_no) order of this plan")
        if len(set(failing)) != len(failing):
            raise ValueError(f"duplicate slice in the failed set: {failing}")
        return self.simulate(tuple(dict.fromkeys(ref for ref, _ in failing)))


def protects(protector: Leg, sold: Leg) -> bool:
    """True when ``protector`` caps ``sold``'s loss (rules and sources in the module docstring)."""
    if sold.action is not Action.SELL or sold.instrument is Instrument.FUT or protector is sold:
        return False
    if protector.expiry < sold.expiry:
        return False
    if sold.instrument is Instrument.CE:
        return protector.action is Action.BUY and protector.instrument in (Instrument.CE, Instrument.FUT)
    return (protector.action is Action.BUY and protector.instrument is Instrument.PE) or (
        protector.action is Action.SELL and protector.instrument is Instrument.FUT)


def _naked(legs: tuple[PlannedLeg, ...], dependencies: list[tuple[str, tuple[str, ...]]]) -> list[Unprotected]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x

    for sold, prots in dependencies:
        for p in prots:
            parent[find(p)] = find(sold)
    sold_legs = [p for p in legs if p.leg.action is Action.SELL and p.leg.instrument is not Instrument.FUT]
    protector_refs = {r for _, prots in dependencies for r in prots}
    out: list[Unprotected] = []
    seen: set[str] = set()
    for s in sold_legs:
        root = find(s.leg_ref)
        if root in seen:
            continue
        seen.add(root)
        members = [p for p in legs if find(p.leg_ref) == root]
        sold_units = sum(m.leg.quantity for m in members if m in sold_legs)
        cover = sum(m.leg.quantity for m in members if m.leg_ref in protector_refs)
        if sold_units > cover:
            out.append(Unprotected(tuple(m.leg_ref for m in members if m in sold_legs), sold_units - cover))
    return out


def _margin_order(plan: ExecutionPlan, steps: dict[StepKind, list[str]],
                  planner: MarginPlanner | None) -> tuple[bool, str]:
    """Reorder each step by margin impact (lower first) in place; return (used, note). Fail -> protection only."""
    if planner is None:
        return False, f"{MARGIN_NOT_USED} (no margin planner)"
    if not any(len(refs) > 1 for refs in steps.values()):
        return False, "margin impact not needed: no step has two legs to order"
    try:
        base = plan_margin(Strategy(tuple(p.leg for p in plan.legs)), planner).total
        impact: dict[str, Decimal] = {}
        for refs in steps.values():
            if len(refs) < 2:
                continue
            for ref in refs:
                others = tuple(p.leg for p in plan.legs if p.leg_ref != ref)
                impact[ref] = base - plan_margin(Strategy(others), planner).total
    except Exception as exc:  # any planner failure: protection-only order, said out loud
        return False, f"{MARGIN_NOT_USED} ({exc})"
    for kind, refs in steps.items():
        if len(refs) > 1:
            steps[kind] = sorted(refs, key=lambda r: impact[r])  # sorted() is stable: ties keep the user's order
    return True, f"margin impact used as the tie-break within each step; {MARGIN_UNVERIFIED}"


def _positive_int(value: object, name: str, cap: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or (cap is not None and value > cap):
        raise ValueError(f"{name} must be a positive integer{f' up to {cap}' if cap else ''}, got {value!r}")
    return value


def _lot_sizes(plan: ExecutionPlan, catalogue: Catalogue) -> dict[str, int]:
    """Each plan leg's lot size from Zerodha's row of the catalogue entry of its contract (REQ-054 AC-4); every
    leg a whole number of lots. An entry with no Zerodha row has no Zerodha symbol and is never matched."""
    if not isinstance(catalogue, Catalogue):
        raise ValueError(f"lot sizes come from the instrument catalogue, got {catalogue!r}")
    by_symbol: dict[str, list[int]] = {}
    for entry in catalogue.all_entries():
        if entry.has_ref(ZERODHA):
            ref = entry.ref(ZERODHA)
            by_symbol.setdefault(ref.broker_symbol, []).append(ref.lot_size)
    lots: dict[str, int] = {}
    for p in plan.legs:
        found = by_symbol.get(p.contract, [])
        if len(found) != 1:
            raise ValueError(f"{p.contract}: the catalogue has {len(found)} instruments with that symbol; "
                             "no lot size, nothing is planned")
        lots[p.leg_ref] = _positive_int(found[0], f"catalogue lot size of {p.contract}")
        if p.leg.quantity % lots[p.leg_ref]:
            raise ValueError(f"{p.contract}: {p.leg.quantity} units is not a whole number of lots of "
                             f"{lots[p.leg_ref]}")
    return lots


def _quantities(plan: ExecutionPlan, quantities: Mapping[str, int] | None) -> dict[str, int]:
    """Units to order per leg: the full plan by default, else ``quantities`` (known legs, 1..planned units).
    Lot alignment of each quantity is checked where it is sliced (``slice_quantity``)."""
    if quantities is None:
        return {p.leg_ref: p.leg.quantity for p in plan.legs}
    if not isinstance(quantities, Mapping):
        raise ValueError(f"quantities must map leg refs to units, got {quantities!r}")
    wanted = {}
    for ref, units in quantities.items():
        p = plan.by_ref(ref) if isinstance(ref, str) else None
        if p is None:
            raise ValueError(f"leg {ref!r} is not in this plan")
        wanted[ref] = _positive_int(units, f"units to order of {ref}", p.leg.quantity)
    return wanted


def slice_quantity(constraints: BrokerConstraints, contract: str, units: int, lot: int | None) -> tuple[int, ...]:
    """THE slicing rule (W-028), shared by every order-preparing path: ``units`` of ``contract`` as orders of at most
    the freeze quantity. With a ``lot``: ``units`` must be whole lots, the freeze is rounded DOWN to whole lots
    (orchestrator default) and a freeze below one lot is refused, so every slice is lot-aligned."""
    freeze = _positive_int(constraints.freeze_quantity(contract), f"freeze quantity of {contract}")
    if lot is not None:
        if units % lot:
            raise ValueError(f"{units} units of {contract} is not a whole number of lots of {lot}")
        freeze = freeze // lot * lot
        if freeze == 0:
            raise ValueError(f"{contract}: the freeze quantity is below one lot of {lot}")
    if -(-units // freeze) > MAX_SLICES_PER_LEG:
        raise ValueError(f"{contract}: {units} units at a freeze of {freeze} needs more than "
                         f"{MAX_SLICES_PER_LEG} orders")
    full, rest = divmod(units, freeze)
    return (freeze,) * full + ((rest,) if rest else ())


def _batched(plan: ExecutionPlan, groups: Sequence[Sequence[str]], constraints: BrokerConstraints,
             quantities: Mapping[str, int], lots: Mapping[str, int] | None) -> tuple[PlannedOrder, ...]:
    """Slice every leg of every group (a step) and number the batches: a new batch at every step boundary and every
    ``max_orders_per_batch`` orders, so a batch never spans two steps. Legs not in ``quantities`` get no orders."""
    per_batch = _positive_int(constraints.max_orders_per_batch(), "max_orders_per_batch", MAX_BATCH_SIZE)
    out: list[PlannedOrder] = []
    batch = 0
    for number, group in enumerate(groups, start=1):
        in_step = 0
        for ref in group:
            if ref not in quantities:
                continue
            sizes = slice_quantity(constraints, plan.by_ref(ref).contract, quantities[ref],
                                   lots[ref] if lots is not None else None)
            for slice_no, size in enumerate(sizes, start=1):
                if in_step % per_batch == 0:
                    batch += 1
                out.append(PlannedOrder(number, batch, ref, slice_no, size))
                in_step += 1
    return tuple(out)


def exit_orders(plan: ExecutionPlan, groups: Sequence[Sequence[tuple[str, int]]],
                constraints: BrokerConstraints | None, catalogue: Catalogue) -> tuple[PlannedOrder, ...]:
    """Close Partial Strategy's orders (W-032, REQ-056 AC-10): ``groups`` are the exit steps in the order the close
    sends them (OD-e: buy-backs of shorts, then sells of longs), each a sequence of (leg_ref, units to exit). Every
    leg is sliced by ``slice_quantity`` with its catalogue lot, batches never span two steps. A leg appears at most
    once and never exits more than its planned units (reduce-only upper bound; the held-units cap is the caller's)."""
    lots = _lot_sizes(plan, catalogue)
    refs = [ref for group in groups for ref, _ in group]
    if len(set(refs)) != len(refs):
        raise ValueError(f"a leg appears more than once in the exits: {refs}")
    wanted = _quantities(plan, {ref: units for group in groups for ref, units in group})
    return _batched(plan, [[ref for ref, _ in group] for group in groups],
                    constraints if constraints is not None else UnverifiedDefaultConstraints(), wanted, lots)


ORDERING_BASIS: Final = (
    "protective legs before the sold legs that depend on them (ADR-017 Q26); within a step, margin impact when "
    "known, otherwise the order you confirmed; legs above the freeze quantity split, batches never span two steps."
)


def sequence_plan(plan: ExecutionPlan, margin_planner: MarginPlanner | None = None,
                  constraints: BrokerConstraints | None = None, *, catalogue: Catalogue | None = None,
                  quantities: Mapping[str, int] | None = None) -> OrderSequence:
    """Build the leg dependencies, the order sequence and the orders for ``plan`` (rules in the module docstring).

    ``catalogue``: lot sizes (every leg and slice a whole number of lots). ``quantities``: units still to order per
    leg (Complete / Retry); legs not named get no orders."""
    if not isinstance(plan, ExecutionPlan):
        raise ValueError(f"sequence_plan needs an ExecutionPlan, got {plan!r}")
    lots = _lot_sizes(plan, catalogue) if catalogue is not None else None
    wanted = _quantities(plan, quantities)
    legs = plan.legs
    dependencies: list[tuple[str, tuple[str, ...]]] = []
    for p in legs:
        prots = tuple(q.leg_ref for q in legs if protects(q.leg, p.leg))
        if prots:
            dependencies.append((p.leg_ref, prots))
    protector_refs = {ref for _, prots in dependencies for ref in prots}
    dependent_refs = {ref for ref, _ in dependencies}
    undetermined = [
        Undetermined(p.leg_ref, "the spec defines no protection OF a futures leg (ADR-017 Q26: futures strategies "
                                "differ); this futures leg has no dependency")
        for p in legs if p.leg.instrument is Instrument.FUT and p.leg_ref not in protector_refs
        and any(q.leg.instrument is not Instrument.FUT for q in legs)
    ]
    members = {
        StepKind.PROTECTION: [p.leg_ref for p in legs if p.leg_ref in protector_refs],
        StepKind.SHORT_POSITIONS: [p.leg_ref for p in legs if p.leg_ref in dependent_refs],
        StepKind.OTHER: [p.leg_ref for p in legs if p.leg_ref not in protector_refs | dependent_refs],
    }
    used, note = _margin_order(plan, members, margin_planner)
    steps = tuple(PlanStep(kind, tuple(refs)) for kind, refs in members.items() if refs)
    orders = _batched(plan, [step.leg_refs for step in steps],
                      constraints if constraints is not None else UnverifiedDefaultConstraints(), wanted, lots)
    return OrderSequence(plan.strategy_id, steps, tuple(dependencies), tuple(undetermined),
                         tuple(_naked(legs, dependencies)), ORDERING_BASIS, orders, used, note, _BUILDER_KEY)
