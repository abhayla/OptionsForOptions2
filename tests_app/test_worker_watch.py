"""GC-ICSAFE (ADR-286, REQ-115 AC-6, ADR-285 (1)): the API's once-a-minute watch of the background worker and of the
market calendar's end. Non-DB, no network: the clock, the heartbeat read, the market and the Notifier are injected."""
from __future__ import annotations

import asyncio
import datetime
import logging

import pytest
from ofo_app import feed_bus, notifier, worker_watch

STOPPED, RECOVERED, UNREADABLE_KIND = "worker-stopped", "worker-recovered", "worker-unreadable"
DAY = datetime.datetime(2026, 11, 10, 10, 0, tzinfo=feed_bus.IST)  # an ordinary day with no calendar warning


class _End(BaseException):  # not an Exception: the loop under test must not swallow it
    pass


class Rig:
    def __init__(self, now=DAY, state=feed_bus.FRESH, is_open=True):
        self.now, self.state, self.is_open, self.sent, self.fail = now, state, is_open, [], False
        self.watch = worker_watch.WorkerWatch(read_state=self._read, notify=self._notify, clock=lambda: self.now,
                                              market_open=lambda _now: self.is_open)

    async def _read(self, _now):
        return self.state

    async def _notify(self, severity, title, body, *, type, dedupe_key):
        self.sent.append((severity, title, body, type, dedupe_key))
        if self.fail:
            raise RuntimeError("notifier down")
        return notifier.SENT

    async def minute(self, state=None):
        if state is not None:
            self.state = state
        self.now += datetime.timedelta(minutes=1)
        await self.watch.check()

    def kinds(self):
        return [s[3] for s in self.sent]


async def test_stale_alerts_once_critical_with_the_day_key_and_repeats_are_silent():
    rig = Rig()
    await rig.minute(feed_bus.STALE)
    await rig.minute()
    await rig.minute()
    [(severity, _title, _body, kind, key)] = rig.sent
    assert (severity, kind, key) == ("critical", STOPPED, "worker-stopped-2026-11-10")


async def test_fresh_after_stale_sends_one_recovered_and_fresh_alone_sends_nothing():
    rig = Rig()
    await rig.minute()
    assert rig.sent == []
    await rig.minute(feed_bus.STALE)
    await rig.minute(feed_bus.FRESH)
    await rig.minute()
    assert rig.kinds() == [STOPPED, RECOVERED]


async def test_unreadable_alerts_once_a_day_and_is_never_read_as_healthy():
    rig = Rig(state=feed_bus.UNREADABLE)
    await rig.minute()
    await rig.minute()
    assert rig.kinds() == [UNREADABLE_KIND]
    await rig.minute(feed_bus.FRESH)  # unreadable then fresh: nothing was announced as stopped, so no "recovered"
    assert rig.kinds() == [UNREADABLE_KIND]


async def test_stale_then_unreadable_then_fresh_still_recovers():
    rig = Rig()
    await rig.minute(feed_bus.STALE)
    await rig.minute(feed_bus.UNREADABLE)
    await rig.minute(feed_bus.FRESH)
    assert rig.kinds() == [STOPPED, UNREADABLE_KIND, RECOVERED]


@pytest.mark.parametrize("state", [feed_bus.STALE, feed_bus.UNREADABLE, "something else"])
async def test_outside_market_hours_or_on_a_closed_day_nothing_is_sent(state):
    rig = Rig(is_open=False)
    await rig.minute(state)
    await rig.minute()
    assert rig.sent == []


async def test_the_state_does_not_advance_while_the_market_is_closed():
    rig = Rig()
    await rig.minute(feed_bus.STALE)
    rig.is_open = False
    await rig.minute(feed_bus.FRESH)  # the worker came back overnight: not seen, not announced
    assert rig.kinds() == [STOPPED]
    rig.is_open = True
    await rig.minute(feed_bus.FRESH)
    assert rig.kinds() == [STOPPED, RECOVERED]


async def test_a_new_day_allows_one_alert_again():
    rig = Rig()
    await rig.minute(feed_bus.STALE)
    rig.now += datetime.timedelta(days=1)
    await rig.minute()
    await rig.minute()
    assert rig.kinds() == [STOPPED, STOPPED]
    assert [s[4] for s in rig.sent] == ["worker-stopped-2026-11-10", "worker-stopped-2026-11-11"]


async def test_a_notifier_that_raises_does_not_stop_the_next_minutes_check():
    rig = Rig()
    rig.fail = True
    rig.state = feed_bus.STALE
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 1:
            rig.fail, rig.state = False, feed_bus.FRESH
        if len(sleeps) == 3:  # noqa: PLR2004
            raise _End  # ends the endless loop of the test

    with pytest.raises(_End):
        await rig.watch.run_forever(sleep)
    assert sleeps[:2] == [worker_watch.POLL_SECONDS] * 2
    assert rig.kinds() == [STOPPED, RECOVERED]  # minute 1 raised in the notifier; minute 2 still ran and recovered


@pytest.mark.parametrize("day, count", [(datetime.datetime(2026, 12, 2, 10, 0, tzinfo=feed_bus.IST), 1),
                                        (datetime.datetime(2026, 11, 11, 10, 0, tzinfo=feed_bus.IST), 0)])
async def test_the_calendar_warning_is_one_alert_a_day_inside_30_days_and_none_before(day, count, caplog):
    rig = Rig(now=day, is_open=False)  # independent of market hours
    caplog.set_level(logging.WARNING)
    await rig.minute()
    await rig.minute()
    assert len(rig.sent) == count
    assert caplog.text.count("market calendar ends") == count
    if count:
        severity, title, body, kind, key = rig.sent[0]
        assert (severity, kind, key) == ("warning", "calendar-ends", "calendar-ends-2026-12-02")
        assert "31 December 2026" in title and "31 December 2026" in body


async def test_the_calendar_warning_comes_again_the_next_day():
    rig = Rig(now=datetime.datetime(2026, 12, 2, 10, 0, tzinfo=feed_bus.IST), is_open=False)
    await rig.minute()
    rig.now += datetime.timedelta(days=1)
    await rig.minute()
    assert [s[4] for s in rig.sent] == ["calendar-ends-2026-12-02", "calendar-ends-2026-12-03"]


def test_alert_texts_carry_no_figures_ids_symbols_or_slots_left_unfilled():
    for severity, title, body in worker_watch.TEXTS.values():
        text = f"{title} {body}"
        assert severity in {"critical", "warning", "info"}
        assert "{" not in text.format(end="31 December 2026")
        assert not any(w in text.lower() for w in ("nifty", "sensex", "strategy id", "rs ", "₹", "token", "key"))


async def test_it_starts_only_with_a_live_market_and_the_bus(monkeypatch):
    class Client:
        closed = False

        async def aclose(self):
            Client.closed = True

    monkeypatch.setattr(feed_bus, "new_client", lambda _url: Client())
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setenv("FEED_MODE", "bus")
    assert worker_watch.start_if(None) is None  # no live market
    monkeypatch.setenv("FEED_MODE", "inprocess")
    assert worker_watch.start_if(object()) is None  # no worker exists in this mode
    monkeypatch.delenv("FEED_MODE")
    assert worker_watch.start_if(object()) is None
    monkeypatch.setenv("FEED_MODE", "bus")
    task = worker_watch.start_if(object())
    assert task is not None and not task.done()
    await asyncio.sleep(0)  # let it enter its loop
    await worker_watch.stop(task)
    assert Client.closed  # the bus client is closed with the task
    await worker_watch.stop(None)
