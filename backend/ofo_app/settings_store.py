"""App settings store: the values in force at a time, their history, and the admin write (REQ-167 AC-1..AC-3).

Spec basis: REQ-167 AC-1 ("the value in force at a time is the newest row not after that time, else the default"),
AC-2 (history; refusal with the reason; reset is a new row), AC-3 ("every change is written to the audit log");
ADR-222 (1), (5) app-wide values only; ADR-023 (the database clock decides "now"). Table: migration 0032.

Answer states of a read (each has a test in tests_app/test_settings_store.py):
- a row in force (effective_from <= at): the newest such row's value;
- no row, or only future-dated rows: the registry default;
- a row for a key the registry no longer holds: ignored;
- a stored value the registry now refuses (its range was narrowed after the write): ``SettingsError`` - fail closed,
  never a silent fall back to the default (no silent substitution).

Writes take effect now (the database clock) or at a later stated time; a back-dated write is refused, because figures
already shown were computed with the value then in force. The audit row uses the existing ADMIN_CHANGE_RECORDED event
(fields ``action`` and ``reason``; no audit migration). Transaction control stays with the caller (READ COMMITTED, the
audit store refuses anything else); the row and its audit event share one savepoint, so a same-instant duplicate or a
failed audit append leaves neither behind and the caller's transaction usable.

Known bypasses (out of the threat model, not chased): a database superuser or the table owner can
``ALTER TABLE public.app_settings DISABLE TRIGGER app_settings_guard`` (or drop it) and then edit or delete rows; the
start-up allow-list check (migration 0032 block 24) reports a disabled or re-bodied guard but cannot stop the owner.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from ofo import settings as registry_mod
from ofo.audit.catalogue import EventType
from ofo.settings import SettingRefused
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from ofo_app import audit_store

MAX_NOTE = 500
AUDIT_ACTION = "app_setting_set"

_NOW = text("SELECT clock_timestamp()")
_IN_FORCE = text(
    """
    SELECT DISTINCT ON (key) key, value, effective_from, set_by
    FROM public.app_settings WHERE effective_from <= :at
    ORDER BY key, effective_from DESC
    """
)
_HISTORY = text(
    "SELECT key, value, effective_from, set_by, note, created_at FROM public.app_settings "
    "ORDER BY key, effective_from DESC"
)
_INSERT = text(
    """
    INSERT INTO public.app_settings (key, value, effective_from, set_by, note)
    VALUES (:key, :value, :effective_from, :set_by, :note)
    """
)


class SettingsError(Exception):
    """The stored settings cannot answer (fail closed)."""


@dataclass(frozen=True)
class StoredSetting:
    key: str
    value: Decimal
    effective_from: datetime.datetime
    set_by: str
    note: str = ""
    created_at: datetime.datetime | None = None


async def database_now(session: AsyncSession | AsyncConnection) -> datetime.datetime:
    return (await session.execute(_NOW)).scalar_one()


async def rows_in_force(session: AsyncSession | AsyncConnection,
                        at: datetime.datetime | None = None) -> dict[str, StoredSetting]:
    """The newest row per REGISTRY key with effective_from <= ``at`` (default: the database clock). Unknown keys are
    ignored; a stored value the registry refuses raises SettingsError."""
    if at is None:
        at = await database_now(session)
    if not isinstance(at, datetime.datetime) or at.utcoffset() is None:
        raise SettingsError("the time asked about must be a timezone-aware datetime")
    known = registry_mod.registry()
    out: dict[str, StoredSetting] = {}
    for r in (await session.execute(_IN_FORCE, {"at": at})).all():
        if r.key not in known:
            continue  # a key retired from the registry: never read
        if not isinstance(r.value, Decimal):
            raise SettingsError(f"setting {r.key} did not come back as an exact Decimal")
        try:
            registry_mod.check_value(known[r.key], r.value)
        except SettingRefused as exc:
            raise SettingsError(
                f"stored setting {r.key} = {r.value} is refused by the registry: {exc.reason}") from None
        out[r.key] = StoredSetting(r.key, r.value, r.effective_from, r.set_by)
    return out


async def settings_in_force(session: AsyncSession | AsyncConnection,
                            at: datetime.datetime | None = None) -> dict[str, Decimal]:
    """key -> value in force at ``at`` for EVERY registry key (a stored row, else the default)."""
    values = registry_mod.defaults()
    values.update({k: s.value for k, s in (await rows_in_force(session, at)).items()})
    return values


async def history(session: AsyncSession | AsyncConnection) -> dict[str, list[StoredSetting]]:
    """Every stored row per registry key, newest effective_from first (future-dated rows included)."""
    known = registry_mod.registry()
    out: dict[str, list[StoredSetting]] = {k: [] for k in known}
    for r in (await session.execute(_HISTORY)).all():
        if r.key in known:
            out[r.key].append(StoredSetting(r.key, r.value, r.effective_from, r.set_by, r.note, r.created_at))
    return out


async def _refuse_cross_field_break(session: AsyncSession | AsyncConnection, key: str, parsed: Decimal,
                                    effective_from: datetime.datetime) -> None:
    """A value that breaks a rule between settings (a scenario step that is not a multiple of its anchor) is refused at
    SAVE time with the reason, checked against the other values in force at ``effective_from``; it never reaches a
    user request as a 422 (step 3 review). Only the scenario keys carry such a rule today."""
    if not key.startswith("scenarios."):
        return
    from ofo.scenario.config import ScenarioSettings  # noqa: PLC0415 - only the scenario keys need it

    merged = await settings_in_force(session, effective_from)
    merged[key] = parsed
    try:
        ScenarioSettings.from_values(merged)
    except ValueError as exc:
        raise SettingRefused("setting_cross_field", f"This value does not fit the other scenario settings: {exc}") from None


async def add_setting(session: AsyncSession | AsyncConnection, key: str, value: str, *,  # noqa: PLR0913
                      set_by: str, effective_from: datetime.datetime | None = None, note: str = "",
                      correlation_id: str) -> StoredSetting:
    """Admin write: validate against the registry (SettingRefused with the readable reason), insert one dated row and
    one audit event in the caller's transaction. ``effective_from`` None = the database clock now."""
    parsed = registry_mod.validate(key, value)
    if not isinstance(note, str) or len(note) > MAX_NOTE:
        raise SettingRefused("setting_note_too_long", f"The note must be at most {MAX_NOTE} characters.")
    if not isinstance(set_by, str) or not set_by.strip():
        raise SettingRefused("setting_no_admin", "A setting change needs the admin who made it.")
    now = await database_now(session)
    if effective_from is None:
        effective_from = now
    elif not isinstance(effective_from, datetime.datetime) or effective_from.utcoffset() is None:
        raise SettingRefused("setting_time_invalid", "The effective time needs a date, a time and a time zone.")
    elif effective_from < now:
        raise SettingRefused("setting_back_dated",
                             "A setting takes effect now or later; an earlier time would change figures already shown.")
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        raise SettingRefused("setting_no_correlation", "A setting change needs the request's correlation id.")
    await _refuse_cross_field_break(session, key, parsed, effective_from)
    label = registry_mod.registry()[key].label
    reason = f"{key} ({label}) = {registry_mod.plain(parsed)} from {effective_from.isoformat()}"
    if note:
        reason += f"; note: {note}"
    # ONE savepoint holds the row and its audit event: a duplicate time or a refused audit append (for example a
    # REPEATABLE READ transaction, which the audit store refuses) rolls both back, never a row without its event
    async with session.begin_nested():
        try:
            await session.execute(_INSERT, {"key": key, "value": parsed, "effective_from": effective_from,
                                            "set_by": set_by, "note": note})
        except IntegrityError:
            raise SettingRefused(
                "setting_same_time",
                "Another value already takes effect at exactly that time; pick another time.") from None
        await audit_store.append(session, EventType.ADMIN_CHANGE_RECORDED, actor=set_by,
                                 correlation_id=correlation_id,
                                 payload={"action": AUDIT_ACTION, "reason": reason})
    return StoredSetting(key, parsed, effective_from, set_by, note)


def as_mapping(rows: Mapping[str, StoredSetting]) -> dict[str, Decimal]:
    return {k: r.value for k, r in rows.items()}
