"""GC-UI review fix 2 (R2-1): a queued fetch no request waits on any more takes no shared slot and sends nothing."""
from __future__ import annotations

import asyncio
import datetime
import threading

import pytest
from ofo_app import strategy_price_history as sph

START = datetime.datetime(2026, 10, 1, 9, 0, tzinfo=datetime.UTC)
END = datetime.datetime(2026, 10, 9, 15, 30, tzinfo=datetime.UTC)


@pytest.fixture(autouse=True)
def _clean():
    sph._cache.clear()
    sph._in_flight.clear()
    yield
    sph._cache.clear()
    sph._in_flight.clear()


async def _request(fetch, ids, timeout):  # noqa: ASYNC109 - test seam
    return await asyncio.wait_for(asyncio.gather(*(sph._bars(fetch, i, START, END, lambda: 0.0) for i in ids)), timeout)


def test_queued_fetches_of_a_request_that_gave_up_are_never_sent():
    calls: list[str] = []
    release = threading.Event()

    def blocking(iid, start, end):
        calls.append(iid)
        release.wait(10)
        return []

    async def scenario():
        ids = [f"NFO:{n}" for n in range(5)]  # cap is 2: two in flight, three queued on the semaphore
        with pytest.raises(TimeoutError):
            await _request(blocking, ids, 0.3)  # request A's deadline
        assert len(calls) == sph.MAX_CONCURRENT_FETCHES
        release.set()  # the two in-flight Kite calls are not interrupted
        for _ in range(100):
            if not sph._in_flight:
                break
            await asyncio.sleep(0.02)
        assert not sph._in_flight
        assert len(calls) == sph.MAX_CONCURRENT_FETCHES, f"queued calls were still sent: {calls}"
        assert sph._gate()._value == sph.MAX_CONCURRENT_FETCHES  # every slot free
        # request B (another strategy) is answered although Kite could serve it
        seen_b: list[str] = []
        got = await _request(lambda i, s, e: seen_b.append(i) or [], ["NFO:90", "NFO:91", "NFO:92"], 5)
        assert got == [[], [], []]
        assert len(seen_b) == 3  # noqa: PLR2004 - literal is the pinned value
        assert len(calls) == sph.MAX_CONCURRENT_FETCHES  # B's calls went to its own fake, A's stayed at two

    asyncio.run(scenario())
