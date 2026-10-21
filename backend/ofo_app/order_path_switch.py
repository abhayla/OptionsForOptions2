"""W-121 (REQ-073 AC-6, ADR-165): the order path is OFF. One server-side switch; every route that prepares, posts or
checks an order at a broker refuses before any Zerodha read or database write.

The switch is ON only when ``APP_ENV`` is exactly ``test`` AND ``OFO_ORDER_PATH`` is in the true set. In any other
environment (unset, production, staging, a case or space variant of ``test``) it is OFF whatever ``OFO_ORDER_PATH``
says, so production cannot turn it on without a code change. It is read on every request (never cached), and any
failure to read the environment means OFF (fail closed).

``require_order_path`` is a router-level dependency (``APIRouter(dependencies=[Depends(require_order_path)])``): FastAPI
resolves router dependencies before the endpoint's own (``get_kite_session``, ``get_db``), so no handler side effect
runs when it refuses.
"""
from __future__ import annotations

import os

from ofo_app.config import app_env
from ofo_app.errors import Failure
from ofo_app.routes.strategies import StrategyRefused

ENV_NAME = "OFO_ORDER_PATH"
TEST_ENV = "test"
_TRUE = {"1", "true", "yes", "on"}
TEMPLATE = "order_path_off"


def order_path_on() -> bool:
    """True only for APP_ENV == "test" (exact) and OFO_ORDER_PATH in 1/true/yes/on (case and edge spaces ignored)."""
    try:
        if app_env() != TEST_ENV:
            return False
    except (ValueError, OSError):  # an unreadable environment (bad .env) is OFF; any other error is a 500, never "on"
        return False
    return os.environ.get(ENV_NAME, "").strip().lower() in _TRUE


def require_order_path() -> None:
    """The refusal (409, catalogue message ``order_path_off``) while the switch is off."""
    if not order_path_on():
        raise StrategyRefused(TEMPLATE, Failure.CONFLICT)
