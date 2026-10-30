"""The refused-strategy-call error, in a module with no route and no order import (ADR-016..019 order-path closure).

It lives here, not in ``ofo_app.routes.strategies``, so a route that only needs to refuse (the adjustment approaches
route) does not import the strategies route and, through ``strategy_store``, the order plan modules.
``ofo_app.routes.strategies`` re-exports it: one class, one identity.
"""
from __future__ import annotations

from ofo.errors import UserFacing, UserFacingError, render

from ofo_app.errors import Failure


class StrategyRefused(UserFacing, Exception):
    """A refused Save Draft call: carries only its `render()` message; the error boundary shows it (422), or at the
    status of ``failure`` (404 not found; 409 for a stale revision or a saved form that no longer reads)."""

    def __init__(self, template: str, failure: Failure | None = None, *,
                 message: UserFacingError | None = None) -> None:
        self.message: UserFacingError = render(template) if message is None else message
        super().__init__(template)
        self.failure: Failure | None = failure
