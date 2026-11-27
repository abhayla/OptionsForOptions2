"""#774 (ADR-330 (42), ADR-016..019): the leg stops a basket takes away, said before Confirm and done at Confirm.

A leg stop is a premium level of ONE option contract (ofo.tracking.stops). When a basket closes that contract and some
other leg stays open (Change expiry, a strike step, Shift, Width: exit A + add A'), the stop has nothing to watch; the
same level means another thing on A' (it may already be crossed), so it is NOT re-pointed (fail closed) and it is not
left to vanish at the monitor's next tick: ``leaving`` names it, the confirm preview lists it and the order route
cancels it in the transaction that stores the orders. ONE function for both, so the preview is what the route does.
Pure; no clock, no database.
"""
from __future__ import annotations

from collections.abc import Collection, Iterable

from ofo.tracking.stops import Trigger


def leaving(armed: Iterable[Trigger], open_after: Collection[int]) -> list[Trigger]:
    """The armed leg stops whose contract is not open after the basket, while some leg is (every leg closing is the
    existing rule: every trigger of a flat strategy is cancelled, ADR-317). In trigger-id order."""
    if not open_after:
        return []
    return sorted((t for t in armed if t.kind == "leg_stop" and t.contract_id not in open_after), key=lambda t: t.id)
