"""W-058 AC-9: the broker access token is stored only as ciphertext bound to its row, never logged or sent to a
browser, destroyed when the session ends, and read back only by the adapter (REQ-015 AC-9, AC-7; REQ-063 AC-5).

Two parts:
- store logic on a recording connection (no database): what store_session writes, AAD binding, fail-closed reads;
- real PostgreSQL (skips locally without TEST_DATABASE_URL, runs in CI): the step-1 core proof through the real
  callback route, the guard and grants, and that ending a session leaves every other table unchanged.
All keys and tokens below are fakes, generated per test run.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ofo.broker.session import EndReason, expected_expiry
from ofo_app import broker_token_store as store
from ofo_app.broker_config import BrokerSettings, load_broker_config
from ofo_app.broker_crypto import NONCE_BYTES, TokenCipher, TokenDecryptError, associated_data
from ofo_app.db import get_db
from ofo_app.kite_client import HttpKiteAuth, KiteTokenException
from ofo_app.main import create_app
from ofo_app.routes import broker as broker_routes

API_KEY = "kite_fake_key"
API_SECRET = "kite_fake_secret_value"
REQUEST_TOKEN = "RQtok_fake_31b7c9d2e4f6a8b0"
ACCESS_TOKEN = "ACtok_fake_7a1c3e5b9d2f4a6c"
CHECKSUM = hashlib.sha256((API_KEY + REQUEST_TOKEN + API_SECRET).encode()).hexdigest()
SECRETS = (ACCESS_TOKEN, REQUEST_TOKEN, CHECKSUM)


def _cipher() -> TokenCipher:
    return TokenCipher(os.urandom(32))


class _Result:
    def __init__(self, value=None, row=None):
        self.value, self.row = value, row

    def scalar_one(self):
        assert self.value is not None
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def one_or_none(self):
        return self.row


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeEngine:
    """Hands out its own recording connection: what ran there ran in a separate, committed transaction."""

    def __init__(self) -> None:
        self.conn = FakeConn()
        self.begun = 0

    def begin(self):
        engine = self

        class _Tx:
            async def __aenter__(self):
                engine.begun += 1
                return engine.conn

            async def __aexit__(self, *exc):
                return False

        return _Tx()


class FakeConn:
    """Records every statement; answers the store's four statements as PostgreSQL would for one new session."""

    def __init__(self, new_id: int = 41, active_row=None) -> None:
        self.new_id, self.active_row = new_id, active_row
        self.calls: list[tuple[str, dict]] = []

    def begin_nested(self):
        return _Nested()

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.calls.append((sql, dict(params or {})))
        if sql.startswith("INSERT"):
            return _Result(self.new_id)
        if sql.startswith("SELECT"):
            return _Result(row=self.active_row)
        if "SET token_ciphertext = :ciphertext" in sql:
            return _Result(params["id"])
        return _Result(None)


# ---- what store_session writes ----


async def test_store_writes_only_ciphertext_bound_to_user_broker_and_id():
    conn, cipher = FakeConn(), _cipher()
    assert await store.store_session(conn, "u-1", ACCESS_TOKEN, cipher) == 41
    written = repr(conn.calls).encode()
    assert ACCESS_TOKEN.encode() not in written
    (blob,) = [p["ciphertext"] for _, p in conn.calls if "ciphertext" in p]
    assert ACCESS_TOKEN.encode() not in blob and len(blob) > NONCE_BYTES
    assert cipher.decrypt(blob, associated_data("u-1", "zerodha", 41)) == ACCESS_TOKEN
    for wrong in (associated_data("u-1", "zerodha", 42), associated_data("u-2", "zerodha", 41), b""):
        with pytest.raises(TokenDecryptError):
            cipher.decrypt(blob, wrong)


async def test_store_replaces_the_active_session_first_destroying_its_token():
    conn = FakeConn()
    await store.store_session(conn, "u-1", ACCESS_TOKEN, _cipher())
    first_sql, first_params = conn.calls[0]
    assert first_sql.startswith("UPDATE") and first_params["reason"] == "replaced"
    assert re.search(r"token_ciphertext\s*=\s*NULL", first_sql)
    assert [c[0].split()[0] for c in conn.calls] == ["UPDATE", "INSERT", "UPDATE"]
    insert_sql, insert_params = conn.calls[1]
    assert set(insert_params) == {"user_ref", "broker", "key_id"} and "ciphertext" not in insert_sql


@pytest.mark.parametrize("reason", [EndReason.EXPIRED, EndReason.DISCONNECTED])
async def test_ending_destroys_the_token_in_the_same_statement(reason):
    conn = FakeConn()
    await store.end_session(conn, "u-1", reason)
    ((sql, params),) = conn.calls
    assert params["reason"] == reason.value
    assert re.search(r"SET\s+ended_at\s*=.*token_ciphertext\s*=\s*NULL", sql)


def test_each_encryption_uses_a_fresh_nonce():
    cipher = _cipher()
    aad = associated_data("u-1", "zerodha", 1)
    a, b = cipher.encrypt(ACCESS_TOKEN, aad), cipher.encrypt(ACCESS_TOKEN, aad)
    assert a[:NONCE_BYTES] != b[:NONCE_BYTES] and a != b


# ---- the adapter read fails closed ----


async def test_access_token_for_decrypts_the_active_row():
    cipher = _cipher()
    blob = cipher.encrypt(ACCESS_TOKEN, associated_data("u-1", "zerodha", 7))
    assert await store.access_token_for(FakeConn(active_row=(7, cipher.key_id, blob, False)), "u-1", cipher,
                                        engine=FakeEngine()) == ACCESS_TOKEN


@pytest.mark.parametrize("case", ["no_row", "other_key", "copied_row", "tampered", "no_ciphertext"])
async def test_an_unreadable_row_is_treated_as_no_session(case, caplog):
    caplog.set_level(logging.DEBUG)
    cipher = _cipher()
    blob = cipher.encrypt(ACCESS_TOKEN, associated_data("u-1", "zerodha", 7))
    rows = {
        "no_row": None,
        "other_key": (7, _cipher().key_id, blob, False),
        "copied_row": (8, cipher.key_id, blob, False),
        "tampered": (7, cipher.key_id, blob[:-1] + bytes([blob[-1] ^ 1]), False),
        "no_ciphertext": (7, cipher.key_id, None, False),
    }
    assert await store.access_token_for(FakeConn(active_row=rows[case]), "u-1", cipher, engine=FakeEngine()) is None
    assert all(ACCESS_TOKEN not in r.getMessage() for r in caplog.records)


async def test_a_kite_token_exception_marks_the_session_expired():
    cipher = _cipher()
    blob = cipher.encrypt(ACCESS_TOKEN, associated_data("u-1", "zerodha", 7))
    conn = FakeConn(active_row=(7, cipher.key_id, blob, False))
    seen = []

    async def call(token):
        seen.append(token)
        raise KiteTokenException()

    engine = FakeEngine()
    with pytest.raises(KiteTokenException):
        await store.call_with_token(conn, "u-1", cipher, call, engine=engine)
    assert seen == [ACCESS_TOKEN]
    # the end ran in the engine's own transaction, not in the caller's (whose rollback would undo it)
    assert not any(sql.startswith("UPDATE") for sql, _ in conn.calls)
    assert engine.begun == 1
    ((sql, params),) = engine.conn.calls
    assert sql.startswith("UPDATE") and params["reason"] == "expired" and "token_ciphertext = NULL" in sql
    assert params["id"] == 7 and "WHERE id = :id" in sql  # only the row that was read


async def test_a_session_past_its_expected_expiry_is_ended_and_not_returned():
    cipher = _cipher()
    blob = cipher.encrypt(ACCESS_TOKEN, associated_data("u-1", "zerodha", 7))
    conn, engine = FakeConn(active_row=(7, cipher.key_id, blob, True)), FakeEngine()
    assert await store.access_token_for(conn, "u-1", cipher, engine=engine) is None
    assert "clock_timestamp()" in conn.calls[0][0]  # the database clock decides, not the caller's
    ((sql, params),) = engine.conn.calls
    assert params["reason"] == "expired" and "token_ciphertext = NULL" in sql
    assert params["id"] == 7 and "WHERE id = :id" in sql  # only the row that was read


def test_cipher_repr_and_key_id_never_show_the_key():
    key = os.urandom(32)
    cipher = TokenCipher(key)
    assert key.hex() not in repr(cipher) and key.hex() not in cipher.key_id
    assert base64.urlsafe_b64encode(key).decode() not in repr(cipher)


# ---------------------------------------------------------------------------------------------------------------
# Real PostgreSQL (CI). Each test uses its own user_ref: session rows are never deleted.
# ---------------------------------------------------------------------------------------------------------------


def _user() -> str:
    return "test-" + uuid.uuid4().hex


def _app(maker, user_ref: str, kite_handler):
    config = load_broker_config(BrokerSettings(
        KITE_API_KEY=API_KEY, KITE_API_SECRET=API_SECRET, KITE_REDIRECT_URL="http://127.0.0.1:8000/kite/callback",
        KITE_EXPECTED_USER_ID="AB1234",
        BROKER_TOKEN_KEY=base64.urlsafe_b64encode(os.urandom(32)).decode()))
    app = create_app(config)

    async def _db():
        async with maker() as session:
            yield session

    async def _kite():
        async with httpx.AsyncClient(transport=httpx.MockTransport(kite_handler)) as client:
            yield HttpKiteAuth(API_KEY, API_SECRET, client)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[broker_routes.get_kite_auth] = _kite
    app.dependency_overrides[broker_routes.current_user_ref] = lambda: user_ref
    return app


def _kite_ok(request: httpx.Request) -> httpx.Response:
    form = parse_qs(request.content.decode())
    assert form["checksum"] == [CHECKSUM] and form["request_token"] == [REQUEST_TOKEN]
    return httpx.Response(200, json={"status": "success", "data": {"user_id": "AB1234",
                                                                   "access_token": ACCESS_TOKEN}})


async def _login(ac: AsyncClient) -> httpx.Response:
    login = await ac.get(broker_routes.LOGIN_PATH)
    state = parse_qs(parse_qs(urlsplit(login.headers["location"]).query)["redirect_params"][0])["state"][0]
    return await ac.get("/kite/callback", params={"action": "login", "type": "login", "status": "success",
                                                  "request_token": REQUEST_TOKEN, "state": state})


async def _rows(admin_engine, user_ref: str) -> list[dict]:
    async with admin_engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT id, token_ciphertext, key_id, started_at, expected_expiry, ended_at, end_reason, t::text AS whole "
            "FROM public.broker_sessions AS t WHERE user_ref = :u ORDER BY id"), {"u": user_ref})
        return [dict(r._mapping) for r in result]


async def _other_tables(admin_engine) -> dict[str, str]:
    """A digest of every other table in public: ending a session must change none (strategies, entitlements...)."""
    async with admin_engine.connect() as conn:
        names = [r[0] for r in await conn.execute(text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname <> 'broker_sessions' ORDER BY 1"))]
        out = {}
        for name in names:
            out[name] = (await conn.execute(text(
                f'SELECT md5(coalesce(string_agg(x::text, \'|\' ORDER BY x::text), \'\')) FROM public."{name}" x'
            ))).scalar_one()
        return out


def _no_secret(blob: bytes, label: str) -> None:
    for secret in SECRETS:
        assert secret.encode() not in blob, f"{label} holds a secret"


async def test_core_proof_callback_stores_only_ciphertext_and_the_adapter_reads_it(app_engine, admin_engine, caplog):
    caplog.set_level(logging.DEBUG)
    user = _user()
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    app = _app(maker, user, _kite_ok)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        response = await _login(ac)
    # the browser: a fixed path, no query, no cookie, no token anywhere
    assert response.status_code == 302 and response.headers["location"] == broker_routes.CONNECTED_FRONTEND_PATH
    assert response.headers["referrer-policy"] == "no-referrer"
    # the only cookie sent is the login cookie being cleared (empty value, Max-Age=0), never a session or token
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 1 and cookies[0].startswith(broker_routes.STATE_COOKIE + '=""') and "Max-Age=0" in cookies[0]
    _no_secret(response.content, "the response body")
    _no_secret(repr(response.headers.multi_items()).encode(), "the response headers")
    _no_secret(repr(dict(response.cookies)).encode(), "the cookies")
    # the row: ciphertext only
    (row,) = await _rows(admin_engine, user)
    _no_secret(bytes(row["token_ciphertext"]), "the stored ciphertext")
    _no_secret(row["whole"].encode(), "the stored row")
    assert row["ended_at"] is None and row["end_reason"] is None
    # every log record from every logger, except the lines the TEST HARNESS's own client emits: httpx logs each
    # request the test sends ("HTTP Request: GET http://t/kite/callback?...request_token=..."), which is the test
    # typing the redirect URL, not the server logging it. Only those records (host t) are left out.
    harness = [r for r in caplog.records if r.name == "httpx" and "http://t/" in r.getMessage()]
    server = [r for r in caplog.records if r not in harness]
    for record in server:
        _no_secret((record.getMessage() + repr(record.args) + (record.exc_text or "")).encode(), record.name)
    # the server's own outbound Kite client logs, and they hold none of the three
    outbound = [r for r in server if r.name == "httpx" and "api.kite.trade" in r.getMessage()]
    assert outbound, [r.getMessage() for r in caplog.records]
    for record in outbound:
        _no_secret(record.getMessage().encode(), "the outbound Kite client log")
    # the adapter returns the original token
    async with maker() as session:
        assert await store.access_token_for(session, user, app.state.broker.cipher, engine=app_engine) == ACCESS_TOKEN
    # the database's expected expiry agrees with the domain rule
    assert row["expected_expiry"] == expected_expiry(row["started_at"])


async def test_a_second_login_replaces_the_first_and_destroys_its_token(app_engine, admin_engine):
    user = _user()
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    app = _app(maker, user, _kite_ok)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        before = await _other_tables(admin_engine)
        assert (await _login(ac)).status_code == 302
        assert (await _login(ac)).status_code == 302
    first, second = await _rows(admin_engine, user)
    assert (first["end_reason"], first["token_ciphertext"]) == ("replaced", None) and first["ended_at"] is not None
    assert second["ended_at"] is None and second["token_ciphertext"] is not None
    assert await _other_tables(admin_engine) == before


@pytest.mark.parametrize("reason", [EndReason.EXPIRED, EndReason.DISCONNECTED])
async def test_ending_destroys_the_token_keeps_the_row_and_touches_nothing_else(app_engine, admin_engine, reason):
    user, cipher = _user(), _cipher()
    async with app_engine.begin() as conn:
        await store.store_session(conn, user, ACCESS_TOKEN, cipher)
    before = await _other_tables(admin_engine)
    async with app_engine.begin() as conn:
        assert await store.end_session(conn, user, reason) is not None
    (row,) = await _rows(admin_engine, user)
    assert (row["end_reason"], row["token_ciphertext"]) == (reason.value, None) and row["ended_at"] is not None
    assert await _other_tables(admin_engine) == before
    async with app_engine.connect() as conn:
        assert await store.access_token_for(conn, user, cipher, engine=app_engine) is None


async def test_a_ciphertext_copied_to_another_row_does_not_decrypt(app_engine):
    a, b, cipher = _user(), _user(), _cipher()
    async with app_engine.begin() as conn:
        await store.store_session(conn, a, ACCESS_TOKEN, cipher)
        blob = (await conn.execute(text("SELECT token_ciphertext FROM public.broker_sessions "
                                        "WHERE user_ref = :u AND ended_at IS NULL"), {"u": a})).scalar_one()
        b_id = (await conn.execute(text("INSERT INTO public.broker_sessions (user_ref, broker, key_id) "
                                        "VALUES (:u, 'zerodha', :k) RETURNING id"), {"u": b, "k": cipher.key_id})
                ).scalar_one()
        await conn.execute(text("UPDATE public.broker_sessions SET token_ciphertext = :c WHERE id = :i"),
                           {"c": blob, "i": b_id})
        assert await store.access_token_for(conn, b, cipher, engine=app_engine) is None
        assert await store.access_token_for(conn, a, cipher, engine=app_engine) == ACCESS_TOKEN


@pytest.mark.parametrize("statement", [
    # ending while keeping the ciphertext
    "UPDATE public.broker_sessions SET ended_at = now(), end_reason = 'expired' WHERE id = :i",
    # a second ciphertext on an active row
    "UPDATE public.broker_sessions SET token_ciphertext = '\\x00'::bytea WHERE id = :i",
    # dropping the token without ending
    "UPDATE public.broker_sessions SET token_ciphertext = NULL WHERE id = :i",
    # an end without a reason
    "UPDATE public.broker_sessions SET ended_at = now(), token_ciphertext = NULL WHERE id = :i",
    # an unknown end reason
    "UPDATE public.broker_sessions SET ended_at = now(), end_reason = 'other', token_ciphertext = NULL WHERE id = :i",
    # no delete
    "DELETE FROM public.broker_sessions WHERE id = :i",
    # no caller-chosen ciphertext, stamps or id on insert
    "INSERT INTO public.broker_sessions (user_ref, broker, key_id, token_ciphertext) VALUES ('x', 'zerodha', 'k', 'a')",
    "INSERT INTO public.broker_sessions (user_ref, broker, key_id, started_at) VALUES ('x', 'zerodha', 'k', now())",
    "UPDATE public.broker_sessions SET expected_expiry = now() WHERE id = :i",
    # only zerodha
    "INSERT INTO public.broker_sessions (user_ref, broker, key_id) VALUES ('x', 'upstox', 'k')",
])
async def test_the_database_refuses_every_way_round_the_token_rules(app_engine, statement):
    user = _user()
    async with app_engine.begin() as conn:
        session_id = await store.store_session(conn, user, ACCESS_TOKEN, _cipher())
    async with app_engine.connect() as conn:
        with pytest.raises(DBAPIError):
            await conn.execute(text(statement), {"i": session_id})
        await conn.rollback()


async def test_an_ended_row_never_changes_and_one_active_session_per_user(app_engine):
    user = _user()
    async with app_engine.begin() as conn:
        session_id = await store.store_session(conn, user, ACCESS_TOKEN, _cipher())
        await store.end_session(conn, user, EndReason.DISCONNECTED)
    async with app_engine.connect() as conn:
        with pytest.raises(DBAPIError):
            await conn.execute(text("UPDATE public.broker_sessions SET end_reason = 'expired' WHERE id = :i"),
                               {"i": session_id})
        await conn.rollback()
    async with app_engine.connect() as conn:
        await conn.execute(text("INSERT INTO public.broker_sessions (user_ref, broker, key_id) "
                                "VALUES (:u, 'zerodha', 'k')"), {"u": user})
        with pytest.raises(DBAPIError):
            await conn.execute(text("INSERT INTO public.broker_sessions (user_ref, broker, key_id) "
                                    "VALUES (:u, 'zerodha', 'k')"), {"u": user})
        await conn.rollback()


async def test_a_token_exception_inside_the_callers_transaction_still_ends_the_session(app_engine, admin_engine):
    user, cipher = _user(), _cipher()
    async with app_engine.begin() as conn:
        await store.store_session(conn, user, ACCESS_TOKEN, cipher)

    async def call(token):
        raise KiteTokenException()

    with pytest.raises(KiteTokenException):
        async with app_engine.begin() as conn:  # this transaction rolls back on the re-raise
            await store.call_with_token(conn, user, cipher, call, engine=app_engine)
    (row,) = await _rows(admin_engine, user)
    assert (row["end_reason"], row["token_ciphertext"]) == ("expired", None) and row["ended_at"] is not None
    async with app_engine.connect() as conn:
        assert await store.access_token_for(conn, user, cipher, engine=app_engine) is None


async def test_a_login_by_another_zerodha_account_never_ends_the_owners_session(app_engine, admin_engine):
    user = _user()
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)

    def other_account(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "success", "data": {"user_id": "XY9999",
                                                                       "access_token": "ACtok_fake_other"}})

    async with AsyncClient(transport=ASGITransport(app=_app(maker, user, _kite_ok)), base_url="http://t") as ac:
        assert (await _login(ac)).status_code == 302
    async with AsyncClient(transport=ASGITransport(app=_app(maker, user, other_account)), base_url="http://t") as ac:
        refused = await _login(ac)
    assert (refused.status_code, refused.json()["code"]) == (403, "broker_user_mismatch")
    (row,) = await _rows(admin_engine, user)
    assert row["ended_at"] is None and row["token_ciphertext"] is not None


class RacingEngine:
    """The real engine, but a re-login lands (committed) just before the store opens its own ending transaction:
    the window between reading session 1 and ending it."""

    def __init__(self, engine, user_ref: str, cipher: TokenCipher) -> None:
        self.engine, self.user_ref, self.cipher = engine, user_ref, cipher
        self.raced = 0

    def begin(self):
        racer = self

        class _Tx:
            async def __aenter__(self):
                async with racer.engine.begin() as other:
                    await store.store_session(other, racer.user_ref, "ACtok_fake_second_login", racer.cipher)
                racer.raced += 1
                self._ctx = racer.engine.begin()
                return await self._ctx.__aenter__()

            async def __aexit__(self, *exc):
                return await self._ctx.__aexit__(*exc)

        return _Tx()


async def _assert_second_session_survives(admin_engine, app_engine, user: str, cipher: TokenCipher) -> None:
    first, second = await _rows(admin_engine, user)
    assert (first["end_reason"], first["token_ciphertext"]) == ("replaced", None)
    assert second["ended_at"] is None and second["token_ciphertext"] is not None
    async with app_engine.connect() as conn:
        assert await store.access_token_for(conn, user, cipher, engine=app_engine) == "ACtok_fake_second_login"


async def test_a_late_token_exception_on_session_1_never_ends_session_2(app_engine, admin_engine):
    user, cipher = _user(), _cipher()
    async with app_engine.begin() as conn:
        await store.store_session(conn, user, ACCESS_TOKEN, cipher)
    racing = RacingEngine(app_engine, user, cipher)

    async def call(token):
        assert token == ACCESS_TOKEN
        raise KiteTokenException()

    with pytest.raises(KiteTokenException):
        async with app_engine.connect() as conn:
            await store.call_with_token(conn, user, cipher, call, engine=racing)
    assert racing.raced == 1
    await _assert_second_session_survives(admin_engine, app_engine, user, cipher)


async def test_the_expiry_path_ends_only_the_row_it_read(app_engine, admin_engine):
    user, cipher = _user(), _cipher()
    async with app_engine.begin() as conn:
        session_id = await store.store_session(conn, user, ACCESS_TOKEN, cipher)
    # the owner moves session 1's expected expiry into the past; the guard stamps that column, so it is disabled for
    # this one statement inside the owner's transaction and enabled again before the transaction ends
    async with admin_engine.begin() as conn:
        await conn.execute(text("ALTER TABLE public.broker_sessions DISABLE TRIGGER broker_sessions_guard"))
        await conn.execute(text("UPDATE public.broker_sessions SET expected_expiry = clock_timestamp() "
                                "- interval '1 hour' WHERE id = :i"), {"i": session_id})
        await conn.execute(text("ALTER TABLE public.broker_sessions ENABLE TRIGGER broker_sessions_guard"))
    racing = RacingEngine(app_engine, user, cipher)
    async with app_engine.connect() as conn:
        assert await store.access_token_for(conn, user, cipher, engine=racing) is None
    assert racing.raced == 1
    await _assert_second_session_survives(admin_engine, app_engine, user, cipher)
