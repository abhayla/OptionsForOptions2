"""#859 (Lane FD2): the Plan watch batch has ONE time budget for the whole request (the old 4 s ran per row: 20 hanging
rows ran 80 s, past the browser's 20 s limit). A row the budget cuts, or never reaches, is ``not_read``; the rows read
before it stay. Fakes only; the budget is shortened for the test (never a wall-clock assertion on the real 15 s)."""
from __future__ import annotations

import asyncio
import datetime
from types import SimpleNamespace

import pytest
from ofo_app.routes import plan_watch_batch as batch


class _Db:
    def __init__(self) -> None:
        self.rollbacks = 0

    async def rollback(self) -> None:
        self.rollbacks += 1


def _call(ids: str, db: _Db):
    o = SimpleNamespace()
    return batch.plan_watch_batch(ids, db=db, user_ref="u", tracked_reader=o, market_reader=o, rest_reader=o,
                                  margin_of=o, ctx=None, rates=None, prefs=o, user_values=o)


def test_the_budget_is_one_and_under_the_browsers_limit():
    assert 0 < batch.BATCH_BUDGET_S < 20  # the browser gives up at 20 s
    assert "not_read" in batch.PlanWatchItemOut.model_fields["state"].annotation.__args__


async def test_twenty_hanging_rows_end_at_the_one_budget_not_at_twenty_budgets(monkeypatch):
    seen: list[int] = []

    async def hangs(sid, **_kw):
        seen.append(sid)
        await asyncio.sleep(30)  # a market read that never answers

    monkeypatch.setattr(batch, "watch_of", hangs)
    monkeypatch.setattr(batch, "BATCH_BUDGET_S", 0.3)
    db = _Db()
    started = asyncio.get_running_loop().time()
    out = await _call(",".join(str(i) for i in range(1, 21)), db)
    took = asyncio.get_running_loop().time() - started
    assert took < 2.0, took  # one budget (0.3 s), not twenty
    assert [i.state for i in out.items] == ["not_read"] * 20
    assert [i.strategy_id for i in out.items] == list(range(1, 21))  # every asked row is named, in order
    assert seen == [1]  # the first hung and used the whole budget; the rest were never waited for
    assert db.rollbacks == 1  # the cut row left the shared session usable


async def test_rows_read_before_the_budget_ends_keep_their_answer_and_a_slow_row_is_cut(monkeypatch):
    calls: list[int] = []

    async def fast_then_slow(sid, **_kw):
        calls.append(sid)
        if sid >= 3:
            await asyncio.sleep(30)
        return SimpleNamespace(as_of=datetime.datetime(2026, 11, 27, 10, 0, tzinfo=datetime.UTC))

    monkeypatch.setattr(batch, "watch_of", fast_then_slow)
    monkeypatch.setattr(batch, "BATCH_BUDGET_S", 0.3)
    monkeypatch.setattr(batch.PlanWatchBatchOut, "model_validate", classmethod(lambda cls, body: body))
    out = await _call("1,2,3,4", _Db())
    assert [(i["strategy_id"], i["state"]) for i in out["items"]] == [(1, "ok"), (2, "ok"), (3, "not_read"),
                                                                       (4, "not_read")]


@pytest.mark.parametrize("ids", ["", "0", "1,x"])
async def test_a_bad_id_list_is_still_the_request_refusal(ids):
    with pytest.raises(Exception):  # noqa: B017, PT011 - the 422 request refusal, unchanged
        await _call(ids, _Db())
