"""The values the response door must never write (GC-MU step 2, issue #517, REQ-048 AC-5).

The reply inventory closes the field NAMES; the leak path left is a VALUE: an `Identifier` allows 64 letters and
digits, so a 32-character Kite access token fits any reviewed field. Every credential value the server holds is
registered here at the one place it exists in plain text - the token cipher (every access token is encrypted on store
and decrypted on read there) and the broker config (the API secret and the token key) - and the door
(``api_models._encode`` for every body, ``errors._mint_headers`` for every header) refuses a response that contains
one. The PUBLIC api_key is not registered: the basket form carries it to Kite by design (ADR-054).

Known limits, stated on purpose: an encoded or transformed value (base64, reversed, split across fields) is not seen;
values shorter than ``MIN_LENGTH`` are not registered (they would match ordinary text).
"""
from __future__ import annotations

import threading

#: shorter values would collide with ordinary reply text; every real credential is far longer (a Kite token is 32)
MIN_LENGTH = 12
_VALUES: set[bytes] = set()
_LOCK = threading.Lock()


def register(value: object) -> None:
    """Remember a credential value the door must never write. Non-strings and short values are ignored."""
    if type(value) is str and len(value) >= MIN_LENGTH:
        with _LOCK:
            _VALUES.add(value.encode("utf-8"))


def contains_secret(data: bytes) -> bool:
    """True when ``data`` holds any registered value (exact bytes; JSON escaping of these characters is identity)."""
    with _LOCK:
        values = tuple(_VALUES)
    return any(value in data for value in values)


__all__ = ["MIN_LENGTH", "contains_secret", "register"]
