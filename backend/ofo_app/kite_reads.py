"""Zerodha's orders, trades and positions over HTTP for the owner's own connection (W-093, REQ-073 AC-3, ADR-054).

Four reads, nothing else: ``GET /orders``, ``GET /trades``, ``GET /portfolio/positions``, ``GET /quote``
(W-099) (the module's entry in
``ALLOWED_CALLS``). Every request goes through ``check_call`` first, so a method or path outside the allow-list is
refused BEFORE the transport is called, and the urllib door checks it again. No call here can place, change or cancel
an order (REQ-073 AC-4).

Each fetch returns the reply's ``data`` parsed with ``parse_float=Decimal`` (ADR-008), ready for
``ofo_app.kite_replies``. The transport is injected; tests replay the recorded 2026-10-16 reply files. The access token
travels only in the Authorization header and is never logged or put in an exception: an error carries a code.

Codes: kite_read_token (403 / TokenException) · kite_read_busy (429) · kite_read_refused (other 4xx, door refused)
· kite_read_unavailable (5xx, network, junk body) · kite_read_bad_reply (not ``status: success``, or ``data`` of the
wrong type).
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from decimal import Decimal
from typing import Final

from ofo.broker.kite_http import QUOTE_INSTRUMENT, KiteCallRefused, check_call
from ofo_app.kite_margin import KITE_API_URL, KiteMarginError, Transport, error_type, kite_headers, urllib_transport

log = logging.getLogger("ofo_app.kite_reads")
ORDERS_PATH: Final = "/orders"
TRADES_PATH: Final = "/trades"
POSITIONS_PATH: Final = "/portfolio/positions"
QUOTE_PATH: Final = "/quote"
QUOTE_LIMIT: Final = 500  # Kite's cap on instruments per quote call
_INSTRUMENT: Final = re.compile(QUOTE_INSTRUMENT, re.ASCII)
_PLAIN_NUMBER: Final = re.compile(r"[0-9]+(\.[0-9]+)?", re.ASCII)
_OK: Final = 200
_BUSY: Final = 429
_DENIED: Final = 403
_SERVER_ERROR: Final = 500


class KiteReadError(Exception):
    """A read failed. Carries only a code; never the token, a header, a URL or the response body."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _rows(data: object) -> list[object]:
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise KiteReadError("kite_read_bad_reply")
    return data


def _limit(value: object) -> Decimal | None:
    """A circuit limit as an exact Decimal, or None. JSON numbers arrive as int / Decimal (parse_float=Decimal); the
    recorders' plain numeric strings are read exactly. A float, bool, NaN, text or anything else is not a limit."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        return Decimal(value) if _PLAIN_NUMBER.fullmatch(value) else None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, Decimal) and value.is_finite():
        return value
    return None


def _band(quote: object) -> tuple[Decimal, Decimal] | None:
    if not isinstance(quote, dict):
        return None
    lower, upper = _limit(quote.get("lower_circuit_limit")), _limit(quote.get("upper_circuit_limit"))
    if lower is None or upper is None or lower <= 0 or upper <= 0 or lower > upper:
        return None
    return lower, upper


class KiteReads:
    def __init__(self, *, api_key: str, access_token: str, transport: Transport = urllib_transport,
                 base_url: str = KITE_API_URL) -> None:
        self._headers = kite_headers(api_key, access_token)  # never logged
        self._call = transport
        self._base = base_url

    def __repr__(self) -> str:
        return "KiteReads()"

    def _data(self, method: str, path: str) -> object:
        url = self._base + path
        try:
            check_call(method, url)  # the allow-list, before anything is sent
        except KiteCallRefused:
            raise KiteReadError("kite_read_refused") from None
        try:
            status, text = self._call(method, url, dict(self._headers), None)
        except KiteCallRefused:
            raise KiteReadError("kite_read_refused") from None
        except KiteMarginError as exc:  # urllib_transport's own codes; only the code is read
            raise KiteReadError("kite_read_refused" if exc.code == "kite_margin_refused"
                                else "kite_read_unavailable") from None
        except Exception:  # noqa: BLE001 - whatever the transport raises: "not confirmed"
            raise KiteReadError("kite_read_unavailable") from None
        if status != _OK:
            log.warning("kite read HTTP status %s", status)
            if status == _DENIED or error_type(text) == "TokenException":
                raise KiteReadError("kite_read_token")
            if status == _BUSY:
                raise KiteReadError("kite_read_busy")
            raise KiteReadError("kite_read_unavailable" if status >= _SERVER_ERROR else "kite_read_refused")
        try:
            reply = json.loads(text, parse_float=Decimal)
        except (ValueError, RecursionError):  # deeply nested JSON raises RecursionError, not ValueError
            raise KiteReadError("kite_read_unavailable") from None
        if not isinstance(reply, dict) or reply.get("status") != "success" or "data" not in reply:
            raise KiteReadError("kite_read_bad_reply")
        return reply["data"]

    def fetch_orders(self) -> list[object]:
        """``GET /orders``: today's orders, as a list of rows with exact Decimal money."""
        return _rows(self._data("GET", ORDERS_PATH))

    def fetch_trades(self) -> list[object]:
        """``GET /trades``: today's trades (fills), as a list of rows with exact Decimal money."""
        return _rows(self._data("GET", TRADES_PATH))

    def fetch_positions(self) -> dict[str, list[object]]:
        """``GET /portfolio/positions``: ``{"net": [...], "day": [...]}`` with exact Decimal money."""
        data = self._data("GET", POSITIONS_PATH)
        if not isinstance(data, dict):
            raise KiteReadError("kite_read_bad_reply")
        return {**data, "net": _rows(data.get("net")), "day": _rows(data.get("day"))}

    def fetch_circuit_bands(self, instruments: Sequence[str]) -> dict[str, tuple[Decimal, Decimal]]:
        """``GET /quote?i=...``: ``{EXCHANGE:SYMBOL: (lower, upper)}`` circuit limits, exact Decimal (ADR-080).

        Only the instruments asked for, only those whose band is present, numeric, positive and ordered; any other is
        ABSENT (the gate then blocks an ENTRY leg as band-unknown), never a guessed band. A whole-reply failure raises
        ``KiteReadError``."""
        asked = list(dict.fromkeys(instruments))
        if len(asked) > QUOTE_LIMIT or not all(isinstance(i, str) and _INSTRUMENT.fullmatch(i) for i in asked):
            raise KiteReadError("kite_read_refused")
        if not asked:
            return {}
        data = self._data("GET", QUOTE_PATH + "?" + "&".join(f"i={i}" for i in asked))
        if not isinstance(data, dict):
            raise KiteReadError("kite_read_bad_reply")
        bands = {i: _band(data.get(i)) for i in asked}
        return {i: b for i, b in bands.items() if b is not None}
