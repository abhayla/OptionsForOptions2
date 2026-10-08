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
import urllib.error
import urllib.request
from typing import Callable, Iterable

from ofo.history.bars import MinuteBar
from ofo.history.candles import parse_candles
from ofo.instruments.models import ZERODHA, ListedContract

log = logging.getLogger("ofo_app.kite_history")
KITE_API_URL = "https://api.kite.trade"
Transport = Callable[[str, dict[str, str]], tuple[int, str]]


class CandleFetchError(RuntimeError):
    """The fetch failed (HTTP status or transport); carries no URL, header or token."""


def urllib_transport(url: str, headers: dict[str, str]) -> tuple[int, str]:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed https host
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CandleFetchError(f"transport error: {type(exc).__name__}") from None


class KiteHistory:
    def __init__(self, listed: Iterable[ListedContract], *, api_key: str, access_token: str,
                 transport: Transport = urllib_transport, base_url: str = KITE_API_URL) -> None:
        self._token_of = {f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}": str(lc.ref(ZERODHA).broker_token)
                          for lc in listed}
        self._index_ids = {i for i, lc in ((f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}", lc)
                                           for lc in listed) if lc.contract.is_index()}
        self._headers = {"X-Kite-Version": "3", "Authorization": f"token {api_key}:{access_token}"}  # never logged
        self._transport = transport
        self._base = base_url

    def minute_candles(self, instrument_id: str, start: datetime.datetime, end: datetime.datetime) -> list[MinuteBar]:
        token = self._token_of.get(instrument_id)
        if token is None:
            raise CandleFetchError("unknown instrument")
        url = (f"{self._base}/instruments/historical/{token}/minute?from={start:%Y-%m-%d+%H:%M:%S}"
               f"&to={end:%Y-%m-%d+%H:%M:%S}&oi=1")
        status, text = self._transport(url, self._headers)
        if status != 200:
            log.warning("kite history HTTP status %s", status)
            raise CandleFetchError(f"http status {status}")
        return parse_candles(text, instrument_id, index=instrument_id in self._index_ids)
