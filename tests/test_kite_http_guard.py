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
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_call(method, url)


@pytest.mark.parametrize("method,url", [
    ("POST", ROOT + "/session/token"),
    ("post", ROOT + "/session/token"),
    ("GET", ROOT + "/instruments"),
    ("GET", ROOT + "/instruments/historical/12345/minute?from=2026-10-15+09:15:00&to=2026-10-15+15:30:00"),
])
def test_check_call_allows(method: str, url: str) -> None:
    kite_http.check_call(method, url)


QUOTE = ROOT + "/quote?i="  # F-76 / REQ-155 AC-5: only the allow-listed index names may carry a space


@pytest.mark.parametrize("query", [
    "NSE:NIFTY%2050", "BSE:SENSEX", "NSE:NIFTY%2050&i=BSE:SENSEX", "NSE:NIFTY%2050&i=NFO:NIFTY26N0323450CE",
    "NFO:NIFTY26N0323450CE&i=NSE:NIFTY%2050",
])
def test_quote_door_allows_index_names(query: str) -> None:
    kite_http.check_call("GET", QUOTE + query)


@pytest.mark.parametrize("query", [
    "NSE:NIFTY%2050X", "NSE:FOO%20BAR", "NSE:NIFTY%252050;rm", "NSE:NIFTY%2050;rm",
    "NSE:NIFTY%20%2050", "NSE:NIFTY%20%20", "NSE:NIFTY%20", "NSE:NIFTY%2050%20", "NSE:NIFTY+50", "NSE:NIFTY 50",
    "nse:nifty%2050", "NSE:nifty%2050", "NSE:NIFTY%2050&i=NSE:FOO%20BAR", "NSE:FOO%20BAR&i=NSE:NIFTY%2050",
    "NSE:NIFTY%2050&i=", "BSE:NIFTY%2050", "NSE:SENSEX%2050", "NSE:NIFTY%2050&j=1", "NSE:NIFTY%2050#x",
    "NSE:NIFTY%2050\\u00a0".encode().decode("unicode_escape"),
])
def test_quote_door_refuses_other_spaced_names(query: str) -> None:
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_call("GET", QUOTE + query)


def test_quote_allow_list_is_exactly_the_two_indices() -> None:
    assert {"NSE:NIFTY 50", "BSE:SENSEX"} == kite_http.QUOTE_INDEX_NAMES


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


def test_plain_non_kite_hosts_are_refused_and_uppercase_kite_still_hits_the_path_rule() -> None:
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.check_call("POST", "https://1.2.3.4/orders/regular")  # round 8: only Kite's own host is called
    with pytest.raises(kite_http.KiteCallRefused):
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


# -- REQ-118 (W-138): every door entry point takes a slot from the ONE limiter before it sends -----------------------

import ast  # noqa: E402

from ofo.broker import rate_limit  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1] / "backend"
DOOR_FILES = ("ofo/broker/kite_http.py", "ofo_app/kite_http.py")
_SENDS = frozenset({"open", "handle_request", "handle_async_request"})  # the calls that put bytes on a socket
_LIMITER_SOURCE = "ofo.broker.rate_limit"
_TAKES_A_SLOT = frozenset({"acquire", "aacquire"})


def _limiter_names(tree: ast.Module) -> tuple[set[str], set[str]] | None:
    """(module aliases, function aliases) naming ``ofo.broker.rate_limit`` BY IMPORT SOURCE, or None when an import
    of it cannot be resolved (a star import): fail closed."""
    modules: set[str] = set()
    functions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "ofo.broker":
            modules |= {a.asname or a.name for a in node.names if a.name == "rate_limit"}
        elif isinstance(node, ast.ImportFrom) and node.module == _LIMITER_SOURCE:
            if any(a.name == "*" for a in node.names):
                return None
            functions |= {a.asname or a.name for a in node.names if a.name in _TAKES_A_SLOT}
        elif isinstance(node, ast.Import):
            modules |= {a.asname for a in node.names if a.name == _LIMITER_SOURCE and a.asname}
    return modules, functions


def doors_without_limiter(source: str) -> list[str]:
    """Names of functions that send (``.open`` / ``.handle_request`` / ``.handle_async_request``) without a call that
    takes a slot from the limiter imported from ``ofo.broker.rate_limit``. A star import or an unparseable file reports
    every sender (fail closed); a local function that is merely NAMED ``acquire`` does not count."""
    tree = ast.parse(source)
    names = _limiter_names(tree)
    bad: list[str] = []
    for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
        if not any(isinstance(c.func, ast.Attribute) and c.func.attr in _SENDS for c in calls):
            continue
        modules, functions = names if names is not None else (set(), set())
        takes = any((isinstance(c.func, ast.Attribute) and c.func.attr in _TAKES_A_SLOT
                     and isinstance(c.func.value, ast.Name) and c.func.value.id in modules)
                    or (isinstance(c.func, ast.Name) and c.func.id in functions) for c in calls)
        if not takes:
            bad.append(fn.name)
    return bad


def test_every_real_door_entry_point_takes_a_slot_from_the_limiter() -> None:
    """AC-2: open_url and both httpx clients' _send_single_request call the limiter; the scan is not empty."""
    senders = 0
    for rel in DOOR_FILES:
        source = (BACKEND / rel).read_text(encoding="utf-8")
        assert doors_without_limiter(source) == [], rel
        senders += sum(1 for n in ast.walk(ast.parse(source)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr in _SENDS
                               for c in ast.walk(n)))
    assert senders >= 3  # noqa: PLR2004 - open_url, KiteClient and KiteAsyncClient _send_single_request


_SENDER = "def go(r):\n    with d():\n        return OPENER.open(r)\n"


def _calling(call: str) -> str:
    """_SENDER with ``call`` made just before its send."""
    return _SENDER.replace("with", f"{call}\n    with")


@pytest.mark.parametrize(("source", "expected"), [
    (_SENDER, ["go"]),                                                                           # no limiter at all
    ("from ofo.broker import rate_limit as rl\n" + _calling("rl.acquire('g','k')"), []),
    ("from ofo.broker import rate_limit\n" + _calling("rate_limit.aacquire('g','k')"), []),
    ("from ofo.broker.rate_limit import acquire as take\n" + _calling("take('g','k')"), []),
    ("def acquire(*a): ...\n" + _calling("acquire('g','k')"), ["go"]),    # same name, wrong source
    ("from elsewhere import acquire\n" + _calling("acquire('g','k')"), ["go"]),
    ("from ofo.broker.rate_limit import *\n" + _calling("acquire('g','k')"), ["go"]),  # unresolvable
    ("from ofo.broker import rate_limit as rl\n" + _calling("other.acquire('g','k')"), ["go"]),
    ("from ofo.broker import rate_limit as rl\ndef go(r):\n    return 1\n", []),                 # sends nothing
])
def test_the_door_scan_fails_closed_and_names_the_limiter_by_import_source(source: str, expected: list[str]) -> None:
    """AC-2 / standing item (c): a sender with no limiter call is reported; the limiter is recognised only by its
    import source (a renamed import counts, a same-named local or foreign function does not); a star import
    fails closed."""
    assert doors_without_limiter(source) == expected


def test_every_allowed_call_has_a_rate_limit_group_and_nothing_else_does() -> None:
    """AC-1/AC-2: the group map is an allow-list over exactly the ALLOWED_CALLS pairs; every group has a Kite rate."""
    from ofo.broker.kite_endpoints import ENDPOINT_GROUPS  # noqa: PLC0415
    allowed = {pair for calls in ALLOWED_CALLS.values() for pair in calls}
    assert set(ENDPOINT_GROUPS) == allowed
    assert {group for group, _ in ENDPOINT_GROUPS.values()} <= set(rate_limit.GROUP_RATES)
    creating = {pair for pair, (_, is_read) in ENDPOINT_GROUPS.items() if not is_read}
    assert creating == {("POST", "/session/token")}  # the one call that creates something at Zerodha (AC-5)


def test_a_kite_path_with_no_group_is_refused_before_anything_is_sent(monkeypatch) -> None:
    """Attack 5: an allow-listed path that has no group entry is refused by the door; nothing is opened."""
    opened: list[object] = []
    monkeypatch.setattr(kite_http._OPENER, "open", lambda *a, **k: opened.append(a))
    monkeypatch.setattr(kite_http, "_GROUPED", ())
    with pytest.raises(kite_http.KiteCallRefused, match="no rate-limit group"):
        kite_http.open_url(ROOT + "/instruments", timeout=1)
    assert opened == []


def test_the_door_takes_a_slot_before_the_socket_and_a_busy_limiter_sends_nothing(monkeypatch) -> None:
    """Attack 5 / AC-3: open_url calls the limiter first; when the limiter refuses (KiteBusy) nothing is opened."""
    order: list[str] = []
    monkeypatch.setattr(kite_http._OPENER, "open", lambda *a, **k: order.append("open") or "RESP")
    monkeypatch.setattr(rate_limit, "acquire", lambda group, key: order.append(f"acquire:{group}"))
    assert kite_http.open_url(ROOT + "/instruments", timeout=1) == "RESP"
    assert order == ["acquire:other", "open"]

    def busy(group: str, key: str) -> None:
        raise rate_limit.KiteBusy("wait")

    order.clear()
    monkeypatch.setattr(rate_limit, "acquire", busy)
    with pytest.raises(rate_limit.KiteBusy):
        kite_http.open_url(ROOT + "/instruments/historical/9/minute", timeout=1)
    assert order == []
