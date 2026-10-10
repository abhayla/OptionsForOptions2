"""W-061 follow-ups (issues #138 gaps 2-3, #167 items 1-2): schema_version is storable only when the domain can load
it, the domain and the database agree on every bound of the stored shape, and the API's 409 and other-user answers are
tested THROUGH the API. Real PostgreSQL only (ADR-048); every test rolls back.

Spec basis: REQ-038 AC-5 ("A strategy's definition and its activity history are saved in the database when the user
presses Save Draft, survive a restart, and load back exactly as saved; live prices are never saved inside the
strategy."); ADR-069 ("short identifiers or numbers only - letters, digits, underscore, hyphen and dot, at most 64
characters").
"""

from __future__ import annotations

import copy
import datetime
import json
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ofo.engine.legs import Action, Instrument
from ofo.strategy import stored_form as sf
from ofo.strategy import definition as definition_module
from ofo.strategy.definition import DefinitionError, render_change_items
from ofo_app import strategy_store as store
from test_strategy_closed_shape import _iron_condor_text
from test_strategy_store import (CHECK_VIOLATION, EXPIRY, IRON_CONDOR, LOT, WING, _app, _body, _client, _expect_refused,
                                 _history_rows, _offline_app, _saved_in, _user, _with_draft)

INSERT = ("INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version) "
          "VALUES (:u, 'NIFTY', CAST(:d AS JSONB), :v)")
HISTORY_NOT_CURRENT = "OF008"  # migration 0008 STRATEGY_SQLSTATE
INSERT_FOR = INSERT  # the column value follows the document's underlying in the generated test
INSERT_HISTORY = ("INSERT INTO public.strategy_history (strategy_id, change_summary, definition, "
                  "definition_schema_version) VALUES (:id, CAST(:s AS JSONB), CAST(:d AS JSONB), 1)")


class _ConnMaker:
    """Hands each request the test's own connection; commit and rollback are no-ops so the test's transaction (rolled
    back by the test) stays the only one."""

    def __init__(self, conn) -> None:
        self.conn = conn

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *a, **k):
        return await self.conn.execute(*a, **k)

    def begin_nested(self):
        return self.conn.begin_nested()

    async def commit(self):
        return None

    async def rollback(self):
        return None


# ---- (b) schema_version: only a version the domain can load is storable ----

@pytest.mark.parametrize("version", [2, 3, 999999999])
async def test_the_database_refuses_a_schema_version_the_domain_cannot_load(app_engine, version):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            good, _, _ = await _iron_condor_text(conn)
            doc = json.loads(good)
            doc["schema_version"] = version
            await _expect_refused(conn, INSERT, CHECK_VIOLATION, {"u": _user(), "d": json.dumps(doc), "v": version})
            assert (await conn.execute(text(INSERT + " RETURNING id"),
                                       {"u": _user(), "d": good, "v": 1})).scalar_one() > 0  # version 1 still stores
        finally:
            await trans.rollback()


# ---- (c) + (d) the API's conflict and ownership answers ----

async def test_the_api_answers_409_to_the_second_put_with_the_same_expected_revision(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            async with _client(_app(_ConnMaker(conn), stored.user_ref)) as ac:
                first = await ac.put(f"/strategies/{stored.id}", json=_body(ids, wing=WING, expected_revision=1))
                assert first.status_code == 200 and first.json()["revision"] == 2, first.text
                history = await _history_rows(conn, stored.id)
                second = await ac.put(f"/strategies/{stored.id}", json=_body(ids, expected_revision=1))
                assert (second.status_code, second.json()["code"]) == (409, "STRATEGY_VALIDATION_409"), second.text
            assert await _history_rows(conn, stored.id) == history
            assert (await store.load(conn, stored.user_ref, stored.id)).revision == 2
        finally:
            await trans.rollback()


async def test_the_api_answers_not_found_to_a_put_on_another_users_strategy_and_stores_nothing(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            before = await store.load(conn, stored.user_ref, stored.id)
            history = await _history_rows(conn, stored.id)
            async with _client(_app(_ConnMaker(conn), "someone-else")) as ac:
                got = await ac.get(f"/strategies/{stored.id}")
                put = await ac.put(f"/strategies/{stored.id}", json=_body(ids, wing=WING, expected_revision=1))
            assert (got.status_code, got.json()["code"]) == (404, "USER_INPUT_003")
            assert (put.status_code, put.json()) == (got.status_code, got.json()), put.text
            assert await store.load(conn, stored.user_ref, stored.id) == before
            assert await _history_rows(conn, stored.id) == history
        finally:
            await trans.rollback()


# ---- an out-of-range contract id: ONE answer whichever side of the range it is on (issue #184 items 2-3) ----
# The catalogue holds ids 1..10^18-1 (stored_form.MAX_CONTRACT_ID); an id outside that cannot be a catalogue contract,
# so every such id gets the catalogue's own "contract not in the catalogue" answer (STRATEGY_VALIDATION_401), never a
# generic input error for one side and a different code for the other, and never a 500 for a value past bigint.

@pytest.mark.parametrize("contract_id", [0, -1, 10**18, 10**19, 2**63, 2**64],
                         ids=["zero", "minus-one", "1e18", "1e19", "2^63", "2^64"])
@pytest.mark.parametrize("method, path, extra", [("POST", "/strategies", {}),
                                                 ("PUT", "/strategies/1", {"expected_revision": 1})])
async def test_an_out_of_range_contract_id_gets_one_error_through_the_api(contract_id, method, path, extra):
    body = {"underlying": "NIFTY", "legs": [{"contract_id": contract_id, "action": "SELL", "quantity": 65}],
            "rules_ref": None, "risk_limits": {}, "preferences": {}} | extra
    async with _client(_offline_app()) as ac:
        response = await ac.request(method, path, json=body)
    assert (response.status_code, response.json()["code"]) == (422, "STRATEGY_VALIDATION_401"), response.text


# ---- (6) the agreement test, GENERATED from one table of bounded slots. A slot is a place in the closed stored shape
# (a document key, a leg key, a change-item key, a key of a leg inside a change item, the item count). The set of
# slots the table must cover is DERIVED from the shape's own key sets (stored_form / definition), not listed by hand,
# so a key added to the shape without a row fails test_the_table_covers_every_slot_of_the_stored_shape. Each row holds
# three kinds of case: "ok" (valid, at the bound), "past" (just beyond the bound), "shape" (wrong type or form). For
# every case the domain and the database (both tables) must return the same verdict, and it must be the one stated.

GOOD_LEG = {"action": "BUY", "instrument": "CE", "strike": "22800", "expiry": EXPIRY.isoformat(), "quantity": 75}
NINES = "9" * 30
_BASE_ITEMS = {
    "underlying": {"kind": "underlying", "old": "NIFTY", "new": "SENSEX"},
    "leg_removed": {"kind": "leg_removed", "leg": GOOD_LEG},
    "leg_added": {"kind": "leg_added", "leg": GOOD_LEG},
    "quantity": {"kind": "quantity", "leg": GOOD_LEG, "before": 75},
    "field": {"kind": "field", "map": "risk_limits", "name": "max_loss", "old": None, "new": "100"},
    "legs_reordered": {"kind": "legs_reordered"},
    "replaced_unreadable": {"kind": "replaced_unreadable"},
    "restored": {"kind": "restored", "seq": 1},
}


def _leg_doc(n: int, base: dict) -> dict:
    return dict(base, contract_id=1000 + n, strike=str(20000 + 50 * n))


def _doc_slot(*path):
    """A document slot: sets the value at ``path`` (a leg key goes on leg 0)."""
    def build(doc, value):
        target = doc
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return doc
    return build


def _is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 1000


def _legs_count(doc, value):
    doc["legs"] = [_leg_doc(n, doc["legs"][0]) for n in range(value)] if _is_count(value) else value
    return doc


def _item_slot(kind, *path):
    def build(_items, value):
        item = copy.deepcopy(_BASE_ITEMS[kind])
        target = item
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        if kind == "field" and path == ("map",):
            item["name"] = {"rules_ref": "rules_ref", "preferences": "objective"}.get(value, "max_loss")
        return [item]
    return build


def _item_count(_items, value):
    return [{"kind": "legs_reordered"}] * value if _is_count(value) else value


def _ok(*values):
    return [("ok", v, True) for v in values]


def _past(*values):
    return [("past", v, False) for v in values]


def _shape(*values):
    return [("shape", v, False) for v in values]


STRIKES = (_ok("22800", "22800.50", "22800.500", "0.01", "999999999999999999", "99999999999999999.99")
           + _past("0", "0.00", "22800.005", "22800.001", "1000000000000000000", "0.001")
           + _shape("-1", "1E+2", "022800", "22 800", None, 22800))
_NO_STRIKE = {k: v for k, v in GOOD_LEG.items() if k != "strike"}
#: slot -> (target, how the value lands, cases). target "doc" = a definition (strategies AND strategy_history);
#: target "items" = a change summary (strategy_history).
TABLE = {
    "doc.schema_version": ("doc", _doc_slot("schema_version"), _ok(1) + _past(2, 0, -1, 999999999)
                           + _shape("1", None)),
    "doc.underlying": ("doc", _doc_slot("underlying"), _ok("NIFTY", "SENSEX") + _past("BANKNIFTY", "nifty")
                       + _shape(None, 1)),
    "doc.legs": ("doc", _legs_count, _ok(1, 20) + _past(21, 0) + _shape("x", None)),
    "doc.rules_ref": ("doc", _doc_slot("rules_ref"), _ok(None, "a", "a" * 64, "rules_1.v-2") + _past("a" * 65, "")
                      + _shape("has space", 5)),
    "doc.risk_limits": ("doc", _doc_slot("risk_limits"),
                        _ok({}, {"max_loss": NINES}, {"max_loss": "0." + "9" * 30}, {"max_loss": "0.000001"})
                        + _past({"max_loss": NINES + "9"}, {"max_loss": "0." + "9" * 31}, {"max_loss": "0.0000001"},
                                {"ltp": "1"})
                        + _shape({"max_loss": 5}, "x", None)),
    "doc.preferences": ("doc", _doc_slot("preferences"), _ok({}, {"objective": "a" * 64})
                        + _past({"objective": "a" * 65}, {"bogus": "x"}) + _shape({"objective": 5}, "x", None)),
    "leg.contract_id": ("doc", _doc_slot("legs", 0, "contract_id"),
                        _ok(1, 10**18 - 1) + _past(0, -1, 10**18, 2**63, 2**64) + _shape("1", None, True)),
    "leg.action": ("doc", _doc_slot("legs", 0, "action"), _ok("BUY", "SELL") + _past("buy", "HOLD")
                   + _shape(None, 1)),
    "leg.instrument": ("doc", _doc_slot("legs", 0, "instrument"), _ok("CE", "PE") + _past("FUT", "ce")
                       + _shape(None, 1)),
    "leg.strike": ("doc", _doc_slot("legs", 0, "strike"), STRIKES),
    "leg.expiry": ("doc", _doc_slot("legs", 0, "expiry"),
                   _ok(EXPIRY.isoformat(), "0001-01-01", "9999-12-31", "2028-02-29")
                   + _past("2026-02-30", "2027-02-29", "2026-13-01", "0000-01-01")
                   + _shape("2026-1-29", "29-01-2026", "2026-01-29T00:00", "", None, 20260129)),
    "leg.quantity": ("doc", _doc_slot("legs", 0, "quantity"), _ok(1, 1_000_000) + _past(1_000_001, 0, -1)
                     + _shape("75", None)),
    "items.count": ("items", _item_count, _ok(1, 100) + _past(0, 101) + _shape("x", None)),
    "item.kind": ("items", _item_slot("legs_reordered", "kind"),
                  _ok("legs_reordered", "replaced_unreadable") + _past("nope", "LEGS_REORDERED") + _shape(None, 1)),
    "item.underlying.old": ("items", _item_slot("underlying", "old"), _ok("NIFTY", "SENSEX") + _past("BANKNIFTY")
                            + _shape(None, 1)),
    "item.underlying.new": ("items", _item_slot("underlying", "new"), _ok("NIFTY", "SENSEX") + _past("BANKNIFTY")
                            + _shape(None, 1)),
    "item.leg_removed.leg": ("items", _item_slot("leg_removed", "leg"), _ok(GOOD_LEG)
                             + _past(dict(GOOD_LEG, extra="x"), _NO_STRIKE) + _shape(None, "x")),
    "item.leg_added.leg": ("items", _item_slot("leg_added", "leg"), _ok(GOOD_LEG)
                           + _past(dict(GOOD_LEG, extra="x"), _NO_STRIKE) + _shape(None, "x")),
    "item.quantity.leg": ("items", _item_slot("quantity", "leg"), _ok(GOOD_LEG) + _past(dict(GOOD_LEG, extra="x"))
                          + _shape(None, "x")),
    "item.quantity.before": ("items", _item_slot("quantity", "before"), _ok(1, 1_000_000)
                             + _past(1_000_001, 0, -1) + _shape("75", None)),
    "item.field.map": ("items", _item_slot("field", "map"), _ok("risk_limits", "preferences", "rules_ref")
                       + _past("other") + _shape(None, 1)),
    "item.field.name": ("items", _item_slot("field", "name"), _ok("max_loss", "max_capital", "max_margin")
                        + _past("ltp", "MAX_LOSS") + _shape(None, 5)),
    "item.field.old": ("items", _item_slot("field", "old"), _ok(None, "100", NINES, "0.000001", "0.0000001")
                       + _past(NINES + "9", "1e5") + _shape(5, ["1"])),
    "item.field.new": ("items", _item_slot("field", "new"), _ok(None, "100", NINES, "0.000001", "0.0000001")
                       + _past(NINES + "9", "1e5") + _shape(5, ["1"])),
    "item.restored.seq": ("items", _item_slot("restored", "seq"), _ok(1, 2**31 - 1) + _past(2**31, 0, -1)
                          + _shape("1", None)),
    "itemleg.action": ("items", _item_slot("leg_added", "leg", "action"), _ok("BUY", "SELL") + _past("buy")
                       + _shape(None, 1)),
    "itemleg.instrument": ("items", _item_slot("leg_added", "leg", "instrument"), _ok("CE", "PE")
                           + _past("ce", "XX") + _shape(None, 1)),
    "itemleg.strike": ("items", _item_slot("leg_added", "leg", "strike"), STRIKES),
    "itemleg.expiry": ("items", _item_slot("leg_added", "leg", "expiry"),
                       _ok(EXPIRY.isoformat(), "0001-01-01", "9999-12-31")
                       + _past("2026-02-30", "2026-13-01") + _shape("2026-1-29", "", None, 20260129)),
    "itemleg.quantity": ("items", _item_slot("leg_added", "leg", "quantity"), _ok(1, 1_000_000)
                         + _past(1_000_001, 0, -1) + _shape("75", None)),
}


def required_slots() -> set[str]:
    """Every slot of the stored shape, derived from the shape's own key sets."""
    return ({f"doc.{k}" for k in sf.DOCUMENT_KEYS} | {f"leg.{k}" for k in sf.LEG_KEYS}
            | {f"itemleg.{k}" for k in definition_module._LEG_KEYS} | {"items.count", "item.kind"}
            | {f"item.{kind}.{k}" for kind, keys in definition_module._ITEM_KEYS.items() for k in keys if k != "kind"})


def uncovered(table: dict) -> set[str]:
    """Slots of the stored shape with no row, plus rows lacking one of the three case kinds."""
    missing = required_slots() - set(table)
    for slot, (_, _, cases) in table.items():
        for kind in ("ok", "past", "shape"):
            if not any(c[0] == kind for c in cases):
                missing.add(f"{slot}:{kind}")
    return missing


def test_the_table_covers_every_slot_of_the_stored_shape():
    assert uncovered(TABLE) == set()
    assert set(TABLE) <= required_slots()  # a row for a slot the shape no longer has is stale
    assert sum(len(cases) for _, _, cases in TABLE.values()) >= 200


@pytest.mark.parametrize("slot", sorted(required_slots()))
def test_removing_one_slot_row_fails_the_coverage_assertion(slot):
    assert uncovered({k: v for k, v in TABLE.items() if k != slot}) == {slot}


def _lenient_resolver(doc: dict):
    """A catalogue that holds exactly what the document's legs say, so only the SHAPE decides the domain verdict."""
    terms = {}
    for raw in doc["legs"] if isinstance(doc["legs"], list) else []:
        try:
            strike = None if raw["strike"] is None else Decimal(raw["strike"])
            terms[raw["contract_id"]] = sf.CatalogueTerms(
                doc["underlying"], Instrument(raw["instrument"]), strike, datetime.date.fromisoformat(raw["expiry"]),
                1, True)
        except Exception:  # an unreadable leg: the domain refuses it before it asks the catalogue
            continue
    return terms.get


def _domain_verdict(call, value) -> bool:
    try:
        call(value)
    except (DefinitionError, sf.StoredFormError, ValueError):
        return False
    return True


def _domain_doc_verdict(doc: dict) -> bool:
    try:
        sf.from_document(copy.deepcopy(doc), _lenient_resolver(doc))
    except (DefinitionError, sf.StoredFormError, ValueError):
        return False
    return True


async def _refused_by_database(conn, sql: str, params: dict) -> bool:
    savepoint = await conn.begin_nested()
    try:
        await conn.execute(text(sql), params)
    except DBAPIError as err:
        state = getattr(err.orig, "sqlstate", None)
        if state == HISTORY_NOT_CURRENT:  # the shape check passed; a history entry must also hold the current definition
            return False
        assert state == CHECK_VIOLATION, err
        return True
    finally:
        await savepoint.rollback()
    return False


def _version_param(doc) -> int:
    version = doc.get("schema_version") if isinstance(doc, dict) else None
    return version if isinstance(version, int) and not isinstance(version, bool) and abs(version) < 2**31 else 1


async def test_domain_and_database_agree_on_every_bounded_slot(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            good, _, strategy_id = await _iron_condor_text(conn)
            good_items = [{"kind": "legs_reordered"}]
            checked, wrong = 0, []
            for slot, (target, build, cases) in TABLE.items():
                for kind, value, valid in cases:
                    payload = build(copy.deepcopy(json.loads(good)) if target == "doc" else None, value)
                    if target == "doc":
                        body = json.dumps(payload)
                        verdicts = {
                            "domain": _domain_doc_verdict(payload),
                            "strategies": not await _refused_by_database(
                                conn, INSERT_FOR.replace("'NIFTY'", ":n"),
                                {"u": _user(), "d": body, "v": _version_param(payload),
                                 "n": payload["underlying"] if payload["underlying"] in ("NIFTY", "SENSEX") else "NIFTY"}),
                            "history": not await _refused_by_database(
                                conn, INSERT_HISTORY, {"id": strategy_id, "s": json.dumps(good_items), "d": body})}
                    else:
                        verdicts = {
                            "domain": _domain_verdict(render_change_items, payload),
                            "history": not await _refused_by_database(
                                conn, INSERT_HISTORY, {"id": strategy_id, "s": json.dumps(payload), "d": good})}
                    checked += 1
                    if set(verdicts.values()) != {valid}:
                        wrong.append((slot, kind, str(value)[:40], f"expected={valid}", verdicts))
            assert wrong == []
            assert checked >= 200
        finally:
            await trans.rollback()




from _migration_replay import round_trip_sql  # noqa: E402  (works wherever 0010 sits in the chain)


async def _volatility(conn) -> str:
    return (await conn.execute(text("SELECT string_agg(provolatile::text, ',') FROM pg_proc "
                                    "WHERE proname LIKE 'ofo_strategy_%_valid'"))).scalar_one()


async def test_0010_downgrade_then_upgrade_round_trips_on_the_real_database(admin_engine):
    """Downgrade (0008's validators): version 2 is storable again; upgrade: refused again, version 1 still stores; the
    allowlist function's 'post' check (md5 pins, no EXECUTE for ofo_app) passes both ways. Rolled back."""
    own_down, own_up, down, up = round_trip_sql("0010_strategy_schema_version.py")
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1] and "'post'" in own_down[-1]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            good, _, _ = await _iron_condor_text(conn)
            v2 = json.loads(good)
            v2["schema_version"] = 2
            for sql in down:
                await conn.execute(text(sql))
            assert await _volatility(conn) == "i,i,i"  # the downgrade restores IMMUTABLE (provolatile 'i')
            assert (await conn.execute(text(INSERT + " RETURNING id"),
                                       {"u": _user(), "d": json.dumps(v2), "v": 2})).scalar_one() > 0
            for sql in up:
                await conn.execute(text(sql))
            await _expect_refused(conn, INSERT, CHECK_VIOLATION, {"u": _user(), "d": json.dumps(v2), "v": 2})
            assert (await conn.execute(text(INSERT + " RETURNING id"),
                                       {"u": _user(), "d": good, "v": 1})).scalar_one() > 0
            assert await _volatility(conn) == "s,s,s"
        finally:
            await trans.rollback()
