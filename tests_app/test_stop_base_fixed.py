"""P3 (ADR-330 (1), refining ADR-247 and ADR-230): a plan's stop amounts are fixed at entry.

The rupee amounts of the "% of max loss" stop and the "2x the credit received" stop are worked out ONCE from the trade
as entered (paper_orders kind 'open'), stored on the plan row, and read by every stop check. Closing a side or a leg
does not move them; an adjustment ('add' orders, a roll) does not move them either (plan question Q4, built as
recommended (a): ``settings_in_force.STOP_BASE_KINDS`` is the one place that says so); only a plan edit recomputes.

Real case (25 Nov, strategy S-21): an iron condor, 1 lot of NIFTY (lot 65), call spread 24000/24100 and put spread
23600/23500, width 100 points on each side. Entry premiums per unit: call 90 sold / 55 bought (net 35), put 70 sold /
45 bought (net 25), so the credit is 60 points x 65 = Rs 3,900 and the max loss is (100 - 60) x 65 = Rs 2,600.
Plan stop 15.4 % of max loss = Rs 400.40; 2x credit = Rs 7,800. Then the call side closes (buy back 24000 at 20,
sell 24100 at 10: two 'exit' orders): the old code re-read the live legs (a put spread) and the lines MOVED.

No database for the readers' seams (as test_d04_entry_shape): the paper book rows, the contract rows and the plan store
are faked; ``_tracked_on``, ``settings_in_force.money_inputs`` and ``stops_of`` are the real code.
"""
from __future__ import annotations

import asyncio
import copy
import datetime
import json
import pathlib
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.adjustment import stop_lines as sl
from ofo_app import adjustment_check as check
from ofo_app import adjustment_readers as readers
from ofo_app import paper_book, playbook_store, tracked_contracts
from ofo_app import settings_in_force as sif
from ofo_app.routes import adjustment_plan as ap
from sqlalchemy import text
from test_strategy_store import _user, _with_draft

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAYBOOKS = json.loads((ROOT / "backend/ofo/adjustment/system_playbooks.json").read_text())["playbooks"]
IC = next(p["body"] for p in PLAYBOOKS if p["strategy_type"] == "ic")
EXPIRY = datetime.date(2026, 11, 26)
LOT = 65
PUT_SPREAD_LEGS, IC_LEGS = 2, 4
T0 = datetime.datetime(2026, 11, 25, 4, 0, tzinfo=datetime.UTC)
T1, T2 = T0 + datetime.timedelta(hours=1), T0 + datetime.timedelta(hours=2)
NOW = datetime.datetime(2026, 11, 25, 9, 0, tzinfo=datetime.UTC)
# contract id -> (type, strike)
CONTRACTS = {1: ("CE", D(24000)), 2: ("CE", D(24100)), 3: ("PE", D(23600)), 4: ("PE", D(23500))}
MAX_LOSS, CREDIT = D("2600"), D("3900")
STOP_PCT = D("15.4")
LINE_PCT, LINE_CREDIT = D("400.40"), D("7800")


def _contract(cid: int) -> SimpleNamespace:
    kind, strike = CONTRACTS[cid]
    c = SimpleNamespace(instrument_type=kind, strike=strike, expiry=EXPIRY, lot_size=LOT, name="NIFTY")
    listed = SimpleNamespace(contract=c, broker_refs=[SimpleNamespace(broker_symbol=f"NIFTY{kind}{strike}")])
    return SimpleNamespace(contract_id=cid, stored=SimpleNamespace(listed=listed), identity=str(cid))


def _order(cid: int, side: str, kind: str, at: datetime.datetime, price: str) -> SimpleNamespace:
    return SimpleNamespace(order=paper_book.NewOrder(cid, side, LOT, D(price), kind, at))


ENTRY = [_order(1, "SELL", "open", T0, "90"), _order(2, "BUY", "open", T0, "55"),
         _order(3, "SELL", "open", T0, "70"), _order(4, "BUY", "open", T0, "45")]
CALL_SIDE_CLOSED = [_order(1, "BUY", "exit", T1, "20"), _order(2, "SELL", "exit", T1, "10")]
ADJUSTMENT = [_order(1, "BUY", "exit", T1, "20"), _order(2, "SELL", "exit", T1, "10"),
              _order(1, "SELL", "add", T2, "30"), _order(2, "BUY", "add", T2, "15")]  # a roll: the call side re-entered


def plan_body(pct: D = STOP_PCT) -> dict:
    body = copy.deepcopy(IC)
    body["triggers"][sl.TRIGGER_MAX_LOSS]["weekly"] = [str(pct)] * 3
    body["triggers"][sl.TRIGGER_MAX_LOSS]["monthly"] = [str(pct)] * 3
    return body


class Store(SimpleNamespace):
    """What the faked plan store holds: ``plan`` (None = no plan row), ``orders``, and every backfill write."""


@pytest.fixture
def seams(monkeypatch):
    store = Store(plan=None, orders=[], writes=[])

    async def load_owned(_db, _user, _sid):
        return store.orders

    async def resolve(_db, ids):
        return [_contract(i) for i in ids]

    async def plan_for(*_a):
        return store.plan

    async def backfill(_sid, value):  # the plan store's own write: only where nothing is stored yet
        store.writes.append(value)
        if store.plan is not None and store.plan.stop_base is None:
            store.plan.stop_base = value
            return True
        return False

    async def adr247(_db):
        return None
    monkeypatch.setattr(paper_book, "load_owned", load_owned)
    monkeypatch.setattr(tracked_contracts, "resolve", resolve)
    monkeypatch.setattr(playbook_store, "plan_for", plan_for)
    monkeypatch.setattr(playbook_store, "adr247_saved_at", adr247)
    monkeypatch.setattr(playbook_store, "backfill_stop_base", backfill, raising=False)
    return store


def _plan(stop_base=None, body=None) -> SimpleNamespace:
    return SimpleNamespace(body=body or plan_body(), playbook_id=9, accepted_at=T0, stop_base=stop_base)


def _read(store, orders):
    store.orders = orders
    return asyncio.run(readers._tracked_on(None, 21, None))


MARKET = SimpleNamespace(chain=(), forward=None, years=None, vol=None, expiry_kind="weekly", now=NOW)


def lines_of(tracked, body=None) -> dict[str, sif.StopInForce]:
    """The stop lines the check reads for ``tracked``: the real ``money_inputs`` then the real ``stops_of``."""
    resolved = check.Resolved("plan", body or plan_body(), 9, None, False, saved_before_adr247=False)
    stops = sif.stops_of(resolved, sif.money_inputs(tracked, MARKET, None), sif.FIRST_STAGE)
    return {x.kind: x for x in stops.lines}


def amounts(tracked) -> tuple[D | None, D | None]:
    got = lines_of(tracked)
    return got[sif.STOP_MAX_LOSS].amount, got[sif.STOP_CREDIT].amount


# ---- item 1: the core ----------------------------------------------------------------------------------------------
def test_s21_call_side_closed_keeps_stop(seams):
    """CORE. Entered: 15.4 % of Rs 2,600 = Rs 400.40 and 2x Rs 3,900 = Rs 7,800. The call side then closes (two
    'exit' orders): the two lines still read Rs 400.40 and Rs 7,800 (the live put spread alone would give other
    figures)."""
    seams.plan = _plan()
    assert amounts(_read(seams, ENTRY)) == (LINE_PCT, LINE_CREDIT)
    after = _read(seams, ENTRY + CALL_SIDE_CLOSED)
    assert len(after.position.legs) == PUT_SPREAD_LEGS  # the live book is a put spread now
    assert amounts(after) == (LINE_PCT, LINE_CREDIT)


# ---- the stored base: what each answer state does --------------------------------------------------------------------
def _stored(max_loss="1000", credit="500", source="entry") -> dict:
    return {"max_loss": max_loss, "credit": credit, "taken_at": T0.isoformat(), "source": source}


def test_stop_base_is_worked_out_from_entry_orders_only_and_the_choice_is_one_constant():
    """Q4 (a): the one place that says which order kinds make the base."""
    assert sif.STOP_BASE_KINDS == ("open",)


def test_stored_base_is_used_as_it_is_even_when_the_entry_orders_say_otherwise(seams):
    """Stored (stated): 15.4 % of Rs 1,000 = Rs 154.00, 2x Rs 500 = Rs 1,000; the entry (2,600 / 3,900) is not read."""
    seams.plan = _plan(_stored())
    assert amounts(_read(seams, ENTRY)) == (D("154.00"), D("1000"))
    assert seams.writes == []


def test_an_adjustment_does_not_move_the_base(seams):
    """Q4 (a): a roll ('add' orders after the exit) leaves the Rs 400.40 / Rs 7,800 lines where they were."""
    seams.plan = _plan()
    assert amounts(_read(seams, ENTRY)) == (LINE_PCT, LINE_CREDIT)
    rolled = _read(seams, ENTRY + ADJUSTMENT)
    assert len(rolled.position.legs) == IC_LEGS
    assert amounts(rolled) == (LINE_PCT, LINE_CREDIT)


def test_plan_saved_before_the_change_is_backfilled_once_from_the_entry_orders(seams):
    """Absent: no base on the plan row -> worked out from the entry orders, stored with source 'backfill'; the second
    read (the call side now closed) reads the stored one and writes nothing."""
    seams.plan = _plan(None)
    first = _read(seams, ENTRY)
    assert amounts(first) == (LINE_PCT, LINE_CREDIT)
    assert len(seams.writes) == 1
    assert seams.writes[0]["source"] == sif.BASE_BACKFILL
    assert (seams.writes[0]["max_loss"], seams.writes[0]["credit"]) == ("2600", "3900")
    assert amounts(_read(seams, ENTRY + CALL_SIDE_CLOSED)) == (LINE_PCT, LINE_CREDIT)
    assert len(seams.writes) == 1  # no recompute, no second write


def test_a_failed_backfill_write_still_reads_the_entry_figures_never_the_live_legs(seams, monkeypatch):
    async def broken(_sid, _value):
        raise RuntimeError("database down")
    monkeypatch.setattr(playbook_store, "backfill_stop_base", broken)
    seams.plan = _plan(None)
    assert amounts(_read(seams, ENTRY + CALL_SIDE_CLOSED)) == (LINE_PCT, LINE_CREDIT)


def test_no_plan_has_nothing_to_store_it_on_and_still_reads_the_entry_figures(seams):
    seams.plan = None
    assert amounts(_read(seams, ENTRY + CALL_SIDE_CLOSED)) == (LINE_PCT, LINE_CREDIT)
    assert seams.writes == []


@pytest.mark.parametrize("raw", [
    {"max_loss": 2600.0, "credit": "3900", "taken_at": T0.isoformat(), "source": "entry"},  # a float
    {"max_loss": "2600", "credit": "3900", "taken_at": T0.isoformat(), "source": "guess"},  # a source nobody writes
    {"max_loss": "abc", "credit": "3900", "taken_at": T0.isoformat(), "source": "entry"},
    {"max_loss": "NaN", "credit": "3900", "taken_at": T0.isoformat(), "source": "entry"},
    {"max_loss": "2600", "credit": "3900"},  # keys missing
    "text"])
def test_stored_base_that_cannot_be_read_says_not_checked_and_is_left_alone(seams, raw):
    """Failed: never a number from the live legs, never overwritten by a back-fill."""
    seams.plan = _plan(raw)
    got = lines_of(_read(seams, ENTRY + CALL_SIDE_CLOSED))
    assert (got[sif.STOP_MAX_LOSS].amount, got[sif.STOP_MAX_LOSS].reason) == (None, sl.MAX_LOSS_UNKNOWN)
    assert (got[sif.STOP_CREDIT].amount, got[sif.STOP_CREDIT].reason) == (None, sl.CREDIT_UNKNOWN)
    assert seams.writes == []


def test_no_entry_order_says_not_checked(seams):
    """Empty: the book holds only an 'add' order (no 'open' kind) -> both lines not checked, nothing stored."""
    seams.plan = _plan(None)
    only_add = [_order(1, "SELL", "add", T0, "90")]
    got = lines_of(_read(seams, only_add))
    assert (got[sif.STOP_MAX_LOSS].amount, got[sif.STOP_MAX_LOSS].reason) == (None, sl.MAX_LOSS_UNKNOWN)
    assert (got[sif.STOP_CREDIT].amount, got[sif.STOP_CREDIT].reason) == (None, sl.CREDIT_UNKNOWN)
    assert seams.writes == []


def test_unlimited_max_loss_says_so_and_the_credit_line_still_works(seams):
    """Ambiguous: a naked short call at 90 (65 units): max loss unlimited, credit Rs 5,850 -> 2x = Rs 11,700."""
    seams.plan = _plan(None)
    got = lines_of(_read(seams, [_order(1, "SELL", "open", T0, "90")]))
    assert (got[sif.STOP_MAX_LOSS].amount, got[sif.STOP_MAX_LOSS].reason) == (None, sl.MAX_LOSS_UNLIMITED)
    assert got[sif.STOP_CREDIT].amount == D("11700")
    assert seams.writes[0]["max_loss"] == "unlimited"


def test_the_stored_json_holds_no_float(seams):
    seams.plan = _plan(None)
    _read(seams, ENTRY)
    value = seams.writes[0]
    assert all(isinstance(v, str) or v is None for v in value.values())
    assert json.loads(json.dumps(value), parse_float=lambda t: pytest.fail(f"float {t}")) == value


def test_a_plan_save_stores_the_base_worked_out_now_from_the_entry_orders(seams):
    """The plan routes store ``tracked.entry_stop_base`` (entry orders only), also after the call side closed."""
    tracked = _read(seams, ENTRY + CALL_SIDE_CLOSED)
    stored = ap._base_json(tracked)
    assert (stored["max_loss"], stored["credit"], stored["source"]) == ("2600", "3900", "entry")
    assert ap._base_json(SimpleNamespace()) is None  # nothing worked out -> nothing stored


# ---- the plan row (real PostgreSQL, the limited application role) ------------------------------------------
@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def test_a_plan_edit_recomputes_and_a_backfill_writes_only_where_nothing_is_stored(db):
    user = _user()
    _, strategy = await _with_draft(db, user)
    system = await playbook_store.active_for(db, user, "ic")
    first, second = _stored("2600", "3900"), _stored("1800", "3000")
    saved = await playbook_store.accept_plan(db, user, strategy.id, system.id, None, first)
    assert saved.stop_base == first
    again = await playbook_store.accept_plan(db, user, strategy.id, system.id, None, second)  # a plan edit
    assert again.stop_base == second
    cleared = await playbook_store.accept_plan(db, user, strategy.id, system.id, None, None)
    assert cleared.stop_base is None
    won = await db.execute(playbook_store._BACKFILL_STOP_BASE,
                           {"strategy_id": strategy.id, "value": json.dumps(first)})
    lost = await db.execute(playbook_store._BACKFILL_STOP_BASE,
                            {"strategy_id": strategy.id, "value": json.dumps(second)})
    assert (won.rowcount, lost.rowcount) == (1, 0)  # the first writer wins, the second changes nothing
    assert (await playbook_store.plan_for(db, user, strategy.id)).stop_base == first
    kind = (await db.execute(text("SELECT jsonb_typeof(stop_base) FROM public.strategy_adjustment_plans "
                                  "WHERE strategy_id = :s"), {"s": strategy.id})).scalar_one()
    assert kind == "object"
