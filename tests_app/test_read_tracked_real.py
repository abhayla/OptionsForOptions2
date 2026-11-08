"""GC-ICTRACK task 5 (ADR-276): ``read_tracked`` answers for a paper strategy from the paper book and, when a strategy
has no paper order, for a real one from the real Zerodha book through the SAME netter and contract resolution. A real
strategy's paid charges and adjustments used are unknown (None, never 0); its booked P&L comes from the one netter.
Setup: scenario ADJ-02 (the seeded iron condor) on a throwaway DB; its own paper rows stand in for the real trades."""
from __future__ import annotations

import pytest
import test_background_worker as bw
from ofo_app import adjustment_readers, paper_book, tracked_book
from ofo_app.adjustment_readers import TrackedUnreadable, read_tracked
from test_background_worker import app_db_url  # noqa: F401 - the fixture

IC_LEGS = 4


async def test_paper_and_real_strategies_give_the_same_legs(app_db_url, monkeypatch):  # noqa: F811
    sid, _scn = await bw._seeded(app_db_url, monkeypatch)
    paper = await read_tracked(sid, None)
    assert paper is not None and len(paper.position.legs) == IC_LEGS
    assert isinstance(paper.adjustments_used, int)
    async with app_db_url.connect() as conn:
        stored = await paper_book.load_owned(conn, "owner", sid)

    async def no_paper(*_a):
        return []

    async def real_book(_db, user_ref, strategy_id):
        assert (user_ref, strategy_id) == ("owner", sid)
        return tuple(o.order for o in stored)

    monkeypatch.setattr(paper_book, "load_owned", no_paper)
    monkeypatch.setattr(tracked_book, "real_book", real_book)
    real = await read_tracked(sid, None)
    assert real is not None
    assert real.position.legs == paper.position.legs
    assert (real.paid_charges, real.adjustments_used) == (None, None)
    assert real.booked is not None and real.entered_at == paper.entered_at


async def test_real_branch_not_found_is_none_and_unreadable_fails_closed(monkeypatch):
    async def no_paper(*_a):
        return []

    async def not_mine(*_a):
        return None  # not this user's strategy (or none, or deleted)

    async def unreadable(*_a):
        raise tracked_book.RealBookUnreadable("adopted r: average 7.025")

    monkeypatch.setattr(paper_book, "load_owned", no_paper)
    monkeypatch.setattr(tracked_book, "real_book", not_mine)
    assert await adjustment_readers._real_rows(None, 1) == []
    monkeypatch.setattr(tracked_book, "real_book", unreadable)
    with pytest.raises(TrackedUnreadable, match=r"7\.025"):
        await adjustment_readers._real_rows(None, 1)


async def test_the_worker_lists_a_real_strategy(app_db_url, monkeypatch):  # noqa: F811
    """GC-ICTRACK task 6: the background lister walks every owner strategy through ``read_tracked``, so a strategy
    with no paper order but real trades is listed (with its playbook) like a paper one."""
    from ofo_app import background  # noqa: PLC0415
    sid, scn = await bw._seeded(app_db_url, monkeypatch)
    async with app_db_url.connect() as conn:
        stored = await paper_book.load_owned(conn, "owner", sid)

    async def no_paper(*_a):
        return []

    async def real_book(*_a):
        return tuple(o.order for o in stored)

    monkeypatch.setattr(paper_book, "load_owned", no_paper)
    monkeypatch.setattr(tracked_book, "real_book", real_book)
    listed = await background.owner_lister(scn.provider)
    (watched,) = [w for w in listed if w.strategy_id == sid]
    assert len(watched.tracked.position.legs) == IC_LEGS and watched.tracked.paid_charges is None
