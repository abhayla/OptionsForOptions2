"""Live test 27 Nov 2026, item 10 (REQ-112 AC-2): an adjustment opportunity is "Acted on" only when a paper order of
its basket is PLACED (accepted); staging the basket, a cancelled basket, or a refused placement leaves it "Open".

Through the real routes on a fresh migrated database (ADJ-02), as the screen takes the path: the record is open, the
builder places the basket naming it (POST /paper/strategies/{id}/orders with ``suggestion_ids``) and only that accepted
answer moves it to acted_on, in the order's own transaction.
"""
from __future__ import annotations

import test_adjustment_check as check_test
from test_adjustment_history_why import CONFLICT, CREATED, NOT_FOUND, OK, _book, _place, _record
from test_adjustment_check import _seeded
from test_adjustment_opportunities import _call, _clean, _opened

app_db_url = check_test.app_db_url


async def _shown(sid: int, rec_id: int) -> tuple[str, str]:
    status, inbox = await _call("GET", "/api/adjustment-opportunities")
    assert status == OK
    r = next(r for g in inbox["groups"] if g["strategy_id"] == sid for r in g["records"] if r["id"] == rec_id)
    return r["outcome"], r["outcome_text"]


async def test_only_an_accepted_paper_order_stamps_acted_on(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    await _opened(app_db_url, sid)
    t01 = await _record(app_db_url, sid, "T-01")
    t03 = await _record(app_db_url, sid, "T-03")

    # staged / cancelled basket: nothing was sent to the server, the opportunity reads Open
    assert (await _shown(sid, t01.id))[0] == "open"

    # refused placement (another strategy's record, a missing record): nothing stored, still Open
    before = len(await _book(app_db_url, sid))
    status, _ = await _place(app_db_url, sid, [t01.id, 987654321])
    assert status == NOT_FOUND
    assert len(await _book(app_db_url, sid)) == before
    assert (await _shown(sid, t01.id))[0] == "open"  # the stamp rolled back with the refused basket

    # accepted placement: acted_on, linked to the order, in the answer the inbox gives
    status, out = await _place(app_db_url, sid, [t01.id])
    assert status == CREATED, out
    new_id = (await _book(app_db_url, sid))[-1].id
    rec = await _record(app_db_url, sid, "T-01")
    assert (rec.outcome, rec.placed_order_ids) == ("acted_on", (new_id,))
    assert [e["outcome"] for e in rec.timeline if "outcome" in e] == ["open", "acted_on"]
    assert (await _shown(sid, t01.id))[0] == "acted_on"
    assert (await _shown(sid, t03.id))[0] == "open"  # a record the basket did not name is untouched

    # a second basket cannot answer the same record again
    status, _ = await _place(app_db_url, sid, [t01.id])
    assert status == CONFLICT
