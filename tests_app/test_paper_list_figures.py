"""GC-TP R-19b (Sensibull 090; ADR-207): GET /paper/strategies carries, per strategy, the SAME breakeven / Max Profit /
Max Loss / Profit left / Loss left and net Greeks that GET /paper/strategies/{id} answers (one function builds both:
ofo_app.routes.paper._summary), on the recorded replay market and real PostgreSQL, every test rolled back.

Real shapes only: every reply here is read from the route; nothing is hand-typed into a reply.
Core proof: strategy 48 of the real fixture (4 legs, one exited, so booked is not 0) - the list entry equals the
single-strategy reply field for field, and each listed breakeven makes the book's at-expiry P&L 0 by an independent
hand sum (booked + open contracts' value at expiry - their average cost) from the reply's own positions.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from ofo_app import paper_store
from ofo_app.routes import paper as paper_routes
from sqlalchemy import event, text
from test_paper_routes import _client, _new, _seed_fixture, _setup, db  # noqa: F401 - db is the rollback fixture

D = Decimal
FIELDS = ("breakevens", "breakevens_text", "breakevens_reason", "max_profit", "max_loss", "profit_left", "loss_left",
          "max_profit_text", "max_loss_text", "profit_left_text", "loss_left_text", "extremes_reason", "greeks",
          "greeks_reason")
MOVE_EXPIRY = "UPDATE public.catalogue_contracts SET expiry = DATE '2026-10-20' WHERE id = :id"


def _payoff(body: dict, level: Decimal) -> Decimal:
    """The book's at-expiry P&L at ``level`` by hand: booked + each open contract's (value - average) x net quantity."""
    total = D(body["booked"])
    for p in body["positions"]:
        if p["net_quantity"] == 0:
            continue
        k = D(p["strike"])
        value = max(level - k, D(0)) if p["instrument"] == "CE" else max(k - level, D(0))
        total += (value - D(p["average"])) * p["net_quantity"]
    return total


async def _both(app, strategy_id: int) -> tuple[dict, dict]:
    async with _client(app) as c:
        single = (await c.get(f"/paper/strategies/{strategy_id}")).json()
        listed = next(s for s in (await c.get("/paper/strategies")).json()["strategies"]
                      if s["strategy_id"] == strategy_id)
    return single, listed


async def test_core_list_figures_equal_the_single_route_and_each_breakeven_is_a_zero_of_the_book(db):  # noqa: F811
    app, stored, *_ = await _seed_fixture(db)
    single, listed = await _both(app, stored.id)
    assert {f: listed[f] for f in FIELDS} == {f: single[f] for f in FIELDS}
    assert listed["extremes_reason"] is None and listed["breakevens_reason"] is None and listed["greeks_reason"] is None
    assert len(listed["breakevens"]) == 2  # noqa: PLR2004 - a condor with one leg exited: two zeros
    for level, shown in zip(listed["breakevens"], listed["breakevens_text"], strict=True):
        assert abs(_payoff(listed, D(level))) <= D("0.01") * 65  # the level is exact to 0.01 point, x 65 units a leg
        assert shown.startswith(f"{int(D(level)):,}") or shown.split(" ")[0].replace(",", "").isdigit(), shown
    assert D(listed["max_profit"]) >= D(listed["total"]) >= D(listed["max_loss"])  # the original range holds the P&L


async def test_list_net_greeks_are_the_sum_of_the_legs_and_the_texts_are_the_servers(db):  # noqa: F811
    app, stored, *_ = await _seed_fixture(db)
    _single, listed = await _both(app, stored.id)
    greeks = listed["greeks"]
    open_ids = {p["contract_id"] for p in listed["positions"] if p["net_quantity"] != 0}
    assert {g["contract_id"] for g in greeks["legs"]} == open_ids and len(open_ids) == 3  # noqa: PLR2004
    for name in ("delta", "gamma", "theta", "vega"):
        assert abs(sum(D(g[name]) for g in greeks["legs"]) - D(greeks["net"][name])) <= D("0.0001") * 3
        assert greeks["net"][f"{name}_text"] and all(g[f"{name}_text"] for g in greeks["legs"])
    sign = {p["contract_id"]: (1 if p["net_quantity"] > 0 else -1) for p in listed["positions"]}
    for g in greeks["legs"]:  # a long option has delta of its own sign; a CE is above 0 long, a PE below 0 long
        kind = next(p["instrument"] for p in listed["positions"] if p["contract_id"] == g["contract_id"])
        assert (D(g["delta"]) > 0) == ((kind == "CE") == (sign[g["contract_id"]] > 0)), g
        assert D(g["gamma"]) * sign[g["contract_id"]] >= 0


async def test_multi_expiry_has_no_breakevens_and_no_range_with_the_reason_and_invents_nothing(db):  # noqa: F811
    app, stored, *_ = await _seed_fixture(db)
    await db.execute(text(MOVE_EXPIRY), {"id": stored.saved.contract_ids[0]})
    single, listed = await _both(app, stored.id)
    assert {f: listed[f] for f in FIELDS} == {f: single[f] for f in FIELDS}
    assert (listed["breakevens"], listed["breakevens_text"], listed["breakevens_reason"]) == (None, None, "multi_expiry")
    assert [listed[f] for f in ("max_profit", "max_loss", "profit_left", "loss_left")] == [None] * 4
    assert listed["extremes_reason"] == "multi_expiry"


async def test_a_fully_exited_strategy_has_every_new_field_absent_with_its_reason_never_zero(db):  # noqa: F811
    app, stored, *_ = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, "SELL", 65, "100.00"),
                                                              _new(c0, "BUY", 65, "80.00", "exit")])
    _single, listed = await _both(app, stored.id)
    assert listed["state"] == "EXITED"
    for name in ("breakevens", "breakevens_text", "max_profit", "max_loss", "profit_left", "loss_left",
                 "max_profit_text", "max_loss_text", "profit_left_text", "loss_left_text", "greeks"):
        assert listed[name] is None, name
    assert (listed["extremes_reason"], listed["breakevens_reason"], listed["greeks_reason"]) == ("exited",) * 3


async def test_prices_not_live_drop_profit_left_and_greeks_with_the_paused_reason_and_show_no_stale_number(db):  # noqa: F811
    app, stored, _provider, clock, last, _fixture = await _seed_fixture(db)
    clock.now = last + datetime.timedelta(minutes=10)
    single, listed = await _both(app, stored.id)
    assert {f: listed[f] for f in FIELDS} == {f: single[f] for f in FIELDS}
    assert listed["state"] == "PAUSED"
    assert (listed["profit_left"], listed["loss_left"], listed["greeks"]) == (None, None, None)
    assert (listed["extremes_reason"], listed["greeks_reason"]) == ("prices_not_live", "prices_not_live")
    # the original range and the breakevens need no price (extremes.py: "known whether or not prices are live")
    assert listed["max_profit"] is not None and listed["breakevens"] is not None and listed["breakevens_reason"] is None


async def test_a_contract_that_is_not_live_gives_greeks_the_contract_reason(db):  # noqa: F811
    app, stored, *_ = await _seed_fixture(db)
    await db.execute(text("UPDATE public.catalogue_contracts SET retired = TRUE, currently_listed = FALSE "
                          "WHERE id = :id"), {"id": stored.saved.contract_ids[0]})
    _single, listed = await _both(app, stored.id)
    assert (listed["greeks"], listed["greeks_reason"]) == (None, "contract_retired")


async def test_not_connected_gives_the_same_absent_reason_not_a_number(db):  # noqa: F811
    from ofo_app.routes.outcome import get_market_context  # noqa: PLC0415

    app, stored, *_ = await _seed_fixture(db)
    app.dependency_overrides[get_market_context] = lambda: None
    _single, listed = await _both(app, stored.id)
    assert (listed["state"], listed["greeks"], listed["greeks_reason"]) == ("NOT_CONNECTED", None, "prices_not_live")
    assert (listed["profit_left"], listed["extremes_reason"]) == (None, "prices_not_live")


async def test_the_database_and_feed_calls_of_the_list_do_not_grow_with_the_number_of_strategies(db, monkeypatch):  # noqa: F811
    from ofo_app import strategy_store as store  # noqa: PLC0415
    from test_strategy_store import _ids, _saved_in  # noqa: PLC0415

    app, stored, *_ = await _seed_fixture(db)
    statements: list[str] = []
    reads: list[str] = []
    real_read = paper_routes.read_snapshot

    def counted_read(*args, **kwargs):
        reads.append(args[1])
        return real_read(*args, **kwargs)

    monkeypatch.setattr(paper_routes, "read_snapshot", counted_read)
    event.listen(db.sync_connection, "before_cursor_execute",
                 lambda _c, _cur, statement, *_a: statements.append(statement))

    async def list_cost() -> tuple[int, int, int]:
        statements.clear()
        reads.clear()
        async with _client(app) as c:
            body = (await c.get("/paper/strategies")).json()
        return len(statements), len(reads), len(body["strategies"])

    one = await list_cost()
    ids = await _ids(db)
    for _ in range(20):
        extra = await store.save_draft(db, stored.user_ref, await _saved_in(db, stored.user_ref, ids))
        await paper_store.place(db, stored.user_ref, extra.id, [_new(extra.saved.contract_ids[0], "BUY", 65, "10.00")])
    many = await list_cost()
    assert (one[2], many[2]) == (1, 21)
    assert many[0] == one[0] and many[1] == one[1], (one, many)  # statements and snapshot reads: same for 21 as for 1
