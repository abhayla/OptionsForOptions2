"""Issue #208 / REQ-038 AC-5 / ADR-075: the stored form carries each leg's planned entry and capture time.

Spec basis (quoted): REQ-038 AC-5 "Each leg's planned entry price and its capture time are part of the definition and
are saved with it (ADR-075)." ADR-075 "LTP, bid, ask, IV and health stay out of the stored strategy". ADR-068 item 1:
the planned entry changes only when the user asks to reprice.
Values: the 2026-10-15 live gate condor's entries 44.90 / 11.75 / 79.05 / 37.15 (ADR-075 source line).
"""

from __future__ import annotations

import ast
import datetime
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.strategy import stored_form as sf

from test_stored_form import _iron_condor  # the same real Iron Condor legs

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
AT = datetime.datetime(2026, 10, 15, 11, 2, 17, tzinfo=IST)
NOW = datetime.datetime(2026, 10, 15, 12, 0, tzinfo=IST)
ENTRIES = ("44.90", "11.75", "79.05", "37.15")
MIGRATION = Path(__file__).resolve().parents[2] / "backend" / "ofo_app" / "alembic" / "versions" / \
    "0011_strategy_planned_entry.py"


def _with_entries(entries=ENTRIES) -> sf.SavedDefinition:
    plain = _iron_condor()
    return sf.SavedDefinition(plain.definition, plain.contract_ids,
                              tuple(None if e is None else sf.LegEntry(Decimal(e), AT) for e in entries))


def _resolver(saved: sf.SavedDefinition):
    terms = {cid: sf.CatalogueTerms(saved.definition.underlying, leg.instrument, leg.strike, leg.expiry, 65, True)
             for cid, leg in zip(saved.contract_ids, saved.definition.legs)}
    return terms.get


def test_ac5_entries_round_trip_through_the_stored_text_exactly():
    """AC-5: dumps -> loads gives the same entries (Decimal, aware datetime) and the same text."""
    saved = _with_entries()
    text = sf.dumps(saved)
    doc = json.loads(text)
    assert [(leg["planned_entry"], leg["captured_at"]) for leg in doc["legs"]] == [
        (e, "2026-10-15T11:02:17+05:30") for e in ENTRIES]
    loaded = sf.loads(text, _resolver(saved))
    assert loaded == saved and sf.dumps(loaded) == text
    assert loaded.entries[0].price == Decimal("44.90") and str(loaded.entries[0].price) == "44.90"


def test_ac5_a_leg_without_an_entry_has_neither_key_and_the_default_is_none():
    saved = _iron_condor()
    assert saved.entries == (None,) * 4
    assert all(set(leg) == sf.LEG_KEYS for leg in json.loads(sf.dumps(saved))["legs"])
    mixed = _with_entries(("44.90", None, None, "37.15"))
    assert sf.loads(sf.dumps(mixed), _resolver(mixed)).entries[1] is None


@pytest.mark.parametrize("leg_change", [
    {"planned_entry": "44.90"}, {"captured_at": "2026-10-15T11:02:17+05:30"},
    {"planned_entry": "44.90", "captured_at": "2026-10-15T11:02:17+05:30", "ltp": "45"},
    {"planned_entry": 44.9, "captured_at": "2026-10-15T11:02:17+05:30"},
    {"planned_entry": "44.901", "captured_at": "2026-10-15T11:02:17+05:30"},
    {"planned_entry": "0", "captured_at": "2026-10-15T11:02:17+05:30"},
    {"planned_entry": "44.90", "captured_at": "2026-10-15T11:02:17"},
    {"planned_entry": "44.90", "captured_at": "2026-10-15T05:32:17Z"},  # stored text is canonical isoformat only
    {"planned_entry": "44.90", "captured_at": "2026-10-15 11:02:17+05:30"},
    {"planned_entry": "44.90", "captured_at": "2026-10-15T11:02:17.000000+05:30"},  # isoformat drops zero micros
    {"planned_entry": "44.90", "captured_at": "2026-10-15T05:32:17-00:00"},  # isoformat writes +00:00
])
def test_ac5_a_stored_leg_outside_the_two_shapes_is_refused(leg_change):
    saved = _iron_condor()
    doc = json.loads(sf.dumps(saved))
    doc["legs"][0] |= leg_change
    with pytest.raises(sf.StoredFormError) as err:
        sf.from_document(doc, _resolver(saved))
    assert err.value.code in (sf.INVALID_PLANNED_ENTRY, sf.UNKNOWN_KEY, sf.MISSING_KEY)


@pytest.mark.parametrize("price, at", [
    (Decimal("0"), AT), (Decimal("-1"), AT), (Decimal("44.901"), AT), (Decimal("NaN"), AT), ("44.90", AT),
    (Decimal("1E+13"), AT), (Decimal("44.90"), AT.replace(tzinfo=None)), (Decimal("44.90"), "2026-10-15"),
    (Decimal("44.90"), AT.replace(tzinfo=datetime.timezone(datetime.timedelta(seconds=19800 + 15)))),
])
def test_ac5_a_leg_entry_is_a_positive_paise_price_with_an_aware_time(price, at):
    with pytest.raises(sf.StoredFormError) as err:
        sf.LegEntry(price, at)
    assert err.value.code == sf.INVALID_PLANNED_ENTRY


def test_ac5_entry_from_input_accepts_z_and_refuses_the_future_and_a_lone_half():
    entry = sf.entry_from_input("44.90", "2026-10-15T05:32:17Z", NOW, "leg_1")
    assert entry == sf.LegEntry(Decimal("44.90"), AT) and entry.captured_at.isoformat().endswith("+00:00")
    assert sf.entry_from_input("44.90", (NOW + sf.MAX_CAPTURE_AHEAD).isoformat(), NOW, "leg_1").price == Decimal("44.90")
    for price, at in (("44.90", (NOW + sf.MAX_CAPTURE_AHEAD + datetime.timedelta(seconds=1)).isoformat()),
                      ("44.90", None), (None, "2026-10-15T05:32:17Z"), ("44.90", "2026-10-15T11:02:17"),
                      ("4.49E+1", "2026-10-15T05:32:17Z"), ("44.90", "noon")):
        with pytest.raises(sf.StoredFormError) as err:
            sf.entry_from_input(price, at, NOW, "leg_1")
        assert err.value.code == sf.INVALID_PLANNED_ENTRY


def test_ac5_saved_definition_refuses_a_wrong_entries_tuple():
    plain = _iron_condor()
    for entries in ((None,) * 3, ("44.90",) * 4, None):
        with pytest.raises(sf.StoredFormError) as err:
            sf.SavedDefinition(plain.definition, plain.contract_ids, entries)
        assert err.value.code == sf.INVALID_PLANNED_ENTRY


def test_ac5_a_reprice_is_a_change_named_in_the_summary():
    """ADR-068 item 1: new entries on the same legs are a change ("planned entry prices repriced"), never cosmetic."""
    old, new = _with_entries(), _with_entries(("46.10", "12.05", "77.80", "36.40"))
    assert json.loads(sf.change_summary(old, new)) == [{"kind": "entries_repriced"}]
    assert str(sf.render_summary(sf.change_summary(old, new))) == "planned entry prices repriced"
    assert json.loads(sf.change_summary(_iron_condor(), _iron_condor())) == [{"kind": "legs_reordered"}]


def test_ac5_entry_keys_are_not_live_state_names():
    assert not sf.ENTRY_LEG_KEYS & sf.LIVE_STATE_NAMES
    assert {"ltp", "bid", "ask", "iv"} <= sf.LIVE_STATE_NAMES


def _migration_constants() -> dict:
    out = {}
    for node in ast.parse(MIGRATION.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


def test_the_migration_patterns_equal_the_domain_patterns():
    const = _migration_constants()
    assert set(const["ENTRY_LEG_KEYS"]) == sf.ENTRY_LEG_KEYS
    assert const["ENTRY_PRICE_REGEX"] == "^" + sf.ENTRY_PRICE_PATTERN + "$"
    assert const["CAPTURED_AT_REGEX"] == "^" + sf.CAPTURED_AT_PATTERN + "$"
    for sample in ("44.90", "45", "0.05", "044.90", "44.901", "1" * 13):
        assert (re.search(const["ENTRY_PRICE_REGEX"], sample) is None) == (
            re.fullmatch(sf.ENTRY_PRICE_PATTERN, sample) is None), sample
