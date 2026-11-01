"""ADR-220 (1): the server is one codebase started as five named roles. Each role names the module that starts it
(``python -m <module>``); a role not built yet has ``None``. Roles talk only through the api's own calls or the
shared store (Redis), never through one role's memory.

Known bypass: nothing yet refuses a second copy of ``liveprices`` (ADR-220 says exactly 1); a process manager runs one.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Role:
    name: str
    start_module: str | None  # None = the role is not built yet


API = Role("api", None)  # today the FastAPI app served by uvicorn; its own start module comes with REQ-164
MATHS = Role("maths", None)
USER_ORDERS = Role("user orders", None)
LIVEPRICES = Role("liveprices", "ofo_app.liveprices")  # REQ-113: the only Kite live connections
BACKGROUND = Role("background", "ofo_app.background")  # REQ-165: playbook checks with no screen open

ROLES: tuple[Role, ...] = (API, MATHS, USER_ORDERS, LIVEPRICES, BACKGROUND)
