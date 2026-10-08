"""PostgreSQL store for broker sessions: the access token only as AES-GCM ciphertext (W-058, REQ-015 AC-7, AC-9).

Copy from: none - algochanakya stored the access token in plaintext (legacy-reuse row 9, REFERENCE: the flow only).

- ``store_session``: inside the caller's transaction (a SAVEPOINT, so any error stores nothing): ends the user's active
  session with end_reason 'replaced' (its ciphertext set to NULL in the same statement), inserts the new row (the guard
  stamps started_at and expected_expiry from the database clock), then sets its ciphertext once, bound by associated
  data to (user_ref, broker, the new id).
- ``access_token_for``: the decrypted token of the active session, or None. A row that does not decrypt (another key,
  a copied ciphertext, tampering, no ciphertext) is treated as no session: fail closed, logged by row id only.
- ``end_session``: ends the active session ('expired' or 'disconnected'), destroying the ciphertext; the row is kept.
- ``call_with_token``: runs one authenticated Kite call; a KiteTokenException marks the session EXPIRED.
Ending a session touches only public.broker_sessions: no strategy, account or entitlement row (REQ-015 AC-7).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy import text

from ofo.broker.session import BROKER_ZERODHA, EndReason
from ofo_app.broker_crypto import TokenCipher, TokenDecryptError, associated_data
from ofo_app.kite_client import KiteTokenException

log = logging.getLogger(__name__)
T = TypeVar("T")

_END_ACTIVE = text(
    "UPDATE public.broker_sessions SET ended_at = clock_timestamp(), end_reason = :reason, token_ciphertext = NULL "
    "WHERE user_ref = :user_ref AND broker = :broker AND ended_at IS NULL RETURNING id")
_INSERT = text(
    "INSERT INTO public.broker_sessions (user_ref, broker, key_id) VALUES (:user_ref, :broker, :key_id) RETURNING id")
_SET_TOKEN = text(
    "UPDATE public.broker_sessions SET token_ciphertext = :ciphertext "
    "WHERE id = :id AND ended_at IS NULL AND token_ciphertext IS NULL RETURNING id")
_ACTIVE = text(
    "SELECT id, key_id, token_ciphertext FROM public.broker_sessions "
    "WHERE user_ref = :user_ref AND broker = :broker AND ended_at IS NULL")


class BrokerStoreError(Exception):
    """Storing a session failed; carries only a code."""


async def store_session(conn: Any, user_ref: str, access_token: str, cipher: TokenCipher,
                        broker: str = BROKER_ZERODHA) -> int:
    if not user_ref or not access_token:
        raise BrokerStoreError("broker_store_invalid")
    async with conn.begin_nested():
        await conn.execute(_END_ACTIVE, {"reason": EndReason.REPLACED.value, "user_ref": user_ref, "broker": broker})
        session_id = (await conn.execute(_INSERT, {"user_ref": user_ref, "broker": broker,
                                                   "key_id": cipher.key_id})).scalar_one()
        blob = cipher.encrypt(access_token, associated_data(user_ref, broker, session_id))
        if (await conn.execute(_SET_TOKEN, {"ciphertext": blob, "id": session_id})).scalar_one_or_none() is None:
            raise BrokerStoreError("broker_store_failed")
    return session_id


async def access_token_for(conn: Any, user_ref: str, cipher: TokenCipher, broker: str = BROKER_ZERODHA) -> str | None:
    row = (await conn.execute(_ACTIVE, {"user_ref": user_ref, "broker": broker})).one_or_none()
    if row is None:
        return None
    session_id, key_id, blob = row
    if key_id != cipher.key_id or blob is None:
        log.warning("broker session %s is not readable with the current key; treated as no session", session_id)
        return None
    try:
        return cipher.decrypt(bytes(blob), associated_data(user_ref, broker, session_id))
    except TokenDecryptError:
        log.warning("broker session %s does not decrypt; treated as no session", session_id)
        return None


async def end_session(conn: Any, user_ref: str, reason: EndReason, broker: str = BROKER_ZERODHA) -> int | None:
    """Ends the active session, destroying its ciphertext in the same statement. Returns its id, or None."""
    if reason not in (EndReason.EXPIRED, EndReason.DISCONNECTED):
        raise ValueError("a session is replaced only by store_session")
    return (await conn.execute(_END_ACTIVE, {"reason": reason.value, "user_ref": user_ref,
                                             "broker": broker})).scalar_one_or_none()


async def call_with_token(conn: Any, user_ref: str, cipher: TokenCipher,
                          call: Callable[[str], Awaitable[T]], broker: str = BROKER_ZERODHA) -> T | None:
    """Runs ``call(access_token)``; None when there is no readable session. A Kite TokenException ends the session as
    EXPIRED (Kite's answer wins over the expected expiry) and is re-raised."""
    token = await access_token_for(conn, user_ref, cipher, broker)
    if token is None:
        return None
    try:
        return await call(token)
    except KiteTokenException:
        await end_session(conn, user_ref, EndReason.EXPIRED, broker)
        raise
