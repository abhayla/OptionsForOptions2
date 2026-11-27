"""REQ-118 / ADR-330 (39), finding page-poll-calls-vendor-rest-before-tick-store: ``SharedReading``, the one cached,
single-flight REST reading. 12 requests inside the TTL are ONE vendor call; a FAILED answer is kept for the cooldown
(no call sent inside it); ABSENT is not kept; after the TTL one more call. No clock sleeps (the clock is injected)."""
import asyncio
import contextlib
from decimal import Decimal

from ofo.marketdata.shared_reading import SharedReading
from ofo.marketdata.spot_source import SourceReading, SourceState

TWO, THREE, FIVE = 2, 3, 5


def _stated():
    return SourceReading(SourceState.STATED, Decimal("23000"), None)


class _Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def _fetcher(reading, counter, gate=None):
    async def fetch():
        counter.append(1)
        if gate is not None:
            await gate.wait()
        return reading
    return fetch


def test_twelve_requests_inside_the_ttl_are_one_vendor_call():
    shared, calls = SharedReading(clock=(c := _Clock())), []
    async def run():
        for _ in range(12):
            await shared.get("NIFTY 50", _fetcher(_stated(), calls))
    asyncio.run(run())
    assert len(calls) == 1 and shared.calls == 1
    c.t += 5.1
    asyncio.run(shared.get("NIFTY 50", _fetcher(_stated(), calls)))
    assert len(calls) == TWO


def test_concurrent_requests_share_one_flight():
    shared, calls = SharedReading(clock=_Clock()), []
    async def run():
        gate = asyncio.Event()
        tasks = [asyncio.create_task(shared.get("N", _fetcher(_stated(), calls, gate))) for _ in range(12)]
        await asyncio.sleep(0)
        gate.set()
        return await asyncio.gather(*tasks)
    out = asyncio.run(run())
    assert len(calls) == 1 and all(r.state is SourceState.STATED for r in out)


def test_a_failed_reading_is_kept_for_the_cooldown_and_nothing_is_sent_inside_it():
    clock = _Clock()
    shared, calls = SharedReading(clock=clock), []
    failed = SourceReading(SourceState.FAILED)
    async def run():
        return [await shared.get("N", _fetcher(failed, calls)) for _ in range(12)]
    out = asyncio.run(run())
    assert len(calls) == 1 and {r.state for r in out} == {SourceState.FAILED}
    clock.t += 9.9
    asyncio.run(shared.get("N", _fetcher(failed, calls)))
    assert len(calls) == 1  # still inside Kite's 10 s cooldown
    clock.t += 0.2
    asyncio.run(shared.get("N", _fetcher(_stated(), calls)))
    assert len(calls) == TWO


def test_absent_is_not_kept_and_an_exception_is_not_kept():
    shared, calls = SharedReading(clock=_Clock()), []
    async def run():
        for _ in range(3):
            await shared.get("N", _fetcher(SourceReading(SourceState.ABSENT), calls))
    asyncio.run(run())
    assert len(calls) == THREE

    async def boom():
        raise RuntimeError("x")
    for _ in range(2):
        with contextlib.suppress(RuntimeError):
            asyncio.run(shared.get("N", boom))
    assert shared.calls == FIVE
