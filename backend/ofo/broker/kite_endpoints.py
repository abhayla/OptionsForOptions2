"""What the backend may say to Kite, and which modules may open a network connection at all (REQ-073 AC-4, ADR-054;
run-discipline B8: a structural guarantee, not a list of forbidden names).

No call may place, modify or cancel an order: the user places the basket on Kite's own page (ADR-060).

- ``ALLOWED_CALLS``: the ONLY Kite REST calls, as (METHOD, path template) pairs per calling module. Every request goes
  through a door (``NETWORK_DOORS``) that refuses anything else BEFORE sending.
- ``NETWORK_DOORS``: the only modules that may import a network-capable module, each only the ones named here.
- ``ALLOWED_IMPORTS``: the exact (module, name) pairs of network-adjacent standard-library modules any module may use
  (pure parsing / constants; none opens a connection).
- ``EXEMPT``: a module that may use one named dynamic construct, with the reason.

``tests/test_no_order_placement.py`` holds every backend module to an import ALLOW-list built from these (an unknown
module fails until it is added deliberately), and fails if ``ALLOWED_CALLS`` gains a write under ``/orders`` or
``/gtt``. Reading orders and the read-only ``POST /charges/orders`` / ``/margins/basket`` are NOT placement.
"""
from __future__ import annotations

from typing import Final

#: The Kite hosts. One constant per host; every door and Kite URL in the backend builds on these.
KITE_API_HOST: Final = "api.kite.trade"
KITE_WS_HOST: Final = "ws.kite.trade"

#: module path (relative to ``backend/``) -> the (METHOD, path template) pairs that module may call.
ALLOWED_CALLS: Final[dict[str, frozenset[tuple[str, str]]]] = {
    "ofo_app/kite_client.py": frozenset({("POST", "/session/token")}),
    "ofo_app/kite_history.py": frozenset({("GET", "/instruments/historical/{token}/minute")}),
    "ofo/instruments/downloader.py": frozenset({("GET", "/instruments")}),
    "ofo_app/kite_margin.py": frozenset({("GET", "/user/margins"), ("POST", "/margins/basket")}),
}

#: door module -> the network-capable modules (and their submodules) that door alone may import.
#: ``ofo/broker/kite_http.py``: urllib ``open_url`` (applies ``check_call`` first); ``ofo_app/kite_http.py``: the httpx
#: client classes whose ``send()`` applies ``check_call`` first; ``ofo_app/kite_ws.py``: the websocket client for
#: ``KITE_WS_HOST``, whose connect URL goes through ``check_ws_url`` first.
NETWORK_DOORS: Final[dict[str, frozenset[str]]] = {
    "ofo/broker/kite_http.py": frozenset({"urllib.request"}),
    "ofo_app/kite_http.py": frozenset({"httpx"}),
    "ofo_app/kite_ws.py": frozenset({"websockets"}),
}

#: (module, name) pairs any module may import, only as ``from module import name``; name ``"*"`` = any name from that
#: module. ``urllib.parse`` / ``urllib.error`` only parse URLs and name exceptions; ``HTTPStatus`` is an enum;
#: ``fileConfig`` (alembic's env.py) reads the logging section of alembic.ini. ``ofo/instruments/sources.py`` holds the
#: instrument list's URL as a string (data for ``downloader.py``) and needs only ``urlsplit`` from here.
ALLOWED_IMPORTS: Final = frozenset({
    ("urllib.parse", "*"),
    ("urllib.error", "*"),
    ("http", "HTTPStatus"),
    ("logging.config", "fileConfig"),
})

#: module (relative to ``backend/``; a key ending in ``/`` covers that directory) -> the constructs it may use.
#: Reasons, one per entry:
#: - alembic versions, importlib: a migration loads an earlier migration file by path (importlib.util) to reuse its
#:   SQL; migrations run only as the owner role, never inside the app.
#: - wording.py, module-freeze: the module freezes itself (its module object gets a read-only subclass, ADR-056); not a
#:   client.
#: - explanations.py, sys._getframe: user_words() reads its caller's module name to refuse callers outside the request
#:   layer.
EXEMPT: Final[dict[str, frozenset[str]]] = {
    "ofo_app/alembic/versions/": frozenset({"importlib"}),
    "ofo/wording.py": frozenset({"module-freeze"}),  # sets its own module object class
    "ofo/errors/explanations.py": frozenset({"sys._getframe"}),
}

__all__ = ["ALLOWED_CALLS", "ALLOWED_IMPORTS", "EXEMPT", "KITE_API_HOST", "KITE_WS_HOST", "NETWORK_DOORS"]
