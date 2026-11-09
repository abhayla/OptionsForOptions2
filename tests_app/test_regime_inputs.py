"""GC-ICTRACK tasks 14b + 26: ADR-280's five market-wide inputs (``regime_inputs``) with fake Kite clients, every
answer state per input (stated, no session, failed, empty), one failing input never blanking the others, one candle
read per underlying per pass; and the scenario twin (ADJ-60) through the SAME clients over the scenario transport,
so T-11b and T-20b fire through ``state_of`` and T-11c answers from the percentile. No DB, no network."""
from __future__ import annotations

import dataclasses
import datetime
import itertools
from decimal import Decimal as D

import pytest
import t19_support as s
from ofo.adjustment import playbook_eval as pe
from ofo.history.candles import CandleError
from ofo_app import live_market, regime_inputs, scenario_mode
from ofo_app.daily_candles import DailyCandles
from ofo_app.kite_history import CandleFetchError, DayCandle
from ofo_app.kite_margin import KiteMarginError
from ofo_app.kite_reads import KiteReadError
from ofo_app.regime_inputs import INDEX_TOKENS, VIX_TOKEN, Clients, RegimeInputs, RegimePerList, read_with
from test_ictrack_state_inputs import answers, state, switched_on

_users = itertools.count()
TRENDING = D(25)  # ADR-277 (3): ADX 25 or more reads as trending
TODAY = datetime.date(2026, 11, 6)
CLOCK = datetime.datetime(2026, 11, 6, 6, 10, tzinfo=datetime.UTC)  # 11:40 IST


class Reads:
    def __init__(self, quote=None, fail: bool = False) -> None:
        self.user_ref = f"regime-test-{next(_users)}"  # the limiter's memo is per user: a fresh user per client
        self.quote, self.fail = quote, fail

    def fetch_index_quote(self, name: str):
        if self.fail:
            raise KiteReadError("kite_read_unavailable")
        return self.quote


class Margin:
    def __init__(self, value=D("150000"), fail: bool = False) -> None:
        self.value, self.fail = value, fail

    def fetch_available_funds(self):
        if self.fail:
            raise KiteMarginError("kite_margin_unavailable")
        return self.value


def _days(n: int) -> list[datetime.date]:
    return [TODAY - datetime.timedelta(days=n - i) for i in range(n)]


def _candles(token: str, n: int = 250) -> list[DayCandle]:
    if token == VIX_TOKEN:  # closes 10.0 .. 19.8: VIX 16.8 ranks at 70% (k = 0..34: 35 of each 50 at or below)
        return [DayCandle(d, None, None, D(10) + D(i % 50) / 5) for i, d in enumerate(_days(n))]
    return [DayCandle(d, D(24000 + 12 * i + 30), D(24000 + 12 * i - 30), D(24000 + 12 * i))
            for i, d in enumerate(_days(n))]


class Fetch:
    def __init__(self, rows=_candles, fail: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.rows, self.fail = rows, fail

    def __call__(self, token: str, start, end):
        self.calls.append(token)
        if self.fail is not None:
            raise self.fail
        return self.rows(token)


QUOTE = {"last_price": D("16.8"), "ohlc": {"close": D("15")}}


def _read(underlying="NIFTY", reads=None, margin=None, fetch=None, history=True) -> tuple[RegimeInputs, Fetch]:
    fetch = fetch or Fetch()
    reads = Reads(QUOTE) if reads is None else reads
    clients = Clients(reads, Margin() if margin is None else margin, object() if history else None)
    return read_with(clients, underlying, DailyCandles(fetch, clock=lambda: CLOCK)), fetch


def test_stated_every_input_read():
    r, fetch = _read()
    assert (r.available_margin, r.vix, r.vix_prev_close, r.vix_percentile) == (D("150000"), D("16.8"), D(15), D(70))
    assert r.adx is not None and r.adx > TRENDING  # a steady up-trend
    assert sorted(fetch.calls) == sorted([VIX_TOKEN, INDEX_TOKENS["NIFTY"]])


def test_no_session_every_input_none():
    assert read_with(Clients(), "NIFTY", DailyCandles(Fetch(), clock=lambda: CLOCK)) == RegimeInputs()


@pytest.mark.asyncio
async def test_live_no_session_reads_nothing(monkeypatch):
    monkeypatch.setattr(scenario_mode, "current", lambda: None)

    async def none():
        return None
    monkeypatch.setattr(live_market, "owner_kite_reads", none)
    assert await regime_inputs.read_regime("NIFTY") == RegimeInputs()


def test_failed_vix_read_blanks_only_vix_and_its_percentile():
    r, _ = _read(reads=Reads(fail=True))
    assert (r.vix, r.vix_prev_close, r.vix_percentile) == (None, None, None)
    assert r.available_margin == D("150000") and r.adx is not None


def test_failed_margin_read_blanks_only_the_margin():
    r, _ = _read(margin=Margin(fail=True))
    assert r.available_margin is None and r.vix == D("16.8") and r.vix_percentile == D(70) and r.adx is not None


@pytest.mark.parametrize("error", [CandleFetchError("http status 500"), CandleError("malformed candle body")])
def test_failed_candle_read_blanks_only_percentile_and_adx(error):
    r, _ = _read(fetch=Fetch(fail=error))
    assert (r.vix_percentile, r.adx) == (None, None)
    assert r.available_margin == D("150000") and r.vix == D("16.8")


def test_failure_is_logged_by_error_class_only(caplog):
    _read(reads=Reads(fail=True))
    assert "KiteReadError" in caplog.text and "kite_read_unavailable" not in caplog.text


@pytest.mark.parametrize("quote", [None, {}, {"last_price": 0, "ohlc": {"close": 0}}],
                         ids=["not-found", "empty", "zero"])
def test_empty_vix_quote_none(quote):
    r, _ = _read(reads=Reads(quote))
    assert (r.vix, r.vix_prev_close, r.vix_percentile) == (None, None, None)


def test_empty_candles_and_too_few_none():
    r, _ = _read(fetch=Fetch(rows=lambda token: []))
    assert (r.vix_percentile, r.adx) == (None, None)
    r, _ = _read(fetch=Fetch(rows=lambda token: _candles(token, 20)))  # fewer than 250 / 28: a ValueError
    assert (r.vix_percentile, r.adx) == (None, None)


def test_a_candle_without_range_gives_no_adx():
    def rows(token):
        out = _candles(token)
        return [*out[:-1], dataclasses.replace(out[-1], high=None)] if token != VIX_TOKEN else out
    r, _ = _read(fetch=Fetch(rows=rows))
    assert r.adx is None and r.vix_percentile == D(70)


def test_sensex_has_no_vix_percentile_and_reads_its_own_candles():
    r, fetch = _read("SENSEX")
    assert r.vix_percentile is None and r.adx is not None and r.vix == D("16.8")
    assert fetch.calls == [INDEX_TOKENS["SENSEX"]]


def test_one_candle_read_per_index_per_day_for_two_strategies():
    fetch = Fetch()
    daily = DailyCandles(fetch, clock=lambda: CLOCK)
    for _ in range(2):  # two NIFTY strategies, the same process-wide cache
        read_with(Clients(Reads(QUOTE), Margin(), object()), "NIFTY", daily)
    assert sorted(fetch.calls) == sorted([VIX_TOKEN, INDEX_TOKENS["NIFTY"]])


@pytest.mark.asyncio
async def test_one_regime_read_per_underlying_per_list(monkeypatch):
    seen: list[str] = []

    async def fake(u):
        seen.append(u)
        return RegimeInputs(vix=D(1))
    monkeypatch.setattr(regime_inputs, "read_regime", fake)
    per = RegimePerList()
    got = [await per.read(u) for u in ("NIFTY", "NIFTY", "SENSEX")]
    assert seen == ["NIFTY", "SENSEX"] and got[0] is got[1]


# ---- task 26: the scenario twin through the SAME clients ------------------------------------------------------------
def _scenario(sid: str) -> scenario_mode.Scenario:
    data = scenario_mode.read(sid)
    at = datetime.datetime.fromisoformat(data["clock"]["ist"])
    return scenario_mode.Scenario(sid, data, at, None, {})  # type: ignore[arg-type] - no provider: not read here


@pytest.mark.asyncio
async def test_scenario_adj60_fires_t11b_and_t20b_and_t11c_answers(monkeypatch):
    scn = _scenario("ADJ-60")
    monkeypatch.setattr(scenario_mode, "current", lambda: scn)
    r = await regime_inputs.read_regime("NIFTY")
    assert (r.vix, r.vix_prev_close) == (D("16.8"), D("15.0"))
    assert r.available_margin is not None and r.vix_percentile is not None and r.adx > TRENDING, r
    sc = s.load("ADJ-60")
    _, m, _ = s.inputs(sc)
    st = state(dataclasses.replace(m, regime=r), sc=sc)
    got = answers(switched_on(sc, "T-11b", "T-11c", "T-20b"), st, "T-11b", "T-11c", "T-20b")
    assert isinstance(got["T-11b"], pe.Flag) and got["T-11b"].value == D(12), got["T-11b"]  # (16.8-15)/15 = 12%
    assert isinstance(got["T-20b"], pe.Flag) and got["T-20b"].value == r.adx
    assert not isinstance(got["T-11c"], pe.NotChecked) and got["T-11c"].value == r.vix_percentile


@pytest.mark.asyncio
async def test_scenario_without_vix_or_candles_answers_not_found(monkeypatch):
    scn = _scenario("ADJ-02")  # no market.vix, no market.daily: never a default
    monkeypatch.setattr(scenario_mode, "current", lambda: scn)
    r = await regime_inputs.read_regime("NIFTY")
    assert (r.vix, r.vix_prev_close, r.vix_percentile, r.adx) == (None,) * 4
