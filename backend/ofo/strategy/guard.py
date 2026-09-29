"""Strategy Guard: an action that changes the strategy's risk profile needs an explicit acknowledgement (REQ-036 AC-5).

Spec basis:
- REQ-036 AC-5 "Strategy Guard: before execution or modification, an action that changes the strategy's risk profile
  shows 'This action changes your strategy's risk profile' with the consequences before the user can proceed".
- ADR-002 (T1 #74-#75): before execution or modification the platform checks whether the action fits the strategy;
  if not, the message and the consequences are shown first.
- W-026 objective: the risk profile is max loss, max profit, breakevens, the unlimited side and margin. ADR-008: every
  number comes from the one engine (``strategy_metrics``, ``net_premium``); nothing here re-derives a payoff.

How the guard is used (never trusting a caller's verdict):
- The owning flow (``ofo.execution.partial`` for execution, ``ofo.strategy.modification`` for modification) builds
  the before and after strategies itself, from its own grounded inputs, and calls :meth:`StrategyGuard.issue`. The
  guard compares the two engine profiles and records the decision under a :class:`GuardBinding` (strategy id,
  version id, hash of the exact proposal). When the profile changes, the decision carries a random, single-use
  acknowledgement token.
- Before anything is sent or applied the flow recomputes the binding from the proposal as it stands NOW and calls
  :meth:`StrategyGuard.redeem`. No entry for that binding (the guard never saw this exact proposal) refuses; a
  flagged entry refuses unless the token given is that entry's own token; a redeemed entry is gone. So a forged
  token, a token of another proposal, a token reused after the proposal changed, and a second use all refuse.
- The guard lives on the ``StrategyRecord`` (``record.guard``); callers cannot supply one.

Orchestrator defaults (not stated by the spec):
- OD-G1 the net premium counts by its SIGN only (credit / debit / zero), as the brief names it; its amounts are
  still shown in the consequences.
- OD-G2 margin counts: known on both sides and different is a change; unknown on either side is ALSO a change (fail
  closed: the platform cannot say the margin is unchanged). A margin-only change is therefore flagged.
- OD-G3 an action that leaves no position has the flat profile: max profit 0, max loss 0, no breakevens, net premium
  0, margin 0 (a payoff that is 0 at every level).
- OD-G4 at most ``MAX_OPEN_DECISIONS`` undecided decisions per strategy; the oldest is dropped first (a dropped
  decision simply has to be checked again). Issuing again for the same binding replaces the earlier token.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from ofo.engine import PriceBasis, Strategy, net_premium, strategy_metrics
from ofo.engine.legs import Leg, require_decimal
from ofo.engine.metrics import _Unlimited

RISK_PROFILE_CHANGED: Final = "This action changes your strategy's risk profile"
MAX_OPEN_DECISIONS: Final = 100  # orchestrator default OD-G4
_ZERO: Final = Decimal("0")


class GuardRefused(ValueError):
    """The action changes the risk profile and was not acknowledged for this exact proposal, or was never checked."""


@dataclass(frozen=True)
class RiskProfile:
    """One side of the comparison. ``margin`` None = unknown (never 0)."""

    max_profit: Decimal | _Unlimited
    max_loss: Decimal | _Unlimited
    breakevens: tuple[Decimal, ...]
    net_premium: Decimal
    margin: Decimal | None
    has_position: bool


def risk_profile(strategy: Strategy | None, margin: Decimal | None) -> RiskProfile:
    """The engine's numbers for ``strategy`` (None = no position left, OD-G3). ``margin`` None means unknown."""
    if margin is not None:
        require_decimal(margin, "margin")
    if strategy is None:
        return RiskProfile(_ZERO, _ZERO, (), _ZERO, _ZERO, False)
    if not isinstance(strategy, Strategy):
        raise ValueError(f"risk_profile needs an engine Strategy or None, got {strategy!r}")
    metrics = strategy_metrics(strategy)
    return RiskProfile(metrics.max_profit, metrics.max_loss, metrics.breakevens,
                       net_premium(strategy, PriceBasis.ENTRY), margin, True)


@dataclass(frozen=True)
class Consequence:
    """One row of the before/after the user sees before proceeding."""

    metric: str
    before: object
    after: object
    changed: bool


def _sign(value: Decimal) -> int:
    return (value > 0) - (value < 0)


@dataclass(frozen=True)
class RiskChange:
    before: RiskProfile
    after: RiskProfile
    consequences: tuple[Consequence, ...]

    @property
    def changes_risk_profile(self) -> bool:
        return any(c.changed for c in self.consequences)

    @property
    def message(self) -> str | None:
        return RISK_PROFILE_CHANGED if self.changes_risk_profile else None


def compare_risk(before: RiskProfile, after: RiskProfile) -> RiskChange:
    """Every metric, before and after; ``changed`` per row. UNLIMITED is a singleton, so ``!=`` compares it exactly."""
    if not isinstance(before, RiskProfile) or not isinstance(after, RiskProfile):
        raise ValueError("compare_risk needs two RiskProfile values")
    margin_changed = before.margin is None or after.margin is None or before.margin != after.margin  # OD-G2
    rows = (
        Consequence("max profit", before.max_profit, after.max_profit, before.max_profit != after.max_profit),
        Consequence("max loss", before.max_loss, after.max_loss, before.max_loss != after.max_loss),
        Consequence("breakevens", before.breakevens, after.breakevens, before.breakevens != after.breakevens),
        Consequence("net premium", before.net_premium, after.net_premium,
                    _sign(before.net_premium) != _sign(after.net_premium)),  # OD-G1
        Consequence("margin", before.margin, after.margin, margin_changed),
        Consequence("position", before.has_position, after.has_position, before.has_position != after.has_position),
    )
    return RiskChange(before, after, rows)


def assess_risk_change(before: Strategy | None, after: Strategy | None, margin_before: Decimal | None,
                       margin_after: Decimal | None) -> RiskChange:
    """Pure: the engine profiles of ``before`` and ``after`` compared. Grants nothing on its own."""
    return compare_risk(risk_profile(before, margin_before), risk_profile(after, margin_after))


def legs_fingerprint(legs: tuple[Leg, ...]) -> list[list[str]]:
    """Canonical, order-independent description of engine legs (side, type, strike, expiry, units, entry price)."""
    rows = []
    for leg in legs:
        strike = "" if leg.strike is None else format(leg.strike.normalize(), "f")
        rows.append([leg.action.value, leg.instrument.value, strike, leg.expiry.isoformat(), str(leg.quantity),
                     format(leg.entry_price.normalize(), "f")])
    return sorted(rows)


def proposal_hash(payload: object) -> str:
    """SHA-256 of a JSON-serialisable description of the exact proposal."""
    return hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GuardBinding:
    """What a decision is bound to: this strategy, this version, this exact proposal."""

    strategy_id: str
    version_id: str
    proposal: str

    def __post_init__(self) -> None:
        for name in ("strategy_id", "version_id", "proposal"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"{name} must be a non-empty string, got {value!r}")


@dataclass(frozen=True)
class GuardDecision:
    """What the user is shown. ``acknowledgement`` is set only when the risk profile changes."""

    binding: GuardBinding
    change: RiskChange
    acknowledgement: str | None

    @property
    def changes_risk_profile(self) -> bool:
        return self.change.changes_risk_profile

    @property
    def message(self) -> str | None:
        return self.change.message


def _decision(binding: GuardBinding, change: RiskChange) -> GuardDecision:
    """Private: a decision with a fresh random token when the profile changes. Used by the owning flows only."""
    if not isinstance(binding, GuardBinding) or not isinstance(change, RiskChange):
        raise ValueError("a guard decision needs a GuardBinding and a RiskChange")
    return GuardDecision(binding, change, secrets.token_urlsafe(32) if change.changes_risk_profile else None)


class StrategyGuard:
    """Per-strategy decision store. Issued only by the owning flows; redeemed once, for the same binding."""

    __slots__ = ("_open",)

    def __init__(self) -> None:
        self._open: dict[GuardBinding, GuardDecision] = {}

    def _issue(self, binding: GuardBinding, before: Strategy | None, after: Strategy | None,
               margin_before: Decimal | None, margin_after: Decimal | None) -> GuardDecision:
        """Private (W-026): called only by ``propose_modification``, which builds ``before``/``after`` itself from
        the record's active definition and the proposed change. No public method accepts metrics or a verdict."""
        decision = _decision(binding, assess_risk_change(before, after, margin_before, margin_after))
        self._open.pop(binding, None)
        while len(self._open) >= MAX_OPEN_DECISIONS:  # OD-G4
            del self._open[next(iter(self._open))]
        self._open[binding] = decision
        return decision

    def _find(self, binding: GuardBinding, acknowledgement: object) -> GuardDecision:
        decision = self._open.get(binding)
        if decision is None:
            raise GuardRefused("Strategy Guard has not checked this exact action for this strategy and version; "
                               "check it again before proceeding. Nothing was sent.")
        if decision.acknowledgement is not None:
            if not isinstance(acknowledgement, str) or not hmac.compare_digest(acknowledgement,
                                                                                decision.acknowledgement):
                rows = "; ".join(f"{c.metric}: {c.before!r} -> {c.after!r}" for c in decision.change.consequences
                                 if c.changed)
                raise GuardRefused(f"{RISK_PROFILE_CHANGED}: {rows}. Acknowledge it to proceed. Nothing was sent.")
        return decision

    def withdraw(self, binding: GuardBinding) -> None:
        """The user dropped the action: its decision (and token) can no longer be used."""
        self._open.pop(binding, None)

    def check(self, binding: GuardBinding, acknowledgement: str | None) -> GuardDecision:
        """Refuse unless ``binding`` was checked and, when flagged, ``acknowledgement`` is its own token. Keeps it."""
        return self._find(binding, acknowledgement)

    def redeem(self, binding: GuardBinding, acknowledgement: str | None) -> GuardDecision:
        """As :meth:`check`, then consume the decision: it can never be used again."""
        decision = self._find(binding, acknowledgement)
        del self._open[binding]
        return decision
