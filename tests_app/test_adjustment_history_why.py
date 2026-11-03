"""REQ-163 AC-1 (GC-IC1 step 10 FAIL, evidence/W-210/AC-1.md): an adjustment made from a suggestion says WHY.

The path the screen takes, through the real routes on a fresh migrated database: the worker opens a record for each flag
of a real check (ADJ-02: T-01, T-03, T-09), Compare marks one acted on (POST .../acted-on), the builder's basket is
placed as paper orders naming it (POST /paper/strategies/{id}/orders with ``suggestion_ids``), and the history row of
that batch names the record's condition (the inbox's own catalogue line), while a batch with no link stays
"Your own change". Fail closed: a record of another strategy or user, a missing one, one not acted on, or one already
linked refuses the whole placement and stores nothing.

One test, in phases: the worker's alert gate (ADR-237) opens a rule's record once per strategy, so the three records of
one real check are all the records this strategy gets; the foreign strategy (ADJ-13) is seeded last because seeding
switches the scenario market.
"""
from __future__ import annotations

import datetime
import itertools
from decimal import Decimal
from typing import Any

import test_adjustment_check as check_test
from ofo_app import paper_book, playbook_store
from ofo_app.routes.outcome import get_answer_clock
from ofo_app.scenario_mode import refuse_orders
from test_adjustment_check import _seeded
from test_adjustment_opportunities import _call, _clean, _opened, _records

app_db_url = check_test.app_db_url

OK, CREATED, NOT_FOUND, CONFLICT = 200, 201, 404, 409
OWN = "Your own change"
NOT_FOUND_TEXT = "This adjustment opportunity was not found."
#: ADJ-02 T-03's condition line, exactly as the catalogue words it (measured on a fresh DB 2026-11-03; the test also
#: reads it back from the inbox, so the two readers must agree)
EXPECTED_T03 = "Tested short's delta reaches: 0.4103 delta (rule 0.3500 delta)"
_TICKS = itertools.count(1)
_BASE = datetime.datetime(2026, 11, 3, 10, 0, tzinfo=datetime.UTC)  # after every scenario's entry clock


def _stepping_clock() -> Any:
    """Each placement its own minute: a basket is the orders of one placed_at (the engine's batch rule), and two
    requests must never share one, as they never do on a real clock."""
    at = _BASE + datetime.timedelta(minutes=next(_TICKS))
    return lambda: at


#: the scenario's market, with the paper order path open (not Kite) and a clock that moves per request
ORDERS_ON = {refuse_orders: lambda: None, get_answer_clock: _stepping_clock}


async def _book(engine, sid: int) -> list:
    async with engine.connect() as conn:
        return list(await paper_book.load_owned(conn, "owner", sid))


async def _add_one(engine, sid: int) -> dict:
    """One 'add' order on the first open contract: same side, one lot, its own entry price (always a valid tick)."""
    first = (await _book(engine, sid))[0].order
    return {"contract_id": first.contract_id, "side": first.side, "quantity": first.quantity,
            "price": str(first.price), "kind": "add"}


async def _place(engine, sid: int, suggestion_ids: list | None, user: str | None = None) -> tuple[int, dict]:
    body: dict = {"orders": [await _add_one(engine, sid)]}
    if suggestion_ids is not None:
        body["suggestion_ids"] = suggestion_ids
    return await _call("POST", f"/paper/strategies/{sid}/orders", body, user=user, overrides=ORDERS_ON)


async def _history(sid: int) -> dict:
    status, body = await _call("GET", f"/api/strategies/{sid}/adjustment-history")
    assert status == OK, body
    return body


async def _record(engine, sid: int, rule: str) -> playbook_store.Suggestion:
    return next(r for r in await _records(engine, sid) if r.rule_id == rule)


async def _acted(engine, sid: int, rule: str) -> playbook_store.Suggestion:
    rec = await _record(engine, sid, rule)
    status, out = await _call("POST", f"/api/adjustment-opportunities/{rec.id}/acted-on")
    assert (status, out["outcome"]) == (OK, "acted_on"), out
    return rec


async def _inbox_condition(sid: int, rec_id: int) -> str:
    status, inbox = await _call("GET", "/api/adjustment-opportunities")
    assert status == OK
    return next(r["condition"] for g in inbox["groups"] if g["strategy_id"] == sid
                for r in g["records"] if r["id"] == rec_id)


async def _refused(engine, sid: int, ids: list[int], expected: int, user: str | None = None) -> dict:
    before = len(await _book(engine, sid))
    status, out = await _place(engine, sid, ids, user=user)
    assert status == expected, out
    assert len(await _book(engine, sid)) == before  # nothing stored
    return out


async def test_an_adjustment_from_a_suggestion_names_its_rule_and_every_bad_link_is_refused(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    await _opened(app_db_url, sid)
    # refused before any link: a record still open (not acted on), another user's placement, a missing record
    t01 = await _record(app_db_url, sid, "T-01")
    await _refused(app_db_url, sid, [t01.id], CONFLICT)
    t03 = await _acted(app_db_url, sid, "T-03")
    assert (await _refused(app_db_url, sid, [987654321], NOT_FOUND))["what_happened"] == NOT_FOUND_TEXT
    await _refused(app_db_url, sid, [t03.id], NOT_FOUND, user="someone-else")
    assert (await _record(app_db_url, sid, "T-03")).placed_order_ids is None  # no refusal linked anything

    # the link: the batch's history row names T-03's condition, as the inbox words it
    status, out = await _place(app_db_url, sid, [str(t03.id)])  # as the browser sends it (a query-string id)
    assert status == CREATED, out
    new_id = (await _book(app_db_url, sid))[-1].id
    assert (await _record(app_db_url, sid, "T-03")).placed_order_ids == (new_id,)
    rows = (await _history(sid))["rows"]
    last = rows[-1]
    assert last["step"] == "adjustment" and last["rule_id"] == "T-03" and last["rule_ids"] == ["T-03"]
    assert last["why_text"] == EXPECTED_T03 == await _inbox_condition(sid, t03.id) and last["why_lines"] == []
    assert (rows[0]["step"], rows[0]["why_text"], rows[0]["rule_id"], rows[0]["rule_ids"]) == ("entry", OWN, None, [])

    # one basket answers a record once: linking it again is refused
    await _refused(app_db_url, sid, [t03.id], CONFLICT)
    # a basket with no link: "Your own change"; the linked row keeps its rule
    status, out = await _place(app_db_url, sid, None)
    assert status == CREATED, out
    rows = (await _history(sid))["rows"]
    assert (rows[-1]["why_text"], rows[-1]["rule_id"], rows[-1]["rule_ids"]) == (OWN, None, [])
    assert rows[-2]["rule_id"] == "T-03" and rows[-2]["why_text"] == EXPECTED_T03

    # a record of ANOTHER strategy (same user) is not found for this one, and stays unlinked
    t09 = await _acted(app_db_url, sid, "T-09")
    other = await _seeded(app_db_url, monkeypatch, "ADJ-13")
    assert other != sid
    assert (await _refused(app_db_url, other, [t09.id], NOT_FOUND))["what_happened"] == NOT_FOUND_TEXT
    assert (await _record(app_db_url, sid, "T-09")).placed_order_ids is None


def _rec(rid: int, rule: str, *, readable: bool = True) -> playbook_store.Suggestion:
    head = {"group": "g1", "source": "system", "label": "Tested short's delta reaches", "unit": "delta"}
    if readable:
        head["cmp"] = "ge"
    return playbook_store.Suggestion(rid, 1, rule, "T-03", None, Decimal("0.4103"), Decimal("0.3500"),
                                     datetime.datetime(2026, 11, 3, 10, 0, tzinfo=datetime.UTC), "acted_on", None,
                                     [head, {"event": "orders_placed", "order_ids": [7]}])


def test_the_why_answer_states():
    """Own change / one record (its line) / several records (count + each line) / unreadable (named, never a guess)."""
    from ofo_app.routes.adjustment_history import _why  # noqa: PLC0415 - after the app env, like the route tests
    assert _why([]) == {"rule_ids": [], "why_text": OWN, "why_lines": []}
    assert _why([_rec(5, "T-03")])["why_text"] == EXPECTED_T03
    several = _why([_rec(9, "T-09"), _rec(5, "T-03")])
    assert several["rule_ids"] == ["T-03", "T-09"] and several["why_text"] == "2 adjustment conditions triggered"
    assert several["why_lines"] == [EXPECTED_T03, EXPECTED_T03]
    unreadable = _why([_rec(5, "T-03", readable=False)])
    assert unreadable["why_text"] == "From an adjustment opportunity whose condition could not be read"
    assert _rec(5, "T-03").placed_order_ids == (7,)
