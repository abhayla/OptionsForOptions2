"""#380-2c: the guards #380-2 added that no database-free test caught when removed (mutation table, 2026-10-20).

Each test names the guard it pins (file and what the guard refuses). They run without a database: a scripted
connection answers the few statements a guard's neighbours run, and a guard that is deleted lets the call continue
into the next statement, which the test sees as a different outcome than the refusal.
Basis: REQ-060 AC-3/AC-5/AC-6;
Q222; Q224; ADR-109 (4); ADR-083.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ofo.engine import Instrument
from ofo_app import execution_plan_store as eps
from ofo_app import next_day_resolution as nd
from ofo_app import reconcile_attribution as ra
from ofo_app import reconciliation_store as rs
from ofo_app import route_reconciliation as rr
from sqlalchemy.exc import DBAPIError

from tests_app.test_route_reconciliation import AT, KEY, USER, _catalogue

KEY_TEXT_OK = "NSE_FO:51392"


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def first(self):
        return self.value


class _Script:
    """A connection that answers in order from ``answers`` and records every statement; past the script fails."""

    def __init__(self, *answers, raise_on_insert=None):
        self.answers, self.statements, self.raise_on_insert = list(answers), [], raise_on_insert

    async def execute(self, statement, params=None):
        text_ = str(statement)
        self.statements.append(text_)
        if self.raise_on_insert is not None and "INSERT" in text_.upper():
            raise self.raise_on_insert
        assert self.answers, f"statement past the script: {text_}"
        return _Result(self.answers.pop(0))

    def begin_nested(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _run(coro):
    return asyncio.run(coro)


async def _locked(conn, user_ref, strategy_id):
    return strategy_id


@pytest.fixture
def stores(monkeypatch):
    monkeypatch.setattr(rs, "_lock", _locked)
    monkeypatch.setattr(eps, "_lock", _locked)


# ---- route_reconciliation ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("user", ["", "   ", None, 7])
def test_lock_user_refuses_a_missing_user_before_any_statement(user):
    conn = _Script()
    with pytest.raises(ra.AttributionError):
        _run(rr.lock_user(conn, user))
    assert conn.statements == []


def test_reconcile_account_refuses_an_unknown_source_before_the_lock():
    conn = _Script()
    with pytest.raises(ra.AttributionError):
        _run(rr.reconcile_account(conn, USER, _catalogue(), {}, [], at=AT, clock=lambda: AT, source="bogus"))
    assert conn.statements == []


# ---- reconcile_attribution --------------------------------------------------------------------------------------

def test_a_contract_without_an_expiry_date_is_refused_not_compared():
    with pytest.raises(ra.AttributionError):
        ra._expired(("NIFTY", Instrument.CE, Decimal("24000"), None), AT)


def test_key_text_refuses_a_contract_the_catalogue_does_not_list():
    other = ("NIFTY", Instrument.CE, Decimal("99999"), KEY[3])
    with pytest.raises(ra.AttributionError):
        ra.key_text(_catalogue(), other)
    assert ra.key_text(_catalogue(), KEY) == KEY_TEXT_OK


def test_a_store_that_answers_a_non_sequence_for_a_strategys_mismatches_is_refused():
    async def mismatches_for(conn, user_ref, strategy_id):
        return iter(())  # iterable, but not the sequence the store promises: refused, never looped over

    reader = SimpleNamespace(mismatches_for=mismatches_for)
    with pytest.raises(ra.AttributionError):
        _run(ra._stored_unresolved(reader, ra.Account(None, USER), SimpleNamespace(id=9, underlying="NIFTY"),
                                   _catalogue(), ({}, set())))


def test_next_day_resolution_refuses_sources_that_are_not_sources():
    with pytest.raises(ra.AttributionError):
        _run(nd.resolve_earlier_day_plans(ra.Account(None, USER), {}, {}, [], "not sources"))  # type: ignore[arg-type]


# ---- reconciliation_store: the checks a malformed mismatch or resolution meets before the database ----------------

@pytest.mark.parametrize("value", [True, 1.5, "7", rs.MAX_UNITS + 1, -rs.MAX_UNITS - 1])
def test_units_outside_the_closed_range_or_not_integers_are_refused(value):
    with pytest.raises(rs.ReconciliationStoreError):
        rs._units(value, "units", rs.BAD_MISMATCH)


@pytest.mark.parametrize("value", [[1], [("a", 1)], "text", None])
def test_a_report_must_be_a_mapping(value):
    with pytest.raises(rs.ReconciliationStoreError):
        rs._report(value)


def test_a_report_over_the_cap_is_refused_before_the_database_and_as_stored():
    with pytest.raises(rs.ReconciliationStoreError):
        rs._report({"x": "y" * (rs.MAX_REPORT_BYTES + 1)})
    with pytest.raises(rs.ReconciliationStoreError):
        _run(rs._report_fits(_Script(rs.MAX_REPORT_BYTES + 1), "{}"))
    _run(rs._report_fits(_Script(rs.MAX_REPORT_BYTES), "{}"))


@pytest.mark.parametrize("note", ["", "  ", " a", "a ", "x" * (rs.MAX_TEXT + 1), 5])
def test_a_note_must_be_trimmed_text_within_the_cap(note):
    with pytest.raises(rs.ReconciliationStoreError):
        rs._note(note)


@pytest.mark.parametrize("user", ["", None, 3, "u" * (rs.MAX_TEXT + 1)])
def test_a_user_reference_must_be_text_within_the_cap(user):
    with pytest.raises(rs.ReconciliationStoreError):
        rs._user_ref(user)


def _mismatch(conn, **over):
    args = {"contract_key": KEY_TEXT_OK, "expected_units": 65, "zerodha_units": 0, "report": {"k": 1},
            "source": "app_start"}
    args.update(over)
    return _run(rs.record_mismatch(conn, USER, 9, **args))


def test_an_agreeing_pair_is_not_a_mismatch(stores):
    conn = _Script(None, 10, 5)
    with pytest.raises(rs.ReconciliationStoreError):
        _mismatch(conn, expected_units=65, zerodha_units=65)
    assert conn.statements == []


@pytest.mark.parametrize("source", ["bogus", None, 3])
def test_a_mismatch_source_outside_the_closed_list_is_refused(stores, source):
    conn = _Script(None, 10, 5)
    with pytest.raises(rs.ReconciliationStoreError):
        _mismatch(conn, source=source)
    assert conn.statements == []


def _resolution(conn, **over):
    args = {"action": rs.BASKET, "note": None, "zerodha_net_now": None}
    mismatch_id = over.pop("mismatch_id", 1)
    args.update(over)
    return _run(rs.record_resolution(conn, USER, 9, mismatch_id, **args))


@pytest.mark.parametrize("mismatch_id", [0, True, 2**63, "1"])
def test_a_resolution_of_a_malformed_mismatch_id_is_not_found(stores, mismatch_id):
    conn = _Script(SimpleNamespace(settled=False, contract_key=KEY_TEXT_OK), False)
    with pytest.raises(rs.ReconciliationStoreError):
        _resolution(conn, mismatch_id=mismatch_id)
    assert conn.statements == []


def test_a_resolution_action_outside_the_closed_list_is_refused(stores):
    conn = _Script(SimpleNamespace(settled=False, contract_key=KEY_TEXT_OK), False)
    with pytest.raises(rs.ReconciliationStoreError):
        _resolution(conn, action="bogus")
    assert conn.statements == []


def test_a_resolution_of_a_mismatch_that_is_not_the_strategys_is_not_found(stores):
    conn = _Script(None)
    with pytest.raises(rs.ReconciliationStoreError) as err:
        _resolution(conn)
    assert err.value.code == rs.NOT_FOUND


def test_a_settled_mismatch_takes_no_further_resolution(stores):
    conn = _Script(SimpleNamespace(settled=True, contract_key=KEY_TEXT_OK), False)
    with pytest.raises(rs.ReconciliationStoreError) as err:
        _resolution(conn)
    assert err.value.code == rs.ALREADY_RESOLVED
    assert len(conn.statements) == 1


@pytest.mark.parametrize("net", [None, 65, -65])
def test_kite_flat_is_refused_unless_zerodhas_net_now_is_zero(stores, net):
    conn = _Script(SimpleNamespace(settled=False, contract_key=KEY_TEXT_OK), False, None)
    with pytest.raises(rs.ReconciliationStoreError) as err:
        _resolution(conn, action=rs.KITE_FLAT, zerodha_net_now=net)
    assert err.value.code == rs.BAD_RESOLUTION
    assert len(conn.statements) == 1


@pytest.mark.parametrize("action", list(rs.SETTLING))
def test_q224_a_settling_action_is_refused_while_another_strategy_holds_the_contract(stores, action):
    conn = _Script(SimpleNamespace(settled=False, contract_key=KEY_TEXT_OK), True, None)
    with pytest.raises(rs.ReconciliationStoreError) as err:
        _resolution(conn, action=action, zerodha_net_now=0)
    assert err.value.code == rs.BAD_RESOLUTION
    assert len(conn.statements) == len(("mismatch", "shared"))


class _Orig(Exception):
    def __init__(self, sqlstate, text):
        super().__init__(text)
        self.sqlstate = sqlstate


def test_a_second_settling_row_is_already_resolved_but_any_other_database_error_passes_through(stores):
    clash = DBAPIError("INSERT", {}, _Orig(rs._UNIQUE_VIOLATION, rs._RESOLUTION_KEYS[1]))
    with pytest.raises(rs.ReconciliationStoreError) as err:
        _resolution(_Script(SimpleNamespace(settled=False, contract_key=KEY_TEXT_OK), False, raise_on_insert=clash))
    assert err.value.code == rs.ALREADY_RESOLVED
    for orig in (_Orig("23503", "foreign key"), _Orig(rs._UNIQUE_VIOLATION, "some_other_unique_index")):
        other = DBAPIError("INSERT", {}, orig)
        with pytest.raises(DBAPIError):
            _resolution(_Script(SimpleNamespace(settled=False, contract_key=KEY_TEXT_OK), False, raise_on_insert=other))


# ---- execution_plan_store.close_plan: unresolved_from_positions -------------------------------------------------

def _close(conn, filled=None):
    return _run(eps.close_plan(conn, USER, 9, 1, reason=eps.UNRESOLVED, filled=filled))


def test_unresolved_from_positions_takes_no_fills_even_with_a_stored_mismatch(stores, monkeypatch):
    async def some_unresolved(conn, strategy_id):
        return True

    monkeypatch.setattr(eps.reconciliation_store, "unresolved_locked", some_unresolved)
    conn = _Script("open")
    with pytest.raises(eps.PlanStoreError) as err:
        _close(conn, {"OFS9V1L0": 65})
    assert err.value.code == eps.BAD_PLAN
    assert len(conn.statements) == 1  # nothing written after the refusal


def test_unresolved_from_positions_needs_a_stored_mismatch_recorded_first(stores, monkeypatch):
    async def none_unresolved(conn, strategy_id):
        return False

    monkeypatch.setattr(eps.reconciliation_store, "unresolved_locked", none_unresolved)
    conn = _Script("open")
    with pytest.raises(eps.PlanStoreError) as err:
        _close(conn)
    assert err.value.code == eps.BAD_PLAN
    assert len(conn.statements) == 1


# ---- the routes' use of the one verdict (no database: the real reconciler on the real 2026-10-19 round trip) ---------

@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")  # the fake store reader is accepted only here


def _route_world(plans, positions, others=None, blocked=None):
    import dataclasses  # noqa: PLC0415

    from ofo_app.routes import execution_return as route  # noqa: PLC0415

    from tests_app.test_route_reconciliation import SID, _attribute  # noqa: PLC0415
    attribution, read = _attribute(plans, positions, others)
    if blocked is not None:
        attribution = dataclasses.replace(attribution, blocked=blocked)
    req = SimpleNamespace(strategy_id=SID, now=AT)
    return route, req, route._World(_catalogue(), "NIFTY", rr.Verdict(attribution, read, (), ()))


def _flat():
    from tests_app.test_route_reconciliation import _plans, _recorded  # noqa: PLC0415
    return _plans((1, 2)), _recorded("positions-2026-10-19-roundtrip")


def _quiet_book(monkeypatch, route):
    monkeypatch.setattr(route.er, "drifted", lambda history, book: {})
    monkeypatch.setattr(route.er, "pnl_or_none", lambda fills: None)
    return SimpleNamespace(external=[], fills=[])


def test_an_exit_is_not_clean_while_the_one_verdict_blocks_the_strategy():
    plans_, flat = _flat()
    route, req, world = _route_world(plans_, flat)
    assert route._exit_clean(req, plans_, world) is True
    route, req, world = _route_world(plans_, flat, blocked=frozenset({"9"}))
    assert route._exit_clean(req, plans_, world) is False


def test_the_answer_is_blocked_exactly_when_the_verdict_blocks(monkeypatch):
    plans_, flat = _flat()
    route, req, world = _route_world(plans_, flat)
    book = _quiet_book(monkeypatch, route)
    assert route._answer(req, plans_, {}, book, world).blocked is False
    route, req, world = _route_world(plans_, flat, blocked=frozenset({"9"}))
    assert route._answer(req, plans_, {}, book, world).blocked is True


def test_a_hand_exit_shows_its_mismatch_kind_on_its_own_strategys_contract_only():
    from tests_app.test_route_reconciliation import _plans, _recorded  # noqa: PLC0415
    plans_ = _plans((1,))
    route, req, world = _route_world(plans_, _recorded("positions-2026-10-19-roundtrip"))
    (key,) = route._keys(plans_, world)
    assert route._kind(world, "9", key) == "recon_missing_platform_position"
    assert route._kind(world, "10", key) is None  # another strategy's id is not named by this mismatch
    (row,) = route._contracts(req, plans_, world)
    assert row["mismatch"] == "recon_missing_platform_position"


def test_another_strategys_open_plan_shows_as_undecided_and_counts_as_flagged(monkeypatch):
    from tests_app.test_route_reconciliation import _other_plan  # noqa: PLC0415
    plans_, flat = _flat()
    route, req, world = _route_world(plans_, flat, {10: (_other_plan("open", None),)})
    (row,) = route._contracts(req, plans_, world)
    assert row["mismatch"] is None
    assert row["reconciliation_reason"] == route.er.OTHER_UNSETTLED
    book = _quiet_book(monkeypatch, route)
    assert route._answer(req, plans_, {}, book, world).mismatches == 1


def test_a_plan_closed_unresolved_after_an_exit_does_not_undo_exited():
    from ofo_app.execution_plan_store import StoredPlan  # noqa: PLC0415

    from tests_app.test_route_reconciliation import SID, _plans  # noqa: PLC0415
    route, _, _ = _route_world(*_flat())
    later = StoredPlan(SID, 3, "ENTRY", "closed", (), AT, AT, route.plans.UNRESOLVED)
    assert route._strategy_state((*_plans((1, 2)), later), {}) == "exited"


@pytest.mark.parametrize(("error", "template"), [(ra.AttributionError("x"), "gate_reconciliation_mismatch"),
                                                 (ValueError("x"), "gate_broker_unconfirmed")])
def test_the_return_route_answers_each_unreadable_state_with_its_own_refusal(monkeypatch, error, template):
    from ofo_app.routes import execution_return as route  # noqa: PLC0415

    async def fails(*args, **kwargs):
        raise error

    monkeypatch.setattr(route.rr, "reconcile_account", fails)
    req = SimpleNamespace(db=None, user_ref=USER, now=AT, now_clock=lambda: AT)
    with pytest.raises(type(route._refuse(template))) as err:
        _run(route._reconcile(req, _catalogue(), SimpleNamespace(positions={}, orders=[])))
    assert repr(err.value.message) == repr(route._refuse(template).message)


def test_the_execute_press_blocks_on_an_unreadable_reconciliation_and_passes_the_verdict_on(monkeypatch):
    from ofo_app.routes import execute as route  # noqa: PLC0415

    class Reads:
        def fetch_positions(self):
            return {}

    req = SimpleNamespace(db=None, user_ref=USER, now=AT, clock=lambda: AT, session=SimpleNamespace(reads=Reads()))
    held = SimpleNamespace(order_rows=[])
    for error in (route.KiteReadError("x"), route.KiteReplyError("x"), ValueError("x")):
        async def fails(*args, _e=error, **kwargs):
            raise _e

        monkeypatch.setattr(route.rr, "reconcile_account", fails)
        assert _run(route._reconcile(req, held, _catalogue())) == (None, None)  # not "nothing blocked"

    async def blocked(*args, **kwargs):
        return SimpleNamespace(positions="P", attribution=SimpleNamespace(blocked=frozenset({"9"})))

    monkeypatch.setattr(route.rr, "reconcile_account", blocked)
    assert _run(route._reconcile(req, held, _catalogue())) == ("P", frozenset({"9"}))
