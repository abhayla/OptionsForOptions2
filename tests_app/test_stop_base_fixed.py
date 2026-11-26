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

ROOT = pathlib.Path(__file__).resolve().parent.parent
IC = next(p["body"] for p in json.loads((ROOT / "backend/ofo/adjustment/system_playbooks.json").read_text())["playbooks"]
          if p["strategy_type"] == "ic")
EXPIRY = datetime.date(2026, 11, 26)
LOT = 65
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


def _order(cid: int, side: str, kind: str, at: datetime.datetime, price: str, lots: int = 1) -> SimpleNamespace:
    return SimpleNamespace(order=paper_book.NewOrder(cid, side, lots * LOT, D(price), kind, at))


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
    assert len(after.position.legs) == 2  # the live book is a put spread now
    assert amounts(after) == (LINE_PCT, LINE_CREDIT)
