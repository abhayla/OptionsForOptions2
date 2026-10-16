"""The ONLY Kite REST calls this platform may make: an allow-list of (method, path template) pairs (REQ-073 AC-4,
ADR-054, run-discipline B8: a structural guarantee, not a list of forbidden names).

No call may place, modify or cancel an order: the user places the basket on Kite's own page (ADR-060). A new Kite
call is added here first, with the module that makes it; ``tests/test_no_order_placement.py`` fails when

- this list holds a write method under ``/orders`` (or any ``/gtt``, ``/portfolio/positions`` conversion), or
- a module not named here imports an HTTP library or names ``api.kite.trade``, or
- a module named here carries a path, an HTTP verb or a request option this list does not allow.

Reading orders (``GET /orders``, ``GET /orders/{id}/trades``) and the read-only ``POST /charges/orders`` and
``POST /margins/orders`` / ``/margins/basket`` are NOT placement; W-081's margin entries are present under its own module.
"""
from __future__ import annotations

from typing import Final

#: module path (relative to ``backend/``) -> the (METHOD, path template) pairs that module may call.
ALLOWED_CALLS: Final[dict[str, frozenset[tuple[str, str]]]] = {
    "ofo_app/kite_client.py": frozenset({("POST", "/session/token")}),
    "ofo_app/kite_history.py": frozenset({("GET", "/instruments/historical/{token}/minute")}),
    "ofo/instruments/downloader.py": frozenset({("GET", "/instruments")}),
    "ofo_app/kite_margin.py": frozenset({("GET", "/user/margins"), ("POST", "/margins/basket")}),
}

#: modules that may import an HTTP library or name the Kite API host without making an allow-listed call themselves:
#: the two doors every request goes through (``ofo/broker/kite_http.py`` for urllib, ``ofo_app/kite_http.py`` for the
#: httpx client factory) and ``sources.py``, which holds the instrument list's URL as data for ``downloader.py``.
#: ``routes/broker.py`` is listed because it builds its client with ``kite_async_client`` for the token exchange; it
#: makes no call of its own, and that client's request hook refuses anything outside ``ALLOWED_CALLS``.
HTTP_PLUMBING_MODULES: Final = frozenset({"ofo/broker/kite_http.py", "ofo_app/kite_http.py",
                                          "ofo/instruments/sources.py", "ofo_app/routes/broker.py"})

__all__ = ["ALLOWED_CALLS", "HTTP_PLUMBING_MODULES"]
