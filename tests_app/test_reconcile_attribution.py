"""W-108 core proof (REQ-060 AC-7; ADR-109 (2) and its first consequence; ADR-105; Q224; F-42): attribute before
compare, on the owner's REAL 2026-10-16 Kite replies (tests/fixtures/kite_replies/, README there) and cases derived
from them.

Real inputs: orders-122104 (OFS1V1L0 BUY 65 NIFTY26O1923650CE, COMPLETE), orders-151006 (that row plus OFS1V2L0 SELL
65), positions-122104 (net +65), positions-151006 (flat row, quantity 0), the instrument slice (lot 65). The stored
plans are built from those order rows (tag -> strategy and plan number, ``filled_quantity`` as Kite reported it).
Derived cases change ONLY the positions row's ``quantity``, an order's side, or the tag's strategy number.

Expected values come from the spec by hand, never from running the adapter: ADR-109's consequence ("strategy BUY 65
NIFTY CE, Kite 130 -> not blocked, 65 outside; strategy 65 + standalone 25, Kite 90 -> no mismatch; Kite 0 ->
blocked"), REQ-060 AC-6 (a shortfall blocks), AC-7 (a position in no strategy blocks no strategy) and Q224 (a shared
contract that disagrees blocks every holder). No database: the store is an injected fake of the two reads the adapter
makes itself (every strategy of the user, every plan of each).
"""
from __future__ import annotations

import asyncio
import copy
import datetime
import inspect
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from ofo.engine import Instrument
from ofo.execution.basket import parse_tag
from ofo.instruments import Catalogue
from ofo.instruments.models import NSE_FO
from ofo.instruments.parser import zerodha_listed
from ofo.reconciliation.compare import MismatchKind, ReconciliationReport
from ofo.timeutil import IST
from ofo_app import execution_plan_store, strategy_store
from ofo_app import reconcile_attribution as ra
from ofo_app.execute_replay import CORE_ID, TOKEN
from ofo_app.execute_replay import listed_contract as _listed
from ofo_app.execution_plan_store import PlanOrder, StoredPlan
from ofo_app.kite_replies import ContractIndex, orders_from_reply, positions_from_reply
from ofo_app.strategy_store import StrategySummary

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kite_replies"
KEY = ("NIFTY", Instrument.CE, Decimal("23650.00"), datetime.date(2026, 10, 19))
IID = f"{NSE_FO}:{CORE_ID.exchange_token}"
AT = datetime.datetime(2026, 10, 16, 15, 10, 8, tzinfo=IST)
CONN, USER = object(), "user-1"


def clock() -> datetime.datetime:
    return AT  # the platform clock, pinned; never the wall clock


def _recorded(name: str) -> object:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"), parse_float=Decimal)["data"]


def _catalogue(*rows) -> Catalogue:
    cat = Catalogue()
    cat.load([_listed(), *rows])
    return cat


def _index() -> ContractIndex:
    slice_rows = json.loads((FIXTURES / "instruments-2026-10-16-slice.json").read_text(encoding="utf-8"))
    return ContractIndex.from_instrument_slice(slice_rows)


class _Entry:
    """One strategy as the fake store holds it: its underlying and ALL its stored plans."""

    def __init__(self, underlying: str, plans: object) -> None:
        self.underlying, self.plans = underlying, plans


def _plans(orders: str, strategy_id: int = 1, *, side: str | None = None) -> _Entry:
    """The real order rows as this strategy's stored plans (one plan per tag); ``side`` flips every order (derived)."""
    by_plan: dict[int, list[PlanOrder]] = {}
    for row in orders_from_reply(_recorded(orders)):
        number = parse_tag(row.tag).plan_version
        by_plan.setdefault(number, []).append(PlanOrder(
            0, f"OFS{strategy_id}V{number}L0", IID, row.tradingsymbol, side or row.side.value, row.quantity,
            row.price, row.filled_quantity))
    return _Entry("NIFTY", tuple(
        StoredPlan(strategy_id, number, "ENTRY" if number == 1 else "EXIT", "closed", tuple(orders_), AT, AT, "filled")
        for number, orders_ in sorted(by_plan.items())))


def _second_buy(entry: _Entry, strategy_id: int = 1, iid: str = IID) -> _Entry:
    """``entry`` plus a plan 2 that BUYs 65 more (filled) on ``iid``: the strategy holds 130 over two plans."""
    first = entry.plans[0].orders[0]
    plan2 = StoredPlan(strategy_id, 2, "ENTRY", "closed", (PlanOrder(
        0, f"OFS{strategy_id}V2L0", iid, first.tradingsymbol, "BUY", 65, first.price, 65),), AT, AT, "filled")
    return _Entry(entry.underlying, (entry.plans[0], plan2))


def _reader(store: object) -> ra.StoreReader:
    """A fake of the two store reads; it answers only for this connection and user (the account is passed through).
    ``store``: strategy id -> _Entry, or a ready-made strategy listing (a list)."""

    async def list_strategies(conn, user_ref):
        assert (conn, user_ref) == (CONN, USER)
        if isinstance(store, list):
            return store
        return [StrategySummary(sid, e.underlying, "draft", AT, AT) for sid, e in store.items()]

    async def plans_for(conn, user_ref, strategy_id):
        assert (conn, user_ref) == (CONN, USER)
        if isinstance(store, list):
            return _plans("orders-122104", strategy_id).plans if strategy_id > 0 else ()
        return store[strategy_id].plans

    return ra.StoreReader(list_strategies, plans_for)


def _positions(quantity: int | None = 65) -> object:
    """positions-122104's data with the net row's quantity set (None: the row is left out of the reply)."""
    data = copy.deepcopy(_recorded("positions-122104"))
    if quantity is None:
        data["net"] = []
    else:
        data["net"][0]["quantity"] = quantity
    return data


def _attribute(store, broker_net, standalone=None, catalogue=None) -> ra.Attribution:
    sources = ra.Sources(catalogue or _catalogue(), clock, _reader(store))
    alone = {} if standalone is None else standalone
    return asyncio.run(ra.attribute_and_compare(ra.Account(CONN, USER), alone, broker_net, sources, at=AT))


def _run(store, positions, standalone=None) -> ra.Attribution:
    """The product path: Zerodha's positions reply through the existing reply adapter, then the attribution (which
    reads every strategy and all its plans from the store itself)."""
    return _attribute(store, positions_from_reply(positions, _index()).net, standalone)


def _blocked(result: ra.Attribution) -> set[str]:
    return set(result.report.blocked_strategy_ids)


# ---- AC-7 (ADR-109): the seven cases of work/W-108.md ----------------------------------------------------------

def test_ac7_a_real_replies_give_no_mismatch():
    """AC-7 (a): the real entry (strategy 1 holds +65, Zerodha +65) and the real exit (V1 BUY 65 + V2 SELL 65 net
    0, Zerodha's flat row) -> no mismatch, nothing outside, Zerodha's raw net kept."""
    entry = _run({1: _plans("orders-122104")}, _recorded("positions-122104"))
    assert isinstance(entry.report, ReconciliationReport)
    assert entry.report.mismatches == ()
    assert dict(entry.raw_net) == {KEY: 65}
    assert dict(entry.compared_net) == {KEY: 65}
    assert dict(entry.outside) == {}
    assert {sid: dict(u) for sid, u in entry.held.items()} == {"1": {KEY: 65}}

    exit_ = _run({1: _plans("orders-151006")}, _recorded("positions-151006"))
    assert exit_.report.mismatches == ()
    assert dict(exit_.raw_net) == {} and dict(exit_.outside) == {} and dict(exit_.held) == {}


def test_ac7_b_same_direction_surplus_is_outside_not_blocked():
    """AC-7 (b), ADR-109 example: strategy BUY 65, Zerodha 130 -> not blocked, 65 outside; raw 130
    kept."""
    result = _run({1: _plans("orders-122104")}, _positions(130))
    assert result.report.mismatches == ()
    assert dict(result.outside) == {KEY: 65}
    assert dict(result.raw_net) == {KEY: 130}
    assert dict(result.compared_net) == {KEY: 65}


def test_ac7_c_zerodha_flat_blocks():
    """AC-7 (c), ADR-109 example "Kite 0 -> blocked" (AC-6 shortfall): strategy 65, Zerodha 0 -> blocked, nothing
    outside."""
    result = _run({1: _plans("orders-122104")}, _positions(0))
    assert _blocked(result) == {"1"}
    assert [m.kind for m in result.report.mismatches] == [MismatchKind.MISSING_PLATFORM_POSITION]
    assert dict(result.outside) == {}


def test_ac7_d_short_strategy_with_outside_long_reaches_compare_and_blocks():
    """AC-7 (d): strategy SELL 65, an outside BUY 65 nets Zerodha to 0 -> an opposite-direction difference is never
    stripped; blocked (ADR-109 (2): netted-away app lots cannot be told apart)."""
    result = _run({1: _plans("orders-122104", side="SELL")}, _positions(0))
    assert {sid: dict(u) for sid, u in result.held.items()} == {"1": {KEY: -65}}
    assert _blocked(result) == {"1"}
    assert dict(result.outside) == {}


@pytest.mark.parametrize(("side", "zerodha"), [("SELL", 130), ("BUY", -65), ("BUY", -130)])
def test_ac7_d_opposite_side_beyond_the_strategy_is_never_outside(side, zerodha):
    """AC-7 (d), the killing case of the same-direction check: Zerodha on the OTHER side, larger than the strategy's
    65 -> blocked, nothing outside (a sign-blind "|Zerodha| > |expected|" would strip it and pass)."""
    result = _run({1: _plans("orders-122104", side=side)}, _positions(zerodha))
    assert _blocked(result) == {"1"}
    assert dict(result.outside) == {}
    assert dict(result.compared_net) == {KEY: zerodha}


def test_ac7_e_recorded_standalone_is_expected_unrecorded_is_outside():
    """AC-7 (e), ADR-109 example: strategy 65 + standalone 25 recorded, Zerodha 90 -> no mismatch, nothing outside.
    The same 25 NOT recorded -> 25 outside, not blocked ("an UNRECORDED surplus no longer needs recording first")."""
    recorded = _run({1: _plans("orders-122104")}, _positions(90), {KEY: 25})
    assert recorded.report.mismatches == ()
    assert dict(recorded.outside) == {}
    assert dict(recorded.compared_net) == {KEY: 90}

    unrecorded = _run({1: _plans("orders-122104")}, _positions(90))
    assert unrecorded.report.mismatches == ()
    assert dict(unrecorded.outside) == {KEY: 25}


def test_ac7_f_two_strategies_short_at_zerodha_both_blocked():
    """AC-7 (f), Q224: strategies 1 and 2 hold 65 each, Zerodha 65 -> both blocked, nothing outside."""
    result = _run({1: _plans("orders-122104"), 2: _plans("orders-122104", 2)}, _positions(65))
    assert _blocked(result) == {"1", "2"}
    assert dict(result.outside) == {}


def test_ac7_f_two_strategies_surplus_counts_both():
    """AC-7 (f), the sum over ALL strategies: 65 + 65 held, Zerodha 195 -> 65 outside, neither blocked."""
    result = _run({1: _plans("orders-122104"), 2: _plans("orders-122104", 2)}, _positions(195))
    assert result.report.mismatches == ()
    assert dict(result.outside) == {KEY: 65}


def test_ac7_g_contract_no_strategy_holds_is_outside():
    """AC-7 (g): no strategy and no standalone, Zerodha 65 -> 65 outside, no mismatch (AC-7: blocks no strategy)."""
    result = _run({}, _positions(65))
    assert result.report.mismatches == ()
    assert dict(result.outside) == {KEY: 65}
    assert dict(result.compared_net) == {}


def test_ac7_holders_on_both_sides_strip_nothing_and_block_all():
    """AC-7, Q224: strategy 1 +130, strategy 2 -65 (expected +65), Zerodha +130 -> nothing stripped (the 65 is a
    shortfall against strategy 2's own short), both blocked."""
    result = _run({1: _second_buy(_plans("orders-122104")), 2: _plans("orders-122104", 2, side="SELL")},
                  _positions(130))
    assert {sid: dict(u) for sid, u in result.held.items()} == {"1": {KEY: 130}, "2": {KEY: -65}}
    assert _blocked(result) == {"1", "2"}
    assert dict(result.outside) == {}


# ---- every answer state of the positions read (B4 d) ----------------------------------------------------------------

def test_ac7_positions_row_absent_or_flat_with_a_holder_blocks():
    """AC-7: the strategy's row absent from Zerodha's reply, or present with quantity 0 -> Zerodha holds 0 ->
    blocked."""
    assert _blocked(_run({1: _plans("orders-122104")}, _positions(None))) == {"1"}
    assert _blocked(_run({1: _plans("orders-122104")}, _recorded("positions-151006"))) == {"1"}


def test_ac7_flat_row_with_no_strategy_reports_nothing():
    """AC-7: a contract in Zerodha's reply with net 0 and no strategy -> nothing outside, no mismatch."""
    result = _run({}, _recorded("positions-151006"))
    assert result.report.mismatches == ()
    assert dict(result.outside) == {} and dict(result.raw_net) == {}


def test_ac7_unfilled_plan_holds_nothing():
    """AC-7, ADR-105: an order not yet filled (filled_quantity None) counts 0, so Zerodha's 65 is outside."""
    order = _plans("orders-122104").plans[0].orders[0]
    unfilled = _Entry("NIFTY", (StoredPlan(1, 1, "ENTRY", "open", (PlanOrder(
        0, order.tag, IID, order.tradingsymbol, "BUY", 65, order.price, None),), AT, None, None),))
    result = _run({1: unfilled}, _positions(65))
    assert dict(result.held) == {}
    assert dict(result.outside) == {KEY: 65}


def _row_without(key: str) -> object:
    data = _positions(65)
    del data["net"][0][key]
    return data


@pytest.mark.parametrize("positions", [
    pytest.param(_row_without("quantity"), id="missing-quantity"),
    pytest.param({**_positions(65), "net": [{**_positions(65)["net"][0], "quantity": Decimal("65")}]},
                 id="decimal-quantity"),
    pytest.param({**_positions(65), "net": [{**_positions(65)["net"][0], "tradingsymbol": "NIFTY26O1923700CE"}]},
                 id="unknown-contract"),
    pytest.param({"day": []}, id="no-net-key"),
    pytest.param({"net": {}}, id="net-not-a-list"),
])
def test_ac7_unparseable_positions_fail_closed(positions):
    """AC-7: an unreadable positions reply raises ValueError (in the reply adapter, before the attribution); it is
    never read as Zerodha holding 0."""
    with pytest.raises(ValueError):
        _run({1: _plans("orders-122104")}, positions)


# ---- the stored plans the adapter reads itself (caller-supplied-verdict-trusted) ----------------------------------

def _one_plan(**changes) -> _Entry:
    order = _plans("orders-122104").plans[0].orders[0]
    order_fields = {k: changes.pop(k) for k in ("tag", "instrument_id") if k in changes}
    new_order = PlanOrder(0, order_fields.get("tag", order.tag), order_fields.get("instrument_id", IID),
                          order.tradingsymbol, "BUY", 65, order.price, 65)
    return _Entry(changes.pop("underlying", "NIFTY"), (StoredPlan(
        changes.pop("strategy_id", 1), 1, "ENTRY", "closed", (new_order,), AT, AT, "filled"),))


@pytest.mark.parametrize("plans", [
    pytest.param(_one_plan(tag="OFS2V1L0"), id="another-strategys-tag"),
    pytest.param(_one_plan(tag="OFS1V3L0"), id="another-plans-tag"),
    pytest.param(_one_plan(tag="MANUAL"), id="not-an-app-tag"),
    pytest.param(_one_plan(strategy_id=2, tag="OFS2V1L0"), id="plan-of-another-strategy"),
    pytest.param(_one_plan(strategy_id=2), id="plan-of-another-strategy-with-this-tag"),
    pytest.param(_one_plan(instrument_id="NSE_FO:99999"), id="not-in-catalogue"),
    pytest.param(_one_plan(instrument_id="NSE_FO:047189"), id="padded-token"),
    pytest.param(_one_plan(instrument_id="47189"), id="no-segment"),
    pytest.param(_one_plan(instrument_id="NSE_FO:47189:1"), id="three-parts"),
    pytest.param(_one_plan(underlying="SENSEX"), id="other-underlying"),
])
def test_ac7_plans_not_this_strategys_are_refused(plans):
    """AC-7, ADR-109 (2): a strategy owns only its own tagged orders; any plan or order that is not provably this
    strategy's, or an instrument the catalogue cannot place, is refused (ValueError), never counted."""
    with pytest.raises(ValueError):
        _run({1: plans}, _positions(65))


def test_ac7_a_plan_that_is_not_a_stored_plan_is_refused():
    """AC-7: plans come from the plan store (StoredPlan); a look-alike object with the same fields is refused."""
    real = _plans("orders-122104").plans[0]
    look_alike = SimpleNamespace(**{f: getattr(real, f) for f in real.__dataclass_fields__})
    with pytest.raises(ra.AttributionError, match="StoredPlan"):
        _run({1: _Entry("NIFTY", (look_alike,))}, _positions(65))


def test_ac7_duplicate_plans_are_refused():
    """AC-7: the store returning one plan twice would double the expected units -> refused."""
    once = _plans("orders-122104")
    with pytest.raises(ra.AttributionError, match="appears twice"):
        _run({1: _Entry("NIFTY", once.plans * 2)}, _positions(130))


@pytest.mark.parametrize("returned", [None, {}, "plans"])
def test_ac7_a_plans_read_that_is_not_a_sequence_is_refused(returned):
    """AC-7: the store's plans read must be a sequence of StoredPlan; anything else is refused."""
    with pytest.raises(ra.AttributionError):
        _run({1: _Entry("NIFTY", returned)}, _positions(65))


@pytest.mark.parametrize("standalone", [{KEY: Decimal("25")}, {KEY: True}, {("NIFTY",): 25}, []])
def test_ac7_malformed_standalone_is_refused(standalone):
    """AC-7: the recorded standalone map is validated (compare.units_map); a wrong type is refused, never 0."""
    with pytest.raises(ValueError):
        _attribute({1: _plans("orders-122104")}, {KEY: 90}, standalone)


@pytest.mark.parametrize("broker_net", [{KEY: Decimal("65")}, {KEY: True}, {KEY: 65.0}, {("NIFTY",): 65}, [(KEY, 65)]])
def test_ac7_malformed_broker_net_is_refused(broker_net):
    """AC-7: Zerodha's net is validated again here (compare.units_map); a non-int quantity or a bad contract key is
    refused, never read as 0."""
    with pytest.raises(ValueError):
        _attribute({1: _plans("orders-122104")}, broker_net)


# ---- fix round 1: the adapter reads every strategy and ALL its plans itself (run-discipline B8) -------------------

def test_ac7_the_caller_passes_no_plans_strategies_or_held_units():
    """AC-7, finding caller-supplied-verdict-trusted: the public signature takes only the account, the standalone map,
    Zerodha's net, the sources and ``at``; the default reader is the stores the routes use."""
    assert list(inspect.signature(ra.attribute_and_compare).parameters) == [
        "account", "standalone", "broker_net", "sources", "at"]
    assert ra.StoreReader().list_strategies is strategy_store.list_strategies
    assert ra.StoreReader().plans_for is execution_plan_store.plans_for


def test_ac7_a_strategy_with_two_plans_is_fully_counted():
    """AC-7, ADR-105: plans 1 and 2 BUY 65 each -> the strategy holds 130 (every stored plan read); Zerodha 65 is a
    shortfall -> blocked (plan 1 read alone would show 65 = 65 and hide it)."""
    result = _run({1: _second_buy(_plans("orders-122104"))}, _positions(65))
    assert {sid: dict(u) for sid, u in result.held.items()} == {"1": {KEY: 130}}
    assert _blocked(result) == {"1"}
    assert dict(result.outside) == {}


def test_ac7_every_stored_strategy_is_expected():
    """AC-7: a strategy holding 65 is in the store, Zerodha 0 -> it is read and blocked; with a second, flat strategy
    (entry and exit filled) in the store, only the holder is blocked."""
    result = _run({1: _plans("orders-122104"), 2: _plans("orders-151006", 2)}, _positions(0))
    assert _blocked(result) == {"1"}
    assert set(result.held) == {"1"}


@pytest.mark.parametrize("listing", [
    pytest.param(lambda: [SimpleNamespace(id=1, underlying="NIFTY")], id="not-a-summary"),
    pytest.param(lambda: [StrategySummary(1, "NIFTY", "draft", AT, AT)] * 2, id="listed-twice"),
    pytest.param(lambda: [StrategySummary(True, "NIFTY", "draft", AT, AT)], id="bool-id"),
    pytest.param(lambda: [StrategySummary(0, "NIFTY", "draft", AT, AT)], id="zero-id"),
    pytest.param(lambda: [StrategySummary("1", "NIFTY", "draft", AT, AT)], id="text-id"),
    pytest.param(lambda: [StrategySummary(i, "NIFTY", "draft", AT, AT) for i in range(1, 1002)], id="over-the-cap"),
])
def test_ac7_a_store_listing_that_cannot_be_read_is_refused(listing):
    """AC-7: the store's strategy list is checked (a StrategySummary each, positive int ids, once each, at most
    compare's cap of 1,000); anything else is refused, never skipped."""
    with pytest.raises(ra.AttributionError):
        _attribute(listing(), {KEY: 65})


def test_ac7_a_store_listing_that_is_not_a_list_is_refused():
    """AC-7: a store answer that is not a sequence of strategies is refused."""
    reader = _reader({})

    async def listing(conn, user_ref):
        return None

    sources = ra.Sources(_catalogue(), clock, ra.StoreReader(listing, reader.plans_for))
    with pytest.raises(ra.AttributionError):
        asyncio.run(ra.attribute_and_compare(ra.Account(CONN, USER), {}, {KEY: 65}, sources, at=AT))


def test_ac7_account_and_sources_are_checked():
    """AC-7: the account needs a user; the sources must be a Sources with a StoreReader (no look-alike reader)."""
    good = ra.Sources(_catalogue(), clock, _reader({1: _plans("orders-122104")}))
    for account in (ra.Account(CONN, ""), ra.Account(CONN, None), (CONN, USER)):
        with pytest.raises(ra.AttributionError):
            asyncio.run(ra.attribute_and_compare(account, {}, {KEY: 65}, good, at=AT))
    look_alike = SimpleNamespace(list_strategies=good.reader.list_strategies, plans_for=good.reader.plans_for)
    for sources in (object(), ra.Sources(_catalogue(), clock, look_alike)):
        with pytest.raises(ra.AttributionError):
            asyncio.run(ra.attribute_and_compare(ra.Account(CONN, USER), {}, {KEY: 65}, sources, at=AT))


@pytest.mark.parametrize(("zerodha", "outside", "blocked"), [
    (40, {}, set()), (65, {KEY: 25}, set()), (130, {KEY: 90}, set()), (0, {}, {"1"})])
def test_ac7_standalone_on_the_other_side_only_adds_to_expected(zerodha, outside, blocked):
    """AC-7, ADR-109 (2), Q224 (single-holder contracts unchanged): own +65, standalone -25 -> expected 40. Zerodha 40
    agrees; 65 and 130 are an outside same-direction surplus (25, 90), not blocked; 0 is a shortfall, blocked."""
    result = _run({1: _plans("orders-122104")}, _positions(zerodha), {KEY: -25})
    assert dict(result.outside) == outside
    assert _blocked(result) == blocked


def test_ac7_two_stored_ids_of_one_contract_add_up():
    """AC-7: two catalogue ids that are the same contract (one key) are one net at Zerodha: plan 1 BUY 65 on one id
    and plan 2 BUY 65 on the other -> the strategy holds 130 there; Zerodha 65 is a shortfall -> blocked."""
    real = _listed()
    twin_token = (int(TOKEN) >> 8) + 1
    twin = zerodha_listed(
        instrument_token=int(TOKEN) + 1, exchange_token=twin_token, tradingsymbol="NIFTY26O1923650CE",
        name=real.contract.name, expiry=real.contract.expiry, strike=real.contract.strike, tick_size=Decimal("0.05"),
        lot_size=real.contract.lot_size, instrument_type=real.contract.instrument_type, segment="NFO-OPT",
        exchange="NFO")
    entry = _second_buy(_plans("orders-122104"), iid=f"{NSE_FO}:{twin_token}")
    net = positions_from_reply(_positions(65), _index()).net
    result = _attribute({1: entry}, net, catalogue=_catalogue(twin))
    assert {sid: dict(u) for sid, u in result.held.items()} == {"1": {KEY: 130}}
    assert _blocked(result) == {"1"}


def test_ac7_split_outside_rule_by_hand():
    """AC-7: the pure rule on hand-worked numbers (module docstring): more than expected in the strategies' direction
    -> the excess; no holder -> all; shortfall, opposite side or strategies on both sides -> 0; a standalone only
    adds to expected (and gives the direction when no strategy holds)."""
    held = {"1": {KEY: 65}}
    assert ra.split_outside({KEY: 130}, held, {}) == {KEY: 65}
    assert ra.split_outside({KEY: 90}, held, {KEY: 25}) == {}
    assert ra.split_outside({KEY: 100}, held, {KEY: 25}) == {KEY: 10}
    assert ra.split_outside({KEY: 40}, held, {}) == {}
    assert ra.split_outside({KEY: -130}, held, {}) == {}
    assert ra.split_outside({KEY: -130}, {"1": {KEY: -65}}, {}) == {KEY: -65}
    assert ra.split_outside({KEY: 65}, {}, {}) == {KEY: 65}
    assert ra.split_outside({KEY: 130}, {"1": {KEY: 130}, "2": {KEY: -65}}, {}) == {}
    assert ra.split_outside({KEY: 65}, held, {KEY: -25}) == {KEY: 25}
    assert ra.split_outside({KEY: 40}, held, {KEY: -25}) == {}
    assert ra.split_outside({KEY: 90}, {}, {KEY: 25}) == {KEY: 65}
    assert ra.split_outside({KEY: -10}, {}, {KEY: 25}) == {}
