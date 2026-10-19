"""#352-1 core proof (ADR-109 (2), (4); ADR-110; ADR-111; ADR-016; REQ-060 AC-1, AC-4, AC-6; Q222): an execution plan
left open from an earlier trading day is closed ``nothing_placed`` only when Zerodha's net shows its orders changed
nothing; every other case is a recorded mismatch and ``unresolved_from_positions``, never ``filled`` / ``exited``.

Real inputs: the owner's 2026-10-16 replies (tests/fixtures/kite_replies/): plan OFS1V1L0 BUY 65 NIFTY26O1923650CE
(orders-122104), the exit OFS1V2L0 SELL 65 (orders-151006), positions-122104 (net +65), the instrument slice.
DERIVED next-day replies: Kite's order book the next day holds none of those orders (``order_book=()``, as
``orders_from_reply([])`` gives) and the positions reply's net row carries the quantity under test (absent = flat).

Expected values are from the spec by hand: the base is the net of every OTHER stored fill plus the standalone (the
GC-2h contract Proof); "net = base -> nothing_placed", "net = base + 65 (or + 30) -> recorded mismatch (NOT filled)",
EXIT "net = held -> nothing_placed", "net 0 -> recorded mismatch, lifted only by ... Kite flat -> mark exited",
"expired overnight -> recorded mismatch ... never nothing_placed", "a same-day open plan is untouched". No database:
the reader and writer are fakes; the fake writer runs the real stores' own argument checks.
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
from decimal import Decimal

import pytest
from ofo.engine import Instrument
from ofo.instruments.models import NSE_FO
from ofo.instruments.parser import zerodha_listed
from ofo.timeutil import IST
from ofo_app import execution_plan_store as eps
from ofo_app import execution_return as er
from ofo_app import next_day_resolution as nd
from ofo_app import reconcile_attribution as ra
from ofo_app import reconciliation_store as rs
from ofo_app.execute_replay import TOKEN
from ofo_app.execute_replay import listed_contract as _listed
from ofo_app.execution_plan_store import StoredPlan
from ofo_app.kite_replies import orders_from_reply, positions_from_reply
from test_reconcile_attribution import CONN, IID, KEY, USER, _catalogue, _index, _plans, _positions, _reader, _recorded

#: The real entry's day (Fri 2026-10-16, request clock 15:07:21 IST) and the next trading day (Mon 2026-10-19).
FRI = datetime.datetime(2026, 10, 16, 15, 7, 21, tzinfo=IST)
MON = datetime.datetime(2026, 10, 19, 10, 0, tzinfo=IST)
#: The contract's expiry close (NIFTY26O1923650CE expires 2026-10-19, ofo.timeutil.EXPIRY_CLOSE 15:30 IST).
EXPIRY = datetime.datetime(2026, 10, 19, 15, 30, tzinfo=IST)


def _real_plan(number: int, *, created: datetime.datetime = FRI, strategy_id: int = 1, status: str = "open",
               orders: str = "orders-151006") -> StoredPlan:
    """The real plan ``number`` (1 = OFS1V1L0 BUY 65 ENTRY, 2 = OFS1V2L0 SELL 65 EXIT); an open plan has no stored
    fill (None), a closed one keeps Kite's filled quantity."""
    plan = next(p for p in _plans(orders, strategy_id).plans if p.plan_number == number)
    if status == "open":
        plan = dataclasses.replace(plan, status="open", closed_at=None, close_reason=None,
                                   orders=tuple(dataclasses.replace(o, filled_quantity=None) for o in plan.orders))
    return dataclasses.replace(plan, created_at=created)


class _Entry:
    def __init__(self, *plans: StoredPlan) -> None:
        self.underlying, self.plans = "NIFTY", plans


class _Writer:
    """Records every write; each call is first passed through the real stores' own checks (the close reason's fill
    rule, the mismatch's contract key, agreeing pair and source), so a write the database would refuse fails here."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def writer(self) -> nd.PlanWriter:
        async def close_plan(conn, user_ref, strategy_id, plan_number, *, reason, filled=None):  # noqa: PLR0913
            assert (conn, user_ref) == (CONN, USER) and filled is None
            assert reason in eps.CLOSE_REASONS
            self.calls.append(("close", strategy_id, plan_number, reason))

        async def record_mismatch(conn, user_ref, strategy_id, *, contract_key, expected_units,  # noqa: PLR0913
                                  zerodha_units, report, source):
            assert (conn, user_ref) == (CONN, USER)
            rs._contract_key(contract_key, rs.BAD_MISMATCH)
            rs._report(report)
            assert expected_units != zerodha_units and source in rs.SOURCES
            self.calls.append(("mismatch", strategy_id, contract_key, expected_units, zerodha_units, report["reason"]))
            return len(self.calls)

        return nd.PlanWriter(close_plan, record_mismatch)


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")


def _net(quantity: int | None) -> dict:
    """Zerodha's next-day net through the real reply adapter (positions-122104 with the row's quantity set)."""
    return dict(positions_from_reply(_positions(quantity), _index()).net)


def _resolve(store, quantity, *, at=MON, standalone=None, book=(), net=None, catalogue=None):  # noqa: PLR0913
    log = _Writer()
    sources = ra.Sources(catalogue or _catalogue(), lambda: at, _reader(store))
    broker = _net(quantity) if net is None else net
    done = asyncio.run(nd.resolve_earlier_day_plans(ra.Account(CONN, USER), standalone or {}, broker, book,
                                                    sources, writer=log.writer()))
    return done, log.calls


def _attribute(store, quantity, *, at=MON, standalone=None, book=(), mismatches=None):  # noqa: PLR0913
    sources = ra.Sources(_catalogue(), lambda: at, _reader(store, mismatches))
    return asyncio.run(ra.attribute_and_compare(ra.Account(CONN, USER), standalone or {}, _net(quantity), book,
                                                sources, at=at))


NEXT_DAY_BOOK = tuple(orders_from_reply([]))  # Kite's order book the next day: none of Friday's orders


# ---- ENTRY ------------------------------------------------------------------------------------------------------

def test_net_roundtrip_entry_net_equals_base_is_unresolved_with_a_stored_mismatch():
    """NET-ROUNDTRIP core (F-55, net-only-read-misses-roundtrip): earlier-day open ENTRY (real OFS1V1L0 BUY 65), no
    other plan (base 0), Zerodha flat the next day. Flat is what a filled-then-hand-sold round trip also leaves (the
    real 2026-10-16 positions-151006 row: quantity 0 with day_buy_quantity 65 and day_sell_quantity 65 the same day,
    and Kite drops that row the next day), so nothing_placed is NOT written: one stored mismatch (by hand: expected =
    base 0 + planned 65 = 65, Zerodha 0) and unresolved_from_positions; the strategy stays blocked."""
    done, calls = _resolve({1: _Entry(_real_plan(1))}, None, book=NEXT_DAY_BOOK)
    assert calls == [("mismatch", 1, IID, 65, 0, ra.UNSETTLED_ROUNDTRIP_UNREAD), ("close", 1, 1, eps.UNRESOLVED)]
    assert [(r.strategy_id, r.plan_number, r.action, r.reason, r.mismatch_ids) for r in done] == [
        (1, 1, "ENTRY", eps.UNRESOLVED, (1,))]
    seen = _attribute({1: _Entry(_real_plan(1))}, None)
    assert dict(seen.pending) == {} and seen.blocked == frozenset({"1"})
    assert [p.reason for p in seen.unresolved[KEY]] == [ra.UNSETTLED_ROUNDTRIP_UNREAD]


@pytest.mark.parametrize("quantity", [65, 30])
def test_ac6_entry_net_above_base_is_a_mismatch_never_filled(quantity):
    """AC-6 / ADR-109 (2): earlier-day ENTRY, base 0, Zerodha +65 (or +30) the next day -> a mismatch (expected 0,
    Zerodha 65/30) then unresolved_from_positions; never filled (the lots cannot be told from outside lots)."""
    done, calls = _resolve({1: _Entry(_real_plan(1))}, quantity)
    assert calls == [("mismatch", 1, IID, 0, quantity, ra.UNSETTLED_NET_CHANGED),
                     ("close", 1, 1, eps.UNRESOLVED)]
    assert done[0].reason == eps.UNRESOLVED and done[0].mismatch_ids == (1,)
    seen = _attribute({1: _Entry(_real_plan(1))}, quantity)
    assert seen.blocked == frozenset({"1"}) and dict(seen.pending) == {}
    assert [(p.strategy_id, p.plan_number, p.tag, p.reason) for p in seen.unresolved[KEY]] == [
        ("1", 1, "OFS1V1L0", ra.UNSETTLED_NET_CHANGED)]
    assert KEY not in seen.compared_net and dict(seen.outside) == {}  # never split as outside lots


@pytest.mark.parametrize(("quantity", "outcome"), [(65, eps.UNRESOLVED), (130, eps.UNRESOLVED),
                                                    (95, eps.UNRESOLVED), (0, eps.UNRESOLVED)])
def test_ac4_base_is_the_other_stored_plans(quantity, outcome):
    """AC-4: the strategy holds +65 from a CLOSED plan (real OFS1V1L0 filled 65) and has an earlier-day open ENTRY
    BUY 65 as plan 2 (derived). Base = 65: net 65 (= base, a round trip is not ruled out) -> mismatch (expected 65 + 65, Zerodha 65); 130 (base + 65), 95 (base + 30), 0 -> mismatch."""
    closed = _real_plan(1, status="closed")
    plan2 = dataclasses.replace(_real_plan(1), plan_number=2, orders=tuple(
        dataclasses.replace(o, tag="OFS1V2L0") for o in _real_plan(1).orders))
    done, calls = _resolve({1: _Entry(closed, plan2)}, quantity)
    assert done[0].plan_number == plan2.plan_number and done[0].reason == outcome
    if quantity == 65:
        assert calls == [("mismatch", 1, IID, 130, 65, ra.UNSETTLED_ROUNDTRIP_UNREAD), ("close", 1, 2, eps.UNRESOLVED)]
    else:
        assert calls == [("mismatch", 1, IID, 65, quantity, ra.UNSETTLED_NET_CHANGED), ("close", 1, 2, eps.UNRESOLVED)]


def test_net_roundtrip_partial_roundtrip_net_differs_is_the_existing_mismatch():
    """Bought 65 and hand-sold 30 leaves net 35 != base 0: the net-changed mismatch (expected 0, Zerodha 35)."""
    _, calls = _resolve({1: _Entry(_real_plan(1))}, 35)
    assert calls == [("mismatch", 1, IID, 0, 35, ra.UNSETTLED_NET_CHANGED), ("close", 1, 1, eps.UNRESOLVED)]


# ---- EXIT (ADR-111's carry-over) ----------------------------------------------------------------------------------

def test_net_roundtrip_exit_net_equals_held_is_unresolved():
    """ADR-111 / F-55: held +65 (real entry, closed filled 65), earlier-day open EXIT OFS1V2L0 SELL 65, Zerodha still
    +65 the next day: the EXIT may have sold and been bought back by hand, so it is not closed nothing_placed; by
    hand expected = held 65 + planned (-65) = 0, Zerodha 65 -> one mismatch, unresolved_from_positions."""
    done, calls = _resolve({1: _Entry(_real_plan(1, status="closed"), _real_plan(2))}, 65)
    assert calls == [("mismatch", 1, IID, 0, 65, ra.UNSETTLED_ROUNDTRIP_UNREAD), ("close", 1, 2, eps.UNRESOLVED)]
    assert done[0].action == "EXIT"


def test_ac6_exit_net_zero_is_a_mismatch_never_exited():
    """AC-6 / ADR-111 / ADR-109 (4): held +65, earlier-day open EXIT, Zerodha flat the next day (filled, or sold by
    hand on Kite) -> mismatch (expected 65, Zerodha 0) and unresolved_from_positions, never exited; Zerodha 0 is what
    the store's kite_flat_marked_exited resolution requires."""
    done, calls = _resolve({1: _Entry(_real_plan(1, status="closed"), _real_plan(2))}, None)
    assert calls == [("mismatch", 1, IID, 65, 0, ra.UNSETTLED_NET_CHANGED), ("close", 1, 2, eps.UNRESOLVED)]
    assert done[0].reason != "exited"
    seen = _attribute({1: _Entry(_real_plan(1, status="closed"), _real_plan(2))}, None)
    assert seen.blocked == frozenset({"1"}) and KEY in seen.unresolved


# ---- expiry and the day boundary ---------------------------------------------------------------------------------

def test_ac6_contract_expired_is_a_mismatch_even_when_net_equals_base():
    """AC-6: the contract's expiry close (2026-10-19 15:30 IST) has passed; base 0, net 0 -> never nothing_placed:
    mismatch with expected = base + planned (65), Zerodha 0, reason contract_expired."""
    _, calls = _resolve({1: _Entry(_real_plan(1))}, None, at=EXPIRY)
    assert calls == [("mismatch", 1, IID, 65, 0, ra.UNSETTLED_EXPIRED), ("close", 1, 1, eps.UNRESOLVED)]
    one_second_before = EXPIRY - datetime.timedelta(seconds=1)
    _, before = _resolve({1: _Entry(_real_plan(1))}, None, at=one_second_before)
    assert before == [("mismatch", 1, IID, 65, 0, ra.UNSETTLED_ROUNDTRIP_UNREAD), ("close", 1, 1, eps.UNRESOLVED)]


@pytest.mark.parametrize("created", [
    datetime.datetime(2026, 10, 19, 9, 20, tzinfo=IST),  # this morning
    datetime.datetime(2026, 10, 18, 18, 31, tzinfo=datetime.UTC),  # 00:01 IST today, stamped in UTC
])
def test_ac1_same_day_open_plan_is_untouched(created):
    """AC-1 / ADR-110: an open plan created today (IST date; a UTC stamp is converted) is not resolved from the net
    (no write); the attribution keeps it pending on today's book."""
    done, calls = _resolve({1: _Entry(_real_plan(1, created=created))}, 65)
    assert (done, calls) == ((), [])
    seen = _attribute({1: _Entry(_real_plan(1, created=created))}, 65)
    assert [p.reason for p in seen.pending[KEY]] == [ra.PENDING_ABSENT] and dict(seen.unresolved) == {}


@pytest.mark.parametrize("created", [datetime.datetime(2026, 10, 16, 23, 59, tzinfo=IST),
                                     datetime.datetime(2026, 10, 15, 15, 7, 21, tzinfo=IST)])
def test_ac4_plan_at_2359_and_two_days_old_are_resolved(created):
    """AC-4: a plan created 23:59 IST the evening before, and one two days old, are earlier-day plans: net = base ->
    unresolved (round trip not ruled out)."""
    _, calls = _resolve({1: _Entry(_real_plan(1, created=created))}, None)
    assert calls == [("mismatch", 1, IID, 65, 0, ra.UNSETTLED_ROUNDTRIP_UNREAD), ("close", 1, 1, eps.UNRESOLVED)]


def test_ac1_earlier_day_plan_with_its_tag_in_todays_book_stays_on_the_book_path():
    """AC-1: an earlier-day plan whose tag IS in today's book (an order placed the evening before shows today) is not
    resolved from the net: the book decides (real orders-122104: COMPLETE 65 -> counted, no mismatch)."""
    book = tuple(orders_from_reply(_recorded("orders-122104")))
    done, calls = _resolve({1: _Entry(_real_plan(1))}, 65, book=book)
    assert (done, calls) == ((), [])
    seen = _attribute({1: _Entry(_real_plan(1))}, 65, book=book)
    assert seen.blocked == frozenset() and dict(seen.held) == {"1": {KEY: 65}}


def test_ac1_naive_created_at_is_refused_with_no_write():
    """AC-1: a created_at without a time zone cannot be placed in a day: refused, nothing written."""
    naive = _real_plan(1, created=FRI.replace(tzinfo=None))
    with pytest.raises(ra.AttributionError, match="created_at"):
        _resolve({1: _Entry(naive)}, None)


# ---- shared contracts ---------------------------------------------------------------------------------------------

def test_ac6_two_earlier_day_plans_on_one_contract_are_both_mismatches():
    """AC-6: strategies 1 and 2 each left an earlier-day open plan on the contract (BUY 65 and the derived SELL 65);
    net 0 = base, yet two opposite fills would net to nothing -> both unresolved (another_plan_unsettled)."""
    store = {1: _Entry(_real_plan(1)), 2: _Entry(_real_plan(2, strategy_id=2))}
    done, calls = _resolve(store, None)
    assert [r.reason for r in done] == [eps.UNRESOLVED] * len(store)
    assert sorted(c for c in calls if c[0] == "mismatch") == [
        ("mismatch", 1, IID, 65, 0, ra.UNSETTLED_SHARED), ("mismatch", 2, IID, -65, 0, ra.UNSETTLED_SHARED)]


def test_ac6_another_strategys_same_day_open_plan_makes_it_a_mismatch():
    """AC-6: strategy 2 has a same-day open plan on the contract (pending on today's book): its units are unknown, so
    strategy 1's earlier-day plan is a mismatch (another_plan_unsettled), not nothing_placed."""
    store = {1: _Entry(_real_plan(1)), 2: _Entry(_real_plan(1, strategy_id=2, created=MON))}
    done, calls = _resolve(store, None)
    assert [(r.strategy_id, r.reason) for r in done] == [(1, eps.UNRESOLVED)]
    assert calls[0] == ("mismatch", 1, IID, 65, 0, ra.UNSETTLED_SHARED)


@pytest.mark.parametrize(("quantity", "outcome"), [(25, eps.UNRESOLVED), (90, eps.UNRESOLVED)])
def test_ac4_standalone_is_in_the_base(quantity, outcome):
    """AC-4 (REQ-060 AC-7): a standalone 25 recorded on the contract; earlier-day ENTRY BUY 65. Net 25 = base ->
    mismatch (expected 25 + 65 = 90, Zerodha 25, round trip not ruled out); net 90 (base + 65) -> mismatch (expected 25, Zerodha 90)."""
    done, calls = _resolve({1: _Entry(_real_plan(1))}, quantity, standalone={KEY: 25})
    assert done[0].reason == outcome
    expected = ("mismatch", 1, IID, 90, 25, ra.UNSETTLED_ROUNDTRIP_UNREAD) if quantity == 25 else (
        "mismatch", 1, IID, 25, 90, ra.UNSETTLED_NET_CHANGED)
    assert calls[0] == expected


def test_ac6_shared_contract_net_equals_base_is_a_mismatch_for_every_holder():
    """AC-6 (Q224, round 2 MINOR 3): strategy 2 holds +65 by a closed plan; strategy 1's earlier-day ENTRY BUY 65.
    Net 65 = base 65, yet S1 filled and S2's lots sold by hand on Kite give the same net: a shared contract, never
    nothing_placed. By hand: expected = base 65 + planned 65 = 130, Zerodha 65, one row for S1 and one for S2."""
    store = {1: _Entry(_real_plan(1)), 2: _Entry(_real_plan(1, strategy_id=2, status="closed"))}
    done, calls = _resolve(store, 65)
    assert calls == [("mismatch", 1, IID, 130, 65, ra.UNSETTLED_HELD_ELSEWHERE),
                     ("mismatch", 2, IID, 130, 65, ra.UNSETTLED_HELD_ELSEWHERE), ("close", 1, 1, eps.UNRESOLVED)]
    assert [(r.strategy_id, r.reason, len(r.mismatch_ids)) for r in done] == [(1, eps.UNRESOLVED, 2)]


def _stored(calls: list[tuple], *, settled: bool = False) -> dict[int, tuple[rs.StoredMismatch, ...]]:
    """The writer's mismatch calls as the store would read them back (unresolved, or settled by a basket)."""
    out: dict[int, list[rs.StoredMismatch]] = {}
    for number, call in enumerate(calls, start=1):
        if call[0] != "mismatch":
            continue
        resolutions = (rs.StoredResolution(rs.BASKET, USER, None, MON),) if settled else ()
        out.setdefault(call[1], []).append(rs.StoredMismatch(
            number, call[1], call[2], call[3], call[4], {"reason": call[5]}, nd.SOURCE, MON, resolutions))
    return {sid: tuple(rows) for sid, rows in out.items()}


def _closed_unresolved(plan: StoredPlan) -> StoredPlan:
    return dataclasses.replace(plan, status="closed", close_reason=eps.UNRESOLVED, closed_at=MON,
                               orders=tuple(dataclasses.replace(o, filled_quantity=0) for o in plan.orders))


def test_ac6_holder_gets_a_stored_mismatch_and_stays_blocked_after_the_write():
    """AC-6 (REQ-060 "blocks every holder", round 2 MAJOR 1, the reviewer's HOLDER attack): S1 earlier-day BUY 65,
    S2 holds 65 (closed plan), Zerodha 130. Before the write both are blocked; the write stores a row for S1 AND S2
    (expected 65, Zerodha 130); after it (S1's plan closed unresolved, 0 stored) both stay blocked and nothing on the
    contract is outside or compared. Control: without the stored rows the same books read 65 outside, none blocked."""
    s2 = _Entry(_real_plan(1, strategy_id=2, status="closed"))
    store = {1: _Entry(_real_plan(1)), 2: s2}
    assert _attribute(store, 130).blocked == {"1", "2"}
    _, calls = _resolve(store, 130)
    assert calls == [("mismatch", 1, IID, 65, 130, ra.UNSETTLED_HELD_ELSEWHERE),
                     ("mismatch", 2, IID, 65, 130, ra.UNSETTLED_HELD_ELSEWHERE), ("close", 1, 1, eps.UNRESOLVED)]
    after = {1: _Entry(_closed_unresolved(_real_plan(1))), 2: s2}
    post = _attribute(after, 130, mismatches=_stored(calls))
    assert post.blocked == {"1", "2"}
    assert dict(post.outside) == {} and KEY not in post.compared_net and dict(post.stored) == {KEY: ("1", "2")}
    control = _attribute(after, 130)
    assert dict(control.outside) == {KEY: 65} and control.blocked == frozenset()
    settled = _attribute(after, 130, mismatches=_stored(calls, settled=True))  # a settling resolution lifts it
    assert dict(settled.stored) == {} and settled.blocked == frozenset()


def test_ac6_a_stored_mismatch_makes_the_contract_shared_for_an_earlier_day_plan():
    """AC-6: an unresolved stored mismatch on the contract (strategy 2) makes strategy 1's earlier-day plan
    unresolved even though net 0 = base 0 (another unsettled state touches it); S2 has no units, so S1 only."""
    stored = _stored([("mismatch", 2, IID, 65, 0, ra.UNSETTLED_NET_CHANGED)])
    store = {1: _Entry(_real_plan(1)), 2: _Entry()}
    sources = ra.Sources(_catalogue(), lambda: MON, _reader(store, stored))
    log = _Writer()
    asyncio.run(nd.resolve_earlier_day_plans(ra.Account(CONN, USER), {}, {}, (), sources, writer=log.writer()))
    assert log.calls == [("mismatch", 1, IID, 65, 0, ra.UNSETTLED_SHARED), ("close", 1, 1, eps.UNRESOLVED)]


def test_ac7_a_forged_or_foreign_stored_mismatch_is_refused_and_an_unmapped_one_blocks():
    """AC-7: the mismatch read is checked: not a StoredMismatch, or another strategy's row -> refused; an unresolved
    row naming no catalogue contract still blocks its strategy (nothing to exclude: Zerodha's net cannot carry it)."""
    row = _stored([("mismatch", 1, IID, 65, 0, ra.UNSETTLED_NET_CHANGED)])[1][0]
    store = {1: _Entry(_closed_unresolved(_real_plan(1)))}
    with pytest.raises(ra.AttributionError, match="stored mismatches"):
        _attribute(store, None, mismatches={1: (dataclasses.asdict(row),)})
    with pytest.raises(ra.AttributionError, match="stored mismatches"):
        _attribute(store, None, mismatches={1: (dataclasses.replace(row, strategy_id=2),)})
    lost = _attribute(store, None, mismatches={1: (dataclasses.replace(row, contract_key="NSE_FO:999999"),)})
    assert lost.blocked == {"1"} and dict(lost.stored) == {}


def test_ac6_two_stored_ids_of_one_contract_are_one_mismatch_key():
    """AC-6 (round 2 MINOR 4): the plan's order sits on a twin id of the real contract (same key); the stored key is
    the contract's smallest catalogue id (the real NSE_FO:47189), never the plan's own id text."""
    real = _listed()
    twin_token = (int(TOKEN) >> 8) + 1
    twin = zerodha_listed(
        instrument_token=int(TOKEN) + 1, exchange_token=twin_token, tradingsymbol="NIFTY26O1923650CE",
        name=real.contract.name, expiry=real.contract.expiry, strike=real.contract.strike, tick_size=Decimal("0.05"),
        lot_size=real.contract.lot_size, instrument_type=real.contract.instrument_type, segment="NFO-OPT",
        exchange="NFO")
    plan = _real_plan(1)
    plan = dataclasses.replace(plan, orders=tuple(dataclasses.replace(o, instrument_id=f"{NSE_FO}:{twin_token}")
                                                  for o in plan.orders))
    _, calls = _resolve({1: _Entry(plan)}, 65, catalogue=_catalogue(twin))
    assert calls == [("mismatch", 1, IID, 0, 65, ra.UNSETTLED_NET_CHANGED), ("close", 1, 1, eps.UNRESOLVED)]


def test_ac1_future_created_at_is_refused_with_no_write():
    """AC-1 (round 2 MINOR 2, the reviewer's FUTURE attack): a plan stamped tomorrow (clock skew) is never read as
    earlier: refused, nothing written; today's book cannot close it either (from_earlier_session stays True)."""
    future = _real_plan(1, created=MON + datetime.timedelta(days=1))
    log = _Writer()
    sources = ra.Sources(_catalogue(), lambda: MON, _reader({1: _Entry(future)}))
    with pytest.raises(ra.AttributionError, match="future"):
        asyncio.run(nd.resolve_earlier_day_plans(ra.Account(CONN, USER), {}, {}, (), sources, writer=log.writer()))
    assert log.calls == []
    assert er.created_session(future, MON.date()) == er.SESSION_FUTURE and er.from_earlier_session(future, MON.date())


def test_ac1_earlier_means_strictly_before_todays_ist_date():
    """AC-1: the IST date decides, strictly before today. 18:29 UTC Sun = 23:59 IST Sun -> earlier; 18:31 UTC Sun =
    00:01 IST Mon -> today (left to the book, no write); FRI -> earlier."""
    utc = datetime.UTC
    sun = _real_plan(1, created=datetime.datetime(2026, 10, 18, 18, 29, tzinfo=utc))
    mon = _real_plan(1, created=datetime.datetime(2026, 10, 18, 18, 31, tzinfo=utc))
    today = MON.date()
    assert [er.created_session(p, today) for p in (sun, mon, _real_plan(1))] == [
        er.SESSION_EARLIER, er.SESSION_TODAY, er.SESSION_EARLIER]
    assert _resolve({1: _Entry(mon)}, None)[1] == []
    assert _resolve({1: _Entry(sun)}, None)[1] == [
        ("mismatch", 1, IID, 65, 0, ra.UNSETTLED_ROUNDTRIP_UNREAD), ("close", 1, 1, eps.UNRESOLVED)]


def test_ac6_mixed_sides_plan_is_a_mismatch_with_gross_expected():
    """AC-6: a derived plan that BUYs 65 and SELLs 65 on one contract; net 0 = base cannot show nothing filled ->
    mismatch, expected = base + gross 130 (the signed plan cancels), reason plan_sides_mixed."""
    buy = _real_plan(1).orders[0]
    sell = dataclasses.replace(buy, leg_index=1, tag="OFS1V1L1", transaction_type="SELL")
    plan = dataclasses.replace(_real_plan(1), orders=(buy, sell))
    _, calls = _resolve({1: _Entry(plan)}, None)
    assert calls == [("mismatch", 1, IID, 130, 0, ra.UNSETTLED_MIXED_SIDES), ("close", 1, 1, eps.UNRESOLVED)]


# ---- seams -------------------------------------------------------------------------------------------------------

def test_ac6_fake_writer_refused_outside_test_env(monkeypatch):
    """AC-6: a writer other than the two stores is refused unless APP_ENV is exactly "test"; nothing is read."""
    monkeypatch.setenv("APP_ENV", "production")
    sources = ra.Sources(_catalogue(), lambda: MON, ra.StoreReader())
    with pytest.raises(ra.AttributionError, match="writer"):
        asyncio.run(nd.resolve_earlier_day_plans(ra.Account(CONN, USER), {}, {}, (), sources,
                                                 writer=_Writer().writer()))
    with pytest.raises(ra.AttributionError, match="PlanWriter"):
        asyncio.run(nd.resolve_earlier_day_plans(ra.Account(CONN, USER), {}, {}, (), sources, writer=object()))


def test_ac1_time_is_the_platform_clock():
    """AC-1: the resolver reads the time from the platform clock (no caller-passed time): the clock at the expiry
    close makes the contract expired; the stored report carries that time."""
    log = _Writer()
    seen: list[dict] = []
    base = log.writer()

    async def record(*args, **kwargs):
        seen.append(kwargs["report"])
        return await base.record_mismatch(*args, **kwargs)

    sources = ra.Sources(_catalogue(), lambda: EXPIRY, _reader({1: _Entry(_real_plan(1))}))
    asyncio.run(nd.resolve_earlier_day_plans(ra.Account(CONN, USER), {}, _net(None), (), sources,
                                             writer=nd.PlanWriter(base.close_plan, record)))
    assert seen[0]["at"] == EXPIRY.isoformat() and seen[0]["reason"] == ra.UNSETTLED_EXPIRED


def test_ac6_store_contract_key_admits_the_apps_real_instrument_id():
    """AC-6: the mismatch store accepts the app's real stored instrument id (NSE_FO:47189, an underscore segment) and
    still refuses a lowercase or zero-token key."""
    assert rs._contract_key(IID, rs.BAD_MISMATCH) == IID
    for bad in ("nse_fo:47189", "NSE_FO:047189", "NSE_FO:", "_NSE:1"):
        with pytest.raises(rs.ReconciliationStoreError):
            rs._contract_key(bad, rs.BAD_MISMATCH)


def test_ac6_two_contract_plan_records_only_the_unsettled_contract():
    """AC-6: a derived two-leg earlier-day ENTRY (BUY 65 on the real 23650 CE, BUY 65 on 23700 CE); Zerodha flat on
    23650 (= base) and +65 on 23700 -> one mismatch, on 23700 only (expected 0, Zerodha 65); the plan is unresolved."""
    real = _listed()
    other_token = (int(TOKEN) >> 8) + 2
    other = zerodha_listed(
        instrument_token=int(TOKEN) + 2, exchange_token=other_token, tradingsymbol="NIFTY26O1923700CE",
        name=real.contract.name, expiry=real.contract.expiry, strike=Decimal("23700"), tick_size=Decimal("0.05"),
        lot_size=real.contract.lot_size, instrument_type=real.contract.instrument_type, segment="NFO-OPT",
        exchange="NFO")
    key2 = ("NIFTY", Instrument.CE, Decimal("23700.00"), KEY[3])
    leg0 = _real_plan(1).orders[0]
    leg1 = dataclasses.replace(leg0, leg_index=1, tag="OFS1V1L1", instrument_id=f"{NSE_FO}:{other_token}",
                               tradingsymbol="NIFTY26O1923700CE")
    plan = dataclasses.replace(_real_plan(1), orders=(leg0, leg1))
    done, calls = _resolve({1: _Entry(plan)}, None, net={key2: 65}, catalogue=_catalogue(other))
    assert calls == [("mismatch", 1, IID, 65, 0, ra.UNSETTLED_ROUNDTRIP_UNREAD),
                     ("mismatch", 1, f"{NSE_FO}:{other_token}", 0, 65, ra.UNSETTLED_NET_CHANGED),
                     ("close", 1, 1, eps.UNRESOLVED)]
    assert [(c.key, c.reason) for c in done[0].decision.contracts] == [
        (KEY, ra.UNSETTLED_ROUNDTRIP_UNREAD), (key2, ra.UNSETTLED_NET_CHANGED)]


def test_ac1_unknown_plan_status_is_refused():
    """AC-1: a stored plan whose status is neither open nor closed is refused (fail closed), nothing written."""
    odd = dataclasses.replace(_real_plan(1), status="opened")
    with pytest.raises(ra.AttributionError, match="status"):
        _resolve({1: _Entry(odd)}, None)


def test_ac1_clock_without_time_zone_is_refused():
    """AC-1: a platform clock that is not time-zone aware cannot name today's IST session: refused, nothing written."""
    with pytest.raises(ra.AttributionError, match="time-zone-aware"):
        _resolve({1: _Entry(_real_plan(1))}, None, at=MON.replace(tzinfo=None))
