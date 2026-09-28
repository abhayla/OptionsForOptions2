"""Margin-planning and charges interfaces (REQ-032 AC-6; IC §5).

Interfaces only. The charges model is open (spec/requirements/REQ-032.md "Open", §95) and Zerodha is the authority on
margin (ADR-016), so the engine holds no rate, slab or broker call: a provider (a broker adapter, a configured
charges table) implements these protocols and the engine checks what it returns. Every amount is exact money.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from ofo.engine.legs import require_price
from ofo.engine.strategy import Strategy


@dataclass(frozen=True)
class MarginRequirement:
    """Margin a strategy needs, in rupees, and who stated it (e.g. the broker's basket-margin response)."""

    total: Decimal
    source: str

    def __post_init__(self) -> None:
        require_price(self.total, "margin total")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("a margin requirement must name its source")


@dataclass(frozen=True)
class ChargesBreakdown:
    """Named charge components in rupees (brokerage, STT, exchange, GST, stamp duty, ...), as the provider states."""

    items: tuple[tuple[str, Decimal], ...]

    def __post_init__(self) -> None:
        items = tuple(self.items)
        if not items:
            raise ValueError("a charges breakdown needs at least one component")
        for name, amount in items:
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"every charge component needs a name, got {name!r}")
            require_price(amount, f"charge {name!r}")
        object.__setattr__(self, "items", items)

    @property
    def total(self) -> Decimal:
        return sum((amount for _, amount in self.items), Decimal(0))


@runtime_checkable
class MarginPlanner(Protocol):
    """Anything that can state the margin a strategy needs before it is placed."""

    def margin_for(self, strategy: Strategy) -> MarginRequirement: ...


@runtime_checkable
class ChargesModel(Protocol):
    """Anything that can state the charges of placing (or exiting) a strategy."""

    def charges_for(self, strategy: Strategy) -> ChargesBreakdown: ...


def plan_margin(strategy: Strategy, planner: MarginPlanner) -> MarginRequirement:
    """Ask ``planner`` for the strategy's margin; refuse a planner or an answer that breaks the contract."""
    if not isinstance(planner, MarginPlanner):
        raise ValueError(f"{planner!r} does not implement MarginPlanner")
    result = planner.margin_for(strategy)
    if not isinstance(result, MarginRequirement):
        raise ValueError(f"the margin planner returned {type(result).__name__}, not a MarginRequirement")
    return result


def estimate_charges(strategy: Strategy, model: ChargesModel) -> ChargesBreakdown:
    """Ask ``model`` for the strategy's charges; refuse a model or an answer that breaks the contract."""
    if not isinstance(model, ChargesModel):
        raise ValueError(f"{model!r} does not implement ChargesModel")
    result = model.charges_for(strategy)
    if not isinstance(result, ChargesBreakdown):
        raise ValueError(f"the charges model returned {type(result).__name__}, not a ChargesBreakdown")
    return result


def pnl_after_charges(pnl: Decimal, charges: ChargesBreakdown) -> Decimal:
    """Strategy P&L net of the stated charges."""
    if not isinstance(pnl, Decimal) or not pnl.is_finite():
        raise ValueError(f"pnl must be a finite decimal.Decimal, got {pnl!r}")
    return pnl - charges.total
