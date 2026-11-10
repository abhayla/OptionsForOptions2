"""GC-ICSAFE (ADR-286, REQ-115 AC-6, ADR-285 (1)): the API's once-a-minute watch of the background worker and of the
market calendar's end. Non-DB, no network: the clock, the heartbeat read, the market and the Notifier are injected."""
from __future__ import annotations

import asyncio
import datetime
import logging

import pytest
from ofo_app import feed_bus, notifier, worker_watch

STOPPED, RECOVERED, UNREADABLE_KIND = "worker-stopped", "worker-recovered", "worker-unreadable"
CAPPED = "worker-capped"
DAY = datetime.datetime(2026, 11, 10, 10, 0, tzinfo=feed_bus.IST)  # an ordinary day with no calendar warning


class _End(BaseException):  # not an Exception: the loop under test must not swallow it
    pass


class Rig:
    def __init__(self, now=DAY, state=feed_bus.FRESH, is_open=True):
        self.now, self.state, self.is_open, self.sent, self.fail = now, state, is_open, [], False
        self.answers: list[str] = []  # the next answers of the Notifier client; empty = sent
        self.watch = worker_watch.WorkerWatch(read_state=self._read, notify=self._notify, clock=lambda: self.now,
                                              market_open=lambda _now: self.is_open)

    async def _read(self, _now):
        return self.state

    async def _notify(self, severity, title, body, *, type, dedupe_key):
        self.sent.append((severity, title, body, type, dedupe_key))
        if self.fail:
            raise RuntimeError("notifier down")
        return self.answers.pop(0) if self.answers else notifier.SENT

    async def minute(self, state=None):
        if state is not None:
            self.state = state
        self.now += datetime.timedelta(minutes=1)
        await self.watch.check()

    async def run(self, *states):
        for state in states:
            await self.minute(state)

    def kinds(self):
        return [s[3] for s in self.sent]


async def test_stale_alerts_once_critical_with_the_day_and_change_number_and_repeats_are_silent():
    rig = Rig()
    await rig.run(feed_bus.STALE, feed_bus.STALE, feed_bus.STALE)
    [(severity, _title, _body, kind, key)] = rig.sent
    assert (severity, kind, key) == ("critical", STOPPED, "worker-stopped-2026-11-10-1")


async def test_fresh_after_stale_sends_one_recovered_and_fresh_alone_sends_nothing():
    rig = Rig()
    await rig.minute()
    assert rig.sent == []
    await rig.run(feed_bus.STALE, feed_bus.FRESH, feed_bus.FRESH)
    assert rig.kinds() == [STOPPED, RECOVERED]


async def test_a_second_outage_the_same_day_is_announced_with_its_own_key():
    """The reviewer's timeline: [stale, fresh, stale, stale] is stopped, running again, stopped (not two messages)."""
    rig = Rig()
    await rig.run(feed_bus.STALE, feed_bus.FRESH, feed_bus.STALE, feed_bus.STALE)
    assert rig.kinds() == [STOPPED, RECOVERED, STOPPED]
    assert [s[4] for s in rig.sent] == ["worker-stopped-2026-11-10-1", "worker-recovered-2026-11-10-2",
                                        "worker-stopped-2026-11-10-3"]


async def test_unreadable_alerts_once_and_is_never_read_as_healthy_then_fresh_is_running_again():
    rig = Rig(state=feed_bus.UNREADABLE)
    await rig.run(None, None)
    assert rig.kinds() == [UNREADABLE_KIND]
    await rig.minute(feed_bus.FRESH)  # a store outage of one minute with no all-clear was the old gap
    assert rig.kinds() == [UNREADABLE_KIND, RECOVERED]


async def test_stale_then_unreadable_then_fresh_is_three_changes():
    rig = Rig()
    await rig.run(feed_bus.STALE, feed_bus.UNREADABLE, feed_bus.FRESH)
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


async def test_a_new_day_announces_a_worker_that_is_still_down():
    rig = Rig()
    await rig.minute(feed_bus.STALE)
    rig.now += datetime.timedelta(days=1)
    await rig.run(None, None)
    assert rig.kinds() == [STOPPED, STOPPED]
    assert [s[4] for s in rig.sent] == ["worker-stopped-2026-11-10-1", "worker-stopped-2026-11-11-1"]


async def test_a_failed_send_is_tried_again_each_minute_with_the_same_key_until_it_goes_through(caplog):
    rig = Rig()
    rig.answers = [notifier.UNREACHABLE, notifier.SERVER_ERROR]
    caplog.set_level(logging.WARNING)
    await rig.run(feed_bus.STALE, feed_bus.STALE, feed_bus.STALE, feed_bus.STALE)
    assert rig.kinds() == [STOPPED] * 3  # two failures, one success, then silence
    assert {s[4] for s in rig.sent} == {"worker-stopped-2026-11-10-1"}
    assert caplog.text.count("alert was not sent") == 2  # noqa: PLR2004


async def test_a_retry_stops_when_the_state_changes_and_the_new_state_is_announced():
    rig = Rig()
    rig.answers = [notifier.UNREACHABLE]
    await rig.run(feed_bus.STALE, feed_bus.FRESH)
    assert rig.kinds() == [STOPPED, RECOVERED]


@pytest.mark.parametrize("answer", [notifier.NOT_CONFIGURED, notifier.BAD_URL])
async def test_an_unconfigured_notifier_leaves_a_log_line_with_the_reason_and_is_not_hammered(answer, caplog):
    rig = Rig()
    rig.answers = [answer, answer]
    caplog.set_level(logging.WARNING)
    await rig.run(feed_bus.STALE, feed_bus.STALE, feed_bus.STALE)
    assert rig.kinds() == [STOPPED]  # a restart is what fixes it; each minute would only repeat the line
    assert "background worker: Background watcher stopped" in caplog.text  # the change itself is in the log
    assert f"the {STOPPED} alert was not sent: {answer}" in caplog.text


async def test_at_most_six_sends_a_day_the_last_one_says_the_rest_are_logged_only(caplog):
    rig = Rig()
    caplog.set_level(logging.WARNING)
    await rig.run(*[feed_bus.STALE, feed_bus.FRESH] * 5)
    assert rig.kinds() == [STOPPED, RECOVERED, STOPPED, RECOVERED, STOPPED, CAPPED]
    assert rig.sent[-1][4] == "worker-capped-2026-11-10"
    assert caplog.text.count("background worker: Background watcher") == 10  # noqa: PLR2004 - every change is logged
    rig.now += datetime.timedelta(days=1)  # a new day starts again
    await rig.minute(feed_bus.STALE)
    assert rig.kinds()[-1] == STOPPED and len(rig.sent) == 7  # noqa: PLR2004


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


async def test_the_calendar_warning_is_tried_again_the_next_minute_when_its_send_failed_and_logged_once(caplog):
    rig = Rig(now=datetime.datetime(2026, 12, 2, 10, 0, tzinfo=feed_bus.IST), is_open=False)
    rig.answers = [notifier.UNREACHABLE]
    caplog.set_level(logging.WARNING)
    await rig.run(None, None, None)
    assert rig.kinds() == ["calendar-ends"] * 2
    assert caplog.text.count("market calendar ends") == 1


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


async def test_it_starts_only_with_a_live_market_and_the_bus(monkeypatch, caplog):
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
