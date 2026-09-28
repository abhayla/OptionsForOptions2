"""REQ-059 AC-5, version-history half: the user's explicit choice of an offered alternative, recorded through W-012.

Spec basis: REQ-059 AC-5 "An unavailable contract is kept in the version history, the problem is shown,
alternatives may be offered, the user chooses explicitly, and any change becomes a new proposed version once the
strategy has been executed, or an activity-history entry before its first execution (Q44, Q135, Q190)"; ADR-019
Q190/Q191; ADR-016 Q44 (never silent substitution).

- ``check_pre_execution`` only reports (problem + offered strikes); it never touches the stored strategy.
- ``record_alternative_choice`` is the ONLY path from a report to a change, and it runs only on an explicit user
  choice of one of the OFFERED strikes. It goes through ``StrategyRecord.edit``: before the first execution that is
  an activity-history entry; after it, a new proposed version that becomes active only after confirmation and a
  matching execution result (W-012). The earlier configuration or version, with the unavailable contract, stays in
  the history unchanged. W-012's refusals (reconciliation required, a proposal pending) apply as they are.
- ``gate_inputs_from_record`` builds the gate's ``active_legs``, ``active_version_id`` and ``active_legs_hash``
  from the record's stored active Version, so a caller never hand-rolls them. Known limit: a stored definition
  carries no entry prices, so the legs carry entry price 0.00. Options are unaffected (rule 5 already treats option
  premiums as 0); a FUTURES leg's entry would be compared at 0, so adjustments of strategies with futures legs need
  the entry price wired by the integration work item before rule 5 is trusted for them.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

from ofo.engine import Leg, Strategy
from ofo.execution.context import active_legs_hash
from ofo.execution.safety import CheckCode, CheckFailure
from ofo.strategy.versions import HistoryEntry, StrategyRecord, Version

UNAVAILABLE_CODES: frozenset[CheckCode] = frozenset({
    CheckCode.CONTRACT_NOT_FOUND,
    CheckCode.CONTRACT_NOT_LISTED,
    CheckCode.CONTRACT_NOT_ELIGIBLE,
})
_ZERO = Decimal("0.00")


def record_alternative_choice(
    record: StrategyRecord,
    checked: Strategy,
    failure: CheckFailure,
    chosen_strike: Decimal,
    *,
    at: datetime.datetime,
    actor: str,
) -> HistoryEntry | Version | None:
    """Record the user's explicit choice of ``chosen_strike`` for the leg ``failure`` reported as unavailable.

    ``checked`` is the strategy the gate checked (``failure.leg_number`` indexes its legs). Raises ``ValueError``
    when the report is not an unavailable-contract report, the strike was not offered, or the leg is not a leg of
    the record's current definition; ``VersionError`` from W-012 when the record refuses edits.
    """
    if not isinstance(failure, CheckFailure) or failure.code not in UNAVAILABLE_CODES or failure.leg_number is None:
        raise ValueError("a choice answers an unavailable contract report for one leg; this report is not one")
    if not isinstance(chosen_strike, Decimal) or chosen_strike not in failure.alternatives:
        offered = ", ".join(f"{s:,}" for s in failure.alternatives) or "none"
        raise ValueError(f"only an offered alternative can be chosen (offered: {offered}); got {chosen_strike!r}")
    if not 1 <= failure.leg_number <= len(checked.legs):
        raise ValueError(f"leg {failure.leg_number} is not a leg of the checked strategy")
    leg = checked.legs[failure.leg_number - 1]
    definition = record.definition
    target = (leg.action, leg.instrument, leg.strike, leg.expiry, leg.quantity)
    index = next(
        (i for i, d in enumerate(definition.legs)
         if (d.action, d.instrument, d.strike, d.expiry, d.quantity) == target),
        None,
    )
    if index is None:
        raise ValueError(f"leg {failure.leg_number} of the checked strategy is not a leg of this strategy's definition")
    legs = list(definition.legs)
    legs[index] = dataclasses.replace(legs[index], strike=chosen_strike)
    changed = dataclasses.replace(definition, legs=tuple(legs))
    reason = (
        f"User chose {chosen_strike:,} {leg.instrument.value} instead of unavailable {leg.strike:,} "
        f"{leg.instrument.value} ({failure.code.value})"
    )
    return record.edit(changed, at=at, initiator=actor, reason=reason)


def gate_inputs_from_record(record: StrategyRecord, *, strategy_id: str) -> dict[str, object]:
    """``ExecutionContext`` fields for the active version, read from the stored record (never hand-rolled)."""
    active = record.active_version
    if active is None:
        return {"active_legs": None, "active_version_id": None, "active_legs_hash": None}
    legs = tuple(
        Leg(d.action, d.instrument, d.strike, d.expiry, d.quantity, _ZERO) for d in active.definition.legs
    )
    version_id = f"v{active.number}"
    return {
        "active_legs": legs,
        "active_version_id": version_id,
        "active_legs_hash": active_legs_hash(strategy_id, version_id, legs),
    }
