"""Stored form of a strategy definition and of an activity-history entry: canonical, versioned JSON (W-061).

Spec basis: REQ-038 AC-5 ("A strategy's definition and its activity history are saved in the database when the user
presses Save Draft, survive a restart, and load back exactly as saved; live prices are never saved inside the
strategy."); REQ-038 AC-1 (definition and live state are separate objects); REQ-038 AC-2 (before the first execution,
definition changes are simple activity-history entries with restore); ADR-008 (money and prices are exact Decimal,
never float); ADR-016 (no silent contract substitution); REQ-054 AC-3 / ADR-057 (links use the catalogue's internal
contract id, never the broker's token or symbol).

Copy from: none for the form itself - legacy-reuse rows ``app/models/strategies.py`` (REFERENCE: Decimal leg shape) and
``app/schemas/strategies.py`` (SKIP: float P&L, optional strategy_id) are not copied.

The form (schema_version 1):

    {"schema_version": 1, "underlying": "NIFTY", "rules_ref": null,
     "legs": [{"contract_id": 17, "action": "SELL", "instrument": "CE", "strike": "22800",
               "expiry": "2026-10-13", "quantity": 65}, ...],
     "risk_limits": {"max_loss": "5000"}, "preferences": {"display": "compact"}}

- Every leg names the catalogue's internal contract id AND the terms the user saw (instrument, strike, expiry). On
  load the catalogue must still hold that id with those terms; a missing id or changed terms is refused with a fixed
  code, never replaced by a guess (ADR-016).
- Decimals (strike, risk limits) are JSON strings written with ``str(Decimal)`` and read back only if the text is
  the same, so the stored text is exact. A JSON float anywhere is refused. Integers (schema_version, contract_id,
  quantity in units) are JSON integers, never booleans.
- A leg may also carry its planned entry price and capture time (ADR-075: "Save Draft stores each leg's planned
  entry price and its capture time with the strategy definition"), always as the pair ``planned_entry`` (a positive
  price in whole paise, as exact decimal text) and ``captured_at`` (ISO 8601 with a UTC offset). A planned entry is the
  user's own planned price, not a live market price; a leg saved before ADR-075 has neither key and loads with no
  entry (the screen asks for a reprice; nothing re-captures it silently, ADR-068 item 1).
- Unknown keys, missing keys and a schema version this code does not know are refused; nothing is ever dropped or
  defaulted. The form holds no live-market value: its keys are a closed set (``DOCUMENT_KEYS`` / ``LEG_KEYS``), and
  the user-named maps (risk_limits, preferences) take only ADR-064's closed lists of names (UNKNOWN_NAME otherwise).
"""
from __future__ import annotations

import dataclasses
import datetime
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Optional, Sequence

from ofo.engine.legs import Action, Instrument
from ofo.instruments.models import is_lot_aligned
from ofo.errors.explanations import UserWords, join_explanations, render_explanation, user_words
from ofo.strategy import live_state as _live_state
from ofo.strategy.definition import (
    DefinitionError,
    MAX_CHANGE_ITEMS,
    render_change_items,
    DefinitionLeg,
    StrategyDefinition,
    UnknownNameError,
    ValueRefusedError,
    check_names,
    DEFAULT_STRATEGY_NAME,
    NAME_EMPTY,
    STRATEGY_NAME_MAX,
    name_problem,
)
from ofo.strategy import settings_value

SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})
#: A catalogue contract id is 1 .. 10^18 - 1: the database validator (migration 0008 ofo_strategy_leg_valid, regex
#: ^[1-9][0-9]{0,17}$) stores no more. The domain refuses first, with MISSING_CONTRACT_ID, never a late check violation.
MAX_CONTRACT_ID = 10**18 - 1

DOCUMENT_KEYS = frozenset({"schema_version", "underlying", "legs", "rules_ref", "risk_limits", "preferences"})
LEG_KEYS = frozenset({"contract_id", "action", "instrument", "strike", "expiry", "quantity"})
#: ADR-075: the optional pair a leg carries when it has a planned entry (both or neither; nothing else is optional).
ENTRY_LEG_KEYS = frozenset({"planned_entry", "captured_at"})
#: REQ-077 AC-4 (migration 0024): the optional ninth key, allowed only with the pair. A leg with the pair and no mark
#: (saved before 0024) reads as captured; a typed price is written with ``entry_source: "typed"``.
ENTRY_SOURCE_KEY = "entry_source"
SOURCE_CAPTURED = "captured"
SOURCE_TYPED = "typed"
ENTRY_SOURCES = (SOURCE_TYPED, SOURCE_CAPTURED)
#: The database's patterns (migration 0011): a price as plain digits, at most 12 before and 2 after the point
#: (NUMERIC(14,2)); a capture time as Python's isoformat of an aware datetime with a whole-minute offset.
ENTRY_PRICE_PATTERN = r"(0|[1-9][0-9]{0,11})([.][0-9]{1,2})?"
CAPTURED_AT_PATTERN = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.](?!000000)[0-9]{6})?[+-][0-9]{2}:[0-9]{2}"
ENTRY_KEYS = frozenset({"schema_version", "seq", "at", "change_summary", "definition"})

#: Every live-market field name (REQ-038 AC-1's live state, read from the LiveState, LegQuote and Greeks classes) plus
#: "price": none may appear in the stored form, a strategy table column or a Save Draft body.
LIVE_STATE_NAMES = frozenset(
    {f.name for cls in (_live_state.LiveState, _live_state.LegQuote, _live_state.Greeks)
     for f in dataclasses.fields(cls)} - {"leg_index"}) | {"price"}
if LIVE_STATE_NAMES & (DOCUMENT_KEYS | LEG_KEYS | ENTRY_LEG_KEYS | ENTRY_KEYS | {ENTRY_SOURCE_KEY}):  # pragma: no cover - a definition key is never live data
    raise RuntimeError("a stored-form key is a live-state name")

# Fixed refusal codes (the API returns them as-is).
MALFORMED = "malformed"
UNKNOWN_KEY = "unknown_key"
MISSING_KEY = "missing_key"
SCHEMA_VERSION_UNKNOWN = "schema_version_unknown"
MISSING_CONTRACT_ID = "missing_contract_id"
NOT_DECIMAL_STRING = "not_decimal_string"
INVALID_DEFINITION = "invalid_definition"
CONTRACT_NOT_IN_CATALOGUE = "contract_not_in_catalogue"
CONTRACT_TERMS_CHANGED = "contract_terms_changed"
CONTRACT_NOT_LIVE = "contract_not_live"
QUANTITY_NOT_LOT_MULTIPLE = "quantity_not_lot_multiple"
UNDERLYING_MISMATCH = "underlying_mismatch"
LIVE_STATE_FIELD = "live_state_field"
UNKNOWN_NAME = "unknown_name"
VALUE_NOT_ALLOWED = "value_not_allowed"  # ADR-069: a setting value that is not an identifier or a number
STRATEGY_NAME_EMPTY = "strategy_name_empty"  # REQ-134 AC-1: an empty name ("Give the strategy a name")
STRATEGY_NAME_INVALID = "strategy_name_invalid"  # REQ-134 AC-1: over 40 characters, a control character, not text
INVALID_PLANNED_ENTRY = "invalid_planned_entry"  # ADR-075: not a positive paise price with an aware capture time


class StoredFormError(ValueError):
    """A stored or submitted strategy form was refused. ``code`` is one of the fixed codes above."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(": ".join((code, detail)))


@dataclass(frozen=True)
class CatalogueTerms:
    """What the catalogue says about one internal contract id today."""

    underlying: str
    instrument: Instrument
    strike: Optional[Decimal]
    expiry: datetime.date
    lot_size: int
    live: bool  # neither retired nor delisted

    def key(self) -> tuple:
        return (self.underlying, self.instrument, self.strike, self.expiry)


#: Looks a contract id up in the catalogue; None when no contract has the id.
Resolver = Callable[[int], Optional[CatalogueTerms]]


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_entry_price_text(text: object) -> bool:
    """ADR-075 / REQ-077 AC-2: the one rule for a planned entry price as text - plain decimal in whole paise (at most 12
    digits before the point, no leading zero, no sign or exponent) and above zero. LegEntry (every stored and sent
    price) and the leg-edit route's legs both judge a price here, so "0" or "0.00" is refused by each the same way."""
    return type(text) is str and re.fullmatch(ENTRY_PRICE_PATTERN, text) is not None and Decimal(text) > 0


@dataclass(frozen=True)
class LegEntry:
    """ADR-075: one leg's planned entry price and the time it was captured. The user's own planned price (captured
    from a live price when the leg was added, ADR-068 item 1), never a live price; it changes only on a reprice."""

    price: Decimal
    captured_at: datetime.datetime
    source: str = SOURCE_CAPTURED  # REQ-077 AC-4: "typed" (the user's own price, its time is captured_at) or "captured"

    def __post_init__(self) -> None:
        if type(self.source) is not str or self.source not in ENTRY_SOURCES:
            raise StoredFormError(INVALID_PLANNED_ENTRY, f"an entry source is one of {list(ENTRY_SOURCES)}")
        price = self.price
        if not isinstance(price, Decimal) or not price.is_finite() or not is_entry_price_text(str(price)):
            raise StoredFormError(INVALID_PLANNED_ENTRY, "a planned entry is a positive price in whole paise (at most "
                                                         "12 digits before the point)")
        at = self.captured_at
        if (not isinstance(at, datetime.datetime) or at.tzinfo is None or at.utcoffset() is None
                or re.fullmatch(CAPTURED_AT_PATTERN, at.isoformat()) is None):
            raise StoredFormError(INVALID_PLANNED_ENTRY, "a capture time is a timezone-aware datetime with a "
                                                         "whole-minute offset")


def entry_from_text(price: Any, captured_at: Any, where: str, source: Any = SOURCE_CAPTURED) -> LegEntry:
    """The pair as stored / sent text: the price is exact decimal text (``str(Decimal)`` of itself, no float, no
    exponent) and the time is ISO 8601 with its offset, written exactly as ``isoformat`` writes it back."""
    if type(price) is not str or re.fullmatch(ENTRY_PRICE_PATTERN, price) is None:
        raise StoredFormError(INVALID_PLANNED_ENTRY, f"{where}.planned_entry is not a plain decimal price text")
    if type(captured_at) is not str or re.fullmatch(CAPTURED_AT_PATTERN, captured_at) is None:
        raise StoredFormError(INVALID_PLANNED_ENTRY, f"{where}.captured_at is not an ISO datetime with an offset")
    try:
        at = datetime.datetime.fromisoformat(captured_at)
    except ValueError:
        raise StoredFormError(INVALID_PLANNED_ENTRY, f"{where}.captured_at is not a real datetime") from None
    if at.isoformat() != captured_at:
        raise StoredFormError(INVALID_PLANNED_ENTRY, f"{where}.captured_at is not in its canonical form")
    return LegEntry(_decimal_from(price, f"{where}.planned_entry", INVALID_PLANNED_ENTRY), at, source)


#: A capture time later than the server clock by more than this is refused (a clock that runs ahead, or a forged time).
MAX_CAPTURE_AHEAD = datetime.timedelta(minutes=5)


def entry_from_input(price: Any, captured_at: Any, now: datetime.datetime, where: str,
                     source: Any = SOURCE_CAPTURED) -> LegEntry:
    """The pair as a Save Draft body sends it (the strings POST /api/strategies/planned-entry returned): the price is
    exact plain decimal text in whole paise (a JSON number or float is refused); the time is any ISO 8601 text WITH an
    offset ("Z" included), stored in its canonical ``isoformat`` form, and never later than ``now`` +
    MAX_CAPTURE_AHEAD. Both or neither: one without the other is refused (INVALID_PLANNED_ENTRY)."""
    if type(price) is not str or re.fullmatch(ENTRY_PRICE_PATTERN, price) is None:
        raise StoredFormError(INVALID_PLANNED_ENTRY, f"{where}.planned_entry is not a plain decimal price text")
    if type(captured_at) is not str:
        raise StoredFormError(INVALID_PLANNED_ENTRY, f"{where}.captured_at is not an ISO datetime text")
    try:
        at = datetime.datetime.fromisoformat(captured_at)
    except ValueError:
        raise StoredFormError(INVALID_PLANNED_ENTRY, f"{where}.captured_at is not an ISO datetime") from None
    if at.tzinfo is None or at.utcoffset() is None:
        raise StoredFormError(INVALID_PLANNED_ENTRY, f"{where}.captured_at has no UTC offset")
    if not isinstance(now, datetime.datetime) or now.tzinfo is None or at > now + MAX_CAPTURE_AHEAD:
        raise StoredFormError(INVALID_PLANNED_ENTRY, f"{where}.captured_at is in the future")
    return LegEntry(_decimal_from(price, f"{where}.planned_entry", INVALID_PLANNED_ENTRY), at, source)


@dataclass(frozen=True)
class SavedDefinition:
    """A definition plus, for each leg in order, the catalogue's internal contract id it was built from and its planned
    entry (ADR-075; None for a leg without one, e.g. a draft saved before ADR-075). ``entries`` defaults to none."""

    definition: StrategyDefinition
    contract_ids: tuple[int, ...]
    entries: tuple[Optional[LegEntry], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.definition, StrategyDefinition):
            raise StoredFormError(INVALID_DEFINITION, f"definition must be a StrategyDefinition, got {self.definition!r}")
        ids = tuple(self.contract_ids) if isinstance(self.contract_ids, (tuple, list)) else None
        if ids is None or len(ids) != len(self.definition.legs):
            raise StoredFormError(MISSING_CONTRACT_ID, "every leg needs exactly one catalogue contract id")
        for contract_id in ids:
            if not _is_int(contract_id) or not 0 < contract_id <= MAX_CONTRACT_ID:
                raise StoredFormError(MISSING_CONTRACT_ID,
                                      f"a contract id is an integer in 1..{MAX_CONTRACT_ID}, got {contract_id!r}")
        if len(set(ids)) != len(ids):
            raise StoredFormError(INVALID_DEFINITION, "two legs on the same catalogue contract")
        # Every path to or from the stored form builds a SavedDefinition, so this is the one place the named maps are
        # checked: a risk limit or preference named like live market data (ltp, spot, iv, ...) is refused.
        check_map_names(risk_limits=[n for n, _ in self.definition.risk_limits],
                        preferences=[n for n, _ in self.definition.preferences])
        object.__setattr__(self, "contract_ids", ids)
        entries = tuple(self.entries) if isinstance(self.entries, (tuple, list)) else None
        if entries == ():
            entries = (None,) * len(ids)
        if entries is None or len(entries) != len(ids) or not all(e is None or isinstance(e, LegEntry)
                                                                   for e in entries):
            raise StoredFormError(INVALID_PLANNED_ENTRY, "entries holds one LegEntry or None per leg")
        object.__setattr__(self, "entries", entries)


def check_map_names(**named: Sequence[str]) -> None:
    """ADR-064: refuses (UNKNOWN_NAME, naming the map) any risk-limit or preference name outside the closed lists in
    ofo.strategy.definition; exact comparison. StrategyDefinition enforces the same lists on every path."""
    for label, names in named.items():
        try:
            check_names(label, list(names))
        except UnknownNameError as exc:
            raise StoredFormError(UNKNOWN_NAME, str(exc)) from None


def _definition_refused(exc: DefinitionError, where: str = "") -> StoredFormError:
    code = (UNKNOWN_NAME if isinstance(exc, UnknownNameError)
            else VALUE_NOT_ALLOWED if isinstance(exc, ValueRefusedError) else INVALID_DEFINITION)
    return StoredFormError(code, f"{where}{exc}")


# ----------------------------------------------------------------------------------------------------------------
# Writing
# ----------------------------------------------------------------------------------------------------------------


def _decimal_text(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise StoredFormError(NOT_DECIMAL_STRING, f"{value!r} is not a finite Decimal")
    return str(value)


def to_document(saved: SavedDefinition) -> dict[str, Any]:
    """The canonical stored form (a JSON-ready dict with no float in it)."""
    if not isinstance(saved, SavedDefinition):
        raise StoredFormError(INVALID_DEFINITION, f"to_document needs a SavedDefinition, got {saved!r}")
    d = saved.definition
    legs = []
    for contract_id, leg, entry in zip(saved.contract_ids, d.legs, saved.entries):
        legs.append({
            "contract_id": contract_id,
            "action": leg.action.value,
            "instrument": leg.instrument.value,
            "strike": None if leg.strike is None else _decimal_text(leg.strike),
            "expiry": leg.expiry.isoformat(),
            "quantity": leg.quantity,
        } | ({} if entry is None else {"planned_entry": str(entry.price),
                                       "captured_at": entry.captured_at.isoformat()})
          | ({ENTRY_SOURCE_KEY: SOURCE_TYPED} if entry is not None and entry.source == SOURCE_TYPED else {}))
    return {
        "schema_version": SCHEMA_VERSION,
        "underlying": d.underlying,
        "legs": legs,
        "rules_ref": d.rules_ref,
        "risk_limits": {name: _decimal_text(value) for name, value in d.risk_limits},
        "preferences": {name: value for name, value in d.preferences},
    }


def dumps(saved: SavedDefinition) -> str:
    """Canonical JSON text: sorted keys, no spaces. Equal definitions give equal text."""
    return json.dumps(to_document(saved), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


# ----------------------------------------------------------------------------------------------------------------
# Reading
# ----------------------------------------------------------------------------------------------------------------


def _refuse_float(text: str) -> Any:
    raise StoredFormError(NOT_DECIMAL_STRING, f"the JSON number {text} is a float; decimals are stored as strings")


def _refuse_constant(text: str) -> Any:
    raise StoredFormError(MALFORMED, f"{text} is not JSON")


def parse_json(text: str) -> Any:
    """JSON text -> Python, refusing floats, NaN/Infinity and duplicate keys."""
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise StoredFormError(MALFORMED, f"duplicate key {key!r}")
            out[key] = value
        return out

    if not isinstance(text, str):
        raise StoredFormError(MALFORMED, f"stored form must be JSON text, got {type(text).__name__}")
    try:
        return json.loads(text, parse_float=_refuse_float, parse_constant=_refuse_constant, object_pairs_hook=pairs)
    except StoredFormError:
        raise
    except (ValueError, RecursionError) as exc:
        raise StoredFormError(MALFORMED, f"not valid JSON: {exc}") from None


def _exact_keys(obj: Any, keys: frozenset[str], where: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise StoredFormError(MALFORMED, f"{where} must be a JSON object, got {type(obj).__name__}")
    unknown = sorted(set(obj) - keys)
    if unknown:
        raise StoredFormError(UNKNOWN_KEY, f"{where} has unknown key(s) {unknown}")
    missing = sorted(keys - set(obj))
    if missing:
        code = MISSING_CONTRACT_ID if missing == ["contract_id"] else MISSING_KEY
        raise StoredFormError(code, f"{where} is missing key(s) {missing}")
    return obj


def _decimal_from(value: Any, where: str, code: str = NOT_DECIMAL_STRING) -> Decimal:
    if isinstance(value, float) or (not isinstance(value, str)):
        raise StoredFormError(code, f"{where} must be a decimal string, got {value!r}")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise StoredFormError(code, f"{where} {value!r} is not a decimal") from None
    if not number.is_finite() or str(number) != value:
        raise StoredFormError(code, f"{where} {value!r} is not an exact finite decimal text")
    return number


def check_setting_values(*, rules_ref: Any = None, preferences: Mapping[str, Any] = {}) -> None:
    """ADR-069 for a caller that must refuse before it reads anything (the API): the same domain type that
    StrategyDefinition applies on every path. The refusal (VALUE_NOT_ALLOWED) never holds the value."""
    try:
        if rules_ref is not None:
            settings_value.identifier(rules_ref, "rules_ref")
        for name, value in preferences.items():
            settings_value.identifier(value, f"preference.{name}")
    except settings_value.SettingsValueError as exc:
        raise StoredFormError(VALUE_NOT_ALLOWED, f"{exc.kind} is not an identifier or number (ADR-069), got a {exc.got}"
                              ) from None


def limit_from_text(value: Any, where: str) -> Decimal:
    """A risk limit given as text (API bodies): ADR-069's plain-digit number form, else VALUE_NOT_ALLOWED (never
    echoed); then the exact-text rule of ``decimal_from_text``."""
    if type(value) is not str or re.fullmatch(settings_value.LIMIT_PATTERN, value) is None:
        raise StoredFormError(VALUE_NOT_ALLOWED, f"{where} is not an identifier or number in ADR-069's form")
    return _decimal_from(value, where)


def decimal_from_text(value: Any, where: str) -> Decimal:
    """A decimal given as exact text (API bodies and the stored form); a JSON number or a float is refused."""
    return _decimal_from(value, where)


def _int_from(value: Any, where: str, code: str = MALFORMED) -> int:
    if not _is_int(value):
        raise StoredFormError(code, f"{where} must be a JSON integer, got {value!r}")
    return value


def _enum_from(enum: type, value: Any, where: str):
    try:
        return enum(value)
    except ValueError:
        raise StoredFormError(MALFORMED, f"{where} {value!r} is not one of {[e.value for e in enum]}") from None


def _date_from(value: Any, where: str) -> datetime.date:
    if not isinstance(value, str):
        raise StoredFormError(MALFORMED, f"{where} must be an ISO date string, got {value!r}")
    try:
        day = datetime.date.fromisoformat(value)
    except ValueError:
        raise StoredFormError(MALFORMED, f"{where} {value!r} is not an ISO date") from None
    if day.isoformat() != value:
        raise StoredFormError(MALFORMED, f"{where} {value!r} is not in YYYY-MM-DD form")
    return day


def check_schema_version(doc: Any, where: str = "stored_definition") -> int:
    if not isinstance(doc, dict):
        raise StoredFormError(MALFORMED, f"{where} must be a JSON object, got {type(doc).__name__}")
    if "schema_version" not in doc:
        raise StoredFormError(MISSING_KEY, f"{where} has no schema_version")
    version = doc["schema_version"]
    if not _is_int(version) or version not in SUPPORTED_SCHEMA_VERSIONS:
        raise StoredFormError(SCHEMA_VERSION_UNKNOWN,
                              f"{where} schema_version {version!r} is not one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}")
    return version


def from_document(doc: Any, resolve: Resolver) -> SavedDefinition:
    """The stored form -> a SavedDefinition, refusing (StoredFormError) anything that is not exactly the form, and any
    leg whose contract id the catalogue no longer holds or whose terms changed."""
    check_schema_version(doc)
    doc = _exact_keys(doc, DOCUMENT_KEYS, "stored_definition")
    underlying = doc["underlying"]
    if not isinstance(underlying, str):
        raise StoredFormError(MALFORMED, f"underlying must be a string, got {underlying!r}")
    raw_legs = doc["legs"]
    if not isinstance(raw_legs, list):
        raise StoredFormError(MALFORMED, f"legs must be a JSON array, got {type(raw_legs).__name__}")
    legs: list[DefinitionLeg] = []
    ids: list[int] = []
    entries: list[Optional[LegEntry]] = []
    for i, raw in enumerate(raw_legs):
        where = f"leg_{i + 1}"
        with_entry = isinstance(raw, dict) and bool(ENTRY_LEG_KEYS & set(raw))
        marked = with_entry and ENTRY_SOURCE_KEY in raw  # the ninth key: only ever with the pair (the database's rule)
        raw = _exact_keys(raw, (LEG_KEYS | ENTRY_LEG_KEYS | ({ENTRY_SOURCE_KEY} if marked else set())) if with_entry
                          else LEG_KEYS, where)
        entries.append(entry_from_text(raw["planned_entry"], raw["captured_at"], where,
                                       raw[ENTRY_SOURCE_KEY] if marked else SOURCE_CAPTURED) if with_entry else None)
        contract_id = _int_from(raw["contract_id"], f"{where}.contract_id", MISSING_CONTRACT_ID)
        if not 0 < contract_id <= MAX_CONTRACT_ID:
            raise StoredFormError(MISSING_CONTRACT_ID,
                                  f"{where} contract_id must be in 1..{MAX_CONTRACT_ID}, got {contract_id}")
        instrument = _enum_from(Instrument, raw["instrument"], f"{where}.instrument")
        if isinstance(raw["strike"], str) and re.fullmatch(r"[0-9]+([.][0-9]+)?", raw["strike"]) is None:
            # plain digits only (the database's rule): no sign, exponent, space or non-ASCII digit
            raise StoredFormError(NOT_DECIMAL_STRING, f"{where}.strike is not a plain decimal text")
        strike = None if raw["strike"] is None else _decimal_from(raw["strike"], f"{where}.strike")
        try:
            legs.append(DefinitionLeg(_enum_from(Action, raw["action"], f"{where}.action"), instrument, strike,
                                      _date_from(raw["expiry"], f"{where}.expiry"),
                                      _int_from(raw["quantity"], f"{where}.quantity")))
        except DefinitionError as exc:
            raise StoredFormError(INVALID_DEFINITION, f"{where}: {exc}") from None
        ids.append(contract_id)
    limits = doc["risk_limits"]
    prefs = doc["preferences"]
    if not isinstance(limits, dict) or not isinstance(prefs, dict):
        raise StoredFormError(MALFORMED, "risk_limits and preferences must be JSON objects")
    risk_limits = tuple((name, _decimal_from(value, f"risk_limit.{name!r}")) for name, value in limits.items())
    for name, value in prefs.items():
        if not isinstance(value, str):
            raise StoredFormError(MALFORMED, f"preference {name!r} must be a string, got {value!r}")
    try:
        definition = StrategyDefinition(underlying, tuple(legs), rules_ref=doc["rules_ref"], risk_limits=risk_limits,
                                        preferences=tuple(prefs.items()))
    except DefinitionError as exc:
        raise _definition_refused(exc) from None
    saved = SavedDefinition(definition, tuple(ids), tuple(entries))
    check_against_catalogue(saved, resolve, require_live=False)
    return saved


def loads(text: str, resolve: Resolver) -> SavedDefinition:
    return from_document(parse_json(text), resolve)


# ----------------------------------------------------------------------------------------------------------------
# The catalogue link
# ----------------------------------------------------------------------------------------------------------------


def _leg_key(underlying: str, leg: DefinitionLeg) -> tuple:
    return (underlying, leg.instrument, leg.strike, leg.expiry)


def check_against_catalogue(saved: SavedDefinition, resolve: Resolver, *, require_live: bool) -> None:
    """Every leg's contract id is in the catalogue with the leg's terms (and live, when saving). Never substitutes."""
    d = saved.definition
    for i, (contract_id, leg) in enumerate(zip(saved.contract_ids, d.legs)):
        terms = resolve(contract_id)
        if terms is None:
            raise StoredFormError(CONTRACT_NOT_IN_CATALOGUE,
                                  f"leg {i + 1}: no catalogue contract has internal id {contract_id}")
        if terms.key() != _leg_key(d.underlying, leg):
            raise StoredFormError(CONTRACT_TERMS_CHANGED,
                                  f"leg {i + 1}: catalogue contract {contract_id} is now {terms.key()!r}, the strategy "
                                  f"holds {_leg_key(d.underlying, leg)!r}; it is never replaced automatically")
        if require_live and not terms.live:
            raise StoredFormError(CONTRACT_NOT_LIVE, f"leg {i + 1}: catalogue contract {contract_id} is not live")


@dataclass(frozen=True)
class LegChoice:
    """What the user picked for one leg: a catalogue contract, a side and a quantity in units."""

    contract_id: int
    action: Action
    quantity: int
    entry: Optional[LegEntry] = None  # ADR-075: the leg's planned entry, when the user has one


def build_from_catalogue(underlying: str, choices: Sequence[LegChoice], resolve: Resolver, *,
                         rules_ref: Optional[str] = None,
                         risk_limits: Mapping[str, Decimal] | tuple = (),
                         preferences: Mapping[str, str] | tuple = ()) -> SavedDefinition:
    """A new definition whose legs take their terms from live catalogue contracts (the Save Draft path)."""
    legs: list[DefinitionLeg] = []
    ids: list[int] = []
    entries: list[Optional[LegEntry]] = []
    for i, choice in enumerate(choices):
        if not isinstance(choice, LegChoice):
            raise StoredFormError(INVALID_DEFINITION, f"leg {i + 1} must be a LegChoice, got {choice!r}")
        if not _is_int(choice.contract_id) or not 0 < choice.contract_id <= MAX_CONTRACT_ID:
            raise StoredFormError(MISSING_CONTRACT_ID, f"leg {i + 1}: contract id {choice.contract_id!r}")
        terms = resolve(choice.contract_id)
        if terms is None:
            raise StoredFormError(CONTRACT_NOT_IN_CATALOGUE,
                                  f"leg {i + 1}: no catalogue contract has internal id {choice.contract_id}")
        if not terms.live:
            raise StoredFormError(CONTRACT_NOT_LIVE, f"leg {i + 1}: catalogue contract {choice.contract_id} is not live")
        if terms.underlying != underlying:
            raise StoredFormError(UNDERLYING_MISMATCH, f"leg {i + 1}: contract {choice.contract_id} is "
                                                       f"{terms.underlying}, the strategy is {underlying}")
        if _is_int(choice.quantity) and (choice.quantity <= 0 or not is_lot_aligned(choice.quantity, terms.lot_size)):
            raise StoredFormError(QUANTITY_NOT_LOT_MULTIPLE, f"leg {i + 1}: quantity {choice.quantity} is not a whole "
                                                             f"number of lots of {terms.lot_size}")
        try:
            legs.append(DefinitionLeg(choice.action, terms.instrument, terms.strike, terms.expiry, choice.quantity))
        except DefinitionError as exc:
            raise StoredFormError(INVALID_DEFINITION, f"leg {i + 1}: {exc}") from None
        if choice.entry is not None and not isinstance(choice.entry, LegEntry):
            raise StoredFormError(INVALID_PLANNED_ENTRY, f"leg {i + 1}: entry must be a LegEntry or None")
        ids.append(choice.contract_id)
        entries.append(choice.entry)
    try:
        definition = StrategyDefinition(underlying, tuple(legs), rules_ref=rules_ref, risk_limits=risk_limits,
                                        preferences=preferences)
    except DefinitionError as exc:
        raise _definition_refused(exc) from None
    return SavedDefinition(definition, tuple(ids), tuple(entries))


def summary_text(items: Sequence[Mapping[str, Any]]) -> str:
    """The stored form of a history summary: canonical JSON of change items in the closed shape (see
    ``render_change_items``). Refuses (StoredFormError) anything that does not render from the catalogue."""
    try:
        if not isinstance(items, (list, tuple)) or not 1 <= len(items) <= MAX_CHANGE_ITEMS:  # the stored summary holds 1..N items (the database's rule)
            raise DefinitionError(detail=f"a summary holds 1..{MAX_CHANGE_ITEMS} change items")
        render_change_items(list(items))
    except DefinitionError as exc:
        raise StoredFormError(MALFORMED, f"history summary: {exc}") from None
    return json.dumps(list(items), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def check_summary_text(text: str) -> str:
    """The stored summary text, if it parses and renders; StoredFormError otherwise (the write path calls this)."""
    try:
        items = json.loads(text)
    except (TypeError, ValueError):
        raise StoredFormError(MALFORMED, "history summary is not JSON") from None
    return summary_text(items)


def check_strategy_name(text: object) -> UserWords:
    """REQ-134 AC-1: the name a user typed for a strategy: trimmed, 1..STRATEGY_NAME_MAX characters, one line. Returns
    the user's words (the request door, ofo.errors.explanations.REQUEST_LAYER); StoredFormError otherwise.
    Duplicates are allowed, so nothing here looks at other names."""
    trimmed = text.strip() if type(text) is str else text
    problem = name_problem(trimmed)
    if problem is None:
        return user_words(trimmed)
    if problem == NAME_EMPTY:
        raise StoredFormError(STRATEGY_NAME_EMPTY, "the strategy name is empty")
    raise StoredFormError(STRATEGY_NAME_INVALID, f"a strategy name is 1..{STRATEGY_NAME_MAX} characters on one line")


def shown_name(stored: object):
    """A stored strategy name as the API shows it: the user's own words in the catalogue's quoted slot (ADR-003), so it
    reaches a response only as quoted user text. A value that is not a valid trimmed name is MALFORMED, never shown."""
    if type(stored) is not str or stored != stored.strip() or name_problem(stored) is not None:
        raise StoredFormError(MALFORMED, "the stored strategy name is not a valid name")
    return render_explanation("strategy_name_shown", name=user_words(stored))


def rename_summary(old: str, new: str) -> str:
    """The history summary of a rename (REQ-134 AC-3): one closed ``renamed`` item holding the two names as typed."""
    return summary_text([{"kind": "renamed", "from": old, "to": new}])


def change_summary(old: SavedDefinition, new: SavedDefinition) -> str:
    """The activity-history summary as stored data: the meaningful changes, or the cosmetic one."""
    items = list(new.definition.change_items(old.definition))
    before, after = _entries_by_contract(old), _entries_by_contract(new)
    if any(before[c] != after[c] for c in before.keys() & after.keys()):  # ADR-068 item 1: a reprice is a change
        items.append({"kind": "entries_repriced"})  # (an added or removed leg is already its own item)
    return summary_text(items or [{"kind": "legs_reordered"}])


def _entries_by_contract(saved: SavedDefinition) -> dict[int, Optional[LegEntry]]:
    return dict(zip(saved.contract_ids, saved.entries))


def unreadable_replacement_summary() -> str:
    return summary_text([{"kind": "replaced_unreadable"}])


def render_summary(text: str):
    """Catalogue text for a stored summary: its items joined with '; '. A stored value that is not in the closed
    shape (an unknown kind, a slot that does not validate, text that is not JSON) is shown as a fixed catalogue line,
    never raw."""
    try:
        items = json.loads(text)
        return join_explanations(render_change_items(items), "; ")
    except (TypeError, ValueError, DefinitionError):
        return render_explanation("change_summary_unreadable")


# ----------------------------------------------------------------------------------------------------------------
# Activity-history entry
# ----------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoryEntry:
    """One pre-execution activity-history entry: the definition as it was before the change ``change_summary``
    names (REQ-038 AC-2). ``at`` is the database clock's stamp."""

    seq: int
    at: datetime.datetime
    change_summary: str
    saved: SavedDefinition
    #: Derived by the store on read (never stored): may this entry be restored. False unless proven (fail closed).
    restorable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.restorable, bool):
            raise StoredFormError(MALFORMED, f"history restorable must be a bool, got {self.restorable!r}")
        if not _is_int(self.seq) or self.seq <= 0:
            raise StoredFormError(MALFORMED, f"history seq must be a positive integer, got {self.seq!r}")
        if not isinstance(self.at, datetime.datetime) or self.at.tzinfo is None:
            raise StoredFormError(MALFORMED, f"history at must be a timezone-aware datetime, got {self.at!r}")
        if not isinstance(self.change_summary, str) or not self.change_summary.strip():
            raise StoredFormError(MALFORMED, "history change_summary must be a non-empty string")
        if not isinstance(self.saved, SavedDefinition):
            raise StoredFormError(MALFORMED, "history entry needs a SavedDefinition")


def entry_to_document(entry: HistoryEntry) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "seq": entry.seq, "at": entry.at.isoformat(),
            "change_summary": entry.change_summary, "definition": to_document(entry.saved)}


def entry_from_document(doc: Any, resolve: Resolver) -> HistoryEntry:
    check_schema_version(doc, "history_entry")
    doc = _exact_keys(doc, ENTRY_KEYS, "history_entry")
    if not isinstance(doc["at"], str):
        raise StoredFormError(MALFORMED, f"history at must be an ISO datetime string, got {doc['at']!r}")
    try:
        at = datetime.datetime.fromisoformat(doc["at"])
    except ValueError:
        raise StoredFormError(MALFORMED, f"history at {doc['at']!r} is not an ISO datetime") from None
    return HistoryEntry(_int_from(doc["seq"], "history_seq"), at, doc["change_summary"],
                        from_document(doc["definition"], resolve))
