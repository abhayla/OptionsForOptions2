"""W-058 AC-6: the Zerodha login happens on Zerodha's page; our routes never ask for or accept a password, PIN or
OTP (REQ-015 AC-6). Every Kite answer state and what it does (brief B4 d). These tests need no database: the session
dependency is a recorder that fails the test if anything is written on a refused path.

Expected values come from Kite Connect v3's documented formats (login URL, redirect query, /session/token answers).
All keys and tokens below are fakes."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from ofo.broker.kite_auth import KiteSession
from ofo.errors import CATALOGUE, render
from ofo_app.broker_config import BrokerConfig, BrokerConfigError, BrokerSettings, load_broker_config
from ofo_app.db import get_db
from ofo_app import errors as errors_module
from ofo_app.errors import STATUS_BY_CLASS
from ofo_app.kite_client import HttpKiteAuth, KiteExchangeError
from ofo_app.main import create_app
from ofo_app.routes import broker as broker_routes

API_KEY = "kite_fake_key"
API_SECRET = "kite_fake_secret_value"
REQUEST_TOKEN = "RQtok_fake_9f2c1a7e5b3d4c6a"
ACCESS_TOKEN = "ACtok_fake_5e8d7c6b5a4f3e2d1c"
CALLBACK = "/kite/callback"
USER_ID = "AB1234"
CREDENTIAL_WORDS = ("password", "pin", "otp", "totp", "twofa", "2fa")


def _key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def _config() -> BrokerConfig:
    return load_broker_config(BrokerSettings(KITE_API_KEY=API_KEY, KITE_API_SECRET=API_SECRET,
                                             KITE_REDIRECT_URL="http://127.0.0.1:8000" + CALLBACK,
                                             KITE_EXPECTED_USER_ID=USER_ID, BROKER_TOKEN_KEY=_key()))


class RecordingDB:
    """Stands in for the AsyncSession on paths that must write nothing."""

    def __init__(self) -> None:
        self.executed: list[object] = []

    async def execute(self, *args, **kwargs):  # pragma: no cover - a refused path never reaches it
        self.executed.append(args)
        raise AssertionError("a refused login wrote to the database")

    def begin(self):
        raise AssertionError("a refused login opened a transaction")


class FakeKite:
    def __init__(self, answer: KiteSession | Exception = KiteSession(ACCESS_TOKEN, USER_ID)) -> None:
        self.answer = answer
        self.calls: list[str] = []

    async def exchange(self, request_token: str) -> KiteSession:
        self.calls.append(request_token)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _app(kite: FakeKite, db: RecordingDB, config: BrokerConfig | None = None):
    app = create_app(config or _config())

    async def _db():
        yield db

    async def _kite():
        yield kite

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[broker_routes.get_kite_auth] = _kite
    return app


async def _state(ac: AsyncClient) -> str:
    response = await ac.get(broker_routes.LOGIN_PATH)
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return parse_qs(query["redirect_params"][0])["state"][0]


#: Each refusal's HTTP status (fix round 1): its failure source when it has one (our cap 429, Kite busy 503, Kite
#: unreachable or junk 502), else its error class. Only a failure of our own code is a 500.
EXPECTED_STATUS = {"broker_login_not_completed": 401, "broker_state_invalid": 401, "broker_login_busy": 429,
                   "broker_user_mismatch": 403, "kite_no_user_id": 401, "kite_no_access_token": 401,
                   "kite_token_exception": 401, "kite_input_exception": 401, "kite_refused": 401,
                   "kite_unavailable": 502, "kite_busy": 503, "broker_store_failed": 500}


def _refused(response, code: str) -> None:
    """A refusal is answered by the one error boundary (W-024): the catalogue template's four parts, the status of its
    failure source or class, the no-leak headers, the login-state cookie cleared, and on a 401 a WWW-Authenticate."""
    assert code in broker_routes.REFUSAL_CODES
    assert response.status_code == EXPECTED_STATUS[code], (response.status_code, code)
    assert response.json() == render(code).as_dict()
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    cookie = response.headers.get("set-cookie", "").lower()
    assert cookie.startswith(broker_routes.STATE_COOKIE + "="), cookie
    assert "max-age=0" in cookie and f"path={CALLBACK}" in cookie, cookie
    if response.status_code == 401:
        assert response.headers["www-authenticate"] == errors_module.WWW_AUTHENTICATE
    if code in ("broker_login_busy", "kite_busy"):
        assert response.headers["retry-after"] == "60"


def _redirected(response, code: str) -> None:
    """A refusal on the callback (#163): a browser coming back from Kite gets a 302 to the frontend refusal page that
    carries only the closed code (no body, no token, no Kite text), the no-leak headers and the cleared state cookie."""
    assert code in broker_routes.REFUSAL_CODES
    assert response.status_code == 302, (response.status_code, code)
    assert response.headers["location"] == f"/broker/refused?code={code}"
    assert response.content == b""
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    cookie = response.headers.get("set-cookie", "").lower()
    assert cookie.startswith(broker_routes.STATE_COOKIE + "="), cookie
    assert "max-age=0" in cookie and f"path={CALLBACK}" in cookie, cookie


async def test_a_cancelled_login_redirects_to_the_refusal_page_with_its_code_and_no_body():
    kite = FakeKite()
    async with AsyncClient(transport=ASGITransport(app=_app(kite, RecordingDB())), base_url="http://t") as ac:
        state = await _state(ac)
        response = await ac.get(CALLBACK, params={"status": "cancelled", "request_token": REQUEST_TOKEN,
                                                  "state": state})
    _redirected(response, "broker_login_not_completed")
    assert kite.calls == []


def test_every_refusal_code_is_a_catalogue_template_at_its_status():
    assert set(EXPECTED_STATUS) == broker_routes.REFUSAL_CODES
    by_class = {c: STATUS_BY_CLASS[CATALOGUE[c].error_class] for c in EXPECTED_STATUS
                if c not in broker_routes.FAILURE_BY_CODE}
    by_failure = {c: f.status for c, f in broker_routes.FAILURE_BY_CODE.items()}
    assert {**by_class, **by_failure} == EXPECTED_STATUS
    assert all(CATALOGUE[c].error_class.name != "INTERNAL_SYSTEM" for c in broker_routes.FAILURE_BY_CODE)
    with pytest.raises(ValueError):
        broker_routes.BrokerLoginRefused("Zerodha login was not completed")


# ---- AC-6: no password, PIN or OTP anywhere ----


def test_no_route_takes_a_password_pin_or_otp_field():
    spec = create_app(_config()).openapi()
    login = spec["paths"][broker_routes.LOGIN_PATH]["get"]
    callback = spec["paths"][CALLBACK]["get"]
    assert login.get("parameters", []) == []
    assert {p["name"] for p in callback["parameters"]} == {"status", "request_token", "state"}
    assert "requestBody" not in login and "requestBody" not in callback
    for path in (broker_routes.LOGIN_PATH, CALLBACK):
        assert set(spec["paths"][path]) == {"get"}
    names = {p["name"].lower() for op in spec["paths"].values() for m in op.values()
             for p in m.get("parameters", [])}
    assert not names & set(CREDENTIAL_WORDS)


async def test_login_redirects_to_zerodhas_own_page_with_a_state():
    async with AsyncClient(transport=ASGITransport(app=_app(FakeKite(), RecordingDB())), base_url="http://t") as ac:
        response = await ac.get(broker_routes.LOGIN_PATH)
    parts = urlsplit(response.headers["location"])
    assert (response.status_code, parts.scheme, parts.netloc, parts.path) == (
        302, "https", "kite.zerodha.com", "/connect/login")
    query = parse_qs(parts.query)
    assert query["v"] == ["3"] and query["api_key"] == [API_KEY]
    assert set(parse_qs(query["redirect_params"][0])) == {"state"}
    assert API_SECRET not in response.headers["location"]
    assert response.headers["cache-control"] == "no-store"


async def test_a_submitted_password_is_ignored_and_never_echoed():
    kite = FakeKite()
    async with AsyncClient(transport=ASGITransport(app=_app(kite, RecordingDB())), base_url="http://t") as ac:
        response = await ac.get(CALLBACK, params={"status": "success", "password": "hunter2", "pin": "123456",
                                                  "otp": "654321", "state": "unknown"})
    _redirected(response, "broker_state_invalid")
    assert "hunter2" not in response.text and "654321" not in response.text
    assert kite.calls == []


# ---- the state: random, single use, 10-minute life ----


@pytest.mark.parametrize("state", [None, "", "never-issued"])
async def test_missing_or_unknown_state_is_refused_without_an_exchange(state):
    kite = FakeKite()
    params = {"status": "success", "request_token": REQUEST_TOKEN}
    if state is not None:
        params["state"] = state
    async with AsyncClient(transport=ASGITransport(app=_app(kite, RecordingDB())), base_url="http://t") as ac:
        response = await ac.get(CALLBACK, params=params)
    _redirected(response, "broker_state_invalid")
    assert kite.calls == []


async def test_a_reused_state_is_refused_without_a_second_exchange():
    kite = FakeKite(KiteExchangeError("kite_token_exception"))
    async with AsyncClient(transport=ASGITransport(app=_app(kite, RecordingDB())), base_url="http://t") as ac:
        state = await _state(ac)
        first = await ac.get(CALLBACK, params={"status": "success", "request_token": REQUEST_TOKEN, "state": state})
        second = await ac.get(CALLBACK, params={"status": "success", "request_token": REQUEST_TOKEN, "state": state})
    _redirected(first, "kite_token_exception")
    _redirected(second, "broker_state_invalid")
    assert kite.calls == [REQUEST_TOKEN]


def test_state_store_expires_after_ten_minutes_and_is_single_use():
    now = [1000.0]
    store = broker_routes.StateStore(clock=lambda: now[0])
    assert store.ttl == 600
    (a, na), (b, nb) = store.issue("u-a"), store.issue("u-b")
    assert a != b and len(a) >= 40 and na != nb
    now[0] += 599
    assert store.consume(a, na) == "u-a"
    assert store.consume(a, na) is None
    now[0] += 1  # b is now exactly 600 s old
    assert store.consume(b, nb) is None


def test_a_state_needs_the_browser_nonce_it_was_issued_with():
    store = broker_routes.StateStore(clock=lambda: 0.0)
    (a, na), (b, nb) = store.issue("u-a"), store.issue("u-b")
    assert store.consume(a, nb) is None and store.consume(a, na) is None  # a wrong nonce burns the state
    assert store.consume(b, None) is None


def test_live_states_are_capped_and_purging_counts_only_the_oldest():
    now = [0.0]
    store = broker_routes.StateStore(clock=lambda: now[0])
    assert store.cap == 20
    for _ in range(20):
        store.issue("u")
    before = store.ops
    for _ in range(1000):
        with pytest.raises(broker_routes.StateCapReached):
            store.issue("u")
    assert store.ops - before == 1000  # one look at the oldest state per refused call, never a scan
    assert len(store._states) == 20  # nothing evicted
    now[0] = 600.0
    before = store.ops
    store.issue("u")  # all 20 expired: purged in one pass, then the new one is held
    assert store.ops - before == 20 and len(store._states) == 1


async def test_the_login_route_refuses_over_the_cap():
    app = _app(FakeKite(), RecordingDB())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        codes = [(await ac.get(broker_routes.LOGIN_PATH)).status_code for _ in range(21)]
        last = await ac.get(broker_routes.LOGIN_PATH)
    assert codes[:20] == [302] * 20 and codes[20] == 429
    _refused(last, "broker_login_busy")
    assert "max-age=0" in last.headers["set-cookie"].lower()  # no new login nonce, only the clearing cookie


async def test_the_login_cookie_is_httponly_lax_and_scoped_to_the_callback():
    async with AsyncClient(transport=ASGITransport(app=_app(FakeKite(), RecordingDB())), base_url="http://t") as ac:
        cookie = (await ac.get(broker_routes.LOGIN_PATH)).headers["set-cookie"].lower()
    assert cookie.startswith(broker_routes.STATE_COOKIE + "=")
    assert "httponly" in cookie and "samesite=lax" in cookie and f"path={CALLBACK}" in cookie
    assert "max-age=600" in cookie and "secure" not in cookie  # http redirect URL: Secure would never be sent back
    https = load_broker_config(BrokerSettings(KITE_API_KEY=API_KEY, KITE_API_SECRET=API_SECRET,
                                              KITE_REDIRECT_URL="https://example.com" + CALLBACK,
                                              KITE_EXPECTED_USER_ID=USER_ID, BROKER_TOKEN_KEY=_key()))
    async with AsyncClient(transport=ASGITransport(app=_app(FakeKite(), RecordingDB(), https)),
                           base_url="http://t") as ac:
        assert "secure" in (await ac.get(broker_routes.LOGIN_PATH)).headers["set-cookie"].lower()


@pytest.mark.parametrize("cookie", [None, "someone-elses-nonce"])
async def test_a_callback_without_the_login_browsers_cookie_is_refused(cookie):
    kite = FakeKite()
    async with AsyncClient(transport=ASGITransport(app=_app(kite, RecordingDB())), base_url="http://t") as ac:
        state = await _state(ac)
        ac.cookies.clear()
        if cookie:
            ac.cookies.set(broker_routes.STATE_COOKIE, cookie, path=CALLBACK)
        response = await ac.get(CALLBACK, params={"status": "success", "request_token": REQUEST_TOKEN,
                                                  "state": state})
    _redirected(response, "broker_state_invalid")
    assert kite.calls == []


async def test_another_zerodha_account_is_refused_and_nothing_is_written():
    kite = FakeKite(KiteSession(ACCESS_TOKEN, "XY9999"))
    async with AsyncClient(transport=ASGITransport(app=_app(kite, RecordingDB())), base_url="http://t") as ac:
        state = await _state(ac)
        response = await ac.get(CALLBACK, params={"status": "success", "request_token": REQUEST_TOKEN,
                                                  "state": state})
    _redirected(response, "broker_user_mismatch")
    assert ACCESS_TOKEN not in response.text and kite.calls == [REQUEST_TOKEN]


async def test_an_expired_state_is_refused_without_an_exchange():
    kite = FakeKite()
    app = _app(kite, RecordingDB())
    now = [0.0]
    app.state.broker.states.clock = lambda: now[0]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        state = await _state(ac)
        now[0] = 600.0
        response = await ac.get(CALLBACK, params={"status": "success", "request_token": REQUEST_TOKEN,
                                                  "state": state})
    _redirected(response, "broker_state_invalid")
    assert kite.calls == []


# ---- Kite's answer on the redirect ----


@pytest.mark.parametrize("params", [
    {"status": "cancelled", "request_token": REQUEST_TOKEN},
    {"request_token": REQUEST_TOKEN},
    {"status": "success"},
    {"status": "success", "request_token": ""},
])
async def test_a_login_not_completed_stores_nothing(params):
    kite = FakeKite()
    async with AsyncClient(transport=ASGITransport(app=_app(kite, RecordingDB())), base_url="http://t") as ac:
        params = {**params, "state": await _state(ac)}
        response = await ac.get(CALLBACK, params=params)
    _redirected(response, "broker_login_not_completed")
    assert kite.calls == []


@pytest.mark.parametrize("code", [
    "kite_token_exception", "kite_input_exception", "kite_no_access_token", "kite_no_user_id", "kite_unavailable",
    "kite_refused", "kite_busy",
])
async def test_a_refused_exchange_stores_nothing(code):
    kite = FakeKite(KiteExchangeError(code))
    async with AsyncClient(transport=ASGITransport(app=_app(kite, RecordingDB())), base_url="http://t") as ac:
        state = await _state(ac)
        response = await ac.get(CALLBACK, params={"status": "success", "request_token": REQUEST_TOKEN,
                                                  "state": state})
    _redirected(response, code)
    assert REQUEST_TOKEN not in response.text


async def test_an_error_while_storing_stores_nothing_and_leaks_nothing(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)

    class Tx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class DB(RecordingDB):
        def begin(self):
            return Tx()

    async def boom(*args, **kwargs):
        raise RuntimeError(f"insert failed for {args[2]}")  # an error text that holds the token

    monkeypatch.setattr(broker_routes, "store_session", boom)
    async with AsyncClient(transport=ASGITransport(app=_app(FakeKite(), DB())), base_url="http://t") as ac:
        state = await _state(ac)
        response = await ac.get(CALLBACK, params={"status": "success", "request_token": REQUEST_TOKEN,
                                                  "state": state})
    _redirected(response, "broker_store_failed")
    assert ACCESS_TOKEN not in response.text
    assert all(ACCESS_TOKEN not in (r.getMessage() + (r.exc_text or "")) for r in caplog.records)


# ---- the token exchange over HTTP: every Kite answer state ----


def _kite_client(handler) -> tuple[HttpKiteAuth, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return HttpKiteAuth(API_KEY, API_SECRET, client), seen


async def test_exchange_posts_the_documented_form_and_returns_the_access_token():
    auth, seen = _kite_client(lambda r: httpx.Response(200, json={
        "status": "success", "data": {"user_id": "AB1234", "access_token": ACCESS_TOKEN}}))
    session = await auth.exchange(REQUEST_TOKEN)
    assert (session.access_token, session.user_id) == (ACCESS_TOKEN, "AB1234")
    assert ACCESS_TOKEN not in repr(session)
    (request,) = seen
    assert (request.method, str(request.url)) == ("POST", "https://api.kite.trade/session/token")
    assert request.headers["x-kite-version"] == "3"
    form = parse_qs(request.content.decode())
    expected = hashlib.sha256((API_KEY + REQUEST_TOKEN + API_SECRET).encode()).hexdigest()
    assert form == {"api_key": [API_KEY], "request_token": [REQUEST_TOKEN], "checksum": [expected]}
    assert API_SECRET not in request.content.decode()


@pytest.mark.parametrize("response, code", [
    (httpx.Response(200, json={"status": "success", "data": {"user_id": "AB1234"}}), "kite_no_access_token"),
    (httpx.Response(200, json={"status": "success", "data": {"access_token": ""}}), "kite_no_access_token"),
    (httpx.Response(200, text="not json"), "kite_unavailable"),
    (httpx.Response(200, json={"status": "success", "data": {"access_token": ACCESS_TOKEN}}), "kite_no_user_id"),
    (httpx.Response(403, json={"status": "error", "message": "Token is invalid or has expired.",
                               "error_type": "TokenException"}), "kite_token_exception"),
    (httpx.Response(400, json={"status": "error", "message": "Invalid `checksum`.",
                               "error_type": "InputException"}), "kite_input_exception"),
    (httpx.Response(429, json={"status": "error", "error_type": "NetworkException"}), "kite_busy"),
    (httpx.Response(429, text="slow down"), "kite_busy"),
    (httpx.Response(500, text="oops"), "kite_unavailable"),
    (httpx.Response(503, text="maintenance"), "kite_unavailable"),
])
async def test_each_kite_answer_maps_to_one_code_without_retry(response, code):
    auth, seen = _kite_client(lambda r: response)
    with pytest.raises(KiteExchangeError) as raised:
        await auth.exchange(REQUEST_TOKEN)
    assert raised.value.code == code and str(raised.value) == code
    assert len(seen) == 1  # no automatic retry


@pytest.mark.parametrize("error", [httpx.ConnectTimeout("t"), httpx.ReadTimeout("t"), httpx.ConnectError("c")])
async def test_timeouts_and_network_errors_are_unavailable_without_retry(error):
    def fail(request):
        raise error

    auth, seen = _kite_client(fail)
    with pytest.raises(KiteExchangeError) as raised:
        await auth.exchange(REQUEST_TOKEN)
    assert raised.value.code == "kite_unavailable" and len(seen) == 1
    assert raised.value.__suppress_context__


# ---- the dedicated key: refuse to start without it, never derived ----


def _settings(**over) -> BrokerSettings:
    base = dict(KITE_API_KEY=API_KEY, KITE_API_SECRET=API_SECRET,
                KITE_REDIRECT_URL="http://127.0.0.1:8000/kite/callback", KITE_EXPECTED_USER_ID=USER_ID,
                BROKER_TOKEN_KEY=_key())
    return BrokerSettings(**{**base, **over})


@pytest.mark.parametrize("over", [
    {"BROKER_TOKEN_KEY": ""},
    {"BROKER_TOKEN_KEY": "not base64 !!"},
    {"BROKER_TOKEN_KEY": base64.urlsafe_b64encode(os.urandom(16)).decode()},
    {"KITE_API_KEY": ""},
    {"KITE_API_SECRET": ""},
    {"KITE_REDIRECT_URL": ""},
    {"KITE_EXPECTED_USER_ID": ""},
    {"KITE_REDIRECT_URL": "/kite/callback"},
    {"KITE_REDIRECT_URL": "http://127.0.0.1:8000/kite/callback?x=1"},
])
def test_broker_routes_refuse_to_start_without_a_valid_configuration(over):
    with pytest.raises(BrokerConfigError) as raised:
        load_broker_config(_settings(**over))
    assert API_SECRET not in str(raised.value)


def test_a_key_derived_from_the_api_secret_is_refused():
    derived = base64.urlsafe_b64encode(hashlib.sha256(API_SECRET.encode()).digest()).decode()
    with pytest.raises(BrokerConfigError):
        load_broker_config(_settings(BROKER_TOKEN_KEY=derived))
    inside = base64.urlsafe_b64encode(b"k" * 32).decode()
    with pytest.raises(BrokerConfigError):
        load_broker_config(_settings(KITE_API_SECRET="x" + "k" * 32 + "y", BROKER_TOKEN_KEY=inside))


def test_the_cipher_key_is_exactly_the_configured_key():
    raw = os.urandom(32)
    config = load_broker_config(_settings(BROKER_TOKEN_KEY=base64.urlsafe_b64encode(raw).decode()))
    assert config.token_key == raw
    assert raw.hex() not in repr(config) and API_SECRET not in repr(config)


def test_create_app_fails_without_the_key(monkeypatch):
    monkeypatch.setenv("BROKER_TOKEN_KEY", "")
    with pytest.raises(BrokerConfigError):
        create_app()


# ---- the access log never records the callback's query string (real uvicorn) ----


async def test_uvicorn_access_log_drops_the_callback_query():
    import uvicorn

    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    access = logging.getLogger("uvicorn.access")
    handler = Capture(level=logging.DEBUG)
    access.addHandler(handler)
    old_level = access.level
    access.setLevel(logging.INFO)
    app = _app(FakeKite(), RecordingDB())
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_config=None, access_log=True,
                                           lifespan="off"))
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.02)
        assert server.started
        port = server.servers[0].sockets[0].getsockname()[1]
        async with httpx.AsyncClient() as ac:
            response = await ac.get(f"http://127.0.0.1:{port}{CALLBACK}",
                                    params={"status": "success", "request_token": REQUEST_TOKEN, "state": "x"})
        _redirected(response, "broker_state_invalid")
    finally:
        server.should_exit = True
        await task
        access.removeHandler(handler)
        access.setLevel(old_level)
    lines = [r.getMessage() for r in records]
    assert any(CALLBACK in line for line in lines), lines
    assert all(REQUEST_TOKEN not in line and "request_token" not in line for line in lines), lines


def _access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                             ("127.0.0.1:5000", "GET", path, "1.1", 400), None)


@pytest.mark.parametrize("path", [
    CALLBACK + "/?request_token=" + REQUEST_TOKEN + "&state=x",
    "/api" + CALLBACK + "?status=success&request_token=" + REQUEST_TOKEN,
    "/anything?state=abc",
    "/elsewhere?access_token=" + ACCESS_TOKEN,
    "/elsewhere?REQUEST_TOKEN=" + REQUEST_TOKEN,
])
def test_the_access_log_filter_redacts_by_query_key_on_any_path(path):
    record = _access_record(path)
    broker_routes.CallbackQueryFilter().filter(record)
    message = record.getMessage()
    assert "?" not in message and REQUEST_TOKEN not in message and ACCESS_TOKEN not in message
    assert path.split("?")[0] in message


def test_the_access_log_filter_keeps_an_ordinary_query():
    record = _access_record("/health?verbose=1")
    broker_routes.CallbackQueryFilter().filter(record)
    assert "/health?verbose=1" in record.getMessage()


# ---- W-024 merge: the redirect is built only at the boundary, from a typed model ----


def test_typed_redirect_refuses_anything_but_an_api_model():
    from ofo_app.errors import typed_redirect

    for bad in ({"redirect": "connected"}, "connected", None):
        with pytest.raises(TypeError):
            typed_redirect(bad, broker_routes.CONNECTED_FRONTEND_PATH)
    response = typed_redirect(broker_routes.BrokerRedirectOut(redirect="connected"),
                              broker_routes.CONNECTED_FRONTEND_PATH)
    assert (response.status_code, response.body) == (302, b"")
    assert response.headers["location"] == broker_routes.CONNECTED_FRONTEND_PATH
    assert response.headers["cache-control"] == "no-store" and "set-cookie" not in response.headers


def test_both_broker_routes_declare_the_typed_redirect_model():
    from fastapi.routing import APIRoute

    routes = {r.path: r for r in create_app(_config()).routes if isinstance(r, APIRoute)}
    for path in (broker_routes.LOGIN_PATH, CALLBACK):
        assert routes[path].response_model is broker_routes.BrokerRedirectOut
        assert routes[path].status_code == 302


async def test_any_boundary_error_carries_the_no_leak_headers():
    """An error the routes do not answer themselves (an unknown path) also goes out no-store / no-referrer."""
    async with AsyncClient(transport=ASGITransport(app=_app(FakeKite(), RecordingDB())), base_url="http://t") as ac:
        response = await ac.get("/no-such-path", params={"request_token": REQUEST_TOKEN})
    assert response.status_code == 404 and response.json() == render("user_input_request_not_available").as_dict()
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


# ---- fix round 1: redirect and cookie guards, catalogue codes survive log redaction ----


@pytest.mark.parametrize("location", ["https://evil.example/x", "//evil.example", "/" + chr(92) + "evil.example",
                                      "https://kite.zerodha.com/connect/login?v=3&api_key=k",
                                      "https://evil.example/connect/login?v=3&api_key=k&redirect_params=state%3Ds"])
def test_typed_redirect_refuses_an_off_site_location(location):
    with pytest.raises(ValueError):
        errors_module.typed_redirect(broker_routes.BrokerRedirectOut(redirect="connected"), location)


def test_typed_redirect_allows_exactly_the_kite_login_url():
    from ofo.broker.kite_auth import KITE_LOGIN_BASE, login_url

    assert errors_module.KITE_LOGIN_PAGE == KITE_LOGIN_BASE

    url = login_url(API_KEY, "s" * 43)
    response = errors_module.typed_redirect(broker_routes.BrokerRedirectOut(redirect="zerodha_login"), url)
    assert response.headers["location"] == url


@pytest.mark.parametrize("field, bad", [("path", "/p; Domain=.evil.example"), ("value", "v; Domain=.evil.example"),
                                        ("value", "v" + chr(13) + chr(10) + "X: y"), ("path", "/p" + chr(10)),
                                        ("path", "/p" + chr(13)), ("value", "v" + chr(13) + "X: y"),
                                        ("value", "v" + chr(10) + "X: y"), ("name", "n" + chr(13))])
def test_a_cookie_with_a_separator_is_refused(field, bad):
    kwargs = {"name": broker_routes.STATE_COOKIE, "path": CALLBACK, "value": "v", field: bad}
    with pytest.raises(ValueError):
        errors_module.RedirectCookie(**kwargs)


def test_catalogue_codes_survive_log_redaction_and_a_kite_token_does_not():
    from ofo_app import redaction

    codes = {t.code for t in CATALOGUE.values()}
    assert redaction.CATALOGUE_CODES == frozenset(codes)
    long_codes = sorted(c for c in codes if len(c) >= 20)
    assert long_codes, "no catalogue code is long enough to look like a token"
    for code in long_codes:
        line = f"user-facing error {code} on GET /kite/callback"
        assert redaction.redact(line) == line
    token = "h7Kq2Lm9Xw4Rt6Yp1Zs8Vb3Nc5Jd0Fg"  # 32 letters and digits: the shape of a Kite access token
    assert redaction.redact(f"token {token} here") == "token [REDACTED] here"


def test_mutant_without_the_code_set_redacts_the_codes(monkeypatch):
    """Mutation: drop the catalogue code set -> a long catalogue code is redacted as if it were a secret."""
    from ofo_app import redaction

    monkeypatch.setattr(redaction, "CATALOGUE_CODES", frozenset())
    code = CATALOGUE["broker_state_invalid"].code
    assert redaction.redact(code) == redaction.REDACTED


# ---- #163: the refusal page reads the reviewed message by code ----


@pytest.mark.parametrize("code", sorted(broker_routes.REFUSAL_CODES))
async def test_the_refusal_route_returns_the_catalogue_parts_for_every_code(code):
    async with AsyncClient(transport=ASGITransport(app=_app(FakeKite(), RecordingDB())), base_url="http://t") as ac:
        response = await ac.get(f"/api/broker/refusals/{code}")
    assert response.status_code == 200
    assert response.json() == {"code": code, "message": render(code).as_dict()}
    assert {"what_happened", "impact", "what_is_blocked", "next_action"} <= set(response.json()["message"])


@pytest.mark.parametrize("code", ["nope", "Kite_refused", "kite_refused%20x", "request_token=abc", "x" * 200])
async def test_an_unknown_refusal_code_gets_the_fixed_input_error_and_no_echo(code):
    async with AsyncClient(transport=ASGITransport(app=_app(FakeKite(), RecordingDB())), base_url="http://t") as ac:
        response = await ac.get(f"/api/broker/refusals/{code}")
    assert response.status_code == 422
    assert response.json() == render("user_input_request_invalid").as_dict()
    assert code not in response.text


async def test_the_refusal_route_never_carries_kites_own_text():
    kite_text = "TokenException: Invalid checksum RAW_KITE_TEXT"
    async with AsyncClient(transport=ASGITransport(app=_app(FakeKite(), RecordingDB())), base_url="http://t") as ac:
        bodies = [(await ac.get(f"/api/broker/refusals/{c}")).text for c in sorted(broker_routes.REFUSAL_CODES)]
    assert all("RAW_KITE_TEXT" not in b and "TokenException" not in b and "checksum" not in b.lower() for b in bodies)
    assert kite_text not in "".join(bodies)


def test_the_callback_has_no_json_refusal_path_left():
    """Class guard: inside kite_callback every refusal is a redirect; a `raise _refused(` would answer JSON again."""
    import inspect

    source = inspect.getsource(broker_routes.kite_callback)
    assert "raise _refused" not in source and "BrokerLoginRefused" not in source
    assert source.count("_refused_redirect(") >= 6
