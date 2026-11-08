"""The values the response door must never write (GC-MU step 2, issue #517, REQ-048 AC-5).

The reply inventory closes the field NAMES; the leak path left is a VALUE: an `Identifier` allows 64 letters and
digits, so a 32-character Kite access token fits any reviewed field. Every credential value the server holds is
registered here at the one place it exists in plain text - the token cipher (every access token is encrypted on store
and decrypted on read there, including a token read from the store after a restart) and the broker config (the API
secret and the token key) - and the door (``api_models._encode`` for every body, ``errors._mint_headers`` for every
header) refuses a response that contains one. The PUBLIC api_key is not registered: the basket form carries it to Kite
by design (ADR-054).

Bound (verifier round 1, minor 2): values are kept per OWNER SLOT, one current value per slot. A token's slot is its
``user_ref|broker`` (the associated data without the session id), so a user's new token REPLACES the old one; a config
value's slot is its variable name. The registry therefore holds at most (users x brokers) + config values, never a
history: 1,000 users on one broker is about 1,000 values, and each reply scans only those.

Known limits, stated on purpose: an encoded or transformed value (base64, reversed, split across fields) is not seen;
values shorter than ``MIN_LENGTH`` are not registered (they would match ordinary text); a token whose session has ended
stays registered until that user's next token replaces it (still bounded by the slot count).
"""
from __future__ import annotations

import threading

#: shorter values would collide with ordinary reply text; every real credential is far longer (a Kite token is 32)
MIN_LENGTH = 12
_BY_SLOT: dict[str, bytes] = {}
_LOCK = threading.Lock()


def register(value: object, slot: str) -> None:
    """Make ``value`` the current credential of ``slot`` (replacing that slot's previous value). Non-strings and short
    values clear nothing and are ignored."""
    if type(value) is str and len(value) >= MIN_LENGTH and type(slot) is str and slot:
        with _LOCK:
            _BY_SLOT[slot] = value.encode("utf-8")


def token_slot(aad: bytes) -> str:
    """The owner slot of a token from its associated data ``user_ref|broker|session_id``: the session id dropped."""
    return "token:" + aad.rpartition(b"|")[0].decode("utf-8", "replace")


def contains_secret(data: bytes) -> bool:
    """True when ``data`` holds any registered value (exact bytes; JSON escaping of these characters is identity)."""
    with _LOCK:
        values = tuple(_BY_SLOT.values())
    return any(value in data for value in values)


def registered_values() -> frozenset[bytes]:
    with _LOCK:
        return frozenset(_BY_SLOT.values())


__all__ = ["MIN_LENGTH", "contains_secret", "register", "registered_values", "token_slot"]
