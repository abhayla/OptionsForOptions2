"""Broker (Kite Connect) settings and the dedicated token key (W-058, REQ-015 AC-9).

Kept apart from ``ofo_app.config.Settings`` so building the app needs no database URL. The broker routes refuse to
start without a valid configuration: ``load_broker_config`` raises ``BrokerConfigError`` and ``create_app`` fails.

The token key is its own secret (``BROKER_TOKEN_KEY``, 32 bytes, URL-safe base64), never derived from another one: the
legacy derived its Fernet key from JWT_SECRET (algochanakya app/utils/encryption.py, REFERENCE). A key that is the hash
of, or contained in, the Kite api secret is refused.

Q210 is open (whether each user brings their own Kite app): the api key and secret come from this ONE source; V1 uses
the platform's configured app (ADR-051).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass
from urllib.parse import urlsplit

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

TOKEN_KEY_BYTES = 32  # AES-256


class BrokerConfigError(RuntimeError):
    """The broker configuration is missing or invalid; the message never contains a secret value."""


class BrokerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    KITE_API_KEY: str = ""
    KITE_API_SECRET: SecretStr = SecretStr("")
    KITE_REDIRECT_URL: str = ""
    #: The one Zerodha user id whose login may connect (V1 single user, ADR-051); a login by anyone else is refused.
    KITE_EXPECTED_USER_ID: str = ""
    BROKER_TOKEN_KEY: SecretStr = SecretStr("")


@dataclass(frozen=True)
class BrokerConfig:
    api_key: str
    api_secret: SecretStr
    redirect_url: str
    callback_path: str
    expected_user_id: str
    token_key: bytes

    def __repr__(self) -> str:  # never print the key bytes
        return f"BrokerConfig(api_key={self.api_key!r}, callback_path={self.callback_path!r})"


def decode_token_key(value: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(value.encode("ascii"))
    except (binascii.Error, ValueError, UnicodeEncodeError):
        raise BrokerConfigError("BROKER_TOKEN_KEY is not URL-safe base64") from None
    if len(raw) != TOKEN_KEY_BYTES:
        raise BrokerConfigError(f"BROKER_TOKEN_KEY must decode to {TOKEN_KEY_BYTES} bytes")
    return raw


def _derived_from(key: bytes, secret: str) -> bool:
    if not secret:
        return False
    s = secret.encode("utf-8")
    return key == hashlib.sha256(s).digest() or key in s


def load_broker_config(settings: BrokerSettings | None = None) -> BrokerConfig:
    s = settings if settings is not None else BrokerSettings()
    missing = [name for name, value in (("KITE_API_KEY", s.KITE_API_KEY),
                                        ("KITE_API_SECRET", s.KITE_API_SECRET.get_secret_value()),
                                        ("KITE_REDIRECT_URL", s.KITE_REDIRECT_URL),
                                        ("KITE_EXPECTED_USER_ID", s.KITE_EXPECTED_USER_ID),
                                        ("BROKER_TOKEN_KEY", s.BROKER_TOKEN_KEY.get_secret_value())) if not value]
    if missing:
        raise BrokerConfigError("broker routes refuse to start: missing " + ", ".join(missing))
    key = decode_token_key(s.BROKER_TOKEN_KEY.get_secret_value())
    if _derived_from(key, s.KITE_API_SECRET.get_secret_value()):
        raise BrokerConfigError("BROKER_TOKEN_KEY must be its own secret, not derived from KITE_API_SECRET")
    parts = urlsplit(s.KITE_REDIRECT_URL)
    if parts.scheme not in ("http", "https") or not parts.netloc or not parts.path.startswith("/") or parts.query:
        raise BrokerConfigError("KITE_REDIRECT_URL must be an absolute http(s) URL with a path and no query")
    return BrokerConfig(api_key=s.KITE_API_KEY, api_secret=s.KITE_API_SECRET, redirect_url=s.KITE_REDIRECT_URL,
                        callback_path=parts.path, expected_user_id=s.KITE_EXPECTED_USER_ID, token_key=key)
