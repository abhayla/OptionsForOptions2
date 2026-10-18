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
from ofo.broker.kite_endpoints import (
    ALLOWED_CALLS,
    CALLER_DOWNLOADER,
    CALLER_KITE_CLIENT,
    CALLER_KITE_HISTORY,
    CALLER_KITE_READS,
)

ROOT = "https://api.kite.trade"


@pytest.mark.parametrize("method,url", [
    ("POST", ROOT + "/orders/regular"),
    ("PUT", ROOT + "/orders/regular/123"),
    ("DELETE", ROOT + "/orders/regular/123"),
    ("PATCH", ROOT + "/orders/regular/123"),
    ("POST", ROOT + "/orders/amo"),
    ("POST", ROOT + "/orders/co"),
    ("POST", ROOT + "/orders/iceberg"),
    ("POST", ROOT + "/orders/auction"),
    ("POST", ROOT + "/gtt/triggers"),
    ("GET", ROOT + "/orders/123"),  # only exact GET /orders is allowed (W-093)
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
    for caller in ALLOWED_CALLS:  # #353: refused for every listed module, not only one
        with pytest.raises(kite_http.KiteCallRefused):
            kite_http.check_call(method, url, caller=caller)


@pytest.mark.parametrize("method,url,caller", [
    ("POST", ROOT + "/session/token", CALLER_KITE_CLIENT),
    ("post", ROOT + "/session/token", CALLER_KITE_CLIENT),
    ("GET", ROOT + "/instruments", CALLER_DOWNLOADER),
    ("GET", ROOT + "/instruments/historical/12345/minute?from=2026-10-15+09:15:00&to=2026-10-15+15:30:00",
     CALLER_KITE_HISTORY),
])
def test_check_call_allows(method: str, url: str, caller: str) -> None:
    kite_http.check_call(method, url, caller=caller)


def test_every_allow_list_entry_passes_its_own_template() -> None:
    for caller, calls in ALLOWED_CALLS.items():
        for method, template in calls:
            kite_http.check_call(method, ROOT + template.replace("{token}", "1").replace("{id}", "1"), caller=caller)


def test_open_url_refuses_before_any_network(monkeypatch) -> None:
    opened: list[object] = []
    monkeypatch.setattr(kite_http._OPENER, "open", lambda *a, **k: opened.append(a))
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.open_url(ROOT + "/orders/regular", caller=CALLER_DOWNLOADER, method="POST", data=b"x", timeout=1)
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.open_url(ROOT + "/orders/regular", caller=CALLER_DOWNLOADER, timeout=1)  # GET of an order path
    assert opened == []


def test_open_url_sends_an_allowed_get(monkeypatch) -> None:
    seen: list[urllib.request.Request] = []
    in_door: list[bool] = []

    def fake_open(req, timeout=None):  # the door's own opener (round 7): no real request leaves
        in_door.append(egress._in_door())
        seen.append((req, timeout))
        return "RESP"

    monkeypatch.setattr(kite_http._OPENER, "open", fake_open)
    assert kite_http.open_url(ROOT + "/instruments", caller=CALLER_DOWNLOADER, headers={"X-Kite-Version": "3"},
                              timeout=7) == "RESP"
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
        kite_http.check_call("POST", f"https://{host}/orders/regular", caller=CALLER_KITE_READS)


@pytest.mark.parametrize("host", NON_ASCII_HOSTS)
def test_open_url_refuses_non_ascii_hosts_before_urlopen(monkeypatch, host: str) -> None:
    opened: list[object] = []
    monkeypatch.setattr(kite_http._OPENER, "open", lambda *a, **k: opened.append(a))
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.open_url(f"https://{host}/orders/regular", caller=CALLER_DOWNLOADER, method="POST", data=b"x",
                           timeout=1)
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
        kite_http.check_call("POST", f"https://{netloc}/orders/regular", caller=CALLER_KITE_READS)


@pytest.mark.parametrize("netloc", ODD_NETLOCS)
def test_open_url_refuses_odd_netlocs_before_urlopen(monkeypatch, netloc: str) -> None:
    opened: list[object] = []
    monkeypatch.setattr(kite_http._OPENER, "open", lambda *a, **k: opened.append(a))
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.open_url(f"https://{netloc}/orders/regular", caller=CALLER_DOWNLOADER, method="POST", data=b"x",
                           timeout=1)
    assert opened == []


@pytest.mark.parametrize("url", ["ftp://api.kite.trade/orders/regular", "file:///orders/regular", "//api.kite.trade/x",
                                 "api.kite.trade/orders/regular", "https:///orders/regular", "javascript:1"])
def test_check_call_refuses_other_schemes_and_empty_hosts(url: str) -> None:
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_call("POST", url, caller=CALLER_KITE_READS)


def test_plain_non_kite_hosts_are_refused_and_uppercase_kite_still_hits_the_path_rule() -> None:
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_call("POST", "https://1.2.3.4/orders/regular", caller=CALLER_KITE_READS)  # round 8: Kite only
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_call("GET", "https://example.com/x", caller=CALLER_DOWNLOADER)
    kite_http.check_call("GET", "https://api.kite.trade:443/instruments", caller=CALLER_DOWNLOADER)
    kite_http.check_call("GET", "http://api.kite.trade/instruments", caller=CALLER_DOWNLOADER)
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_call("POST", "https://API.KITE.TRADE/orders/regular", caller=CALLER_KITE_READS)


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


# -- #353: each call is allowed only for the module listed for it -----------------------------------------------------

def _sample(template: str) -> str:
    return ROOT + template.replace("{token}", "1").replace("{id}", "1")


def test_353_a_call_listed_only_for_another_module_is_refused() -> None:
    """REQ-073 AC-4 (#353): every (caller, call) pair where the call is not listed for that caller is refused with the
    existing refusal - generated over the whole map, never hand-listed (GET /orders from the margin module included)."""
    pairs = 0
    for caller in ALLOWED_CALLS:
        for other, calls in ALLOWED_CALLS.items():
            for method, template in calls - ALLOWED_CALLS[caller]:
                with pytest.raises(kite_http.KiteCallRefused, match="is not an allow-listed Kite call"):
                    kite_http.check_call(method, _sample(template), caller=caller)
                pairs += 1
    assert pairs > 0
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_call("GET", ROOT + "/orders", caller="ofo_app/kite_margin.py")


@pytest.mark.parametrize("caller", [None, "", "ofo_app/kite_marginx.py", "ofo_app/routes/execute.py", b"x",
                                    "OFO_APP/KITE_READS.PY", 1, ("ofo_app/kite_reads.py",)])
def test_353_a_caller_not_listed_or_not_a_plain_str_is_refused(caller: object) -> None:
    """REQ-073 AC-4 (#353, fail closed): an unknown module, another type, or a str that is not exactly a key."""
    with pytest.raises(kite_http.KiteCallRefused, match="caller is not a module listed"):
        kite_http.check_call("GET", ROOT + "/instruments", caller=caller)  # type: ignore[arg-type]


def test_353_a_str_subclass_caller_is_refused() -> None:
    """REQ-073 AC-4 (#353): a str subclass equal to a real key is not that key (exact type)."""
    class Sneaky(str):
        pass

    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_call("GET", ROOT + "/instruments", caller=Sneaky(CALLER_DOWNLOADER))


def test_353_the_caller_is_required_on_both_doors() -> None:
    """REQ-073 AC-4 (#353): neither ``check_call`` nor ``open_url`` has a default caller."""
    with pytest.raises(TypeError):
        kite_http.check_call("GET", ROOT + "/instruments")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        kite_http.open_url(ROOT + "/instruments", timeout=1)  # type: ignore[call-arg]


def test_353_open_url_refuses_another_modules_call_before_any_network(monkeypatch) -> None:
    """REQ-073 AC-4 (#353): the downloader's identity cannot read orders; nothing reaches the opener."""
    opened: list[object] = []
    monkeypatch.setattr(kite_http._OPENER, "open", lambda *a, **k: opened.append(a))
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.open_url(ROOT + "/orders", caller=CALLER_DOWNLOADER, timeout=1)
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.open_url(ROOT + "/orders", caller="ofo_app/routes/execute.py", timeout=1)
    assert opened == []
