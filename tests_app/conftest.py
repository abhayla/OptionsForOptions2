"""Fixtures for the API/DB tests (ADR-048: real PostgreSQL only, never SQLite).

TEST_DATABASE_URL       the application role (ofo_app: LOGIN, NOSUPERUSER, ...), e.g.
                        postgresql+asyncpg://ofo_app:${PW}@127.0.0.1:5432/ofo_test
TEST_ADMIN_DATABASE_URL the owner role that ran the migrations (used only by mutation tests, inside a rolled-back
                        transaction)
OFO_REQUIRE_DB_TESTS=1  CI sets this so a missing URL fails the run instead of skipping it.

The `client` fixture pattern is copied/adapted from abhayla/algochanakya@bf9faf7:backend/tests/conftest.py
(ADR-047): `app.dependency_overrides[get_db]` + `httpx.AsyncClient(transport=ASGITransport(app=app))`. Its SQLite
engine and @compiles shims are deliberately not copied.
"""

from __future__ import annotations

import asyncio
import base64
import math
import os
import platform
import sys
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.broker import egress as _egress
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# W-080 round 7 (REQ-073 AC-4): the egress gate's TEST mode (this suite only): the doors accept their test seams (a
# mock transport, an injected websocket connect) and this Python may run as a child process. Production never enters it.
# The gate itself is installed here with the call the API's create_app makes (importing ofo does not install it).
# finding local-pytest-plugin-not-in-ci: on Windows the first platform.uname()/win32_ver() call starts a process
# (platform._syscmd_ver), which the no-process hook below refuses if the first call comes later; prime the caches now.
for _name in ("uname", "win32_ver", "platform", "system", "release", "version", "machine", "python_implementation"):
    getattr(platform, _name)()
_egress.install()
_egress._enter_test_mode([sys.executable])
# The app runs only on the selector loop (ofo_app.event_loop); on Windows the default is the Proactor loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def _fresh_kite_limiter():
    """REQ-118: a 429 case starts a REAL 10 s cooldown in the process-wide limiter, and the next test's Kite call would
    wait it out (6 ``test_kite_login`` tests went red that way). Each test gets its own fresh limiter; production keeps
    ONE per process (``rate_limit.current``)."""
    from ofo.broker import rate_limit  # noqa: PLC0415 - the KITE_* placeholders below are set after this module's top
    with rate_limit.use(rate_limit.process_limiter(os.environ)):
        yield


@pytest.fixture(autouse=True)
def _no_charge_rates_by_default(monkeypatch):
    """W-075: the outcome route and the live push load the charge rates in force from the database, cached in
    ``ofo_app.routes.outcome._rates_cache``. Tests that do not care get a cached "no rate set" (never a connection
    attempt, never a wall-clock wait); the wiring tests seed the cache with a rate set instead."""
    # the import waits for the test: the KITE_* placeholders below must be in the environment before the app loads
    from ofo_app.routes import outcome  # noqa: PLC0415 - import order: env placeholders are set after this module's top
    monkeypatch.setattr(outcome, "_rates_cache", {"until": math.inf, "value": None})


# W-058: create_app refuses to build without a broker configuration. Tests get placeholders and a key generated for
# this run (never a real secret); a value already in the environment (CI) is kept.
os.environ.setdefault("KITE_API_KEY", "test_placeholder_key")
os.environ.setdefault("KITE_API_SECRET", "test_placeholder_secret")
os.environ.setdefault("KITE_REDIRECT_URL", "http://127.0.0.1:8000/kite/callback")
os.environ.setdefault("FRONTEND_ORIGIN", "http://127.0.0.1:4173")
os.environ.setdefault("KITE_EXPECTED_USER_ID", "ZZ0000")
os.environ.setdefault("BROKER_TOKEN_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"))

DB_SKIP_REASON ="TEST_DATABASE_URL is unset: database tests need real PostgreSQL (ADR-048); never SQLite"
ADMIN_SKIP_REASON = "TEST_ADMIN_DATABASE_URL is unset: mutation tests need the owner role (ADR-048)"


def _required() -> bool:
    return os.environ.get("OFO_REQUIRE_DB_TESTS") == "1"


def _url_or_skip(name: str, reason: str) -> str:
    url = os.environ.get(name, "").strip()
    if not url:
        if _required():
            pytest.fail(f"{name} is unset but OFO_REQUIRE_DB_TESTS=1 (CI must run the database proof)")
        pytest.skip(reason)
    if not url.startswith("postgresql"):
        pytest.fail(f"{name} must be a PostgreSQL URL (ADR-048 forbids any other engine)")
    return url


def _engine(url: str) -> AsyncEngine:
    return create_async_engine(url, poolclass=NullPool, connect_args={"server_settings": {"jit": "off"}})


@pytest.fixture
async def app_engine() -> AsyncIterator[AsyncEngine]:
    engine = _engine(_url_or_skip("TEST_DATABASE_URL", DB_SKIP_REASON))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def admin_engine() -> AsyncIterator[AsyncEngine]:
    engine = _engine(_url_or_skip("TEST_ADMIN_DATABASE_URL", ADMIN_SKIP_REASON))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(app_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    from ofo_app.db import get_db  # noqa: PLC0415
    from ofo_app.main import create_app  # noqa: PLC0415

    app = create_app()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def order_path_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """W-121 (REQ-073 AC-6): the order path is OFF everywhere but APP_ENV=test + OFO_ORDER_PATH=1; the tests of the
    Execute and return routes opt in with ``pytestmark = pytest.mark.usefixtures("order_path_on")``."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OFO_ORDER_PATH", "1")


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    """REQ-113: the bus address. CI sets REDIS_URL from a ``redis:7`` service; a developer PC gets the pure-Python
    stand-in (fakeredis, finding F-58) on a loopback port. No Redis and no stand-in FAILS when OFO_REQUIRE_DB_TESTS=1
    (CI), else skips."""
    given = os.environ.get("REDIS_URL", "").strip()
    if given:
        yield given
        return
    try:
        import fakeredis  # noqa: PLC0415
    except ImportError:
        if _required():
            pytest.fail("REDIS_URL is unset and fakeredis is not installed, but OFO_REQUIRE_DB_TESTS=1")
        pytest.skip("no Redis: set REDIS_URL or install fakeredis (requirements-dev.txt)")
    import threading  # noqa: PLC0415

    server = fakeredis.TcpFakeServer(("127.0.0.1", 0), server_type="redis")
    threading.Thread(target=server.serve_forever, daemon=True, name="redis-stand-in").start()
    yield f"redis://127.0.0.1:{server.server_address[1]}/0"
    stopper = threading.Thread(target=server.shutdown, daemon=True)  # shutdown() waits for the serve loop: bound it
    stopper.start()
    stopper.join(timeout=3)
    # server_close() joins every handler thread, so ONE client left open by a failed test hung the whole run for good
    # (mutant M6, 420 s): bound it too, and let the daemon thread go (the process exits anyway).
    closer = threading.Thread(target=server.server_close, daemon=True)
    closer.start()
    closer.join(timeout=3)
