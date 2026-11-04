"""Per-user adjustment preferences: the value for a user at a time, the user's own history, change and reset
(REQ-168 AC-2, AC-3, AC-5; ADR-222 (5), (7), (9)). Table: migration 0033.

Spec basis: ADR-222 (7) "A user who has not changed a value follows the admin default in force (an admin change moves
them); a user who changed it keeps their own"; REQ-168 AC-2 "changes it within the allowed range (refused with the
reason otherwise) or resets it to follow the default. History of the user's own changes is kept"; AC-3 "every read and
write is keyed by the user".

The value of key K for user U at time T (each answer state has a test in tests_app/test_user_preferences.py):
- U's newest row for K with effective_from <= T holds a value: that value ("yours");
- that newest row is a reset (value NULL), or U has no row: the admin default in force at T ("default"), read with
  ``settings_store.settings_in_force`` (the admin's newest "Adjustment defaults" row, else the registry default);
- a stored value (the user's or the admin's) the registry now refuses (its range was narrowed): PreferencesError /
  SettingsError - fail closed, never a silent fall back.

Every query is keyed by ``user_ref``: no function here reads or writes without it. Writes take effect at the database
clock now; a reset is a new row with value NULL, never a delete. Transaction control stays with the caller.

Known bypasses (out of the threat model): a database superuser or the table owner can disable or drop the guard
trigger and edit rows; until sign-in exists every caller is the one owner (``routes.adjustment_preferences.require_user``).
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from ofo import settings as registry_mod
from ofo.adjustment import alert_presets
from ofo.adjustment import preferences as prefs_mod
from ofo.settings import SettingRefused, layers
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from ofo_app import settings_store

MAX_NOTE = 500
CAP_ABOVE_ADMIN = "preference_above_admin_cap"
Session = AsyncSession | AsyncConnection

_IN_FORCE = text(
    """
    SELECT DISTINCT ON (key) key, value, effective_from
    FROM public.user_adjustment_preferences WHERE user_ref = :user AND effective_from <= :at
    ORDER BY key, effective_from DESC
    """
)
_HISTORY = text(
    "SELECT key, value, effective_from, note FROM public.user_adjustment_preferences WHERE user_ref = :user "
    "ORDER BY key, effective_from DESC"
)
_INSERT = text(
    "INSERT INTO public.user_adjustment_preferences (user_ref, key, value, effective_from, note) "
    "VALUES (:user, :key, :value, :effective_from, :note)"
)


class PreferencesError(Exception):
    """The stored preferences cannot answer (fail closed)."""


@dataclass(frozen=True)
class StoredPreference:
    key: str
    value: Decimal | None  # None = a reset: follow the admin default
    effective_from: datetime.datetime
    note: str = ""


@dataclass(frozen=True)
class Answer:
    key: str
    value: Decimal
    source: Literal["yours", "default"]
    admin_default: Decimal
    since: datetime.datetime | None  # when the user's own value took effect; None for "default"


def preference_keys() -> tuple[str, ...]:
    """The closed list: the registry keys under the adjustments prefix (the admin's "Adjustment defaults" group; the
    list must equal the pure layer's KEYS), then the user-changeable alert-discipline values per trading style
    (REQ-170 AC-6: confirm candle, cool-down, quiet time, a lower daily cap; the re-arm margin stays admin-only)."""
    reg = registry_mod.registry()
    keys = tuple(k for k in reg if k.startswith(prefs_mod.PREFIX))
    if set(keys) != set(prefs_mod.KEYS):
        raise PreferencesError(f"the registry's adjustment defaults {sorted(keys)} differ from the preferences "
                               f"{sorted(prefs_mod.KEYS)}")
    missing = [k for k in alert_presets.USER_KEYS if k not in reg]
    if missing:
        raise PreferencesError(f"the registry has no alert-discipline entries {missing}")
    extra = [k for k in layers.THREE_LAYER_KEYS if k not in reg]
    if extra:
        raise PreferencesError(f"the registry has no three-layer entries {extra}")
    # ADR-245: the three-layer settings outside the adjustments group (GC "Your adjustment settings" step 1: the carry
    # gap) are user-changeable too; the admin's value stays their default
    return keys + alert_presets.USER_KEYS + tuple(k for k in layers.THREE_LAYER_KEYS if k not in keys)


def preference(key: object) -> registry_mod.Setting:
    if not isinstance(key, str) or key not in preference_keys():
        raise SettingRefused("setting_unknown", f"There is no adjustment preference named {key!r}.")
    return registry_mod.registry()[key]


def _user(user_ref: object) -> str:
    if not isinstance(user_ref, str) or not user_ref.strip():
        raise PreferencesError("a preference read or write needs the user it belongs to")
    return user_ref


async def answers(session: Session, user_ref: str, at: datetime.datetime | None = None) -> dict[str, Answer]:
    """Every preference of ``user_ref`` in force at ``at`` (default: the database clock), with its source."""
    user = _user(user_ref)
    if at is None:
        at = await settings_store.database_now(session)
    admin = await settings_store.settings_in_force(session, at)  # fail closed on a refused admin value
    own: dict[str, StoredPreference] = {}
    known = registry_mod.registry()
    closed = set(preference_keys())
    for r in (await session.execute(_IN_FORCE, {"user": user, "at": at})).all():
        if r.key not in closed:
            continue  # a retired key: never read
        if r.value is not None:
            if not isinstance(r.value, Decimal):
                raise PreferencesError(f"preference {r.key} did not come back as an exact Decimal")
            try:
                registry_mod.check_value(known[r.key], r.value)
            except SettingRefused as exc:
                raise PreferencesError(
                    f"stored preference {r.key} = {r.value} is refused by the registry: {exc.reason}") from None
        own[r.key] = StoredPreference(r.key, r.value, r.effective_from)
    out: dict[str, Answer] = {}
    for key in preference_keys():
        mine = own.get(key)
        if mine is not None and mine.value is not None:
            out[key] = Answer(key, mine.value, "yours", admin[key], mine.effective_from)
        else:
            out[key] = Answer(key, admin[key], "default", admin[key], None)
    return out


class UserValues(dict):
    """key -> the value in force for a user (the merged mapping every existing reader takes), that also carries the
    user's OWN values (``own``: the keys whose source is "yours"), the user layer of ADR-245's resolver
    (``ofo.settings.layers``). One read gives both, never a second query."""

    def __init__(self, found: Mapping[str, Answer]) -> None:
        super().__init__({k: a.value for k, a in found.items()})
        self.own: dict[str, Decimal] = {k: a.value for k, a in found.items() if a.source == "yours"}


async def values_for(session: Session, user_ref: str, at: datetime.datetime | None = None) -> UserValues:
    """key -> the value in force for ``user_ref`` (the mapping ``ofo.adjustment.preferences.from_values`` takes), with
    the user's own values on ``.own``."""
    return UserValues(await answers(session, user_ref, at))


async def history(session: Session, user_ref: str) -> dict[str, list[StoredPreference]]:
    """The user's own rows per preference, newest first (a reset is a row with value None)."""
    user = _user(user_ref)
    out: dict[str, list[StoredPreference]] = {k: [] for k in preference_keys()}
    for r in (await session.execute(_HISTORY, {"user": user})).all():
        if r.key in out:
            out[r.key].append(StoredPreference(r.key, r.value, r.effective_from, r.note))
    return out


async def _insert(session: Session, user: str, key: str, value: Decimal | None, note: str) -> StoredPreference:
    if not isinstance(note, str) or len(note) > MAX_NOTE:
        raise SettingRefused("setting_note_too_long", f"The note must be at most {MAX_NOTE} characters.")
    now = await settings_store.database_now(session)
    async with session.begin_nested():
        try:
            await session.execute(_INSERT, {"user": user, "key": key, "value": value, "effective_from": now,
                                            "note": note})
        except IntegrityError:
            raise SettingRefused("setting_same_time",
                                 "Another change of this preference took effect at the same instant; try again.") from None
    return StoredPreference(key, value, now, note)


async def set_preference(session: Session, user_ref: str, key: str, value: str, note: str = "") -> StoredPreference:
    """The user's own value from now: a known preference key and a decimal STRING within the registry entry's range
    (SettingRefused with the readable reason otherwise)."""
    user = _user(user_ref)
    preference(key)
    parsed = registry_mod.validate(key, value)
    if key in alert_presets.CAP_KEYS:
        ceiling = await cap_ceiling(session, key)
        if parsed > ceiling:  # REQ-170 AC-6: the user may lower the daily cap, never raise it
            raise SettingRefused(CAP_ABOVE_ADMIN, f"The daily limit can be at most {registry_mod.plain(ceiling)}.")
    return await _insert(session, user, key, parsed, note)


async def cap_ceiling(session: Session, key: str) -> Decimal:
    """The admin's daily-cap ceiling in force now for a cap key (the refusal's limit, read back for its words)."""
    return (await settings_store.settings_in_force(session, await settings_store.database_now(session)))[key]


async def reset_preference(session: Session, user_ref: str, key: str, note: str = "") -> StoredPreference:
    """From now the user follows the admin default again: a new row with value NULL (never a delete)."""
    user = _user(user_ref)
    preference(key)
    return await _insert(session, user, key, None, note)


def as_values(found: Mapping[str, Answer]) -> dict[str, Decimal]:
    return {k: a.value for k, a in found.items()}
