"""The execution review: what the user sees before pressing Execute (REQ-056 AC-5; ADR-017 Q26).

Spec basis: REQ-056 AC-5 "The execution review shows strategy, margin, max loss, max profit, current P&L, leg count,
execution sequence and broker." ADR-008: every P&L number comes from the one engine. ADR-016: margin comes from the
planner interface, Zerodha's own figure stays final. Unknown means unknown: a value that cannot be computed is
``None`` with the reason in ``unknown``, never 0.

- max profit / max loss: ``strategy_metrics`` (engine); ``UNLIMITED`` passes through; a multi-expiry strategy has no
  exact at-expiry metrics (``MultiExpiryError``), so both are unknown.
- current P&L: the engine's live P&L, only when every leg has an LTP.
- margin: ``plan_margin(strategy, planner)`` (engine interface); a planner that fails or breaks its contract leaves it
  unknown.
- sequence: built here by ``sequence_plan`` with the same planner and broker constraints (never accepted from the
  caller): one line per order (the slicing of a leg above the freeze limit still shows here; the review now BLOCKS such a
  leg, ADR-081, and the slicing remainder is issue #255), the margin-impact basis, and
  the undetermined / naked notes from the same protection relation the sequence uses.
- broker: Zerodha, the only V1 broker (ADR-012, ADR-029: brokers sit behind adapters).
"""
from __future__ import annotations
from ofo.errors.explanations import render_explanation

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

from ofo.engine import Action, Strategy, strategy_metrics
from ofo.engine.interfaces import MarginPlanner, plan_margin
from ofo.engine.metrics import MultiExpiryError
from ofo.execution.freeze import FreezeFinding, StoredFreeze, freeze_check
from ofo.execution.planned import ExecutionPlan
from ofo.execution.sequence import BrokerConstraints, OrderSequence, sequence_plan

BROKER: Final = "Zerodha"


@dataclass(frozen=True)
class ReviewLine:
    step: int
    step_label: str
    leg_ref: str
    action: Action
    contract: str
    quantity: int
    batch: int = 1
    slice_no: int = 1


@dataclass(frozen=True)
class ExecutionReview:
    strategy_id: str
    margin_required: Decimal | None
    max_loss: object  # Decimal, UNLIMITED, or None when unknown
    max_profit: object  # Decimal, UNLIMITED, or None when unknown
    current_pnl: Decimal | None
    leg_count: int
    sequence: tuple[ReviewLine, ...]
    broker: str
    margin_basis: str  # how margin impact entered the order ("margin impact unknown — not used" when it did not)
    notes: tuple[str, ...]  # undetermined protection and naked units, from the sequence builder
    unknown: tuple[tuple[str, str], ...]  # (field, reason) for every value shown as unknown
    blocked: tuple[FreezeFinding, ...] = ()  # W-076: legs not below their freeze limit; Execute is not offered
    warnings: tuple[FreezeFinding, ...] = ()  # W-076: legs with no stored freeze limit

    @property
    def can_execute(self) -> bool:
        return not self.blocked


def _lines(plan: ExecutionPlan, seq: OrderSequence) -> tuple[ReviewLine, ...]:
    labels = {number: step.kind.value for number, step in enumerate(seq.steps, start=1)}
    out = []
    for order in seq.orders:
        p = plan.by_ref(order.leg_ref)
        out.append(ReviewLine(order.step, labels[order.step], order.leg_ref, p.leg.action, p.contract, order.quantity,
                              order.batch, order.slice_no))
    return tuple(out)


def _notes(seq: OrderSequence) -> tuple[str, ...]:
    notes = [render_explanation("review_note_undetermined", leg=u.leg_ref, reason=u.reason) for u in seq.undetermined]
    notes += [render_explanation("review_note_naked", legs=tuple(u.leg_refs), units=u.units) for u in seq.unprotected]
    return tuple(notes)


def execution_review(plan: ExecutionPlan, planner: MarginPlanner | None,
                     constraints: BrokerConstraints | None = None, *,
                     freeze_limits: Mapping[str, StoredFreeze] | None, today: date) -> ExecutionReview:
    """AC-5: build the review from the engine, the margin planner and the sequence builder.

    W-076 (ADR-081): ``freeze_limits`` (broker trading symbol -> stored limit) decides which legs are blocked; a leg
    with no entry carries the warning. The argument is REQUIRED (no default, so the check cannot be skipped by
    omission), as is ``today`` (the review date, passed in by the caller, for the limit's age warning); ``None`` means no limit is known, so every leg warns. Build it with ``freeze_limits_for_plan``."""
    if not isinstance(plan, ExecutionPlan):
        raise ValueError(f"execution_review needs an ExecutionPlan, got {plan!r}")
    strategy = Strategy(tuple(p.leg for p in plan.legs))
    unknown: list[tuple[str, str]] = []
    max_loss = max_profit = None
    try:
        metrics = strategy_metrics(strategy)
        max_loss, max_profit = metrics.max_loss, metrics.max_profit
    except MultiExpiryError:
        multi_expiry = render_explanation("review_unknown_multi_expiry")
        unknown += [("max_loss", multi_expiry), ("max_profit", multi_expiry)]
    current = None
    if all(p.leg.ltp is not None for p in plan.legs):
        current = strategy.live_pnl()
    else:
        unknown.append(("current_pnl", render_explanation("review_unknown_no_ltp")))
    margin = None
    try:
        margin = plan_margin(strategy, planner).total
    except Exception as exc:  # fail closed to "unknown": never a made-up figure
        unknown.append(("margin_required", render_explanation("review_unknown_margin")))  # the planner's own error is not shown
    seq = sequence_plan(plan, planner, constraints)
    freeze = freeze_check(plan, freeze_limits, today=today)
    return ExecutionReview(plan.strategy_id, margin, max_loss, max_profit, current, len(plan.legs), _lines(plan, seq),
                           BROKER, seq.margin_note, _notes(seq), tuple(unknown), freeze.blocks, freeze.warnings)


__all__ = ["BROKER", "ExecutionReview", "ReviewLine", "execution_review"]
