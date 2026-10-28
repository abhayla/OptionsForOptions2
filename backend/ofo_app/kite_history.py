"""Kite's one-minute candles over HTTP for the owner's own connection (W-062, ADR-066/067): internal use only.

``GET /instruments/historical/<token>/minute?from=..&to=..&oi=1`` behind the domain's ``MinuteCandleSource`` protocol.
The transport is injected (tests use the recorded bodies through a fake; no live call in tests). The access token is
sent only in the Authorization header and is never logged or put in an exception: only generic messages and the
exception class name leave this module. Answer states: 200 + success body -> candles; a non-200 status or a transport
error -> ``CandleFetchError`` (the caller keeps the day PROVISIONAL); a malformed body -> ``CandleError``.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Callable, Iterable  # noqa: UP035
from urllib.error import HTTPError, URLError

from ofo.broker import rate_limit
from ofo.broker.kite_endpoints import KITE_API_HOST
from ofo.broker.kite_http import open_url as kite_open_url
from ofo.history.bars import MinuteBar
from ofo.history.candles import parse_candles
from ofo.instruments.models import ZERODHA, ListedContract

log = logging.getLogger("ofo_app.kite_history")
KITE_API_URL = f"https://{KITE_API_HOST}"
Transport = Callable[[str, dict[str, str]], tuple[int, str]]


class CandleFetchError(RuntimeError):
    """The fetch failed (HTTP status or transport); carries no URL, header or token."""


def urllib_transport(url: str, headers: dict[str, str]) -> tuple[int, str]:
    try:
        with rate_limit.background(), kite_open_url(url, headers=headers, timeout=20) as response:  # allow-list first
            return response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, ""
    except rate_limit.KiteBusy:  # refused at once, nothing sent (REQ-118 AC-3): the day stays PROVISIONAL
        return 429, ""
    except (URLError, TimeoutError, OSError) as exc:
        raise CandleFetchError(f"transport error: {type(exc).__name__}") from None


class KiteHistory:
    def __init__(self, listed: Iterable[ListedContract], *, api_key: str, access_token: str,
                 transport: Transport = urllib_transport, base_url: str = KITE_API_URL) -> None:
        self._token_of = {f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}": str(lc.ref(ZERODHA).broker_token)  # noqa: E501
                          for lc in listed}
        self._index_ids = {i for i, lc in ((f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}", lc)
                                           for lc in listed) if lc.contract.is_index()}
        self._headers = {"X-Kite-Version": "3", "Authorization": f"token {api_key}:{access_token}"}  # never logged
        self._fetch = transport
        self._base = base_url

    def minute_candles(self, instrument_id: str, start: datetime.datetime, end: datetime.datetime) -> list[MinuteBar]:
        token = self._token_of.get(instrument_id)
        if token is None:
            raise CandleFetchError("unknown instrument")
        url = (f"{self._base}/instruments/historical/{token}/minute?from={start:%Y-%m-%d+%H:%M:%S}"
               f"&to={end:%Y-%m-%d+%H:%M:%S}&oi=1")
        status, text = self._fetch(url, self._headers)
        if status != 200:  # noqa: PLR2004
            log.warning("kite history HTTP status %s", status)
            raise CandleFetchError(f"http status {status}")
        return parse_candles(text, instrument_id, index=instrument_id in self._index_ids)


#: (listed contracts) -> the minute-candle reader for exactly those contracts on the owner's stored session
ReaderFactory = Callable[[Iterable[ListedContract]], Callable[[str, datetime.datetime, datetime.datetime],
                                                               list[MinuteBar]]]


async def owner_minute_reader(db: Any, *, transport: Transport | None = None) -> ReaderFactory | None:
    """GC-UI S5-1 (Strategy Chart): the owner's stored session (encrypted store, never the environment) -> a factory of
    ``KiteHistory.minute_candles``; None when there is no usable session.

    Called FIRST on the request's connection, before anything else touches it: ``access_token_for`` may commit (it
    ends a session past its expiry, GC-6 MAJOR-1) and refuses a connection already in a transaction, so reading first
    keeps ONE role connection per request (ADR-048) and its commit can never carry the caller's work. A store or
    configuration error is no session (logged by its code only, never the token), never a 500. The HTTP transport is
    looked up at call time (``urllib_transport``) so a test replaces only Kite's transport, nothing else."""
    from ofo_app.broker_config import BrokerConfigError, load_broker_config  # noqa: PLC0415 - loads only on use
    from ofo_app.broker_crypto import TokenCipher  # noqa: PLC0415
    from ofo_app.broker_token_store import BrokerStoreError, access_token_for  # noqa: PLC0415
    from ofo_app.live_market import OWNER_REF  # noqa: PLC0415

    try:
        config = load_broker_config()
        token = await access_token_for(db, OWNER_REF, TokenCipher(config.token_key))
    except BrokerStoreError as exc:  # carries only a code (e.g. token_read_needs_fresh_connection), never the token
        log.warning("strategy chart: no usable broker session (store refused: %s)", exc.args[0] if exc.args else "-")
        return None
    except BrokerConfigError:  # its message names missing settings only; not logged, the class name is enough
        log.warning("strategy chart: no usable broker session (broker configuration incomplete)")
        return None
    if token is None:
        return None
    send = transport if transport is not None else urllib_transport

    def reader(listed: Iterable[ListedContract]) -> Callable[[str, datetime.datetime, datetime.datetime],
                                                             list[MinuteBar]]:
        return KiteHistory(listed, api_key=config.api_key, access_token=token, transport=send).minute_candles
    return reader
