"""W-061 round 2 (issue #165): the database refuses a definition outside the closed key shape, and ADR-069's value
type is enforced on every path that writes a definition. Real PostgreSQL only (ADR-048); every test rolls back.

Spec basis: REQ-038 AC-5 ("live prices are never saved inside the strategy."); ADR-064 ("Any other name is refused on
every path that builds or loads a definition"); ADR-069 ("short identifiers or numbers only - letters, digits,
underscore, hyphen and dot, at most 64 characters", "is refused on save with the fixed input error (HTTP 422) and is
never echoed back.").
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ofo.engine.legs import Action
from ofo.strategy import stored_form as sf
from ofo_app import strategy_store as store
from ofo_app.catalogue_store import apply_update
from test_strategy_store import (AS_OF, CHECK_VIOLATION, IRON_CONDOR, LOT, _app, _client, _expect_refused,
                                 _fixture_rows, _ids, _user, _with_draft)

SENTENCE = "LTP is 22950.35 buy now"
INSERT_DEFINITION = ("INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version) "
                     "VALUES (:u, 'NIFTY', CAST(:d AS JSONB), 1)")
_DROP = object()


def _mutated(good: str, change) -> str:
    doc = json.loads(good)
    change(doc)
    return json.dumps(doc)


def _set(path_keys: list, value):
    def apply(doc):
        target = doc
        for key in path_keys[:-1]:
            target = target[key]
        if value is _DROP:
            del target[path_keys[-1]]
        else:
            target[path_keys[-1]] = value
    return apply


#: name -> change to the real Iron Condor document. Every one is outside the closed key shape (ADR-064, ADR-069).
REFUSED_SHAPES = {
    "top-level-ltp": _set(["ltp"], "22950.35"),
    "top-level-Spot": _set(["Spot"], "22950.35"),
    "top-level-key-missing": _set(["preferences"], _DROP),
    "preferences-Spot": _set(["preferences", "Spot"], "22950"),
    "preferences-sentence-value": _set(["preferences", "objective"], SENTENCE),
    "preferences-space-in-value": _set(["preferences", "objective"], "a b"),
    "preferences-nested-object-value": _set(["preferences", "objective"], {"ltp": "1"}),
    "preferences-number-value": _set(["preferences", "objective"], 5),
    "preferences-not-an-object": _set(["preferences"], ["objective"]),
    "risk-limit-unknown-name": _set(["risk_limits", "ltp"], "5000"),
    "risk-limit-sentence-value": _set(["risk_limits", "max_loss"], "5000 rupees"),
    "risk-limit-negative-value": _set(["risk_limits", "max_loss"], "-5"),
    "risk-limit-exponent-value": _set(["risk_limits", "max_loss"], "1E+3"),
    "risk-limits-not-an-object": _set(["risk_limits"], ["max_loss"]),
    "leg-nested-last_price": _set(["legs", 0, "last_price"], "101.5"),
    "leg-key-missing": _set(["legs", 0, "quantity"], _DROP),
    "leg-strike-is-an-object": _set(["legs", 0, "strike"], {"ltp": "1"}),
    "leg-not-an-object": _set(["legs", 0], "NIFTY26O1322800CE"),
    "rules-ref-sentence": _set(["rules_ref"], SENTENCE),
    "rules-ref-number": _set(["rules_ref"], 7),
    "schema-version-as-text": _set(["schema_version"], "1"),
}


async def _iron_condor_text(conn) -> tuple[str, dict[str, int], int]:
    ids, stored = await _with_draft(conn, _user())
    good = (await conn.execute(text("SELECT definition::text FROM public.strategies WHERE id = :id"),
                               {"id": stored.id})).scalar_one()
    return good, ids, stored.id


@pytest.mark.parametrize("shape", sorted(REFUSED_SHAPES))
async def test_ac5_the_database_refuses_a_definition_outside_the_closed_key_shape(app_engine, shape):
    """Issue #165 defect 2: as ofo_app, a raw INSERT holding ltp / Spot / a nested last_price (or a value outside
    ADR-064's names and ADR-069's pattern) is refused by PostgreSQL itself."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            good, _, _ = await _iron_condor_text(conn)
            bad = _mutated(good, REFUSED_SHAPES[shape])
            assert bad != good
            await _expect_refused(conn, INSERT_DEFINITION, CHECK_VIOLATION, {"u": _user(), "d": bad})
        finally:
            await trans.rollback()


async def test_ac5_the_database_accepts_the_real_iron_condor_with_every_allowed_name(app_engine):
    """The closed shape is not a blanket refusal: all three risk limits, all six preferences and a rules reference
    that follow ADR-064 / ADR-069 insert."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            good, _, _ = await _iron_condor_text(conn)
            full = _mutated(good, lambda d: d.update(
                rules_ref="rules-set_1.v2",
                risk_limits={"max_loss": "9000.50", "max_capital": "250000", "max_margin": "0"},
                preferences={"objective": "income", "market_view": "range-bound", "risk_preference": "low",
                             "capital": "250000", "expected_range_low": "22400", "expected_range_high": "23000.5"}))
            assert (await conn.execute(text(INSERT_DEFINITION + " RETURNING id"),
                                       {"u": _user(), "d": full})).scalar_one() > 0
        finally:
            await trans.rollback()


async def test_ac5_the_history_table_refuses_the_same_shapes_even_to_the_owner(admin_engine):
    """strategy_history carries the same CHECKs. The owner role with triggers off for the transaction shows that the
    CHECK, not the guard, refuses."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL session_replication_role = replica"))
            good, _, strategy_id = await _iron_condor_text(conn)
            sql = ("INSERT INTO public.strategy_history (strategy_id, seq, change_summary, definition, "
                   "definition_schema_version) VALUES (:id, :seq, '[]', CAST(:d AS JSONB), 1)")
            assert (await conn.execute(text(sql + " RETURNING id"), {"id": strategy_id, "seq": 1, "d": good})
                    ).scalar_one() > 0
            for n, shape in enumerate(("top-level-ltp", "preferences-Spot", "leg-nested-last_price",
                                       "risk-limit-unknown-name", "preferences-sentence-value",
                                       "rules-ref-sentence"), start=2):
                bad = _mutated(good, REFUSED_SHAPES[shape])
                savepoint = await conn.begin_nested()
                with pytest.raises(DBAPIError) as err:
                    await conn.execute(text(sql), {"id": strategy_id, "seq": n, "d": bad})
                await savepoint.rollback()
                assert getattr(err.value.orig, "sqlstate", None) == CHECK_VIOLATION, shape
        finally:
            await trans.rollback()


def _choices(ids):
    return [sf.LegChoice(ids[s], Action(side), LOT) for s, side, *_ in IRON_CONDOR]


async def test_ac5_save_draft_refuses_a_sentence_preference_value(app_engine):
    """Issue #165 defect 1, store door: ADR-069 'short identifiers or numbers only'. Nothing is stored."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture_rows(), as_of=AS_OF)
            ids = await _ids(conn)
            user = _user()
            with pytest.raises(sf.StoredFormError) as err:
                saved = await store.build_definition(conn, "NIFTY", _choices(ids), preferences={"objective": SENTENCE})
                await store.save_draft(conn, user, saved)
            assert err.value.code == "value_not_allowed"
            assert SENTENCE not in str(err.value)
            assert await store.list_strategies(conn, user) == []
        finally:
            await trans.rollback()


async def test_ac5_the_api_answers_the_fixed_input_error_and_never_echoes_the_value(app_engine):
    """ADR-069: a sentence preference / risk limit / rules reference is 422 'user_input_request_invalid' on POST and
    PUT; the body does not contain what was sent; the draft is unchanged."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())

            class _Maker:
                def __call__(self):
                    return self

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *exc):
                    return False

                async def execute(self, *a, **k):
                    return await conn.execute(*a, **k)

                def begin_nested(self):
                    return conn.begin_nested()

                async def commit(self):
                    return None

                async def rollback(self):
                    return None

            body = {"underlying": "NIFTY", "rules_ref": None, "risk_limits": {}, "preferences": {},
                    "legs": [{"contract_id": ids[s], "action": side, "quantity": LOT} for s, side, *_ in IRON_CONDOR]}
            bad_bodies = [body | {"preferences": {"objective": SENTENCE}},
                          body | {"risk_limits": {"max_loss": SENTENCE}},
                          body | {"rules_ref": SENTENCE}]
            async with _client(_app(_Maker(), stored.user_ref)) as ac:
                for bad in bad_bodies:
                    for method, path, extra in (("POST", "/strategies", {}),
                                                ("PUT", f"/strategies/{stored.id}", {"expected_revision": 1})):
                        response = await ac.request(method, path, json=bad | extra)
                        assert response.status_code == 422, response.text
                        assert response.json()["code"] == "USER_INPUT_002", response.text
                        assert "LTP" not in response.text and "22950" not in response.text, response.text
            assert (await store.load(conn, stored.user_ref, stored.id)).saved == stored.saved
            assert len(await store.list_strategies(conn, stored.user_ref)) == 1
        finally:
            await trans.rollback()


async def test_ac5_update_with_a_refused_value_stores_nothing_and_history_is_unchanged(app_engine):
    """Fail closed: a refused definition never reaches update, and a value the type refuses cannot be smuggled in
    through a SavedDefinition built another way."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            with pytest.raises(sf.StoredFormError) as err:
                await store.build_definition(conn, "NIFTY", _choices(ids), rules_ref=SENTENCE)
            assert err.value.code == "value_not_allowed"
            assert (await store.history(conn, stored.user_ref, stored.id)) == []
            assert (await store.load(conn, stored.user_ref, stored.id)).saved == stored.saved
        finally:
            await trans.rollback()


ROOT = Path(__file__).resolve().parents[1]
INI = "backend/ofo_app/alembic.ini"


def _alembic(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, ALEMBIC_DATABASE_URL=os.environ["TEST_ADMIN_DATABASE_URL"])
    return subprocess.run([sys.executable, "-m", "alembic", "-c", INI, *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=240)


async def _table_exists(admin_engine, name: str) -> bool:
    async with admin_engine.connect() as conn:
        return (await conn.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": f"public.{name}"})).scalar_one()


async def test_ac5_downgrade_refuses_while_a_row_exists_then_downgrade_and_upgrade_restore_the_checks(admin_engine):
    """Issue #165 open item: the 0008 downgrade with a row present. A saved draft is the user's data, so the downgrade
    refuses and the row survives; once the row is gone, downgrade then upgrade leaves a store that still refuses a
    definition outside the closed key shape."""
    doc = json.dumps({"schema_version": 1, "underlying": "NIFTY", "rules_ref": None, "risk_limits": {},
                      "preferences": {}, "legs": [{"contract_id": 1, "action": "SELL", "instrument": "CE",
                                                   "strike": "22800", "expiry": "2026-10-13", "quantity": 65}]})
    user = _user()
    async with admin_engine.connect() as conn:
        async with conn.begin():
            strategy_id = (await conn.execute(text(INSERT_DEFINITION + " RETURNING id"), {"u": user, "d": doc})
                           ).scalar_one()
    try:
        refused = await asyncio.to_thread(_alembic, "downgrade", "0007_broker_sessions")
        assert refused.returncode != 0, refused.stdout + refused.stderr
        assert "refusing to downgrade" in refused.stdout + refused.stderr
        async with admin_engine.connect() as conn:
            assert (await conn.execute(text("SELECT count(*) FROM public.strategies WHERE id = :i"),
                                       {"i": strategy_id})).scalar_one() == 1
    finally:
        async with admin_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(text("SET LOCAL session_replication_role = replica"))
                await conn.execute(text("DELETE FROM public.strategies WHERE user_ref = :u"), {"u": user})
    try:
        down = await asyncio.to_thread(_alembic, "downgrade", "0007_broker_sessions")
        assert down.returncode == 0, down.stdout + down.stderr
        assert not await _table_exists(admin_engine, "strategies")
        assert not await _table_exists(admin_engine, "strategy_history")
    finally:
        up = await asyncio.to_thread(_alembic, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    assert await _table_exists(admin_engine, "strategies") and await _table_exists(admin_engine, "strategy_history")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text(INSERT_DEFINITION), {"u": user, "d": doc})  # the real shape inserts
            bad = _mutated(doc, REFUSED_SHAPES["top-level-ltp"])
            await _expect_refused(conn, INSERT_DEFINITION, CHECK_VIOLATION, {"u": user, "d": bad})
        finally:
            await trans.rollback()
