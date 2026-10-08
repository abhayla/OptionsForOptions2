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
from ofo_app.broker_config import BrokerConfig, BrokerConfigError, BrokerSettings, load_broker_config
from ofo_app.db import get_db
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
    assert response.status_code == 400 and response.json()["code"] == "broker_state_invalid"
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
    assert (response.status_code, response.json()) == (400, {
        "code": "broker_state_invalid", "message": broker_routes.MESSAGES["broker_state_invalid"]})
    assert kite.calls == []


async def test_a_reused_state_is_refused_without_a_second_exchange():
    kite = FakeKite(KiteExchangeError("kite_token_exception"))
    async with AsyncClient(transport=ASGITransport(app=_app(kite, RecordingDB())), base_url="http://t") as ac:
        state = await _state(ac)
        first = await ac.get(CALLBACK, params={"status": "success", "request_token": REQUEST_TOKEN, "state": state})
        second = await ac.get(CALLBACK, params={"status": "success", "request_token": REQUEST_TOKEN, "state": state})
    assert first.json()["code"] == "kite_token_exception"
    assert second.json()["code"] == "broker_state_invalid"
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
    assert last.json() == {"code": "broker_login_busy", "message": broker_routes.MESSAGES["broker_login_busy"]}


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
    assert response.json()["code"] == "broker_state_invalid" and kite.calls == []


async def test_another_zerodha_account_is_refused_and_nothing_is_written():
    kite = FakeKite(KiteSession(ACCESS_TOKEN, "XY9999"))
    async with AsyncClient(transport=ASGITransport(app=_app(kite, RecordingDB())), base_url="http://t") as ac:
        state = await _state(ac)
        response = await ac.get(CALLBACK, params={"status": "success", "request_token": REQUEST_TOKEN,
                                                  "state": state})
    assert (response.status_code, response.json()["code"]) == (403, "broker_user_mismatch")
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
    assert response.json()["code"] == "broker_state_invalid" and kite.calls == []


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
    assert (response.status_code, response.json()) == (400, {
        "code": "broker_login_not_completed", "message": "Zerodha login was not completed"})
    assert kite.calls == []


@pytest.mark.parametrize("code, status", [
    ("kite_token_exception", 400), ("kite_input_exception", 400), ("kite_no_access_token", 400),
    ("kite_unavailable", 502), ("kite_refused", 400),
])
async def test_a_refused_exchange_stores_nothing(code, status):
    kite = FakeKite(KiteExchangeError(code))
    async with AsyncClient(transport=ASGITransport(app=_app(kite, RecordingDB())), base_url="http://t") as ac:
        state = await _state(ac)
        response = await ac.get(CALLBACK, params={"status": "success", "request_token": REQUEST_TOKEN,
                                                  "state": state})
    assert (response.status_code, response.json()["code"]) == (status, code)
    assert response.json()["message"] == broker_routes.MESSAGES[code]
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
    assert (response.status_code, response.json()["code"]) == (500, "broker_store_failed")
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
    (httpx.Response(429, json={"status": "error", "error_type": "NetworkException"}), "kite_refused"),
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
        assert response.status_code == 400
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
