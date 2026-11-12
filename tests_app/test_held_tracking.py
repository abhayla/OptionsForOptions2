"""GC-TRACK1 k11-k15 (ADR-290 (5), ADR-292 (5), ADR-264, ADR-259): the background watcher tracks a held condor (paper
orders + a ``strategy_held_entries`` row) exactly like a paper one. Pinning tests: a held condor IS a paper book, so no
code is expected to change.

k11 (core) and k13 run the real ``owner_lister`` and the real ``Worker`` on strategies seeded through the app's own
stores (as test_background_worker). k12 and k14 run on the rolled-back connection of test_held_entry. k15 settles a held
book at a FIXED past expiry (never today's date) through ``paper_settlement``.
"""
from __future__ import annotations

import collections
import datetime
import itertools
from decimal import Decimal as D

import test_background_worker as bw
from _scenario_catalogue import load_library
from ofo.timeutil import IST
from ofo_app import (
    adjustment_check,
    adjustment_readers,
    background,
    held_entry_store,
    paper_store,
    scenario_mode,
    strategy_store,
)
from ofo_app import paper_settlement as ps
from ofo_app import paper_trigger_store as pts
from ofo_app import playbook_store as pb
from sqlalchemy import text
from test_held_entry import ENTERED, _held_body, _post
from test_paper_settlement import _catalogue, _close_of, _legs, _real
from test_playbook_store import _body
from test_strategy_store import _with_draft
from test_strategy_tracking import _paper_body, _setup
from test_strategy_tracking import db as tracking_db

app_db_url = bw.app_db_url  # fixture: the app's own sessionmaker on the test database
db = tracking_db  # fixture: one rolled-back connection
_RUN = itertools.count(1)
PAST = datetime.datetime(2026, 11, 2, 4, 0, tzinfo=datetime.UTC)  # a fixed past entry time (before every expiry used)


async def _seed_two(app_engine, monkeypatch) -> tuple[int, int, scenario_mode.Scenario]:
    """Two open strategies of the owner: (plain paper, held). The held one has a ``strategy_held_entries`` row, which
    is all the held block adds to a paper book (held_entry_store.record, same transaction as the first basket)."""
    monkeypatch.setenv("OFO_SCENARIO", "ADJ-02")
    scn = scenario_mode.load("ADJ-02")
    await load_library(app_engine)
    run = next(_RUN)
    ids = []
    for kind in ("paper", "held"):
        name = f"{bw.seed_mod.NAME_PREFIX}k{kind[0]}{run}"  # 20-character limit
        monkeypatch.setattr(bw.seed_mod, "strategy_name", lambda _s, n=name: n)
        ids.append(await bw.seed_mod.seed("ADJ-02"))
    paper, held = ids
    async with app_engine.connect() as conn:
        await held_entry_store.record(conn, held, PAST, None)
        await conn.commit()
    real_list = strategy_store.list_strategies

    async def own(conn, user_ref):
        return [s for s in await real_list(conn, user_ref) if s.id in {paper, held}]
    monkeypatch.setattr(strategy_store, "list_strategies", own)
    return paper, held, scn


# rolled-back tests first: they load the small fixture catalogue, which the committed scenario library would refuse


async def test_k12_the_settings_in_force_are_the_same_for_a_held_and_a_paper_condor(db):
    app, held, *_ = await _setup(db)
    user = held.user_ref
    assert (await _post(app, held, _held_body(held, {"entry_at": ENTERED.isoformat()}))).status_code == 201  # noqa: PLR2004
    paper = (await _with_draft(db, user))[1]
    assert (await _post(app, paper, _paper_body(paper))).status_code == 201  # noqa: PLR2004

    async def both():
        return [await adjustment_check.resolve(db, user, s.id, "ic") for s in (held, paper)]
    a, b = await both()  # playbook defaults (ADR-264): the same system playbook
    assert (a.source, a.body, a.playbook_id, a.is_system) == (b.source, b.body, b.playbook_id, b.is_system)
    assert a.source == "system"
    own = await pb.create(db, user, "ic", "My IC", _body(value="0.42"))  # the owner's override
    await pb.make_active(db, user, own.id)
    a, b = await both()
    assert a.body == b.body and a.playbook_id == b.playbook_id == own.id and not a.is_system
    assert a.body["triggers"]["T-01"]["weekly"][0] == "0.42"


async def test_k14_a_held_condors_alert_is_in_the_inbox_and_the_bell_like_a_paper_ones(db):
    app, held, *_ = await _setup(db)
    user = held.user_ref
    assert (await _post(app, held, _held_body(held, {"entry_at": ENTERED.isoformat()}))).status_code == 201  # noqa: PLR2004
    paper = (await _with_draft(db, user))[1]
    assert (await _post(app, paper, _paper_body(paper))).status_code == 201  # noqa: PLR2004
    opened = {}
    for s in (held, paper):
        opened[s.id] = await pb.open_suggestion(db, user, s.id, "T-01", trigger_id="T-01", stage="Early",
                                                value=D("0.42"), threshold=D("0.5"))
        tid = (await db.execute(text("INSERT INTO public.paper_triggers (strategy_id, kind, underlying, direction, "
                                     "level) VALUES (:s, 'conditional_exit', 'NIFTY', 'below', 22850.00) "
                                     "RETURNING id"), {"s": s.id})).scalar_one()
        await pts.add_alert(db, s.id, int(tid), "a", "b")
    assert {r.suggestion.id for r in await pb.inbox(db, user)} == {o.id for o in opened.values()}
    rows, unread = await pts.alerts(db, user)
    assert {r.strategy_id for r in rows} == {held.id, paper.id} and unread == 2  # noqa: PLR2004


async def test_k15_a_held_condor_past_expiry_settles_at_intrinsic_value_and_reads_completed(db):
    ids = await _catalogue(db)
    sid = await _real(db, ids, 52)  # the fixture's real SENSEX book, expiry 2026-10-29 (a fixed past date)
    await held_entry_store.record(db, sid, PAST.replace(month=10, day=20), None)
    status = text("SELECT status FROM public.strategies WHERE id = :s")
    assert (await db.execute(status, {"s": sid})).scalar_one() == "draft"
    run = await ps.settle_expired(db, datetime.datetime(2026, 10, 30, 9, 0, tzinfo=IST), _close_of())
    assert sorted((s.side, s.price) for s in run.settled if s.strategy_id == sid) == sorted(
        [("BUY", D("0.00")), ("BUY", D("246.03"))]), run  # the PE out of the money, the CE in: intrinsic value
    assert len(_legs(52)) == 2  # noqa: PLR2004 - the fixture strategy has two legs, both settled
    assert (await db.execute(status, {"s": sid})).scalar_one() == "closed"  # Completed
    held_rows = (await db.execute(text("SELECT count(*) FROM public.strategy_held_entries "
                                              "WHERE strategy_id = :s"), {"s": sid})).scalar_one()
    assert held_rows == 1  # the held record stays; the book is what settled


async def test_k11_core_held_and_paper_are_both_listed_and_each_checked_once_per_cycle(app_db_url, monkeypatch):
    paper, held, scn = await _seed_two(app_db_url, monkeypatch)
    listed = await background.owner_lister(scn.provider)
    assert sorted(w.strategy_id for w in listed) == sorted([paper, held]) and not listed.unread
    now = [scn.clock_at]
    worker = bw._worker(scn, lambda: now[0])
    await worker.cycle()
    assert worker.errors == [], worker.errors
    assert sorted(w.strategy_id for w in worker.monitors) == sorted([paper, held])
    assert collections.Counter(sid for sid, _ in worker.checks) == {paper: 1, held: 1}
    assert worker._recomputes == {paper: 1, held: 1}, worker._recomputes  # the minute line's recomputes counter
    assert worker.status[held] is background.MonitoringStatus.ACTIVE
    print(f"K11-CORE-PROOF paper={paper} held={held} checks=1/1 recomputes={worker._recomputes}")


async def test_k11_a_failed_read_of_one_strategy_skips_it_and_keeps_the_other(app_db_url, monkeypatch):
    paper, held, scn = await _seed_two(app_db_url, monkeypatch)
    real = adjustment_readers.read_tracked

    async def read(sid, rates, *a, **k):
        if sid == held:
            raise adjustment_readers.TrackedUnreadable("read failed")
        return await real(sid, rates, *a, **k)
    monkeypatch.setattr(adjustment_readers, "read_tracked", read)
    listed = await background.owner_lister(scn.provider)
    assert [w.strategy_id for w in listed] == [paper] and held in listed.unread  # skipped, not dropped from the DB


async def test_k13_no_open_strategy_no_check_and_exited_or_settled_leave_the_list(app_db_url, monkeypatch):
    paper, held, scn = await _seed_two(app_db_url, monkeypatch)
    now = [scn.clock_at]
    # absent: the owner has no open strategy -> the cycle makes no check
    empty = bw._worker(scn, lambda: now[0], lister=_none)
    await empty.cycle()
    assert empty.checks == [] and empty.monitors == []
    # exited: every leg of the held condor closed -> it leaves the list; the paper one stays
    async with app_db_url.connect() as conn:
        rows = await paper_store.load(conn, held)
        exits = [paper_store.NewOrder(r.order.contract_id, "BUY" if r.order.side == "SELL" else "SELL",
                                      r.order.quantity, D("1"), "exit", scn.clock_at) for r in rows]
        await paper_store.place(conn, "owner", held, exits)
        await conn.commit()
    listed = await background.owner_lister(scn.provider)
    assert [w.strategy_id for w in listed] == [paper]
    # settled: past its fixed expiry the paper one settles and leaves the list too
    expiry = (await _expiry(app_db_url, paper))
    at = datetime.datetime.combine(expiry, datetime.time(15, 50), IST)

    async def close_of(_u, _e):
        return D("23000")
    async with app_db_url.connect() as conn:
        run = await ps.settle_expired(conn, at, close_of)
    assert paper in {s.strategy_id for s in run.settled} and run.failed == ()
    assert await background.owner_lister(scn.provider) == []
    worker = bw._worker(scn, lambda: now[0])
    await worker.cycle()
    assert worker.checks == []


async def _none():
    return background.Listed()


async def _expiry(engine, sid: int) -> datetime.date:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT min(c.expiry) FROM public.paper_orders o JOIN "
                                        "public.catalogue_contracts c ON c.id = o.contract_id "
                                        "WHERE o.strategy_id = :s"), {"s": sid})).scalar_one()
