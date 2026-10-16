"""W-080 round 3 (REQ-073 AC-4): the structural guarantee, pure part. Every Kite HTTP request is checked against
``ALLOWED_CALLS`` BEFORE it is sent: ``check_call(method, url)`` and the urllib door ``open_url``. The httpx factory
that applies the same check lives in ``backend/ofo_app/kite_http.py`` (tests_app/test_kite_http_guard.py)."""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from ofo.broker import egress, kite_http
from ofo.broker.kite_endpoints import ALLOWED_CALLS

ROOT = "https://api.kite.trade"


@pytest.mark.parametrize("method,url", [
    ("POST", ROOT + "/orders/regular"),
    ("PUT", ROOT + "/orders/regular/123"),
    ("DELETE", ROOT + "/orders/regular/123"),
    ("PATCH", ROOT + "/orders/regular/123"),
    ("POST", ROOT + "/orders/amo"),
    ("POST", ROOT + "/gtt/triggers"),
    ("GET", ROOT + "/orders"),  # a read, but not allow-listed yet: nothing is allowed by default
    ("POST", ROOT + "/session/token/extra"),
    ("GET", ROOT + "/session/token"),  # right path, wrong method
    ("POST", ROOT + "//orders/regular"),
    ("POST", ROOT + "/session/../orders/regular"),
    ("POST", ROOT + "/session/token/../../orders/regular"),
    ("POST", ROOT + "/%6frders/regular"),
    ("GET", ROOT + "/instruments/historical/../minute"),  # a template slot matching ".." would walk up a level
    ("GET", ROOT + "/instruments/historical/%2e%2e/minute"),
    ("GET", ROOT + "/instruments/historical/./minute"),
    ("POST", "https://API.KITE.TRADE/orders/regular"),
    ("POST", "https://api.kite.trade./orders/regular"),
    ("POST", "https://api.kite.trade:443/orders/regular"),
    ("POST", "https://kite.zerodha.com/connect/basket"),  # no other Kite/Zerodha host is called by the backend
    ("POST", "https://other.kite.trade/orders/regular"),
])
def test_check_call_refuses(method: str, url: str) -> None:
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_call(method, url)


@pytest.mark.parametrize("method,url", [
    ("POST", ROOT + "/session/token"),
    ("post", ROOT + "/session/token"),
    ("GET", ROOT + "/instruments"),
    ("GET", ROOT + "/instruments/historical/12345/minute?from=2026-10-15+09:15:00&to=2026-10-15+15:30:00"),
    ("GET", "https://example.com/orders/regular"),  # not a Kite host: not this guard's business
])
def test_check_call_allows(method: str, url: str) -> None:
    kite_http.check_call(method, url)


def test_every_allow_list_entry_passes_its_own_template() -> None:
    for calls in ALLOWED_CALLS.values():
        for method, template in calls:
            kite_http.check_call(method, ROOT + template.replace("{token}", "1").replace("{id}", "1"))


def test_open_url_refuses_before_any_network(monkeypatch) -> None:
    opened: list[object] = []
    monkeypatch.setattr(kite_http._OPENER, "open", lambda *a, **k: opened.append(a))
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.open_url(ROOT + "/orders/regular", method="POST", data=b"x", timeout=1)
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.open_url(ROOT + "/orders/regular", timeout=1)  # a plain GET of an order path
    assert opened == []


def test_open_url_sends_an_allowed_get(monkeypatch) -> None:
    seen: list[urllib.request.Request] = []
    in_door: list[bool] = []

    def fake_open(req, timeout=None):  # the door's own opener (round 7): no real request leaves
        in_door.append(egress._in_door())
        seen.append((req, timeout))
        return "RESP"

    monkeypatch.setattr(kite_http._OPENER, "open", fake_open)
    assert kite_http.open_url(ROOT + "/instruments", headers={"X-Kite-Version": "3"}, timeout=7) == "RESP"
    assert in_door == [True] and not egress._in_door()  # door context only around the send, reset after
    (req, timeout), = seen
    assert req.get_method() == "GET" and req.full_url == ROOT + "/instruments" and timeout == 7  # noqa: PLR2004
    assert req.get_header("X-kite-version") == "3"


NON_ASCII_HOSTS = [
    "api\u3002kite\u3002trade", "api\uff0ekite\uff0etrade", "api\uff61kite\uff61trade",  # dots urllib/ssl fold to "."
    "\uff41pi.kite.trade",  # full-width letter
    "ex\u00e4mple.com",  # non-ASCII, not a Kite host: refused outright, never compared
]


@pytest.mark.parametrize("host", NON_ASCII_HOSTS)
def test_check_call_refuses_non_ascii_hosts(host: str) -> None:
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_call("POST", f"https://{host}/orders/regular")


@pytest.mark.parametrize("host", NON_ASCII_HOSTS)
def test_open_url_refuses_non_ascii_hosts_before_urlopen(monkeypatch, host: str) -> None:
    opened: list[object] = []
    monkeypatch.setattr(kite_http._OPENER, "open", lambda *a, **k: opened.append(a))
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.open_url(f"https://{host}/orders/regular", method="POST", data=b"x", timeout=1)
    assert opened == []



# -- round 5: only a plain netloc (a-z 0-9 . - and an optional :443) is read; two parsers can never disagree ----------

ODD_NETLOCS = [
    "api.kite%2Etrade", "api%2ekite%2etrade", "api%2Ekite.trade", "api.kite.trad%65", "%61pi.kite.trade",
    "user@api.kite.trade", "api.kite.trade@evil.com", "evil.com\\@api.kite.trade", "api.kite.trade\\.evil.com",
    "api.kite.trade ", "api kite.trade", "[::1]", "[::ffff:1.2.3.4]", "api.kite.trade:80", "api.kite.trade:", "",
    "api.kite.trade:443:443", "api_kite.trade",
]


@pytest.mark.parametrize("netloc", ODD_NETLOCS)
def test_check_call_refuses_odd_netlocs(netloc: str) -> None:
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_call("POST", f"https://{netloc}/orders/regular")


@pytest.mark.parametrize("netloc", ODD_NETLOCS)
def test_open_url_refuses_odd_netlocs_before_urlopen(monkeypatch, netloc: str) -> None:
    opened: list[object] = []
    monkeypatch.setattr(kite_http._OPENER, "open", lambda *a, **k: opened.append(a))
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.open_url(f"https://{netloc}/orders/regular", method="POST", data=b"x", timeout=1)
    assert opened == []


@pytest.mark.parametrize("url", ["ftp://api.kite.trade/orders/regular", "file:///orders/regular", "//api.kite.trade/x",
                                 "api.kite.trade/orders/regular", "https:///orders/regular", "javascript:1"])
def test_check_call_refuses_other_schemes_and_empty_hosts(url: str) -> None:
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_call("POST", url)


def test_plain_hosts_still_pass_through_and_uppercase_kite_still_hits_the_path_rule() -> None:
    kite_http.check_call("POST", "https://1.2.3.4/orders/regular")  # a plain IP is not a Kite host: not our door's call
    kite_http.check_call("GET", "https://example.com/x")
    kite_http.check_call("GET", "https://api.kite.trade:443/instruments")
    kite_http.check_call("GET", "http://api.kite.trade/instruments")
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_call("POST", "https://API.KITE.TRADE/orders/regular")


# -- round 6: the websocket door's address check (ofo_app/kite_ws.py applies it) ------------------------------------


@pytest.mark.parametrize("url", [
    "wss://ws.kite.trade?api_key=k&access_token=t", "wss://ws.kite.trade/?api_key=k", "wss://ws.kite.trade:443",
    "ws://127.0.0.1:9", "ws://localhost:8765/x",  # local fakes are not Kite hosts: not this door's concern
])
def test_ws_door_accepts_the_kite_socket_and_local_fakes(url: str) -> None:
    kite_http.check_ws_url(url)


@pytest.mark.parametrize("url", [
    "ws://ws.kite.trade",                    # Kite only over TLS
    "wss://api.kite.trade",                  # wrong Kite host
    "wss://ws.kite.trade/orders/regular",    # a path on the socket host
    "wss://ws.kite.trade:80", "wss://WS.KITE.TRADE", "wss://ws.kite.trade.",
    "wss://ws.kite%2Etrade", "wss://user@ws.kite.trade", "wss://ws。kite。trade", "wss://ws.zerodha.com",
    "https://ws.kite.trade", "wss://", "",
])
def test_ws_door_refuses_anything_else(url: str) -> None:
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_ws_url(url)


def test_the_kite_hosts_come_from_one_place() -> None:
    from ofo.broker import kite_endpoints  # noqa: PLC0415
    assert kite_http.KITE_API_HOST is kite_endpoints.KITE_API_HOST
    assert kite_http.KITE_WS_HOST is kite_endpoints.KITE_WS_HOST
