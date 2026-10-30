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
import json
import os
import pathlib
from decimal import Decimal

from ofo_app import paper_store
from ofo_app.routes import paper as paper_routes
from sqlalchemy import event, text
from test_paper_routes import _client, _new, _seed_fixture, _setup, db  # noqa: F401 - db is the rollback fixture

D = Decimal
FIELDS = ("breakevens", "breakevens_display", "breakevens_reason", "max_profit", "max_loss", "profit_left", "loss_left",
          "max_profit_text", "max_loss_text", "profit_left_text", "loss_left_text", "extremes_reason", "greeks",
          "greeks_reason")
OTHER_EXPIRY = ("SELECT id FROM public.catalogue_contracts WHERE name = 'NIFTY' AND instrument_type = 'CE' "
                "AND expiry > DATE '2026-10-13' AND NOT retired AND NOT delisted ORDER BY expiry, strike LIMIT 1")


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


CAPTURE = pathlib.Path(__file__).resolve().parent.parent / "frontend/tests/fixtures/paper-list-r19b"


def _capture(name: str, body: dict) -> None:
    """R_19B_CAPTURE=1: write the route's real list reply for the frontend tests (they never hand-type a reply)."""
    if os.environ.get("R_19B_CAPTURE"):
        CAPTURE.mkdir(parents=True, exist_ok=True)
        (CAPTURE / f"{name}.json").write_text(json.dumps(body, indent=1, sort_keys=True) + "\n", encoding="utf-8")


async def _both(app, strategy_id: int, capture: str | None = None) -> tuple[dict, dict]:
    async with _client(app) as c:
        single = (await c.get(f"/paper/strategies/{strategy_id}")).json()
        whole = (await c.get("/paper/strategies")).json()
    if capture:
        _capture(capture, whole)
    return single, next(s for s in whole["strategies"] if s["strategy_id"] == strategy_id)


async def test_core_list_figures_equal_the_single_route_and_each_breakeven_is_a_zero_of_the_book(db):  # noqa: F811
    app, stored, *_ = await _seed_fixture(db)
    single, listed = await _both(app, stored.id, "live")
    assert {f: listed[f] for f in FIELDS} == {f: single[f] for f in FIELDS}
    assert listed["extremes_reason"] is None and listed["breakevens_reason"] is None and listed["greeks_reason"] is None
    assert len(listed["breakevens"]) == 2  # noqa: PLR2004 - a condor with one leg exited: two zeros
    for level, shown in zip(listed["breakevens"], listed["breakevens_display"], strict=True):
        assert abs(_payoff(listed, D(level))) <= D("0.01") * 65  # the level is exact to 0.01 point, x 65 units a leg
        assert shown.split(" ")[0] == f"{round(D(level)):,}", shown  # grouped whole points, the outcome summary's shape
        assert shown.endswith("%)"), shown  # GC-TPD R-34: a live book carries the move-from-spot percent
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
    other = (await db.execute(text(OTHER_EXPIRY))).scalar_one()  # a real contract of a later expiry joins the book
    await paper_store.place(db, stored.user_ref, stored.id, [_new(int(other), "BUY", 65, "50.00")])
    single, listed = await _both(app, stored.id, "multi_expiry")
    assert {f: listed[f] for f in FIELDS} == {f: single[f] for f in FIELDS}
    assert (listed["breakevens"], listed["breakevens_display"]) == (None, None)
    assert listed["breakevens_reason"] == "multi_expiry"
    assert [listed[f] for f in ("max_profit", "max_loss", "profit_left", "loss_left")] == [None] * 4
    assert listed["extremes_reason"] == "multi_expiry"


async def test_a_fully_exited_strategy_has_every_new_field_absent_with_its_reason_never_zero(db):  # noqa: F811
    app, stored, *_ = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, "SELL", 65, "100.00"),
                                                              _new(c0, "BUY", 65, "80.00", "exit")])
    _single, listed = await _both(app, stored.id, "exited")
    assert listed["state"] == "EXITED"
    for name in ("breakevens", "breakevens_display", "max_profit", "max_loss", "profit_left", "loss_left",
                 "max_profit_text", "max_loss_text", "profit_left_text", "loss_left_text", "greeks"):
        assert listed[name] is None, name
    assert (listed["extremes_reason"], listed["breakevens_reason"], listed["greeks_reason"]) == ("exited",) * 3


async def test_prices_not_live_drop_profit_left_and_greeks_with_the_paused_reason_and_show_no_stale_number(db):  # noqa: F811
    app, stored, _provider, clock, last, _fixture = await _seed_fixture(db)
    clock.now = last + datetime.timedelta(minutes=10)
    single, listed = await _both(app, stored.id, "paused")
    assert {f: listed[f] for f in FIELDS} == {f: single[f] for f in FIELDS}
    assert listed["state"] == "PAUSED"
    assert (listed["profit_left"], listed["loss_left"], listed["greeks"]) == (None, None, None)
    assert (listed["extremes_reason"], listed["greeks_reason"]) == ("prices_not_live", "prices_not_live")
    # the original range and the breakevens need no price (extremes.py: "known whether or not prices are live")
    assert listed["max_profit"] is not None and listed["breakevens"] is not None and listed["breakevens_reason"] is None
    assert not any("%" in t for t in listed["breakevens_display"])  # no percent from a spot that is not live


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


# GC-TP fix1 item 1 (ADR-211 (5)): every reason beside a dash is a pinned server template in the reply
ADR_211 = pathlib.Path(__file__).resolve().parent.parent / "spec" / "decisions" / "ADR-211.md"


def _adr_211_five() -> str:
    import re  # noqa: PLC0415

    import yaml  # noqa: PLC0415
    decision = yaml.safe_load(ADR_211.read_text(encoding="utf-8").split("---")[1])["decision"]
    found = re.search(r"\(5\) A paper card on legs with different expiries: \"(.*?)\"", decision)
    assert found
    return found.group(1)


async def test_fix1_calendar_reply_carries_the_three_reason_texts_and_breakeven_one_is_the_adr_sentence(db):  # noqa: F811
    from ofo.errors.explanations import TABLE_REASON_TEXT  # noqa: PLC0415
    from ofo_app import paper_reasons  # noqa: PLC0415
    app, stored, *_ = await _seed_fixture(db)
    other = (await db.execute(text(OTHER_EXPIRY))).scalar_one()
    await paper_store.place(db, stored.user_ref, stored.id, [_new(int(other), "BUY", 65, "50.00")])
    single, listed = await _both(app, stored.id, "fix1_multi_expiry")
    for body in (single, listed):
        for key in ("breakevens_reason_text", "extremes_reason_text", "greeks_reason_text"):
            assert key in body, key
        assert body["breakevens_reason_text"] == _adr_211_five()
        assert _adr_211_five() == "Breakeven is exact only for a single-expiry strategy"
        assert body["extremes_reason_text"] == paper_reasons.extremes_reason_text("multi_expiry")
        assert body["greeks_reason"] == "no_iv"  # the real later-expiry contract has no IV
        assert body["greeks_reason_text"] == paper_reasons.greeks_reason_text("no_iv") == TABLE_REASON_TEXT["no_iv"]
        assert "multi_expiry" not in body["breakevens_reason_text"]


async def test_fix1_exited_and_paused_replies_carry_server_texts_never_a_code(db):  # noqa: F811
    app, stored, *_ = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, "SELL", 65, "100.00"),
                                                              _new(c0, "BUY", 65, "80.00", "exit")])
    _single, listed = await _both(app, stored.id, "fix1_exited")
    for key in ("breakevens_reason_text", "extremes_reason_text", "greeks_reason_text"):
        assert listed[key] == "Exited", key


async def test_fix1_paused_reply_carries_the_paused_texts(db):  # noqa: F811
    app, stored, _provider, clock, last, _fixture = await _seed_fixture(db)
    clock.now = last + datetime.timedelta(minutes=10)
    _single, paused = await _both(app, stored.id, "fix1_paused")
    assert paused["greeks_reason_text"] == "Paper P&L paused - prices not live"
    assert paused["extremes_reason_text"].startswith("Profit left and Loss left are not worked out")
    assert paused["breakevens_reason_text"] is None


async def test_a_paused_book_carries_the_oldest_known_quote_time_in_the_list_and_the_single_route(db):  # noqa: F811
    """REQ-109 AC-5: "prices not live, as of <time>". Class: every PAUSED paper book (list, single, totals strip)."""
    app, stored, _provider, clock, last, _fixture = await _seed_fixture(db)
    clock.now = last + datetime.timedelta(minutes=10)
    single, listed = await _both(app, stored.id)
    async with _client(app) as c:
        totals = (await c.get("/paper/strategies")).json()["totals"]
    assert listed["state"] == single["state"] == "PAUSED"
    assert listed["as_of"] == single["as_of"] and listed["as_of"] is not None
    assert datetime.datetime.fromisoformat(listed["as_of"].replace("Z", "+00:00")) <= last.astimezone(datetime.UTC)
    assert totals["totals_reason"] == "prices_not_live" and totals["totals_as_of"] is not None


async def test_a_live_book_has_no_as_of(db):  # noqa: F811
    app, stored, *_ = await _seed_fixture(db)
    single, listed = await _both(app, stored.id)
    assert listed["state"] == "LIVE" and listed["as_of"] is None and single["as_of"] is None


async def test_an_exited_book_has_no_as_of(db):  # noqa: F811
    app, stored, *_ = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, "SELL", 65, "100.00"),
                                                              _new(c0, "BUY", 65, "80.00", "exit")])
    _single, listed = await _both(app, stored.id)
    assert listed["state"] == "EXITED" and listed["as_of"] is None
