"""Settings API (GC-SET step 2; REQ-167 AC-2, AC-3, AC-5): the admin reads every app-wide setting by group and changes
one over HTTP; the next calculation reads the new value (``settings_store``, no restart).

Spec basis: REQ-167 AC-2 ("shows the settings by group with the value in force, the default, when it took effect and
who set it, and the earlier values ... a value outside the allowed range or of the wrong unit is refused
with the reason ... Reset to default is a new row, never a delete"); AC-3 ("Only the admin can change a setting;
every change is written to
the audit log ... every settings write passes one guard"); AC-5 (Charges: "shown from its existing dated
table, a new rate set added from the page with its source URL"); ADR-008 (rates are exact decimals).

- GET /api/settings: groups -> settings (key, label, unit, what it changes, min, max, default, value in force, since,
  set by, earlier values, newest first, each row marked in_force / scheduled / earlier),
  plus the Charges rate set in force.
- POST /api/settings/{key}: change (value, effective_from, note); POST /api/settings/{key}/reset: a new row holding the
  registry default; POST /api/settings/charges: a new dated rate set with its source address.
- Values go in and out as decimal STRINGS. A JSON number in a request is refused (422), never coerced.
- Answer states: no row (the default is shown), a row in force, a future row (state "scheduled", not in force), a
  refused
  value (422 with the reason text), an unknown key (404), a back-dated time (422), a store error (500, fail closed: the
  transaction is rolled back and nothing is answered from a default).
- The admin's note is stored and written to the audit log; it is NOT sent back in a response (admin free text cannot
  pass
  the response door, which carries catalogue words only).

``require_admin`` is the ONE guard every write route depends on (a test in ``tests_app/test_settings_route.py``
fails the suite for a write route without it). Known bypasses (out of the threat model today): until sign-in exists
the admin is the one fixed owner
(``current_user_ref``), so ANY caller that can reach the API is the admin; a route added on ANOTHER router that writes
``app_settings`` or ``charge_rates`` is not seen by this module's check.
"""
from __future__ import annotations

import datetime
import logging
import uuid
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from ofo import settings as registry_mod
from ofo.audit.catalogue import EventType
from ofo.charges import ChargeRates
from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.instruments.models import BSE_FO, NSE_FO
from ofo.settings import SettingRefused
from pydantic import BaseModel, ConfigDict, StrictStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ofo_app import audit_store, charge_rates_store, settings_store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, Money
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, respond
from ofo_app.routes.broker import current_user_ref
from ofo_app.sql_time import IST_SQL_ZONE

log = logging.getLogger(__name__)
router = APIRouter(route_class=ClosedRoute)

_TODAY = text(f"SELECT (clock_timestamp() {IST_SQL_ZONE})::date")
CHARGES_GROUP = "Charges"
CHARGE_AUDIT_ACTION = "charge_rate_set_added"
Db = Annotated[AsyncSession, Depends(get_db)]


def require_admin(user: Annotated[str, Depends(current_user_ref)]) -> str:
    """The one guard of every settings write. Today the admin is the single fixed owner (``current_user_ref``); this
    becomes the admin role check when sign-in lands (REQ-167 AC-3)."""
    return user


Admin = Annotated[str, Depends(require_admin)]


# ---- request bodies ------------------------------------------------------------------------------------------------

class SetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: StrictStr
    effective_from: datetime.datetime | None = None
    note: StrictStr = ""


class ResetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: StrictStr = ""


class ChargesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brokerage_per_order: StrictStr
    stt_sell_rate: StrictStr
    stt_exercise_rate: StrictStr
    transaction_rate_nse_fo: StrictStr
    transaction_rate_bse_fo: StrictStr
    sebi_rate: StrictStr
    stamp_buy_rate: StrictStr
    gst_rate: StrictStr
    source_url: StrictStr
    read_on: datetime.date | None = None
    note: StrictStr = ""


# ---- response bodies -----------------------------------------------------------------------------------------------

class EarlierValueOut(ApiModel):
    value: Money
    effective_from: datetime.datetime
    set_by: Identifier
    state: Literal["in_force", "scheduled", "earlier"]


class SettingOut(ApiModel):
    key: Identifier
    group: CatalogueText
    label: CatalogueText
    unit: Identifier
    type: Identifier
    what_it_changes: CatalogueText
    min: Money
    max: Money
    default: Money
    value: Money
    is_default: bool
    effective_from: datetime.datetime | None
    set_by: Identifier | None
    earlier_values: list[EarlierValueOut]


class GroupOut(ApiModel):
    name: CatalogueText
    settings: list[SettingOut]


class ChargesOut(ApiModel):
    name: Identifier
    read_on: datetime.date
    source_url: CatalogueText | None
    rates: dict[Identifier, Money]


class SettingsOut(ApiModel):
    groups: list[GroupOut]
    charges: ChargesOut | None


class RefusedOut(ApiModel):
    reason: CatalogueText


# ---- reading -------------------------------------------------------------------------------------------------------

def _num(value: Decimal) -> Decimal:
    """The value without trailing zeros (0.0650 -> 0.065); the door writes it as a plain decimal string."""
    return Decimal(registry_mod.plain(value))


def _words(value: str) -> ExplanationText:
    return render_explanation("settings_registry_text", text=value)


def _setting_out(key: str, in_force: settings_store.StoredSetting | None, rows: list[settings_store.StoredSetting],
                 now: datetime.datetime) -> SettingOut:
    s = registry_mod.registry()[key]
    earlier_values = [EarlierValueOut(
        value=_num(r.value), effective_from=r.effective_from, set_by=r.set_by,
        state=("scheduled" if r.effective_from > now else
               "in_force" if in_force is not None and r.effective_from == in_force.effective_from else "earlier"))
        for r in rows]
    return SettingOut(
        key=key, group=_words(s.group), label=_words(s.label), unit=s.unit, type=s.type,
        what_it_changes=_words(s.what_it_changes), min=_num(s.min), max=_num(s.max), default=_num(s.default),
        value=_num(in_force.value if in_force else s.default), is_default=in_force is None,
        effective_from=in_force.effective_from if in_force else None,
        set_by=in_force.set_by if in_force else None, earlier_values=earlier_values)


def _shown_url(source: str) -> ExplanationText | None:
    """The web address in a stored source (the seeded set reads "https://zerodha.com/charges (F&O options), read ...":
    its first word), or None when the source holds no address. The rest of a stored source is not sent back."""
    words = source.split()
    word = words[0].rstrip(",;.)") if words else ""
    try:
        return render_explanation("settings_source_url", url=word)
    except TypeError:
        return None


async def _charges(db: AsyncSession, on: datetime.date | None = None) -> ChargesOut | None:
    try:
        rates = await charge_rates_store.rates_in_force(db, on)
    except charge_rates_store.ChargeRatesError:
        return None  # no complete set yet: the page offers "Add rate set"; a database error still raises (500)
    values = {
        "brokerage_per_order": rates.brokerage_per_order, "stt_sell_rate": rates.stt_sell_rate,
        "stt_exercise_rate": rates.stt_exercise_rate, "transaction_rate_nse_fo": rates.transaction_rates[NSE_FO],
        "transaction_rate_bse_fo": rates.transaction_rates[BSE_FO], "sebi_rate": rates.sebi_rate,
        "stamp_buy_rate": rates.stamp_buy_rate, "gst_rate": rates.gst_rate,
    }
    return ChargesOut(name=CHARGES_GROUP, read_on=rates.read_on,
                      source_url=_shown_url(rates.source_url),
                      rates={k: _num(v) for k, v in values.items()})


async def _read_all(db: AsyncSession) -> tuple[dict[str, settings_store.StoredSetting],
                                               dict[str, list[settings_store.StoredSetting]], datetime.datetime]:
    now = await settings_store.database_now(db)
    return (await settings_store.rows_in_force(db, now)), (await settings_store.history(db)), now


@router.get("/api/settings", response_model=SettingsOut)
async def read_settings(db: Db) -> SettingsOut:
    """Every setting by group (registry order), then the Charges rate set in force. A store that cannot answer
    (SettingsError, a database error) is raised to the error boundary: a 500, never a default."""
    forced, hist, now = await _read_all(db)
    groups: dict[str, list[SettingOut]] = {}
    for key, s in registry_mod.registry().items():
        groups.setdefault(s.group, []).append(_setting_out(key, forced.get(key), hist[key], now))
    return SettingsOut(groups=[GroupOut(name=_words(g), settings=items) for g, items in groups.items()],
                       charges=await _charges(db))


# ---- refusals ------------------------------------------------------------------------------------------------------

_PLAIN_REFUSALS = {  # code -> (template, status): the refusals with no slot
    "setting_back_dated": ("settings_refused_back_dated", 422),
    "setting_same_time": ("settings_refused_same_time", 422),
    "setting_time_invalid": ("settings_refused_time_invalid", 422),
    "setting_unknown": ("settings_refused_unknown", 404),
}


def _refusal(key: str, exc: SettingRefused, raw: object) -> tuple[ExplanationText, int]:
    """The catalogue words for a registry refusal, with the slots read back from the registry (never the exception's
    own text). A code with no catalogue words (setting_no_admin, setting_no_correlation) is a bug: a 500."""
    s = registry_mod.registry().get(key)
    plain_template = _PLAIN_REFUSALS.get("setting_unknown" if s is None else exc.code)
    if plain_template is not None:
        return render_explanation(plain_template[0]), plain_template[1]
    plain = registry_mod.plain
    slots: dict[str, dict[str, object]] = {
        "setting_not_a_number": {"label": s.label, "example": plain(s.default)},
        "setting_not_whole": {"label": s.label},
        "setting_out_of_range": {"label": s.label, "low": plain(s.min), "high": plain(s.max), "unit": s.unit},
        "setting_note_too_long": {"max": settings_store.MAX_NOTE},
    }
    if exc.code == "setting_fraction_unit":
        entered = Decimal(str(raw).strip())
        slots[exc.code] = {"label": s.label, "suggested": plain(entered.scaleb(-2)), "entered": plain(entered)}
    if exc.code not in slots:
        raise exc
    return render_explanation(exc.code.replace("setting_", "settings_refused_", 1), **slots[exc.code]), 422


async def _write(db: AsyncSession, key: str, raw: str, *, effective_from: datetime.datetime | None,  # noqa: PLR0913
                 note: str, admin: str) -> object:
    """One setting write: the store call, then commit; a refusal rolls back and is answered with its reason."""
    try:
        await settings_store.add_setting(db, key, raw, set_by=admin, effective_from=effective_from, note=note,
                                         correlation_id=f"settings-{uuid.uuid4().hex}")
        await db.commit()
    except SettingRefused as exc:
        await db.rollback()
        reason, status = _refusal(key, exc, raw)
        return respond(RefusedOut(reason=reason), status)
    except Exception:
        await db.rollback()
        raise
    forced, hist, now = await _read_all(db)
    return _setting_out(key, forced.get(key), hist[key], now)


# ---- writes (every one depends on require_admin) -------------------------------------------------------------------

Refusal = tuple[str, dict[str, object]]  # (explanation template, its slots)


def _parse_rates(body: ChargesIn, read_on: datetime.date) -> ChargeRates | Refusal:
    """The typed rate set, or the refusal naming the field (a number written as text, within the ChargeRates caps)."""
    parsed: dict[str, Decimal] = {}
    fields = body.model_dump()
    for name in charge_rates_store.COMPONENTS:
        raw = fields[name]
        try:
            value = Decimal(raw.strip())
        except InvalidOperation:
            return "settings_refused_charges_value", {"field": name}
        if not value.is_finite() or len(raw) > registry_mod.MAX_TEXT:
            return "settings_refused_charges_value", {"field": name}
        parsed[name] = value
    try:
        return ChargeRates(
            brokerage_per_order=parsed["brokerage_per_order"], stt_sell_rate=parsed["stt_sell_rate"],
            stt_exercise_rate=parsed["stt_exercise_rate"],
            transaction_rates={NSE_FO: parsed["transaction_rate_nse_fo"], BSE_FO: parsed["transaction_rate_bse_fo"]},
            sebi_rate=parsed["sebi_rate"], stamp_buy_rate=parsed["stamp_buy_rate"], gst_rate=parsed["gst_rate"],
            read_on=read_on, source_url=body.source_url.strip())
    except ValueError as exc:  # a component outside its cap: name the one the message names
        named = next((c for c in charge_rates_store.COMPONENTS if c in str(exc)), None)
        if named is None:
            named = ("transaction_rate_nse_fo" if NSE_FO in str(exc) else
                     "transaction_rate_bse_fo" if BSE_FO in str(exc) else "brokerage_per_order")
        return "settings_refused_charges_value", {"field": named}


def _source_refusal(body: ChargesIn) -> Refusal | None:
    try:
        render_explanation("settings_source_url", url=body.source_url.strip())
    except TypeError:
        return "settings_refused_charges_source", {}
    if len(body.note) > settings_store.MAX_NOTE:
        return "settings_refused_note_too_long", {"max": settings_store.MAX_NOTE}
    return None


def _refused(refusal: Refusal) -> object:
    return respond(RefusedOut(reason=render_explanation(refusal[0], **refusal[1])), 422)


@router.post("/api/settings/charges", response_model=ChargesOut)
async def add_charge_rate_set(body: ChargesIn, db: Db, admin: Admin) -> object:
    """A new dated charge rate set (ADR-082): every component and the source address. The table is append-only."""
    read_on = body.read_on or (await db.execute(_TODAY)).scalar_one()
    problem = _source_refusal(body)
    if problem is not None:
        return _refused(problem)
    rates = _parse_rates(body, read_on)
    if isinstance(rates, tuple):
        return _refused(rates)
    url = rates.source_url
    try:
        async with db.begin_nested():  # the rows and their audit event: both or neither
            await charge_rates_store.add_rate_set(db, rates, body.note)
            await audit_store.append(
                db, EventType.ADMIN_CHANGE_RECORDED, actor=admin, correlation_id=f"settings-{uuid.uuid4().hex}",
                payload={"action": CHARGE_AUDIT_ACTION,
                         "reason": f"charge rates read on {read_on.isoformat()} from {url}"
                                   + (f"; note: {body.note}" if body.note else "")})
        await db.commit()
    except charge_rates_store.ChargeRatesFutureDate:
        await db.rollback()
        return _refused(("settings_refused_charges_future", {"date": read_on}))
    except charge_rates_store.ChargeRatesError:
        await db.rollback()
        return _refused(("settings_refused_charges_date", {"date": read_on}))
    except Exception:
        await db.rollback()
        raise
    out = await _charges(db, read_on)  # the set just written (a future-dated set is read as of its own date)
    if out is None:
        raise charge_rates_store.ChargeRatesError("the rate set just written cannot be read back")
    return out


@router.post("/api/settings/{key}/reset", response_model=SettingOut)
async def reset_setting(key: str, body: ResetIn, db: Db,
                        admin: Admin) -> object:
    """Reset to default is a NEW row holding the registry default, effective now; nothing is deleted."""
    if key not in registry_mod.registry():
        return respond(RefusedOut(reason=render_explanation("settings_refused_unknown")), 404)
    default = registry_mod.plain(registry_mod.registry()[key].default)
    return await _write(db, key, default, effective_from=None, note=body.note, admin=admin)


@router.post("/api/settings/{key}", response_model=SettingOut)
async def change_setting(key: str, body: SetIn, db: Db,
                         admin: Admin) -> object:
    """Change one setting from ``effective_from`` (default now); the registry refuses a wrong value with its reason."""
    if key not in registry_mod.registry():
        return respond(RefusedOut(reason=render_explanation("settings_refused_unknown")), 404)
    return await _write(db, key, body.value, effective_from=body.effective_from, note=body.note, admin=admin)


