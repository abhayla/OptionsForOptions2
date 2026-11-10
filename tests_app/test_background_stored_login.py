"""GC-ICSAFE c23/c24 (#627): the background worker reads T-16's margin with the day's STORED broker login, re-read each
margin read, so a late login, a re-login and an expiry are seen with no restart. The real chain runs (StoredLogin ->
OutcomeMargin -> get_approach_margin -> screen_margin_reader -> Worker); only the store and Zerodha's transport are
fakes (the recorded 2026-10-16 basket reply). No database, no network."""
from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from http import HTTPStatus
from types import SimpleNamespace

import pytest
from ofo.adjustment import playbook_eval as pe
from ofo_app import background, live_market, outcome_margin, scenario_mode
from ofo_app.feed_main import StoredSession
from ofo_app.outcome_margin import OutcomeMargin
from ofo_app.routes.adjustment import get_approach_margin
from test_background_cycle import Calls, Prov, _verdict, _worker
from test_background_day_open_margin import GAP_SCENARIO, _gap_time, _ic_watched
from test_outcome_margin import BASKET_TEXT, CHECKED_AT, CTX, FUNDS_TEXT, plan

NEEDED = Decimal("7065.50")  # the recorded reply's required total (test_outcome_margin)
FAKE_ACCESS = "tok-SECRET-STORED-456"
FP1, FP2 = b"fingerprint-1", b"fingerprint-2"
TWO_READS = 2
STEP = int(background.MARGIN_REFRESH_S)
ORDERS = outcome_margin.basket_orders(CTX.provider, plan())


class Store:
    """``read_session``: one scripted answer per read (a StoredSession, None, or an exception to raise)."""

    def __init__(self, *answers) -> None:
        self.answers, self.reads = list(answers), 0

    async def __call__(self, _user):
        self.reads += 1
        answer = self.answers[min(self.reads, len(self.answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer


class Zerodha:
    """Replaces the bounded urllib transport the client is built with; replays the recorded replies, counts calls."""

    def __init__(self, funds: str = FUNDS_TEXT, basket: str = BASKET_TEXT, status: int = HTTPStatus.OK,
                 basket_status: int = HTTPStatus.OK) -> None:
        self.funds, self.basket, self.status, self.basket_status, self.calls = funds, basket, status, basket_status, []

    def __call__(self, method, url, headers, body, *, timeout):
        self.calls.append(url)
        is_basket = "/margins/basket" in url
        status = self.basket_status if is_basket else self.status
        if status != HTTPStatus.OK:
            return status, '{"status": "error", "error_type": "NetworkException"}'
        return HTTPStatus.OK, (self.basket if is_basket else self.funds)

    def baskets(self) -> int:
        return sum("/margins/basket" in u for u in self.calls)


def session(fp: bytes = FP1, expires_at: datetime.datetime | None = None) -> StoredSession:
    return StoredSession("key", FAKE_ACCESS, fp, expires_at)


class Rig:
    """The worker wired as ``_serve_live`` wires it, on the scenario provider; ``at`` drives refresh + check."""

    def __init__(self, monkeypatch, gap_scn, store: Store, zerodha: Zerodha | None = None) -> None:
        self.zerodha = zerodha or Zerodha()
        monkeypatch.setattr(live_market, "urllib_transport", self.zerodha)
        monkeypatch.setattr(outcome_margin, "basket_orders", lambda _provider, _legs: ORDERS)
        self.prov, self.store = Prov(gap_scn), store
        self.t0 = _gap_time(self.prov)
        self.now, self.calls = [self.t0], Calls()
        self.login = background.StoredLogin(store, lambda: self.now[0])
        source = OutcomeMargin(self.login.session, self.login.open_client, clock=lambda: CHECKED_AT)
        margin_of = self.login.reading(background.screen_margin_reader(
            get_approach_margin(SimpleNamespace(provider=None), source)))
        self.w = _ic_watched(gap_scn)
        self.worker = _worker(self.prov, [self.w], self.now, self.calls, margin_of=margin_of)

    async def start(self) -> None:
        await self.worker.cycle()  # the first check: no margin yet, and it tells the cache the market to read for

    async def at(self, seconds: int) -> pe.StrategyState:
        """Move the clock, run one margin pass, then one check; that check's state."""
        self.now[0] = self.t0 + datetime.timedelta(seconds=seconds)
        self.prov.move_spot(self.prov.spot.ltp + 1, self.now[0])
        await self.worker.refresh_margins()
        await self.worker.cycle()
        return self.calls.states[-1][1]

    def verdict(self, state: pe.StrategyState):
        return _verdict(self.w.body, state, "T-16")


def assert_not_checked(rig: Rig, state: pe.StrategyState) -> None:
    v = rig.verdict(state)
    assert state.margin is None
    assert isinstance(v, pe.NotChecked)
    assert v.code.endswith("missing_margin")


@pytest.fixture
def gap_scn(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OFO_SCENARIO", GAP_SCENARIO)
    return scenario_mode.load(GAP_SCENARIO)


# ---- c23: the core ------------------------------------------------------------------------------------------------
def test_today_the_worker_has_no_session_of_its_own() -> None:
    """The defect: the app's margin source answers no session in a process without a LiveMarket object."""
    live_market.margin_source.cache_clear()
    assert live_market.margin_source().session() is None


async def test_core_a_stored_login_makes_the_worker_check_t16_with_zerodhas_margin(monkeypatch, gap_scn) -> None:
    rig = Rig(monkeypatch, gap_scn, Store(session()))
    await rig.start()
    state = await rig.at(1)
    assert state.margin == NEEDED
    assert not isinstance(rig.verdict(state), pe.NotChecked)
    assert rig.zerodha.baskets() == 1
    assert rig.login.session() == ("owner", FP1)


# ---- c24: login states --------------------------------------------------------------------------------------------
async def test_no_login_today_is_not_checked_and_zerodha_is_never_called(monkeypatch, gap_scn) -> None:
    rig = Rig(monkeypatch, gap_scn, Store(None))
    await rig.start()
    assert_not_checked(rig, await rig.at(1))
    assert rig.zerodha.calls == []


@pytest.mark.parametrize("past_by", [0, 3600])
async def test_a_login_past_its_expiry_when_read_is_not_checked(monkeypatch, gap_scn, past_by) -> None:
    """The store ends an expired login and answers None (that is the no-login test); here the store still hands one
    whose ``expires_at`` is already reached when read: refused as well."""
    at = _gap_time(Prov(gap_scn))
    store = Store(session(expires_at=at + datetime.timedelta(seconds=1 - past_by)))
    rig = Rig(monkeypatch, gap_scn, store)
    await rig.start()
    assert_not_checked(rig, await rig.at(1))
    assert rig.zerodha.calls == []


async def test_a_login_valid_until_after_now_is_used(monkeypatch, gap_scn) -> None:
    at = _gap_time(Prov(gap_scn))
    rig = Rig(monkeypatch, gap_scn, Store(session(expires_at=at + datetime.timedelta(hours=6))))
    await rig.start()
    assert (await rig.at(1)).margin == NEEDED


async def test_a_login_that_arrives_after_the_worker_started_is_used_at_the_next_round(monkeypatch, gap_scn) -> None:
    store = Store(None, session())
    rig = Rig(monkeypatch, gap_scn, store)
    await rig.start()
    assert_not_checked(rig, await rig.at(1))
    assert rig.zerodha.calls == []
    state = await rig.at(1 + STEP)
    assert state.margin == NEEDED
    assert store.reads == TWO_READS


async def test_a_relogin_never_serves_the_old_sessions_figure(monkeypatch, gap_scn) -> None:
    store = Store(session(FP1), session(FP1), session(FP2), None)
    rig = Rig(monkeypatch, gap_scn, store)
    await rig.start()
    assert (await rig.at(1)).margin == NEEDED
    assert rig.zerodha.baskets() == 1
    assert (await rig.at(1 + STEP)).margin == NEEDED  # same login: the plan-keyed cache answers, no new call
    assert rig.zerodha.baskets() == 1
    assert (await rig.at(1 + 2 * STEP)).margin == NEEDED  # new fingerprint: a new read, not the old key's figure
    assert rig.zerodha.baskets() == TWO_READS
    assert_not_checked(rig, await rig.at(1 + 3 * STEP))  # the login is gone: the cached figure is not used
    assert rig.zerodha.baskets() == TWO_READS


async def test_a_failing_store_read_is_not_checked_keeps_the_worker_running_and_logs_only_the_type(
        monkeypatch, gap_scn, caplog) -> None:
    store = Store(RuntimeError(f"db password {FAKE_ACCESS}"), session())
    rig = Rig(monkeypatch, gap_scn, store)
    await rig.start()
    with caplog.at_level(logging.DEBUG):
        assert_not_checked(rig, await rig.at(1))
        assert (await rig.at(1 + STEP)).margin == NEEDED  # the worker kept running and the next round recovers
    assert "RuntimeError" in caplog.text
    assert FAKE_ACCESS not in caplog.text
    assert "password" not in caplog.text


# ---- c24: the other answer states ---------------------------------------------------------------------------------
EMPTY = '{"status": "success", "data": {}}'


@pytest.mark.parametrize("zerodha", [
    Zerodha(status=HTTPStatus.INTERNAL_SERVER_ERROR),                       # the read fails
    Zerodha(status=HTTPStatus.FORBIDDEN),                                   # Kite rejects the token
    Zerodha(status=HTTPStatus.TOO_MANY_REQUESTS),                           # rate limit
    Zerodha(funds=EMPTY),                                                   # Kite answers empty (no funds figure)
    Zerodha(basket=EMPTY),                                                  # funds answer, basket states no figure
    Zerodha(basket_status=HTTPStatus.INTERNAL_SERVER_ERROR),                # funds answer, basket call fails
], ids=["fails", "token", "busy", "empty-funds", "empty-basket", "basket-fails"])
async def test_every_other_answer_state_is_not_checked_never_a_figure(monkeypatch, gap_scn, zerodha) -> None:
    rig = Rig(monkeypatch, gap_scn, Store(session()), zerodha)
    await rig.start()
    assert_not_checked(rig, await rig.at(1))


async def test_ten_checks_a_minute_make_one_zerodha_read_and_one_store_read(monkeypatch, gap_scn) -> None:
    """The 300 s per-strategy cache still holds with the stored login."""
    store = Store(session())
    rig = Rig(monkeypatch, gap_scn, store)
    await rig.start()
    for i in range(10):
        state = await rig.at(1 + 6 * i)
    assert state.margin == NEEDED
    assert rig.zerodha.baskets() == 1
    assert store.reads == 1


# ---- c24: token hygiene -------------------------------------------------------------------------------------------
async def test_the_token_appears_in_no_log_and_no_repr(monkeypatch, gap_scn, caplog) -> None:
    store = Store(session(), session(), RuntimeError(FAKE_ACCESS))
    rig = Rig(monkeypatch, gap_scn, store)
    failing = Rig(monkeypatch, gap_scn, Store(session()), Zerodha(status=HTTPStatus.FORBIDDEN))
    with caplog.at_level(logging.DEBUG):
        await rig.start()
        await rig.at(1)
        await rig.at(1 + STEP)
        await rig.at(1 + 2 * STEP)
        await failing.start()
        await failing.at(1)
    assert FAKE_ACCESS not in caplog.text
    await rig.login.reload()
    for shown in (repr(rig.login), repr(session()), repr(await failing.login.open_client())):
        assert FAKE_ACCESS not in shown
