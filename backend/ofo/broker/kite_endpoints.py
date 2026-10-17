"""What the backend may say to Kite, and which modules may open a network connection at all (REQ-073 AC-4, ADR-054;
run-discipline B8: a structural guarantee, not a list of forbidden names).

No call may place, modify or cancel an order: the user places the basket on Kite's own page (ADR-060).

- ``ALLOWED_CALLS``: the ONLY Kite REST calls, as (METHOD, path template) pairs per calling module. Every request goes
  through a door (``NETWORK_DOORS``) that refuses anything else BEFORE sending.
- ``NETWORK_DOORS``: the only modules that may import a network-capable module, each only the ones named here. At
  runtime the egress gate (``ofo.broker.egress``) lets a connect through only inside a door, after its URL check.

``tests/test_no_order_placement.py`` keeps network imports in their doors and fails if ``ALLOWED_CALLS`` gains a write
under ``/orders`` or ``/gtt``. Reading orders and the read-only ``POST /charges/orders`` / ``/margins/basket`` are NOT placement.
"""  # noqa: E501
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
    "ofo_app/kite_reads.py": frozenset({("GET", "/orders"), ("GET", "/trades"), ("GET", "/portfolio/positions"),
                                        ("GET", "/quote")}),
}

#: door module -> the network-capable modules (and their submodules) that door alone may import.
#: ``ofo/broker/kite_http.py``: urllib ``open_url`` (applies ``check_call`` first); ``ofo_app/kite_http.py``: the httpx
#: client classes that apply ``check_call`` at their last hop; ``ofo_app/kite_ws.py``: the websocket client for
#: ``KITE_WS_HOST``, whose connect URL goes through ``check_ws_url`` first.
NETWORK_DOORS: Final[dict[str, frozenset[str]]] = {
    "ofo/broker/kite_http.py": frozenset({"urllib.request"}),
    "ofo_app/kite_http.py": frozenset({"httpx", "httpcore", "anyio", "h11", "sniffio", "socket"}),  # W-080 r9: own last hop
    "ofo_app/kite_ws.py": frozenset({"websockets"}),
    "ofo/broker/egress.py": frozenset({"socket"}),  # the gate itself: address-family constants and one getaddrinfo
}

__all__ = ["ALLOWED_CALLS", "KITE_API_HOST", "KITE_WS_HOST", "NETWORK_DOORS"]
