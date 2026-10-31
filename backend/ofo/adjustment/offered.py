"""The adjustment approaches a playbook offers NOW (ADR-221 T-19 pick; catalogue S-11 "Adjustment limit reached").

One rule, one home: the T-19 cheapest pick reads ``offered_now``. The scenario generator
(tests/adjust_scenarios_gen.py) keeps its own hand copy of the same rule (``EXIT_REDUCE`` and the limit test), so the
two paths still check each other.

- The playbook's ``approaches.applicable`` list, in its order, without "No change" (A-36: it trades nothing, so its
  cost is 0 and would make T-19 meaningless) - ``compare.offered_approaches``.
- S-11: when the adjustments used reach the playbook's ``guards.max_adjustments``, only exit and reduce approaches
  are offered. A count that could not be read (None) or a playbook without that guard filters nothing here (T-18
  already answers "not checked" for an unread count).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from ofo.adjustment.compare import offered_approaches

#: catalogue S-11 "Only exit and reduce are offered": the exit and reduce approaches (same list as the generator's)
EXIT_REDUCE: Final = frozenset({"A-23", "A-24", "A-25", "A-26", "A-27", "A-28", "A-29", "A-31", "A-35", "A-36",
                                "A-37", "A-38"})


def limit_reached(body: Mapping | None, adjustments_used: int | None) -> bool:
    guards = (body or {}).get("guards") if isinstance(body, Mapping) else None
    mx = guards.get("max_adjustments") if isinstance(guards, Mapping) else None
    return isinstance(mx, int) and isinstance(adjustments_used, int) and adjustments_used >= mx


def offered_now(body: Mapping | None, adjustments_used: int | None) -> tuple[str, ...]:
    """The approaches ``body`` offers at this check, playbook order; S-11 keeps only exit and reduce."""
    offered = offered_approaches(body)
    if limit_reached(body, adjustments_used):
        return tuple(a for a in offered if a in EXIT_REDUCE)
    return offered
