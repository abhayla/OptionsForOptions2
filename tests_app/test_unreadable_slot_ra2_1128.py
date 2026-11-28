"""Lane RA2 (Lane FE3's deferred issue; REQ-115 AC-4): a monitor's slot in the index-exit report that cannot be read is
not dropped. Real case: monitor ``a`` is evaluating the index exit of trade 100 and its slot is fresh; monitor ``b``'s
slot was written in a shape this reader does not know (a half write, another build). Before: ``b``'s slot was skipped
and what it claimed was unknown, so a trade only ``b`` evaluated read "judged". Now the whole report reads unreadable:
every trade the worker calls ACTIVE reads paused with ``state_unreadable`` until a live monitor's next write removes the
bad slot."""
from __future__ import annotations

import datetime
import json

from ofo_app import monitoring_state
from test_monitor_reports_fe2_1128 import NOW, _Client, _report, _slot

SECOND = datetime.timedelta(seconds=1)


def test_a_slot_that_cannot_be_read_makes_the_report_unreadable_never_a_judged_trade():
    good = _slot(NOW - SECOND, watching=[100])
    raw = _report(a=good)
    assert monitoring_state.decode_exits(raw, NOW) == {}, "one good fresh slot: trade 100 is judged"
    body = json.loads(raw)
    body["owners"]["b"] = {"at": "yesterday", "watching": "all"}  # a shape this reader does not know
    assert monitoring_state.decode_exits(json.dumps(body), NOW) is None


def test_the_one_good_slot_alone_still_reads_as_before_and_a_slot_of_another_shape_alone_is_unreadable():
    assert monitoring_state.decode_exits(_report(a=_slot(NOW - SECOND, watching=[100])), NOW) == {}
    assert monitoring_state.decode_exits(_report(a={"at": "x"}), NOW) is None


async def test_every_active_trade_reads_paused_unreadable_while_a_bad_slot_is_stored():
    client = _Client()
    body = json.loads(_report(a=_slot(NOW - SECOND, watching=[100])))
    body["owners"]["b"] = {"nonsense": True}
    client.data[monitoring_state.exits_key()] = json.dumps(body)
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [monitoring_state.Entry(100, monitoring_state.ACTIVE, "", "", NOW)], NOW)
    got = (await monitoring_state.read_states(client, [100], NOW, heartbeat=_fresh))[100]
    assert (got.status, got.reason) == (monitoring_state.PAUSED, monitoring_state.STATE_UNREADABLE), got


async def _fresh(*_a, **_k):
    from ofo_app import feed_bus  # noqa: PLC0415
    return feed_bus.FRESH


async def test_the_next_write_removes_a_bad_slot_even_when_its_time_reads_fine():
    """Opus review F2: a slot with a good ``at`` but no ``watching`` list was never removed (only a missing or old
    ``at`` was), so the report stayed unreadable for an hour. Now the next write of a live monitor removes it."""
    import fakeredis  # noqa: PLC0415

    client = fakeredis.FakeAsyncRedis()
    await client.hset(monitoring_state.exit_slots_key(), "old", json.dumps({"at": NOW.isoformat(), "not_run": {}}))
    assert await monitoring_state.ExitsPublisher(client, "new").publish([1], {}, NOW) is True
    owners = [k.decode() for k in await client.hkeys(monitoring_state.exit_slots_key())]
    assert owners == ["new"]
