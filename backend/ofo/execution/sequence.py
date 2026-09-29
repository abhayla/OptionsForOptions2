"""The execution plan: leg dependencies and the order sequence (REQ-056 AC-2, AC-3, AC-4; ADR-017 Q26).

Spec basis:
- REQ-056 AC-2 "an execution plan with leg dependencies and an order sequence based on protection, margin impact,
  dependencies and broker constraints"; AC-3 "protective/buy legs before the sell legs that depend on them, but 'all
  buys first' is never hard-coded for every strategy"; AC-4 "If a protective leg fails, the sell leg that depends on
  it is not submitted" (core invariant 21).
- ADR-017 Q26: "Strategy -> Execution Plan -> Leg Dependencies -> Execution Sequence -> Orders"; the user sees
  "Step 1 - Establish protection · Step 2 - Establish short positions"; "futures/naked strategies differ". The owner's
  reason (T1 #55): buys placed first free margin for the sells they hedge.

Rules, each labelled with where it comes from:
- DEP (orchestrator default, W-022 brief, built to its stated principle "the bought leg(s) that cap its risk"): a
  SOLD option leg depends on every BOUGHT option leg of the same expiry and the same option type. A bought call of
  ANY strike caps a sold call's upside loss, and a bought put of any strike caps a sold put's downside loss (a bull
  call spread's bought call sits BELOW its sold call and still hedges it), so strike is not a condition. The brief's
  "strike beyond it on the protective side" is narrower than its own principle and would leave a debit spread's sell
  unprotected; this conflict is reported, not decided silently. Same underlying: an ``ExecutionPlan`` belongs to one
  strategy, and a strategy has one underlying (``ExecutionContext.underlying``).
- UNDETERMINED (brief: "applies only if the spec defines it"): the spec defines no protection across expiries
  (calendar, diagonal) and none by or of a futures leg (ADR-017 Q26 only says futures strategies "differ"). Such legs
  get NO dependency and are listed in ``undetermined`` with the reason, so the review can say so.
- STEPS (ADR-017 Q26 display): step 1 "Establish protection" = every bought leg some sold leg depends on; step 2
  "Establish short positions" = every sold leg that depends on a step-1 leg; step 3 = every other leg (no protection
  relation, including undetermined legs). Within a step, legs keep the order the user confirmed them in (the stable,
  documented order). A strategy with no dependency is therefore sent exactly in the user's order: a sell can precede
  a buy, so "all buys first" is never imposed (AC-3).
- MARGIN IMPACT: enters only through protection (the owner's reason for protective-first). No per-leg margin figure
  is used to reorder legs, because ADR-017 Q26 says "Verify real Zerodha margin behaviour before relying on it" and no
  verified per-leg source exists; this is stated in ``ordering_basis``, not hidden.
- BROKER CONSTRAINTS: the plan-size cap (``MAX_PLAN_LEGS``, W-023 OD-g). Order-rate limits and market protection are
  REQ-056 AC-10 (not this item).
- WITHHOLD (AC-4): a dependent is not submitted when ANY of its protectors failed or was itself withheld (fixpoint,
  so the rule is transitive whatever the graph's depth). A sold leg's protection is the sum of its protectors; with
  one of them missing its protection is incomplete, so it is withheld.
- RATIO (orchestrator default, documented per the reviewer checklist): when the sold units of an (expiry, option
  type) group exceed its bought units, the excess is naked. Units are fungible within a contract, so no sold leg of
  the group is singled out as "the naked one": every sold leg of the group depends on the group's bought legs, is
  sequenced after them, and is withheld if they fail. The shortfall is listed in ``unprotected``.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

from ofo.engine import Action, Instrument
from ofo.execution.planned import ExecutionPlan, PlannedLeg

_BUILDER_KEY: Final = object()
ORDERING_BASIS: Final = (
    "protective legs before the sold legs that depend on them (ADR-017 Q26); otherwise the order you confirmed. "
    "Per-leg margin impact is not used to reorder legs: Zerodha's margin behaviour is not yet verified (ADR-017 Q26)."
)


class StepKind(Enum):
    PROTECTION = "Establish protection"
    SHORT_POSITIONS = "Establish short positions"
    OTHER = "Legs with no protection relation"


@dataclass(frozen=True)
class PlanStep:
    kind: StepKind
    leg_refs: tuple[str, ...]


@dataclass(frozen=True)
class Undetermined:
    leg_ref: str
    reason: str


@dataclass(frozen=True)
class Unprotected:
    """Sold units of one (expiry, option type) group that no bought leg covers: naked."""

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


def _is_option(p: PlannedLeg) -> bool:
    return p.leg.instrument is not Instrument.FUT


def sequence_plan(plan: ExecutionPlan) -> OrderSequence:
    """Build the leg dependencies and the order sequence for ``plan`` (rules in the module docstring)."""
    if not isinstance(plan, ExecutionPlan):
        raise ValueError(f"sequence_plan needs an ExecutionPlan, got {plan!r}")
    legs = plan.legs
    has_futures = any(not _is_option(p) for p in legs)
    has_options = any(_is_option(p) for p in legs)
    dependencies: list[tuple[str, tuple[str, ...]]] = []
    undetermined: list[Undetermined] = []
    unprotected: list[Unprotected] = []
    for p in legs:
        if not _is_option(p):
            if has_options:
                undetermined.append(Undetermined(
                    p.leg_ref, "the spec does not define protection by or of a futures leg (ADR-017 Q26: futures "
                               "strategies differ); this leg has no dependency"))
            continue
        if p.leg.action is not Action.SELL:
            continue
        protectors = tuple(
            q.leg_ref for q in legs
            if _is_option(q) and q.leg.action is Action.BUY and q.leg.instrument is p.leg.instrument
            and q.leg.expiry == p.leg.expiry
        )
        if protectors:
            dependencies.append((p.leg_ref, protectors))
            continue
        cross_expiry = any(
            _is_option(q) and q.leg.action is Action.BUY and q.leg.instrument is p.leg.instrument for q in legs)
        if cross_expiry or has_futures:
            what = "another expiry (calendar/diagonal)" if cross_expiry else "a futures leg"
            undetermined.append(Undetermined(
                p.leg_ref, f"its only possible protection is {what}, which the spec does not define as protection; "
                           "this leg has no dependency"))
    groups: dict[tuple[object, Instrument], list[PlannedLeg]] = {}
    for p in legs:
        if _is_option(p):
            groups.setdefault((p.leg.expiry, p.leg.instrument), []).append(p)
    for members in groups.values():
        sold = sum(m.leg.quantity for m in members if m.leg.action is Action.SELL)
        bought = sum(m.leg.quantity for m in members if m.leg.action is Action.BUY)
        if sold > bought:
            unprotected.append(Unprotected(
                tuple(m.leg_ref for m in members if m.leg.action is Action.SELL), sold - bought))
    protector_refs = {ref for _, prots in dependencies for ref in prots}
    dependent_refs = {ref for ref, _ in dependencies}
    step_members = {
        StepKind.PROTECTION: tuple(p.leg_ref for p in legs if p.leg_ref in protector_refs),
        StepKind.SHORT_POSITIONS: tuple(p.leg_ref for p in legs if p.leg_ref in dependent_refs),
        StepKind.OTHER: tuple(p.leg_ref for p in legs
                              if p.leg_ref not in protector_refs and p.leg_ref not in dependent_refs),
    }
    steps = tuple(PlanStep(kind, refs) for kind, refs in step_members.items() if refs)
    return OrderSequence(plan.strategy_id, steps, tuple(dependencies), tuple(undetermined), tuple(unprotected),
                         ORDERING_BASIS, _BUILDER_KEY)
