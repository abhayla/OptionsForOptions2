"""D-04 (ADR-318 (4)): a strategy with no plan of its own follows the playbook of the shape it had AT ENTRY, so the
plan maximum and every other rule survive an adjustment that changes the shape (real case 23 Nov, strategy 164: a
condor reduced to a put spread read "1 used; no plan maximum set").

No database: the readers' two seams (the paper book rows, the contract rows) and the playbook store are faked; the
shape classifier, ``_tracked_on`` and ``adjustment_check.resolve`` are the real code.
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
from ofo_app import adjustment_check as check
from ofo_app import adjustment_readers as readers
from ofo_app import paper_book, playbook_store, tracked_contracts

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYSTEM = {p["strategy_type"]: p["body"] for p in
          json.loads((ROOT / "backend/ofo/adjustment/system_playbooks.json").read_text())["playbooks"]}
EXPIRY = datetime.date(2026, 11, 26)
LOT, GAP, SPOT = 75, D(50), D(23800)
T0 = datetime.datetime(2026, 11, 23, 10, 0, tzinfo=datetime.UTC)
T1, T2 = T0 + datetime.timedelta(hours=1), T0 + datetime.timedelta(hours=2)
# contract id -> (type, strike): the iron condor's four legs
CONTRACTS = {1: ("CE", D(24000)), 2: ("CE", D(24200)), 3: ("PE", D(23600)), 4: ("PE", D(23400)),
             5: ("PE", D(23600)), 6: ("PE", D(23400))}  # 5, 6: a put spread on the next expiry
EXPIRY2 = datetime.date(2026, 12, 1)
IC_MAX = 2
LAST_FIRST_EXPIRY_ID = 4  # contracts 1-4 expire first, 5 and up on the second expiry
SPREAD_LEGS = 2
PLAN_MAX_ADJUSTMENTS = 5


def _contract(cid: int) -> SimpleNamespace:
    kind, strike = CONTRACTS[cid]
    c = SimpleNamespace(instrument_type=kind, strike=strike, expiry=EXPIRY2 if cid > LAST_FIRST_EXPIRY_ID else EXPIRY,
                        lot_size=LOT, name="NIFTY")
    listed = SimpleNamespace(contract=c, broker_refs=[SimpleNamespace(broker_symbol=f"NIFTY{kind}{strike}")])
    return SimpleNamespace(contract_id=cid, stored=SimpleNamespace(listed=listed), identity=str(cid))


def _order(cid: int, side: str, kind: str, at: datetime.datetime, lots: int = 1) -> SimpleNamespace:
    return SimpleNamespace(order=paper_book.NewOrder(cid, side, lots * LOT, D("100.00"), kind, at))


ENTRY = [_order(1, "SELL", "open", T0), _order(2, "BUY", "open", T0),
         _order(3, "SELL", "open", T0), _order(4, "BUY", "open", T0)]
REDUCE_CALL_SIDE = [_order(1, "BUY", "exit", T1), _order(2, "SELL", "exit", T1)]  # the call spread is closed


@pytest.fixture
def seams(monkeypatch):
    """The readers' seams and the shape classifier's strike gap; ``store`` holds what the playbook store answers."""
    store = SimpleNamespace(plan=None, orders=[])

    async def load_owned(_db, _user, _sid):
        return store.orders

    async def resolve(_db, ids):
        return [_contract(i) for i in ids]

    async def plan_for(*_a):
        return store.plan

    async def active_for(_db, _user, stype):
        body = copy.deepcopy(SYSTEM[stype])
        if stype == "credit":  # the live case: the playbook the reduced shape reads has no maximum
            body["guards"].pop("max_adjustments", None)
        return SimpleNamespace(is_system=True, status="approved", body=body, id=hash(stype) % 1000)

    async def adr247(_db):
        return None
    monkeypatch.setattr(paper_book, "load_owned", load_owned)
    monkeypatch.setattr(tracked_contracts, "resolve", resolve)
    monkeypatch.setattr(playbook_store, "plan_for", plan_for)
    monkeypatch.setattr(playbook_store, "active_for", active_for)
    monkeypatch.setattr(playbook_store, "adr247_saved_at", adr247)
    monkeypatch.setattr(check, "strike_gap_of", lambda *_a: GAP)
    return store


def _read(store, orders):
    store.orders = orders
    return asyncio.run(readers._tracked_on(None, 164, None))


def _playbook_of(store, tracked):
    stype = check.entry_type(tracked, SPOT, [])
    return stype, asyncio.run(check.resolve(None, "u", 164, stype))


def test_condor_reduced_to_a_put_spread_keeps_the_condor_playbook_and_its_maximum(seams):
    tracked = _read(seams, ENTRY + REDUCE_CALL_SIDE)
    assert len(tracked.position.legs) == SPREAD_LEGS  # now a put spread ...
    assert check.strategy_type(tracked.position, SPOT, []) == "credit"  # ... which reads the credit playbook today
    stype, resolved = _playbook_of(seams, tracked)
    assert stype == "ic"
    assert resolved.source == "system" and resolved.body["guards"]["max_adjustments"] == IC_MAX
    assert tracked.adjustments_used == 1  # "1 of 2"


def test_the_whole_rule_set_comes_from_the_entry_shape_not_only_the_maximum(seams):
    tracked = _read(seams, ENTRY + REDUCE_CALL_SIDE)
    _, resolved = _playbook_of(seams, tracked)
    assert resolved.body["guards"]["time_exit"] == "14:30"  # an iron condor only value (the credit one has none)
    assert "time_exit" not in SYSTEM["credit"]["guards"]


def test_a_strategy_with_its_own_plan_stays_on_its_plan_after_a_shape_change(seams):
    body = copy.deepcopy(SYSTEM["ic"])
    body["guards"]["max_adjustments"] = 5
    seams.plan = SimpleNamespace(body=body, playbook_id=9, accepted_at=T0)
    tracked = _read(seams, ENTRY + REDUCE_CALL_SIDE)
    _, resolved = _playbook_of(seams, tracked)
    assert resolved.source == "plan" and resolved.body["guards"]["max_adjustments"] == PLAN_MAX_ADJUSTMENTS


def test_an_entry_shape_that_matches_no_playbook_falls_back_to_the_current_shape(seams):
    odd = [_order(1, "SELL", "open", T0), _order(4, "BUY", "open", T0)]  # a short call with a long far put: no template
    odd_reduce = [_order(4, "SELL", "exit", T1)]
    tracked = _read(seams, odd + odd_reduce)  # now one naked short call, which the current shape maps
    current = check.strategy_type(tracked.position, SPOT, [])
    assert current is not None and check.entry_type(tracked, SPOT, []) == current


def test_an_entry_whose_contracts_are_no_longer_listed_falls_back_to_the_current_shape(seams, monkeypatch):
    """Core (D-04, ADR-318 (4)): the entry expiry has left the listed set (no strike gap, entry type None), the current
    legs (a put spread on the next expiry) classify as a credit spread: its playbook is read, not "no playbook"."""
    monkeypatch.setattr(check, "strike_gap_of", lambda _l, _u, expiries: None if EXPIRY in expiries else GAP)
    close_all = [_order(1, "BUY", "exit", T1), _order(2, "SELL", "exit", T1),
                 _order(3, "BUY", "exit", T1), _order(4, "SELL", "exit", T1)]
    roll = [_order(5, "SELL", "open", T2), _order(6, "BUY", "open", T2)]
    tracked = _read(seams, ENTRY + close_all + roll)
    assert check.strategy_type(tracked.entry_position, SPOT, []) is None  # the entry shape cannot be classified
    stype, resolved = _playbook_of(seams, tracked)
    assert stype == "credit" == check.strategy_type(tracked.position, SPOT, [])
    assert resolved.source == "system" and resolved.body is not None


def test_a_trade_entered_in_two_confirms_is_classified_by_its_first_confirm_only(seams):
    """Known limit (ADR-255: the entry is the first basket of orders): hedges first, shorts later -> the entry shape is
    the hedges alone, never the condor."""
    hedges, shorts = [_order(2, "BUY", "open", T0), _order(4, "BUY", "open", T0)], [_order(1, "SELL", "open", T1),
                                                                                    _order(3, "SELL", "open", T1)]
    tracked = _read(seams, hedges + shorts)
    assert check.entry_type(tracked, SPOT, []) == check.strategy_type(tracked.entry_position, SPOT, []) != "ic"


def test_a_condor_reduced_twice_counts_two_of_two(seams):
    entry2 = [_order(o.order.contract_id, o.order.side, "open", T0, lots=2) for o in ENTRY]
    first = [_order(1, "BUY", "exit", T1), _order(2, "SELL", "exit", T1)]  # one lot of the call spread closed
    second = [_order(3, "BUY", "exit", T2), _order(4, "SELL", "exit", T2)]  # one lot of the put spread closed
    tracked = _read(seams, entry2 + first + second)
    assert tracked.adjustments_used == IC_MAX
    _, resolved = _playbook_of(seams, tracked)
    assert resolved.body["guards"]["max_adjustments"] == IC_MAX  # used == maximum: the at-limit rule (0713b6ef) applies


def test_an_entry_rule_that_cannot_be_read_on_the_current_legs_says_so(seams):
    from ofo.adjustment import playbook_eval as pe  # noqa: PLC0415
    # both shorts bought back
    tracked = _read(seams, [*ENTRY, _order(1, "BUY", "exit", T1), _order(3, "BUY", "exit", T1)])
    _, resolved = _playbook_of(seams, tracked)
    state = pe.StrategyState(stops=None, expiry_kind="weekly", days_left=3, hhmm="11:00", spot=SPOT, shorts=(),
                             prices_fresh=True)
    ev = pe.evaluate(resolved.body, state, {}, None, gap_until="09:15")
    t01 = [r for r in ev.results if r.trigger_id == "T-01"]
    assert t01 and all(isinstance(r, pe.NotChecked) and r.code.endswith("no_short_leg") for r in t01)
