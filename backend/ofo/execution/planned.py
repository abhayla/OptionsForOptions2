"""The legs a user confirmed for execution: ``PlannedLeg`` and ``ExecutionPlan`` (REQ-056, REQ-058).

Moved here unchanged from ``partial.py`` (W-023) so that the order-sequence builder (``sequence.py``, W-022) and the
partial-execution module can both use them without importing each other. ``partial.py`` re-exports both names.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ofo.engine import Leg

MAX_PLAN_LEGS: Final = 20  # orchestrator default OD-g (W-023)


def ident(value: object, name: str) -> str:
    """Return ``value`` if it is a non-empty string without surrounding whitespace; raise ``ValueError`` otherwise."""
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a non-empty string without surrounding whitespace, got {value!r}")
    return value


@dataclass(frozen=True)
class PlannedLeg:
    """One leg the user confirmed: ``contract`` is the broker's trading symbol, ``leg`` the engine leg."""

    leg_ref: str
    contract: str
    leg: Leg

    def __post_init__(self) -> None:
        ident(self.leg_ref, "leg_ref")
        ident(self.contract, "contract")
        if not isinstance(self.leg, Leg):
            raise ValueError(f"leg must be an engine Leg, got {self.leg!r}")


@dataclass(frozen=True)
class ExecutionPlan:
    strategy_id: str
    legs: tuple[PlannedLeg, ...]

    def __post_init__(self) -> None:
        ident(self.strategy_id, "strategy_id")
        legs = tuple(self.legs)
        if not legs or len(legs) > MAX_PLAN_LEGS:
            raise ValueError(f"a plan needs 1..{MAX_PLAN_LEGS} legs, got {len(legs)}")
        if not all(isinstance(p, PlannedLeg) for p in legs):
            raise ValueError("every plan leg must be a PlannedLeg")
        for attr in ("leg_ref", "contract"):
            values = [getattr(p, attr) for p in legs]
            if len(set(values)) != len(values):
                raise ValueError(f"duplicate {attr} in the plan: {values}")
        object.__setattr__(self, "legs", legs)

    def by_contract(self, contract: str) -> PlannedLeg | None:
        return next((p for p in self.legs if p.contract == contract), None)

    def by_ref(self, leg_ref: str) -> PlannedLeg | None:
        return next((p for p in self.legs if p.leg_ref == leg_ref), None)
