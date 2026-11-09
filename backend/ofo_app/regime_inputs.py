"""The market-wide inputs of ADR-280's new iron condor triggers (GC-ICTRACK task 14b, ADR-277): Zerodha's available
margin (T-15), India VIX and its previous close (T-11b), the VIX percentile over 250 sessions (T-11c, NIFTY only) and
ADX(14) on the underlying's daily candles (T-20b).

ONE reader for both modes (ADR-275): live reads go through the owner's own Kite clients (``live_market``); scenario
mode passes the SAME clients over the scenario's transport (``scenario_mode.Scenario``), so test data passes the same
doors. Answer states, per input: stated -> the value; no session / not in the reply / empty -> None; failed (a Kite,
margin, candle or maths error) -> None, logged by error class only (never a token or a body). One failing input never
blanks the others. None means "not checked", never a pass and never test data in place of live data (ADR-279 (4)).
"""
from __future__ import annotations

import asyncio
import functools
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from ofo.history.candles import CandleError
from ofo.instruments.models import QUOTE_ONLY_INDEXES, VIX_NAME
from ofo.marketdata import regime

from ofo_app import kite_period_reads
from ofo_app.daily_candles import DailyCandles
from ofo_app.kite_history import CandleFetchError, KiteHistory
from ofo_app.kite_history import urllib_transport as history_transport
from ofo_app.kite_margin import KiteMargin, KiteMarginError
from ofo_app.kite_reads import KiteReadError, KiteReads

log = logging.getLogger("ofo_app.regime_inputs")

#: Kite instrument tokens of the index day candles (Kite's instrument list; no catalogue row carries them)
INDEX_TOKENS: Final = {"NIFTY": "256265", "SENSEX": "265"}
VIX_TOKEN: Final = str(QUOTE_ONLY_INDEXES[VIX_NAME])
_PERCENTILE_INDEX: Final = "NIFTY"  # India VIX is a NIFTY index (ADR-277 (2)); SENSEX has none
_READ_ERRORS: Final = (KiteReadError, KiteMarginError, CandleFetchError, CandleError, ValueError, ArithmeticError)


@dataclass(frozen=True)
class RegimeInputs:
    available_margin: Decimal | None = None
    vix: Decimal | None = None
    vix_prev_close: Decimal | None = None
    vix_percentile: Decimal | None = None
    adx: Decimal | None = None


@dataclass(frozen=True)
class Clients:
    """The three Kite clients of one read: quotes, margin, day candles (any None = that source is not available)."""

    reads: Any = None
    margin: Any = None
    history: KiteHistory | None = None


class _LiveHistory:
    """The live day-candle fetch for the ONE process-wide ``DailyCandles``: the owner's current history client is set
    before each read, so a new login is picked up while the once-a-day cache stays."""

    history: KiteHistory | None = None

    def __call__(self, token: str, start: Any, end: Any) -> list:
        if self.history is None:
            raise CandleFetchError("no session")
        return self.history.day_candles(token, start, end)


_LIVE_FETCH = _LiveHistory()
_LIVE_DAILY = DailyCandles(_LIVE_FETCH)  # one per process: at most one read per index per IST day


def _attempt(what: str, read: Any) -> Any:
    try:
        return read()
    except _READ_ERRORS as exc:
        log.warning("regime input %s not read: %s", what, type(exc).__name__)
        return None


def read_with(clients: Clients, underlying: str, daily: DailyCandles) -> RegimeInputs:
    """Every input from ``clients`` (blocking; run in a worker thread). See the module docstring for answer states."""
    reads, margin = clients.reads, clients.margin
    funds = None if reads is None or margin is None else _attempt(
        "available_margin", lambda: kite_period_reads.available_margin(reads, margin).value)
    vix = prev = None
    if reads is not None:
        pair = _attempt("vix", lambda: kite_period_reads.india_vix(reads).value)
        vix, prev = pair if pair is not None else (None, None)
    pct = adx = None
    if clients.history is not None:
        if underlying == _PERCENTILE_INDEX and vix is not None:
            pct = _attempt("vix_percentile",
                           lambda: regime.vix_percentile(vix, [c.close for c in daily.last(VIX_TOKEN)]))
        token = INDEX_TOKENS.get(underlying)
        if token is not None:
            adx = _attempt("adx", lambda: regime.adx(_bars(daily.last(token))))
    return RegimeInputs(funds, vix, prev, pct, adx)


def _bars(candles: list) -> list[tuple[Decimal, Decimal, Decimal]]:
    if any(c.high is None or c.low is None for c in candles):
        raise ValueError("a day candle has no range")
    return [(c.high, c.low, c.close) for c in candles]


async def _live_clients() -> Clients:
    from ofo_app import live_market  # noqa: PLC0415 - the Kite composition root
    owner = await live_market.owner_kite_reads()
    if owner is None:
        return Clients()
    history = await live_market.owner_client(
        lambda key, token: KiteHistory((), api_key=key, access_token=token, transport=history_transport))
    return Clients(owner[1], await live_market.owner_margin_client(), history)


async def read_regime(underlying: str) -> RegimeInputs:
    """ADR-280's five market-wide inputs for ``underlying`` ("NIFTY" / "SENSEX"), live or from the running scenario
    through the same clients. Never raises for a read failure: that input is None."""
    from ofo_app import scenario_mode  # noqa: PLC0415 - the process mode, read at call time
    scn = scenario_mode.current()
    if scn is not None:
        return await asyncio.to_thread(in_scenario, scn, underlying)
    clients = await _live_clients()
    _LIVE_FETCH.history = clients.history
    if clients.reads is None and clients.history is None:
        return RegimeInputs()
    return await asyncio.to_thread(read_with, clients, underlying, _LIVE_DAILY)


def in_scenario(scn: Any, underlying: str) -> RegimeInputs:
    """Scenario mode: the same clients over ``scn``'s transport (``Scenario.regime_clients``), candles on the
    scenario's own day (a fresh ``DailyCandles``: never the live process cache)."""
    keys = {INDEX_TOKENS.get(scn.data["underlying"]): "underlying", VIX_TOKEN: "vix"}
    fake = {"api_key": "scenario", "access_token": "scenario"}  # no real token: the transport never reaches Kite
    history = KiteHistory((), **fake, transport=functools.partial(scn.day_candles_transport, keys=keys))
    clients = Clients(KiteReads(**fake, transport=scn.vix_transport),
                      KiteMargin(**fake, transport=scn.margin_transport),
                      history)
    return read_with(clients, underlying, DailyCandles(history.day_candles, clock=scn.clock))


class RegimePerList:
    """One ``read_regime`` per underlying for one pass (the worker's list): two strategies on NIFTY share one read."""

    def __init__(self) -> None:
        self._by: dict[str, RegimeInputs] = {}

    async def read(self, underlying: str) -> RegimeInputs:
        if underlying not in self._by:
            self._by[underlying] = await read_regime(underlying)
        return self._by[underlying]


__all__ = ["INDEX_TOKENS", "VIX_TOKEN", "Clients", "RegimeInputs", "RegimePerList", "read_regime", "read_with"]
