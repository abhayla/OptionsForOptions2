"""Per-user adjustment preferences API and the ONE per-request read the adjustment routes use (REQ-168 AC-2..AC-5).

Spec basis: REQ-168 AC-2 ("Each preference shows its value, 'Your value' or 'Default' and the admin default; the user
changes it within the allowed range (refused with the reason otherwise) or resets it to follow the default. History of
the user's own changes is kept"); AC-3 ("A user reads and changes only their own preferences ... every read and write
is keyed by the user and passes one guard"); AC-4 ("A change applies at the next check ... a saved plan is not
changed"); AC-5 (the admin default in force is the starting value); ADR-222 (5)-(9).

- GET /api/adjustments/preferences: each preference (key, label, unit, what it changes, value, source yours/default,
  admin default, min, max, history of the user's own rows, newest first, a reset shown with value null).
- POST /api/adjustments/preferences/{key} {value, note}: the user's own value from now; POST .../{key}/reset {note}:
  follow the admin default again (a new row, never a delete).
- Answer states: no row / a reset (the admin default in force), an own value, a refused value (422 with the reason),
  an unknown key (404), a stored value the registry now refuses (500, fail closed: no figure from a default).

``require_user`` is the ONE guard every read and write of preferences depends on (a test in
``tests_app/test_user_preferences.py`` fails the suite for a route without it); ``get_user_preferences`` is the one
read the adjustment check, the Compare and the approaches route take, once per request, keyed by that user.
Known bypasses (out of the threat model today): until sign-in exists ``require_user`` is the one fixed owner
(``current_user_ref``), so ANY caller that can reach the API is that user; a route on another router that writes
``user_adjustment_preferences`` is not seen by the guard test.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from ofo import settings as registry_mod
from ofo.adjustment import preferences as prefs_mod
from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.settings import SettingRefused
from pydantic import BaseModel, ConfigDict, StrictStr
from sqlalchemy.ext.asyncio import AsyncSession

from ofo_app import user_preferences_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, Money
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, respond
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.settings import refusal as settings_refusal

router = APIRouter(route_class=ClosedRoute)
Db = Annotated[AsyncSession, Depends(get_db)]


def require_user(user: Annotated[str, Depends(current_user_ref)]) -> str:
    """The ONE guard of every preference read and write. Today the one fixed owner (``current_user_ref``); it becomes
    the signed-in user's check when sign-in lands (REQ-168 AC-3). Bypass: see the module docstring."""
    return user


User = Annotated[str, Depends(require_user)]


async def get_user_preferences(db: Db, user: User) -> prefs_mod.Preferences:
    """The signed-in user's preferences in force now, read ONCE per request (FastAPI caches a dependency per request)
    and handed to the pure adjustment functions as required parameters. A store that cannot answer raises (500)."""
    return prefs_mod.from_values(await store.values_for(db, user))


UserPreferences = Annotated[prefs_mod.Preferences, Depends(get_user_preferences)]


class SetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: StrictStr
    note: StrictStr = ""


class ResetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: StrictStr = ""


class PreferenceHistoryOut(ApiModel):
    value: Money | None  # None: a reset (followed the admin default from then)
    effective_from: datetime.datetime


class PreferenceOut(ApiModel):
    key: Identifier
    label: CatalogueText
    unit: Identifier
    type: Identifier
    what_it_changes: CatalogueText
    value: Money
    source: Literal["yours", "default"]
    admin_default: Money
    min: Money
    max: Money
    since: datetime.datetime | None
    history: list[PreferenceHistoryOut]


class PreferencesOut(ApiModel):
    preferences: list[PreferenceOut]


class RefusedOut(ApiModel):
    reason: CatalogueText


def _num(value: Decimal) -> Decimal:
    return Decimal(registry_mod.plain(value))


def _words(value: str) -> ExplanationText:
    return render_explanation("settings_registry_text", text=value)


def _out(a: store.Answer, rows: list[store.StoredPreference]) -> PreferenceOut:
    s = registry_mod.registry()[a.key]
    return PreferenceOut(
        key=a.key, label=_words(s.label), unit=s.unit, type=s.type, what_it_changes=_words(s.what_it_changes),
        value=_num(a.value), source=a.source, admin_default=_num(a.admin_default), min=_num(s.min), max=_num(s.max),
        since=a.since,
        history=[PreferenceHistoryOut(value=None if r.value is None else _num(r.value), effective_from=r.effective_from)
                 for r in rows])


async def _read(db: AsyncSession, user: str) -> PreferencesOut:
    found = await store.answers(db, user)
    hist = await store.history(db, user)
    return PreferencesOut(preferences=[_out(found[k], hist[k]) for k in store.preference_keys()])


def _refused(key: str, exc: SettingRefused, raw: object, ceiling: Decimal | None = None) -> object:
    if exc.code == "setting_unknown":
        return respond(RefusedOut(reason=render_explanation("adjust_preference_refused_unknown")), 404)
    if exc.code == store.CAP_ABOVE_ADMIN and ceiling is not None:  # the limit read back, never the exception's text
        label = registry_mod.registry()[key].label
        return respond(RefusedOut(reason=render_explanation("adjust_preference_refused_above_cap", label=label,
                                                            limit=registry_mod.plain(ceiling))), 422)
    reason, status = settings_refusal(key, exc, raw)
    return respond(RefusedOut(reason=reason), status)


@router.get("/api/adjustments/preferences", response_model=PreferencesOut)
async def read_preferences(db: Db, user: User) -> PreferencesOut:
    """The user's own preferences (never another user's: every query is keyed by ``require_user``'s answer)."""
    return await _read(db, user)


async def _write(db: AsyncSession, user: str, key: str, raw: str | None, note: str) -> object:
    try:
        if raw is None:
            await store.reset_preference(db, user, key, note)
        else:
            await store.set_preference(db, user, key, raw, note)
        await db.commit()
    except SettingRefused as exc:
        await db.rollback()
        ceiling = await store.cap_ceiling(db, key) if exc.code == store.CAP_ABOVE_ADMIN else None
        return _refused(key, exc, raw, ceiling)
    except Exception:
        await db.rollback()
        raise
    return await _read(db, user)


@router.post("/api/adjustments/preferences/{key}", response_model=PreferencesOut)
async def set_preference(key: str, body: SetIn, db: Db, user: User) -> object:
    """The user's own value from now (applies at the next check; saved plans are not changed, REQ-168 AC-4)."""
    return await _write(db, user, key, body.value, body.note)


@router.post("/api/adjustments/preferences/{key}/reset", response_model=PreferencesOut)
async def reset_preference(key: str, body: ResetIn, db: Db, user: User) -> object:
    """Follow the admin default again from now: a new row, never a delete (REQ-168 AC-2)."""
    return await _write(db, user, key, None, body.note)
