"""AES-256-GCM for the broker access token at rest (W-058, REQ-015 AC-9, core-invariants section 4).

Stored value = 12-byte random nonce || ciphertext-with-tag. Associated data = ``user_ref|broker|session id``, so a
ciphertext copied to another row (another user, broker or session) fails to decrypt. ``key_id`` names the key version
(a one-way fingerprint, never the key); a row written under another key is treated as no session.

Copy from: algochanakya app/utils/encryption.py (REFERENCE only: it used Fernet with a key derived from JWT_SECRET; here
the key is dedicated and the cipher is bound to its row).
"""

from __future__ import annotations

import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12


class TokenDecryptError(Exception):
    """The stored ciphertext does not decrypt under this key and row (wrong key, wrong row, or tampered)."""


def associated_data(user_ref: str, broker: str, session_id: int) -> bytes:
    return f"{user_ref}|{broker}|{int(session_id)}".encode("utf-8")


class TokenCipher:
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("the token key must be 32 bytes (AES-256)")
        self._aead = AESGCM(key)
        self.key_id = "k-" + hashlib.sha256(b"ofo broker token key id|" + key).hexdigest()[:16]

    def __repr__(self) -> str:
        return f"TokenCipher(key_id={self.key_id!r})"

    def encrypt(self, token: str, aad: bytes) -> bytes:
        if not token:
            raise ValueError("an empty token is never stored")
        nonce = os.urandom(NONCE_BYTES)
        return nonce + self._aead.encrypt(nonce, token.encode("utf-8"), aad)

    def decrypt(self, blob: bytes, aad: bytes) -> str:
        if blob is None or len(blob) <= NONCE_BYTES:
            raise TokenDecryptError("no ciphertext")
        try:
            return self._aead.decrypt(bytes(blob[:NONCE_BYTES]), bytes(blob[NONCE_BYTES:]), aad).decode("utf-8")
        except (InvalidTag, UnicodeDecodeError):
            raise TokenDecryptError("ciphertext does not decrypt for this row") from None
