"""GC-BP steps 4 + 5 over HTTP on the recorded replay: GET /tracking (every tracked strategy of the signed-in user,
booked / unbooked / total) and POST /strategies/{id}/tracking/exit (REQ-109 AC-4, AC-5; ADR-201 (2)).

The saved strategy is test_strategy_store's iron condor (65 units a leg): SELL 22800 CE, BUY 23000 CE, SELL 22400 PE,
BUY 22200 PE, entered at the recorded LTPs 39.15 / 12.95 / 82.75 / 35.80 (2026-10-08 09:20:09 IST). The feed then moves
to 45.15 / 14.95 / 70.75 / 30.80. By hand: (39.15 - 45.15) x 65 = -390.00; (14.95 - 12.95) x 65 = +130.00;
(82.75 - 70.75) x 65 = +780.00; (30.80 - 35.80) x 65 = -325.00 -> total +195.00.
"""
from __future__ import annotations

import asyncio
import datetime
from decimal import Decimal
from http import HTTPStatus

import pytest
from ofo_app import paper_store, tracked_contracts
from ofo_app import strategy_store as store
from ofo_app.routes import tracking as tracking_routes
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from test_execution_plan_store import _remove_own_rows
from test_strategy_store import WING, _client, _saved_in, _user, _with_draft
from test_strategy_tracking import (
    _DELIST,
    _RETIRE,
    _REUSE,
    IDS,
    _frame,
    _paper_body,
    _setup,
)

D = Decimal


@pytest.fixture
async def db(app_engine):
    """The rolled-back connection (as test_strategy_tracking): no test leaves a row in the insert-only tables."""
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()
MOVED = ["45.15", "14.95", "70.75", "30.80"]


def _move(provider, last, prices=MOVED):
    for iid, rupees in zip(IDS, prices, strict=True):
        provider.on_frame(_frame(provider, iid, rupees), last)


async def _tracked(db, count: int = 1):
    """``count`` tracked strategies of one user (all on the same condor), then the feed moved to MOVED."""
    app, stored, provider, clock, last = await _setup(db)
    ids = [stored.id]
    for _ in range(count - 1):
        ids.append(  # noqa: PERF401 - awaited one at a time
            (await store.save_draft(db, stored.user_ref, await _saved_in(db, stored.user_ref,
                                                                               await _contract_ids(db)))).id)
    async with _client(app) as c:
        for sid in ids:
            placed = await c.post(f"/paper/strategies/{sid}/orders", json=_paper_body(await store.load(
                db, stored.user_ref, sid)))
            assert placed.status_code == HTTPStatus.CREATED, placed.text
    _move(provider, last)
    return app, ids, provider, clock, last


async def _contract_ids(db):
    from test_strategy_store import _ids  # noqa: PLC0415

    return await _ids(db)


async def _exits(db, strategy_id: int) -> list[tuple[int, Decimal]]:
    """(leg index, exit price) of every exit order (GC-TP 1a part 4: the paper book is public.paper_orders; a leg's
    index is its contract's place among the open orders)."""
    legs = await _leg_contracts(db, strategy_id)
    rows = await db.execute(text("SELECT contract_id, price FROM public.paper_orders WHERE kind = 'exit' "
                                 "AND strategy_id = :i ORDER BY id"), {"i": strategy_id})
    return sorted((legs.index(int(r[0])), r[1]) for r in rows)


# --- step 4: GET /tracking -------------------------------------------------------------------------------------------

async def test_list_none_tracked_is_an_empty_list(db):
    app, *_ = await _setup(db)
    async with _client(app) as c:
        listed = await c.get("/tracking")
    assert listed.status_code == HTTPStatus.OK and listed.json()["strategies"] == []


async def test_list_all_live_gives_total_booked_unbooked_and_leg_fields(db):
    app, ids, *_ = await _tracked(db, 2)
    async with _client(app) as c:
        body = (await c.get("/tracking")).json()
    assert [s["strategy_id"] for s in body["strategies"]] == ids
    first = body["strategies"][0]
    assert (first["state"], first["total"], first["booked"], first["unbooked"], first["underlying"]) == (
        "LIVE", "195.00", "0.00", "195.00", "NIFTY")
    assert "detections" not in first and body["answered_at"]
    leg = first["legs"][0]
    assert {k: leg[k] for k in ("leg_index", "action", "instrument", "strike", "quantity", "entry_price",
                                "current_price", "price_state", "exit_price", "exited_at")} == {
        "leg_index": 0, "action": "SELL", "instrument": "CE", "strike": "22800.00", "quantity": 65,
        "entry_price": "39.15", "current_price": "45.15", "price_state": "live", "exit_price": None, "exited_at": None}


async def test_list_sends_each_figure_as_server_text_and_a_true_zero_has_no_sign(db):
    """Review fix 4 (REQ-109 AC-2, REQ-152 AC-4): the money text comes from the server; booked 0.00 is "0.00", never "+0.00"."""  # noqa: E501 - long line kept whole
    app, *_ = await _tracked(db)
    async with _client(app) as c:
        first = (await c.get("/tracking")).json()["strategies"][0]
    assert (first["total_text"], first["booked_text"], first["unbooked_text"]) == ("+195.00", "0.00", "+195.00")


def test_signed_paisa_text_of_zero_and_negative_zero_is_unsigned():
    from ofo.errors.explanations import render_explanation  # noqa: PLC0415 - late import as its neighbours
    for zero in (Decimal("0.00"), Decimal("-0.00"), Decimal("0.004"), Decimal("-0.004")):
        assert render_explanation("summary_paisa_signed", amount=zero) == "0.00"
    assert render_explanation("summary_paisa_signed", amount=Decimal("195")) == "+195.00"


async def test_list_never_shows_another_users_tracking(db):
    _app, ids, *_ = await _tracked(db)
    other, *_ = await _setup(db)
    async with _client(other) as c:
        body = (await c.get("/tracking")).json()
    assert ids[0] not in [s["strategy_id"] for s in body["strategies"]]


async def test_list_paused_strategy_keeps_booked_and_drops_unbooked_and_total(db):
    app, ids, _provider, clock, last = await _tracked(db)
    async with _client(app) as c:
        exited = await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0]})
        assert exited.status_code == HTTPStatus.OK, exited.text
        clock.now = last + datetime.timedelta(minutes=10)
        row = (await c.get("/tracking")).json()["strategies"][0]
    assert (row["state"], row["pause_reason"], row["booked"], row["unbooked"], row["total"]) == (
        "PAUSED", "prices_not_live", "-390.00", None, None)
    assert row["as_of"] is not None


async def test_list_not_connected_keeps_booked(db):
    app, ids, *_ = await _tracked(db)
    async with _client(app) as c:
        assert (await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0]})).status_code == HTTPStatus.OK
        app.dependency_overrides[tracking_routes.get_market_context] = lambda: None
        row = (await c.get("/tracking")).json()["strategies"][0]
    assert (row["state"], row["booked"], row["unbooked"], row["total"]) == ("NOT_CONNECTED", "-390.00", None, None)


async def test_list_expired_contract_pauses_with_its_reason_never_crashes(db):
    app, ids, *_ = await _tracked(db)
    await db.execute(text(_RETIRE), {"id": (await _leg_contracts(db, ids[0]))[0]})
    async with _client(app) as c:
        listed = await c.get("/tracking")
    assert listed.status_code == HTTPStatus.OK
    row = listed.json()["strategies"][0]
    assert (row["state"], row["pause_reason"], row["total"], row["legs"][0]["price_state"]) == (
        "PAUSED", "contract_retired", None, "contract_retired")


async def _leg_contracts(db, sid):
    return [int(r[0]) for r in await db.execute(text(
        "SELECT contract_id FROM public.paper_orders WHERE strategy_id = :i AND kind = 'open' ORDER BY id"),
        {"i": sid})]


async def test_list_fully_exited_strategy_is_exited_with_total_equal_booked_and_no_market_read(db, monkeypatch):
    app, ids, *_ = await _tracked(db)
    async with _client(app) as c:
        assert (await c.post(f"/strategies/{ids[0]}/tracking/exit",
                             json={"legs": [0, 1, 2, 3]})).status_code == HTTPStatus.OK
        reads = []
        real = tracking_routes.read_snapshot
        monkeypatch.setattr(tracking_routes, "read_snapshot", lambda *a, **k: reads.append(a) or real(*a, **k))
        row = (await c.get("/tracking")).json()["strategies"][0]
    assert (row["state"], row["total"], row["booked"], row["unbooked"]) == ("EXITED", "195.00", "195.00", "0.00")
    assert reads == []


async def test_list_read_failure_is_refused_never_a_partial_list(db, monkeypatch):
    app, *_ = await _tracked(db)

    async def broken(*_a, **_k):
        raise RuntimeError("read failed")

    monkeypatch.setattr(paper_store, "load_all", broken)
    async with _client(app) as c:
        listed = await c.get("/tracking")
    assert listed.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR and "strategies" not in listed.text


async def _list_cost(db, count: int, monkeypatch) -> tuple[int, int]:
    app, *_ = await _tracked(db, count)
    statements = []
    reads = []
    real = tracking_routes.read_snapshot
    monkeypatch.setattr(tracking_routes, "read_snapshot", lambda *a, **k: reads.append(a) or real(*a, **k))

    def counted(_conn, _cursor, statement, *_rest):
        statements.append(statement)

    event.listen(db.sync_engine, "before_cursor_execute", counted)
    try:
        async with _client(app) as c:
            body = (await c.get("/tracking")).json()
    finally:
        event.remove(db.sync_engine, "before_cursor_execute", counted)
    assert len(body["strategies"]) == count
    return len(statements), len(reads)


async def test_list_cost_does_not_grow_from_2_to_6_tracked_strategies(db, monkeypatch):
    """Finding F-3: a fixed number of queries and ONE market read per underlying, whatever the count."""
    two = await _list_cost(db, 2, monkeypatch)
    six = await _list_cost(db, 6, monkeypatch)
    assert two == six and two[1] == 1, (two, six)


# --- step 5: POST /strategies/{id}/tracking/exit ---------------------------------------------------------------------

async def test_exit_books_the_leg_at_its_live_price_and_freezes_it(db):
    app, ids, provider, _clock, last = await _tracked(db)
    async with _client(app) as c:
        exited = await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0]})
        assert exited.status_code == HTTPStatus.OK, exited.text
        body = exited.json()
        assert (body["state"], body["booked"], body["unbooked"], body["paper_pnl"]) == (
            "LIVE", "-390.00", "585.00", "195.00")
        assert (body["legs"][0]["price_state"], body["legs"][0]["exit_price"]) == ("exited", "45.15")
        assert body["legs"][0]["exited_at"] is not None
        _move(provider, last, ["50.00", *MOVED[1:]])  # the exited leg moves: booked must not
        view = (await c.get(f"/strategies/{ids[0]}/tracking")).json()
    assert (view["booked"], view["unbooked"], view["paper_pnl"]) == ("-390.00", "585.00", "195.00")
    assert await _exits(db, ids[0]) == [(0, D("45.15"))]


async def test_exit_refused_when_a_named_leg_is_not_live_and_nothing_is_stored(db):
    app, ids, _provider, clock, last = await _tracked(db)
    clock.now = last + datetime.timedelta(minutes=10)
    async with _client(app) as c:
        refused = await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0, 1]})
    assert refused.status_code == HTTPStatus.CONFLICT
    assert "Prices are not live; try again when they update" in refused.text
    assert await _exits(db, ids[0]) == []


@pytest.mark.parametrize(("sqls", "state"), [((_DELIST, _REUSE), "token_reassigned"), ((_RETIRE,), "contract_retired"),
                                             ((_DELIST,), "contract_delisted")])
async def test_exit_of_a_leg_whose_contract_is_not_live_is_refused_contract_not_live_never_try_again(db, sqls, state):
    """Review M2: a retired / delisted / token-reassigned contract never comes back, so "try again when prices update"
    would be a lie. The exit answers tracking_exit_contract_not_live (409, STRATEGY_VALIDATION_436) - never Start
    tracking's words "Tracking did not start" - and stores nothing; the feed still quotes the old token at 45.15, which
    is never used."""
    app, ids, *_ = await _tracked(db)
    leg0 = (await _leg_contracts(db, ids[0]))[0]
    for sql in sqls:
        await db.execute(text(sql), {"id": leg0})
    assert (await tracked_contracts.resolve_one(db, leg0)).state == state
    async with _client(app) as c:
        refused = await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0, 1]})
    assert refused.status_code == HTTPStatus.CONFLICT
    body = refused.json()
    assert body["code"] == "STRATEGY_VALIDATION_436" and "no longer a live contract" in body["what_happened"]
    assert "try again" not in refused.text.lower()
    assert "tracking did not start" not in refused.text.lower()
    assert await _exits(db, ids[0]) == []


async def test_exit_of_a_live_contract_whose_price_is_stale_keeps_the_ac5_try_again_answer(db):
    """AC-5's words stay for a LIVE contract whose price is stale (it can update): 433, nothing stored."""
    app, ids, _provider, clock, last = await _tracked(db)
    clock.now = last + datetime.timedelta(minutes=10)
    async with _client(app) as c:
        refused = await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0]})
    assert refused.status_code == HTTPStatus.CONFLICT
    assert refused.json()["code"] == "STRATEGY_VALIDATION_433"
    assert "Prices are not live; try again when they update" in refused.text
    assert await _exits(db, ids[0]) == []


async def test_a_leg_exits_once(db):
    app, ids, *_ = await _tracked(db)
    async with _client(app) as c:
        assert (await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [2]})).status_code == HTTPStatus.OK
        again = await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [2, 3]})
    assert again.status_code == HTTPStatus.CONFLICT and "already been exited" in again.text
    assert await _exits(db, ids[0]) == [(2, D("70.75"))]


@pytest.mark.parametrize("body", [{"legs": [4]}, {"legs": []}, {"legs": [0, 0]}, {"legs": [0], "price": "1.00"},
                                  {"legs": [-1]}], ids=["unknown", "empty", "twice", "extra_key", "negative"])
async def test_exit_body_refused_422(db, body):
    app, ids, *_ = await _tracked(db)
    async with _client(app) as c:
        refused = await c.post(f"/strategies/{ids[0]}/tracking/exit", json=body)
    assert refused.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert await _exits(db, ids[0]) == []


async def test_exit_of_an_untracked_or_another_users_strategy_is_404_and_not_connected_409(db):
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        assert (await c.post(f"/strategies/{stored.id}/tracking/exit",
                             json={"legs": [0]})).status_code == HTTPStatus.NOT_FOUND
    app, ids, *_ = await _tracked(db)
    other, *_ = await _setup(db)
    async with _client(other) as c:
        assert (await c.post(f"/strategies/{ids[0]}/tracking/exit",
                             json={"legs": [0]})).status_code == HTTPStatus.NOT_FOUND
    app.dependency_overrides[tracking_routes.get_market_context] = lambda: None
    async with _client(app) as c:
        refused = await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0]})
    assert refused.status_code == HTTPStatus.CONFLICT and "not connected" in refused.text
    assert await _exits(db, ids[0]) == []


@pytest.mark.parametrize("sql", ["UPDATE public.paper_orders SET price = 1 WHERE strategy_id = :i AND kind = 'exit'",
                                 "DELETE FROM public.paper_orders WHERE strategy_id = :i AND kind = 'exit'"],
                         ids=["update", "delete"])
async def test_paper_exit_rows_are_append_only(db, sql):
    app, ids, *_ = await _tracked(db)
    async with _client(app) as c:
        assert (await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0]})).status_code == HTTPStatus.OK
    nested = await db.begin_nested()
    with pytest.raises(DBAPIError):
        await db.execute(text(sql), {"i": ids[0]})
    await nested.rollback()
    assert await _exits(db, ids[0]) == [(0, D("45.15"))]


# --- review M4: the batch catalogue answer and the exit race, kept in the suite ---------------------------------------

_REUSE_OF = ("INSERT INTO public.catalogue_contracts (exchange_segment, exchange_token, name, expiry, strike, "
             "instrument_type) SELECT exchange_segment, exchange_token, name, DATE '2026-11-24', :strike, "
             "instrument_type FROM public.catalogue_contracts WHERE id = :id")


async def test_batched_resolve_gives_exactly_resolve_ones_answers_for_every_catalogue_state(db):
    """F-3's batched tracked_contracts.resolve (two queries) must answer as resolve_one (one contract at a time) for
    every state: live, retired, delisted, token reassigned, retired-then-reused (retired wins), a duplicate id and an
    id no contract has."""
    _app, stored, *_ = await _setup(db)
    c0, c1, c2, c3 = stored.saved.contract_ids
    live = (await _contract_ids(db))[WING]
    await db.execute(text(_RETIRE), {"id": c0})
    await db.execute(text(_DELIST), {"id": c1})
    await db.execute(text(_DELIST), {"id": c2})
    await db.execute(text(_REUSE_OF), {"id": c2, "strike": 26000})
    await db.execute(text(_RETIRE), {"id": c3})
    await db.execute(text(_REUSE_OF), {"id": c3, "strike": 26100})
    ids = [live, c0, c1, c2, c3, c0, 2**62]
    batched = await tracked_contracts.resolve(db, ids)
    one_by_one = [await tracked_contracts.resolve_one(db, i) for i in ids]

    def shape(c):
        return (c.contract_id, c.state, c.feed_key, c.identity, c.stored is None)

    assert [c.state for c in batched] == ["live", "contract_retired", "contract_delisted", "token_reassigned",
                                          "contract_retired", "contract_retired", "contract_missing"]
    assert [shape(c) for c in batched] == [shape(c) for c in one_by_one]
    assert batched[0].feed_key is not None and all(c.feed_key is None for c in batched[1:])


async def _remove_tracked_rows(admin_engine, user_ref: str, contract_ids: list[int]) -> None:
    """This test's committed tracking rows, removed as the owner with the insert-only guards off inside one
    transaction (the house pattern, test_execution_plan_store._remove_own_rows), children first; then that helper
    removes the strategy, its history and the catalogue rows."""
    async with admin_engine.connect() as conn:  # noqa: SIM117
        async with conn.begin():
            mine = "(SELECT id FROM public.strategies WHERE user_ref = :u)"
            for table in ("paper_orders",):
                await conn.execute(text(f'ALTER TABLE public."{table}" DISABLE TRIGGER USER'))
                await conn.execute(text(f"DELETE FROM public.{table} WHERE strategy_id IN {mine}"),  # noqa: S608
                                   {"u": user_ref})
                await conn.execute(text(f'ALTER TABLE public."{table}" ENABLE TRIGGER USER'))
    await _remove_own_rows(admin_engine, contract_ids, user_ref)


async def test_two_concurrent_exits_of_one_leg_one_stored_the_other_refused_already_exited(app_engine, admin_engine):
    """Two connections exit leg 0 at once: the strategy's row lock makes the second wait for the first; once the first
    commits, the second's exit exceeds the open quantity (EXIT_EXCEEDS_OPEN, which the route answers as
    tracking_leg_already_exited) and exactly one exit order (the first's price, 11.00) is stored."""
    user = _user()
    at = datetime.datetime(2026, 10, 8, 3, 50, tzinfo=datetime.UTC)
    contract_ids: list[int] = []
    try:
        async with app_engine.connect() as setup:
            before = {r[0] for r in await setup.execute(text("SELECT id FROM public.catalogue_contracts"))}
            await setup.rollback()  # end the read's autobegun transaction; the seed commits in its own
            async with setup.begin():
                _, stored = await _with_draft(setup, user)
                # every catalogue row this test committed (the whole recorded list, not only the legs' contracts):
                # a row left behind makes a later test's small catalogue trip the ADR-058 10% guard
                after = {r[0] for r in await setup.execute(text("SELECT id FROM public.catalogue_contracts"))}
                contract_ids = sorted(after - before)
                entry = [paper_store.NewOrder(cid, leg.action.value, leg.quantity, D("10.00"), "open", at)
                         for cid, leg in zip(stored.saved.contract_ids, stored.saved.definition.legs, strict=True)]
                await paper_store.place(setup, user, stored.id, entry)
        leg0 = stored.saved.definition.legs[0]
        close = "BUY" if leg0.action.value == "SELL" else "SELL"

        def _exit(price: str) -> list[paper_store.NewOrder]:
            return [paper_store.NewOrder(stored.saved.contract_ids[0], close, leg0.quantity, D(price), "exit", at)]

        async with app_engine.connect() as first, app_engine.connect() as second:
            t1, t2 = await first.begin(), await second.begin()
            await paper_store.place(first, user, stored.id, _exit("11.00"))
            waiter = asyncio.create_task(paper_store.place(second, user, stored.id, _exit("12.00")))
            await asyncio.sleep(1.0)
            assert not waiter.done(), "the second exit must wait for the first transaction's row lock"
            await t1.commit()
            with pytest.raises(store.StrategyStoreError) as refused:
                await asyncio.wait_for(waiter, 10)
            assert refused.value.code == paper_store.EXIT_EXCEEDS_OPEN
            await t2.rollback()
            assert await _exits(first, stored.id) == [(0, D("11.00"))]
    finally:
        await _remove_tracked_rows(admin_engine, user, contract_ids)


# --- GC-UI D-B48: each leg's own paper P&L, from the one engine ------------------------------------------------------
# The replay condor moved to 45.15 / 14.95 / 70.75 / 30.80 from entries 39.15 / 12.95 / 82.75 / 35.80, 65 a leg:
# SELL 22800 CE (39.15 - 45.15) x 65 = -390.00; BUY 23000 CE (14.95 - 12.95) x 65 = +130.00;
# SELL 22400 PE (82.75 - 70.75) x 65 = +780.00; BUY 22200 PE (30.80 - 35.80) x 65 = -325.00; total +195.00.
HAND = ["-390.00", "130.00", "780.00", "-325.00"]


def _pnl_fields(row):
    return [(leg["pnl"], leg["pnl_kind"], leg["pnl_text"]) for leg in row["legs"]]


def _sum(row):
    return sum(Decimal(leg["pnl"]) for leg in row["legs"])


async def test_leg_pnl_all_live_each_leg_has_its_figure_and_they_add_to_the_total(db):
    app, ids, *_ = await _tracked(db)
    async with _client(app) as c:
        row = (await c.get("/tracking")).json()["strategies"][0]
        one = (await c.get(f"/strategies/{ids[0]}/tracking")).json()
    assert [f[0] for f in _pnl_fields(row)] == HAND and {f[1] for f in _pnl_fields(row)} == {"unbooked"}
    assert [f[2] for f in _pnl_fields(row)] == ["\u2212390.00", "+130.00", "+780.00", "\u2212325.00"]
    assert _sum(row) == Decimal(row["total"]) == Decimal("195.00")
    assert _pnl_fields(one) == _pnl_fields(row) and _sum(one) == Decimal(one["paper_pnl"])


async def test_leg_pnl_one_exited_one_open_still_sum_to_the_total_and_the_exited_leg_is_frozen(db):
    app, ids, provider, _clock, last = await _tracked(db)
    async with _client(app) as c:
        assert (await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0]})).status_code == HTTPStatus.OK
        _move(provider, last, ["50.00", *MOVED[1:]])  # the exited SELL leg moves: its booked figure must not
        row = (await c.get("/tracking")).json()["strategies"][0]
    assert [f[1] for f in _pnl_fields(row)] == ["booked", "unbooked", "unbooked", "unbooked"]
    assert [f[0] for f in _pnl_fields(row)] == HAND
    assert _sum(row) == Decimal(row["total"]) == Decimal(row["booked"]) + Decimal(row["unbooked"])


async def test_leg_pnl_fully_exited_is_all_booked_and_adds_to_the_total(db):
    app, ids, *_ = await _tracked(db)
    async with _client(app) as c:
        assert (await c.post(f"/strategies/{ids[0]}/tracking/exit",
                             json={"legs": [0, 1, 2, 3]})).status_code == HTTPStatus.OK
        row = (await c.get("/tracking")).json()["strategies"][0]
    assert {f[1] for f in _pnl_fields(row)} == {"booked"} and _sum(row) == Decimal(row["total"]) == Decimal("195.00")


async def test_leg_pnl_paused_has_no_open_figure_never_zero_and_the_exited_leg_keeps_its_booked_figure(db):
    app, ids, _provider, clock, last = await _tracked(db)
    async with _client(app) as c:
        assert (await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0]})).status_code == HTTPStatus.OK
        clock.now = last + datetime.timedelta(minutes=10)
        row = (await c.get("/tracking")).json()["strategies"][0]
    assert _pnl_fields(row) == [("-390.00", "booked", "\u2212390.00"), (None, None, None), (None, None, None),
                                (None, None, None)]


async def test_leg_pnl_not_connected_keeps_only_the_exited_leg(db):
    app, ids, *_ = await _tracked(db)
    async with _client(app) as c:
        assert (await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0]})).status_code == HTTPStatus.OK
        app.dependency_overrides[tracking_routes.get_market_context] = lambda: None
        row = (await c.get("/tracking")).json()["strategies"][0]
    assert [f[0] for f in _pnl_fields(row)] == ["-390.00", None, None, None]
