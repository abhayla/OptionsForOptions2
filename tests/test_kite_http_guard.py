"""W-080 round 3 (REQ-073 AC-4): the structural guarantee, pure part. Every Kite HTTP request is checked against
``ALLOWED_CALLS`` BEFORE it is sent: ``check_call(method, url)`` and the urllib door ``open_url``. The httpx factory
that applies the same check lives in ``backend/ofo_app/kite_http.py`` (tests_app/test_kite_http_guard.py)."""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from ofo.broker import kite_http  # noqa: E402
from ofo.broker.kite_endpoints import ALLOWED_CALLS  # noqa: E402

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
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: opened.append(a))
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.open_url(ROOT + "/orders/regular", method="POST", data=b"x", timeout=1)
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.open_url(ROOT + "/orders/regular", timeout=1)  # a plain GET of an order path
    assert opened == []


def test_open_url_sends_an_allowed_get(monkeypatch) -> None:
    seen: list[urllib.request.Request] = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: seen.append((req, timeout)) or "RESP")
    assert kite_http.open_url(ROOT + "/instruments", headers={"X-Kite-Version": "3"}, timeout=7) == "RESP"
    (req, timeout), = seen
    assert req.get_method() == "GET" and req.full_url == ROOT + "/instruments" and timeout == 7
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
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: opened.append(a))
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.open_url(f"https://{host}/orders/regular", method="POST", data=b"x", timeout=1)
    assert opened == []
