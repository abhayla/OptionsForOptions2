"""PostgreSQL store for small per-user settings: one JSON value per (user, key) (W-124; REQ-087 AC-3). Schema: 0022.

Generic on purpose: the margin preference (cluster B1) and the strategy preferences (A4) register their own key here. The
database fixes only the table shape; WHICH keys exist and what each value may be is this module's ``SETTINGS`` registry,
so an unknown key or a value off its list is refused before any SQL (fail closed), never stored.

- read: the stored value, else the key's DEFAULT (a user who never set one gets the default, REQ-087 AC-3: 10). A stored
  value that is no longer allowed (a list that changed) also reads as the default, never as an error.
- write: an upsert of ONE key for the session's user. The user comes from the caller (the session); this module has no
  user of its own and never hard-codes the owner (ADR-165 (8)). The caller commits.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from ofo_app.chain_push import DEFAULT_STRIKES_EACH_SIDE, STRIKES_CHOICES

UNKNOWN_KEY = "unknown_key"
BAD_VALUE = "bad_value"

#: REQ-087 AC-3: the chain's strikes either side of ATM.
CHAIN_STRIKES_EACH_SIDE = "chain.strikes_each_side"


class SettingError(ValueError):
    """A key that is not registered, or a value its key does not allow. ``code`` is UNKNOWN_KEY or BAD_VALUE."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SettingSpec:
    default: Any
    allowed: Callable[[Any], bool]


def _is_choice(value: Any) -> bool:
    return type(value) is int and value in STRIKES_CHOICES  # a bool is not an int choice


SETTINGS: dict[str, SettingSpec] = {CHAIN_STRIKES_EACH_SIDE: SettingSpec(DEFAULT_STRIKES_EACH_SIDE, _is_choice)}

_SELECT = text("SELECT value::text AS value_text FROM public.user_settings WHERE user_ref = :user_ref AND key = :key")
_UPSERT = text("INSERT INTO public.user_settings (user_ref, key, value) VALUES (:user_ref, :key, CAST(:value AS JSONB)) "
               "ON CONFLICT (user_ref, key) DO UPDATE SET value = EXCLUDED.value")


def _spec(key: str) -> SettingSpec:
    spec = SETTINGS.get(key)
    if spec is None:
        raise SettingError(UNKNOWN_KEY, "no such setting")
    return spec


def _user(user_ref: str) -> str:
    if not isinstance(user_ref, str) or not user_ref:
        raise SettingError(BAD_VALUE, "a setting belongs to a user")
    return user_ref


async def read(conn: Any, user_ref: str, key: str) -> tuple[Any, bool]:
    """(value, is_default). Never raises for a missing or no-longer-allowed stored value: that is the default."""
    spec, user = _spec(key), _user(user_ref)
    row = (await conn.execute(_SELECT, {"user_ref": user, "key": key})).one_or_none()
    if row is not None:
        value = json.loads(row.value_text)
        if spec.allowed(value):
            return value, False
    return spec.default, True


async def write(conn: Any, user_ref: str, key: str, value: Any) -> Any:
    """Stores ``value`` for the user's ``key`` (one row, updated in place). The caller commits."""
    spec, user = _spec(key), _user(user_ref)
    if not spec.allowed(value):
        raise SettingError(BAD_VALUE, "that value is not allowed for this setting")
    await conn.execute(_UPSERT, {"user_ref": user, "key": key, "value": json.dumps(value)})
    return value
