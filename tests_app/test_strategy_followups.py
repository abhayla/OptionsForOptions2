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
import json
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ofo.engine.legs import Action, Instrument
from ofo.strategy import stored_form as sf
from ofo.strategy.definition import DefinitionError, DefinitionLeg, StrategyDefinition, render_change_items
from ofo_app import strategy_store as store
from test_strategy_closed_shape import _iron_condor_text
from test_strategy_store import (CHECK_VIOLATION, EXPIRY, IRON_CONDOR, LOT, WING, _app, _body, _client, _expect_refused,
                                 _history_rows, _saved_in, _user, _with_draft)

INSERT = ("INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version) "
          "VALUES (:u, 'NIFTY', CAST(:d AS JSONB), :v)")
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


# ---- (6) the agreement test: for every bounded slot, the value at the bound and one past it get the same verdict
# from the domain and from the database ----

def _leg_doc(n: int, base: dict) -> dict:
    return dict(base, contract_id=1000 + n, strike=str(20000 + 50 * n))


def _definition_with_legs(count: int) -> StrategyDefinition:
    return StrategyDefinition("NIFTY", tuple(
        DefinitionLeg(Action.SELL, Instrument.CE, Decimal(20000 + 50 * n), EXPIRY, LOT) for n in range(count)))


def _domain_one_leg(**changes):
    args = dict(strike=Decimal("22800"), quantity=LOT) | changes
    return DefinitionLeg(Action.SELL, Instrument.CE, args["strike"], EXPIRY, args["quantity"])


def _domain_ids(contract_id):
    return sf.SavedDefinition(_definition_with_legs(1), (contract_id,))


def _domain_limit(value: str):
    return StrategyDefinition("NIFTY", (_domain_one_leg(),), risk_limits={"max_loss": Decimal(value)})


def _domain_pref(value: str):
    return StrategyDefinition("NIFTY", (_domain_one_leg(),), preferences={"objective": value})


def _domain_rules(value: str):
    return StrategyDefinition("NIFTY", (_domain_one_leg(),), rules_ref=value)


def _domain_version(value: int):
    sf.check_schema_version({"schema_version": value})


def _set_leg(key):
    return lambda doc, value: doc["legs"][0].__setitem__(key, value)


def _set_top(*path):
    def apply(doc, value):
        target = doc
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    return apply


def _set_legs_count(doc, count):
    doc["legs"] = [_leg_doc(n, doc["legs"][0]) for n in range(count)]


#: slot -> (value cases, domain call that raises on refusal, how the value lands in the document, document text of it).
#: Every case sits just inside or just past a bound; the verdict of the two sides must be equal.
NINES = "9" * 30
SLOTS = {
    "strike": ([Decimal("999999999999999999"), Decimal("1000000000000000000"), Decimal("99999999999999999.99"),
                Decimal("1E+2"), Decimal("22800.500"), Decimal("0.01")],
               lambda v: _domain_one_leg(strike=v), _set_leg("strike"), str),
    "contract_id": ([1, 10**18 - 1, 10**18, 10**19], _domain_ids, _set_leg("contract_id"), int),
    "quantity": ([1, 1_000_000, 1_000_001, 0], lambda v: _domain_one_leg(quantity=v), _set_leg("quantity"), int),
    "legs": ([1, 20, 21], _definition_with_legs, _set_legs_count, int),
    "risk_limit": ([NINES, NINES + "9", "0." + "9" * 30, "0." + "9" * 31, "0.000001", "0.0000001"], _domain_limit,
                   _set_top("risk_limits", "max_loss"), str),
    "preference": (["a" * 64, "a" * 65], _domain_pref, _set_top("preferences", "objective"), str),
    "rules_ref": (["a" * 64, "a" * 65], _domain_rules, _set_top("rules_ref"), str),
    "schema_version": ([1, 2, 0, 999999999], _domain_version, _set_top("schema_version"), int),
}


def _domain_verdict(call, value) -> bool:
    try:
        call(value)
    except (DefinitionError, sf.StoredFormError, ValueError):
        return False
    return True


async def _db_verdict(conn, doc: dict) -> bool:
    savepoint = await conn.begin_nested()
    try:
        await conn.execute(text(INSERT), {"u": _user(), "d": json.dumps(doc), "v": doc["schema_version"]})
    except DBAPIError as err:
        assert getattr(err.orig, "sqlstate", None) == CHECK_VIOLATION, err
        return False
    finally:
        await savepoint.rollback()
    return True


def _is_stored_text(slot: str, value) -> object:
    return value if slot in ("contract_id", "quantity", "legs", "schema_version") else str(value)


async def test_domain_and_database_agree_on_every_bounded_slot(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            good, _, _ = await _iron_condor_text(conn)
            disagreements = []
            for slot, (cases, domain_call, put, _) in SLOTS.items():
                for value in cases:
                    doc = copy.deepcopy(json.loads(good))
                    put(doc, _is_stored_text(slot, value))
                    domain, database = _domain_verdict(domain_call, value), await _db_verdict(conn, doc)
                    if domain != database:
                        disagreements.append((slot, str(value)[:40], f"domain={domain}", f"database={database}"))
            assert disagreements == []
        finally:
            await trans.rollback()


async def test_domain_and_database_agree_on_the_change_item_bounds(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            good, _, strategy_id = await _iron_condor_text(conn)
            disagreements = []
            for count in (0, 1, 100, 101):
                items = [{"kind": "legs_reordered"}] * count
                domain = _domain_verdict(render_change_items, items)
                savepoint = await conn.begin_nested()
                try:
                    await conn.execute(text(INSERT_HISTORY), {"id": strategy_id, "s": json.dumps(items), "d": good})
                    database = True
                except DBAPIError:
                    database = False
                finally:
                    await savepoint.rollback()
                if domain != database:
                    disagreements.append((count, f"domain={domain}", f"database={database}"))
            assert disagreements == []
        finally:
            await trans.rollback()
