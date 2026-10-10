"""W-061 round 3 (issue #165, finding jsonpath-check-lax-mode-unwraps-arrays): the database accepts a stored strategy
definition and a history change summary only when every slot of the closed shape holds exactly its type. The cases are
GENERATED from one table of positions (every position x every JSON type other than the allowed one, plus the correct
value wrapped in an array), never from a hand list of bad documents, so a shape the author did not imagine is still
covered. Real PostgreSQL only (ADR-048); every test rolls back.

Spec basis: REQ-038 AC-5 ("live prices are never saved inside the strategy."); ADR-064 ("Any other name is refused on
every path that builds or loads a definition"); ADR-069 ("short identifiers or numbers only - letters, digits,
underscore, hyphen and dot, at most 64 characters").
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ofo.strategy import stored_form as sf
from ofo_app import strategy_store as store
from test_strategy_closed_shape import INSERT_DEFINITION, _iron_condor_text
from test_strategy_store import CHECK_VIOLATION, _user

INSERT_HISTORY = ("INSERT INTO public.strategy_history (strategy_id, change_summary, definition, "
                  "definition_schema_version) VALUES (:id, CAST(:s AS JSONB), CAST(:d AS JSONB), 1)")
REORDERED = json.dumps([{"kind": "legs_reordered"}])

#: One sample per JSON type; a slot's wrong types are these minus the types it allows.
SAMPLES: dict[str, Any] = {"null": None, "bool": True, "number": 7.5, "string": "LTP 22950.35", "array": [],
                           "object": {}}


def _get(doc: Any, path: tuple) -> Any:
    for key in path:
        doc = doc[key]
    return doc


def _with(doc: Any, path: tuple, value: Any) -> Any:
    """A copy of ``doc`` with ``value`` at ``path`` (the whole document when the path is empty)."""
    if not path:
        return copy.deepcopy(value)
    out = copy.deepcopy(doc)
    _get(out, path[:-1])[path[-1]] = copy.deepcopy(value)
    return out


def _without(doc: Any, path: tuple) -> Any:
    out = copy.deepcopy(doc)
    del _get(out, path[:-1])[path[-1]]
    return out


def _name(path: tuple) -> str:
    return ".".join(str(p) for p in path) or "root"


def type_cases(doc: Any, positions: list[tuple[tuple, frozenset]]) -> list[tuple[str, Any]]:
    """Every position x every JSON type it does not allow, plus the correct value wrapped in an array."""
    out = []
    for path, allowed in positions:
        wrong = [(t, v) for t, v in SAMPLES.items() if t not in allowed]
        wrong.append(("wrapped-in-array", [_get(doc, path) if path else doc]))
        out.extend((f"{_name(path)}={label}", _with(doc, path, v)) for label, v in wrong)
    return out


def key_cases(doc: Any, object_paths: list[tuple], required: set[tuple]) -> list[tuple[str, Any]]:
    """An extra key at every object level, and every key missing where the shape requires it."""
    out = []
    for path in object_paths:
        obj = _get(doc, path) if path else doc
        for extra in ("ltp", "Max_loss"):
            out.append((f"{_name(path)}+{extra}", _with(doc, path + (extra,), "1")))
        if path in required:
            out.extend((f"{_name(path)}-{k}", _without(doc, path + (k,))) for k in obj)
    return out


S, N, NUM, A, O, B = (frozenset({x}) for x in ("string", "null", "number", "array", "object", "bool"))
LEG_ALLOWED = {"contract_id": NUM, "action": S, "instrument": S, "strike": S, "expiry": S, "quantity": NUM}
LEG_KEYS = tuple(LEG_ALLOWED)
LIMIT_NAMES = ("max_loss", "max_capital", "max_margin")
PREFERENCE_NAMES = ("objective", "market_view", "risk_preference", "capital", "expected_range_low",
                    "expected_range_high")


def definition_cases(full: dict) -> list[tuple[str, Any]]:
    legs = len(full["legs"])
    positions = [((k,), a) for k, a in (("schema_version", NUM), ("underlying", S), ("legs", A), ("rules_ref", N | S),
                                       ("risk_limits", O), ("preferences", O))]
    for i in range(legs):
        positions.append((("legs", i), O))
        positions.extend((("legs", i, k), a) for k, a in LEG_ALLOWED.items())
    positions.extend((("risk_limits", k), S) for k in LIMIT_NAMES)
    positions.extend((("preferences", k), S) for k in PREFERENCE_NAMES)
    object_paths = [(), ("risk_limits",), ("preferences",)] + [("legs", i) for i in range(legs)]
    required = {(), *(("legs", i) for i in range(legs))}
    cases = type_cases(full, positions) + key_cases(full, object_paths, required)
    leg0 = full["legs"][0]
    values = {
        "legs=[]": (("legs",), []), "legs=[[leg]]": (("legs",), [[leg0]]),
        "legs=21 legs": (("legs",), [dict(leg0, contract_id=1000 + n, strike=str(20000 + 50 * n)) for n in range(21)]),
        "legs=[string]": (("legs",), ["NIFTY26O1322800CE"]),
        "legs=same contract twice": (("legs",), [leg0, dict(leg0, contract_id=leg0["contract_id"] + 1000)]),
        "legs=same contract id twice": (("legs",), [leg0, dict(leg0, strike="23999")]),
        "underlying=['NIFTY']": (("underlying",), ["NIFTY"]), "underlying=BANKNIFTY": (("underlying",), "BANKNIFTY"),
        "schema_version='1'": (("schema_version",), "1"), "schema_version=1.5": (("schema_version",), 1.5),
        "objective=['income']": (("preferences", "objective"), ["income"]),
        "objective=sentence": (("preferences", "objective"), "LTP 22950.35"),
        "rules_ref=sentence": (("rules_ref",), "LTP 22950.35"),
        "strike=sentence": (("legs", 0, "strike"), "LTP 22950.35"), "strike=null on a CE": (("legs", 0, "strike"), None),
        "strike=1E+3": (("legs", 0, "strike"), "1E+3"), "strike=0": (("legs", 0, "strike"), "0"),
        "strike=-5": (("legs", 0, "strike"), "-5"), "strike=007": (("legs", 0, "strike"), "007"),
        "strike=3 decimals": (("legs", 0, "strike"), "22800.005"),
        "action=sentence": (("legs", 0, "action"), "LTP 22950.35"), "action=sell": (("legs", 0, "action"), "sell"),
        "instrument=sentence": (("legs", 0, "instrument"), "LTP 22950.35"),
        "expiry=sentence": (("legs", 0, "expiry"), "LTP 22950.35"), "expiry=2026-02-30": (("legs", 0, "expiry"), "2026-02-30"),
        "expiry=no zero pad": (("legs", 0, "expiry"), "2026-2-3"), "expiry=datetime": (("legs", 0, "expiry"), "2026-10-13T00:00"),
        "limit=1E+3": (("risk_limits", "max_loss"), "1E+3"), "limit=-5": (("risk_limits", "max_loss"), "-5"),
        "limit=sentence": (("risk_limits", "max_loss"), "5000 rupees"),
        "preference=space": (("preferences", "objective"), "a b"),
        "preference=65 chars": (("preferences", "objective"), "a" * 65),
    }
    for number_slot in ("contract_id", "quantity"):
        for label, value in (("22950.35", 22950.35), ("0", 0), ("-1", -1), ("true", True), ("'65'", "65")):
            values[f"{number_slot}={label}"] = (("legs", 0, number_slot), value)
    values["quantity=1000001"] = (("legs", 0, "quantity"), 1_000_001)
    cases.extend((label, _with(full, path, value)) for label, (path, value) in values.items())
    return cases


ITEM_LEG = {"action": "SELL", "instrument": "CE", "strike": "22800", "expiry": "2026-10-13", "quantity": 65}
ITEM_EXAMPLES = {
    "underlying": {"kind": "underlying", "old": "NIFTY", "new": "SENSEX"},
    "leg_removed": {"kind": "leg_removed", "leg": ITEM_LEG},
    "leg_added": {"kind": "leg_added", "leg": dict(ITEM_LEG, instrument="PE")},
    "quantity": {"kind": "quantity", "leg": ITEM_LEG, "before": 65},
    "field-risk_limits": {"kind": "field", "map": "risk_limits", "name": "max_loss", "old": None, "new": "5000.5"},
    "field-preferences": {"kind": "field", "map": "preferences", "name": "objective", "old": "income", "new": None},
    "field-rules_ref": {"kind": "field", "map": "rules_ref", "name": "rules_ref", "old": None, "new": "rules-set_1.v2"},
    "legs_reordered": {"kind": "legs_reordered"},
    "replaced_unreadable": {"kind": "replaced_unreadable"},
    "restored": {"kind": "restored", "seq": 3},
}
ITEM_SLOTS = {
    "underlying": {"kind": S, "old": S, "new": S}, "leg_removed": {"kind": S}, "leg_added": {"kind": S},
    "quantity": {"kind": S, "before": NUM}, "legs_reordered": {"kind": S}, "replaced_unreadable": {"kind": S},
    "restored": {"kind": S, "seq": NUM},
}
for _k, _item in ITEM_EXAMPLES.items():
    if _k.startswith("field"):
        ITEM_SLOTS[_k] = {"kind": S, "map": S, "name": S, "old": N | S, "new": N | S}
ITEM_LEG_ALLOWED = {k: v for k, v in LEG_ALLOWED.items() if k != "contract_id"}


def item_cases() -> list[tuple[str, Any]]:
    cases: list[tuple[str, Any]] = []
    for label, item in ITEM_EXAMPLES.items():
        doc = [item]
        positions: list[tuple[tuple, frozenset]] = [((), A), ((0,), O)]
        positions.extend(((0, slot), allowed) for slot, allowed in ITEM_SLOTS[label].items())
        if "leg" in item:
            positions.append(((0, "leg"), O))
            positions.extend(((0, "leg", k), a) for k, a in ITEM_LEG_ALLOWED.items())
        cases.extend((f"{label}:{n}", d) for n, d in type_cases(doc, positions))
        object_paths = [(0,)] + ([(0, "leg")] if "leg" in item else [])
        cases.extend((f"{label}:{n}", d) for n, d in key_cases(doc, object_paths, set(object_paths)))
    good = [ITEM_EXAMPLES["underlying"]]
    values = {
        "empty list": [], "unknown kind": [{"kind": "ltp"}], "kind wrong case": [{"kind": "Underlying", "old": "NIFTY",
                                                                                 "new": "SENSEX"}],
        "underlying BANKNIFTY": [dict(ITEM_EXAMPLES["underlying"], new="BANKNIFTY")],
        "leg strike sentence": [dict(ITEM_EXAMPLES["leg_removed"], leg=dict(ITEM_LEG, strike="LTP 22950.35"))],
        "leg quantity fractional": [dict(ITEM_EXAMPLES["leg_removed"], leg=dict(ITEM_LEG, quantity=22950.35))],
        "leg quantity 0": [dict(ITEM_EXAMPLES["leg_removed"], leg=dict(ITEM_LEG, quantity=0))],
        "leg expiry 2026-02-30": [dict(ITEM_EXAMPLES["leg_removed"], leg=dict(ITEM_LEG, expiry="2026-02-30"))],
        "leg FUT with a strike": [dict(ITEM_EXAMPLES["leg_removed"], leg=dict(ITEM_LEG, instrument="FUT"))],
        "leg CE without a strike": [dict(ITEM_EXAMPLES["leg_removed"], leg=dict(ITEM_LEG, strike=None))],
        "before fractional": [dict(ITEM_EXAMPLES["quantity"], before=22950.35)],
        "before 0": [dict(ITEM_EXAMPLES["quantity"], before=0)],
        "before -1": [dict(ITEM_EXAMPLES["quantity"], before=-1)],
        "seq 0": [dict(ITEM_EXAMPLES["restored"], seq=0)],
        "seq 1.5": [dict(ITEM_EXAMPLES["restored"], seq=1.5)],
        "field map unknown": [dict(ITEM_EXAMPLES["field-preferences"], map="ltp")],
        "field name outside the map": [dict(ITEM_EXAMPLES["field-preferences"], name="max_loss")],
        "field limit sentence": [dict(ITEM_EXAMPLES["field-risk_limits"], new="5000 rupees")],
        "field limit exponent": [dict(ITEM_EXAMPLES["field-risk_limits"], new="1E+3")],
        "field preference sentence": [dict(ITEM_EXAMPLES["field-preferences"], new="LTP 22950.35")],
        "field rules_ref sentence": [dict(ITEM_EXAMPLES["field-rules_ref"], new="LTP 22950.35")],
        "item is a string": ["legs_reordered"], "two items one bad": good + [{"kind": "legs_reordered", "x": 1}],
    }
    cases.extend((f"value:{n}", v) for n, v in values.items())
    return cases


async def _db_verdict(conn, sql: str, params: dict) -> tuple[str | None, str]:
    """(sqlstate, message) when PostgreSQL refuses the write, (None, '') when it accepts it. Always rolled back."""
    savepoint = await conn.begin_nested()
    try:
        await conn.execute(text(sql), params)
        return None, ""
    except DBAPIError as err:
        return getattr(err.orig, "sqlstate", None), str(err.orig)
    finally:
        await savepoint.rollback()


def _full(good: str) -> dict:
    doc = json.loads(good)
    doc.update(rules_ref="rules-set_1.v2",
               risk_limits={"max_loss": "9000.50", "max_capital": "250000", "max_margin": "0"},
               preferences={"objective": "income", "market_view": "range-bound", "risk_preference": "low",
                            "capital": "250000", "expected_range_low": "22400", "expected_range_high": "23000.5"})
    return doc


async def test_generated_definition_matrix_is_refused_on_strategies_and_history(app_engine):
    """Every position x every wrong JSON type (and the correct value wrapped in an array), plus key sets and value
    predicates, is refused with 23514 by PostgreSQL itself on BOTH tables, as ofo_app; the real documents insert."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            good, _, strategy_id = await _iron_condor_text(conn)
            full = _full(good)
            cases = definition_cases(full)
            assert len(cases) >= 150, len(cases)
            print(f"generated definition cases: {len(cases)}")
            accepted_ok = [await _db_verdict(conn, INSERT_DEFINITION, {"u": _user(), "d": json.dumps(d)})
                           for d in (json.loads(good), full)]
            assert accepted_ok == [(None, "")] * 2, accepted_ok
            wrong: list[str] = []
            for label, doc in cases:
                state, _ = await _db_verdict(conn, INSERT_DEFINITION, {"u": _user(), "d": json.dumps(doc)})
                if state != CHECK_VIOLATION:
                    wrong.append(f"strategies {label}: {state}")
                state, _ = await _db_verdict(conn, INSERT_HISTORY, {"id": strategy_id, "s": REORDERED,
                                                                    "d": json.dumps(doc)})
                if state != CHECK_VIOLATION:
                    wrong.append(f"strategy_history {label}: {state}")
            per_table = {t: sum(w.startswith(t + " ") for w in wrong) for t in ("strategies", "strategy_history")}
            assert not wrong, (f"{len(wrong)} of {2 * len(cases)} generated cases not refused {per_table}:\n"
                               + "\n".join(wrong[:40]))
        finally:
            await trans.rollback()


async def test_the_trigger_validator_is_what_refuses(app_engine):
    """The refusal comes from the guard's positive validator (not a leftover CHECK): its message names the shape."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            good, _, strategy_id = await _iron_condor_text(conn)
            bad = _with(json.loads(good), ("preferences",), {"objective": ["income"]})
            for sql, params in ((INSERT_DEFINITION, {"u": _user(), "d": json.dumps(bad)}),
                                (INSERT_HISTORY, {"id": strategy_id, "s": REORDERED, "d": json.dumps(bad)}),
                                (INSERT_HISTORY, {"id": strategy_id, "s": json.dumps([{"kind": "ltp"}]), "d": good})):
                state, message = await _db_verdict(conn, sql, params)
                assert state == CHECK_VIOLATION and "closed shape" in message, (state, message)
        finally:
            await trans.rollback()


async def test_generated_change_item_matrix_is_refused_and_each_kinds_example_accepted(app_engine):
    """Every kind x every slot x every wrong JSON type, key sets and value predicates on change_summary."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            good, _, strategy_id = await _iron_condor_text(conn)
            cases = item_cases()
            assert len(cases) >= 250, len(cases)
            print(f"generated change-item cases: {len(cases)}")
            refused_accepted = []
            for label, item in ITEM_EXAMPLES.items():
                got = await _db_verdict(conn, INSERT_HISTORY, {"id": strategy_id, "s": json.dumps([item]), "d": good})
                if got != (None, ""):
                    refused_accepted.append(f"example {label} refused: {got}")
            wrong = list(refused_accepted)
            for label, doc in cases:
                state, _ = await _db_verdict(conn, INSERT_HISTORY, {"id": strategy_id, "s": json.dumps(doc), "d": good})
                if state != CHECK_VIOLATION:
                    wrong.append(f"{label}: {state}")
            assert not wrong, f"{len(wrong)} of {len(cases)} generated cases wrong:\n" + "\n".join(wrong[:40])
        finally:
            await trans.rollback()


async def test_database_and_domain_agree_on_every_generated_case(app_engine):
    """The database refuses a definition (or change summary) exactly when ofo.strategy.stored_form / render_change_items
    does; the real Iron Condor and every allowed name are accepted by both."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            good, ids, strategy_id = await _iron_condor_text(conn)
            resolve = await store.catalogue_resolver(conn, list(ids.values()))
            full = _full(good)
            disagree = []

            def domain_definition(doc) -> bool:
                try:
                    sf.from_document(sf.parse_json(json.dumps(doc)), resolve)
                    return True
                except sf.StoredFormError:
                    return False

            def domain_items(doc) -> bool:
                try:
                    sf.summary_text(doc)  # the write path: render_change_items plus the 1..N size rule
                    return True
                except sf.StoredFormError:
                    return False

            for label, doc in [("real iron condor", json.loads(good)), ("every allowed name", full)] + \
                    definition_cases(full):
                state, _ = await _db_verdict(conn, INSERT_DEFINITION, {"u": _user(), "d": json.dumps(doc)})
                if (state is None) != domain_definition(doc):
                    disagree.append(f"definition {label}: database={state} domain={domain_definition(doc)}")
            for label, doc in [(f"example {k}", [v]) for k, v in ITEM_EXAMPLES.items()] + item_cases():
                state, _ = await _db_verdict(conn, INSERT_HISTORY, {"id": strategy_id, "s": json.dumps(doc), "d": good})
                if (state is None) != domain_items(doc):
                    disagree.append(f"items {label}: database={state} domain={domain_items(doc)}")
            assert not disagree, f"{len(disagree)} disagreements:\n" + "\n".join(disagree[:40])
        finally:
            await trans.rollback()


async def test_futures_leg_takes_a_null_strike_only(app_engine):
    """The strike is null for FUT and a decimal string otherwise; the database holds no catalogue, so a FUT leg is
    checked on its own terms."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            good, _, strategy_id = await _iron_condor_text(conn)
            doc = json.loads(good)
            fut = dict(doc["legs"][0], instrument="FUT", strike=None, contract_id=99999)
            ok = _with(doc, ("legs",), [fut])
            assert (await _db_verdict(conn, INSERT_DEFINITION, {"u": _user(), "d": json.dumps(ok)}))[0] is None
            bad = _with(ok, ("legs", 0, "strike"), "22800")
            assert (await _db_verdict(conn, INSERT_DEFINITION, {"u": _user(), "d": json.dumps(bad)}))[0] == \
                CHECK_VIOLATION
            item = {"kind": "leg_added", "leg": dict(ITEM_LEG, instrument="FUT", strike=None)}
            assert (await _db_verdict(conn, INSERT_HISTORY, {"id": strategy_id, "s": json.dumps([item]), "d": good})
                    )[0] is None
            item["leg"]["strike"] = "22800"
            assert (await _db_verdict(conn, INSERT_HISTORY, {"id": strategy_id, "s": json.dumps([item]), "d": good})
                    )[0] == CHECK_VIOLATION
        finally:
            await trans.rollback()


async def test_update_path_validates_too(app_engine):
    """The same validator runs on UPDATE of a definition (a bad document is refused even with its history entry in)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            good, _, strategy_id = await _iron_condor_text(conn)
            await conn.execute(text(INSERT_HISTORY), {"id": strategy_id, "s": REORDERED, "d": good})
            bad = _with(json.loads(good), ("legs",), [[json.loads(good)["legs"][0]]])
            state, _ = await _db_verdict(conn, "UPDATE public.strategies SET definition = CAST(:d AS JSONB) "
                                               "WHERE id = :id", {"d": json.dumps(bad), "id": strategy_id})
            assert state == CHECK_VIOLATION, state
        finally:
            await trans.rollback()


async def test_validators_are_pinned_and_the_app_role_has_no_execute(app_engine, admin_engine):
    """Both validators (and the shared leg helper) match their md5 pins, are owned by the table owner and are not
    executable by ofo_app (the SECURITY DEFINER guards call them)."""
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions" / "0010_strategy_schema_version.py"
    spec = importlib.util.spec_from_file_location("m0010_for_validator_pins", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pins = module.NEW_PINS  # 0010 re-created the validators (0008's pins are the downgrade's)
    assert len(pins) == 3, pins
    async with admin_engine.connect() as conn:
        for signature, pinned in pins.items():
            got = (await conn.execute(text("SELECT md5(prosrc) FROM pg_proc WHERE oid = to_regprocedure(:s)"),
                                      {"s": signature})).scalar_one_or_none()
            assert got == pinned, signature
            assert (await conn.execute(text("SELECT has_function_privilege(current_user, to_regprocedure(:s), "
                                            "'EXECUTE')"), {"s": signature})).scalar_one()
    async with app_engine.connect() as conn:
        for signature in pins:
            assert not (await conn.execute(text("SELECT has_function_privilege(current_user, "
                                                "to_regprocedure(:s), 'EXECUTE')"), {"s": signature})).scalar_one()
