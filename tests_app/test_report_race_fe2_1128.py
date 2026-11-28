"""Lane FE2 (28 Nov 2026), coordinator hand-over 5 (review F4) and 6. Spec basis: REQ-115 AC-3 and AC-4 (a trade is
shown as watched only while its exits are judged); ADR-016 to ADR-019 (an unresolved state blocks).

5: the merged index-exit report is read-merge-write. Two monitors that write at the same moment can lose one slot (each
read the old report). A lost slot now reads as "not watched" for a healthy trade, so the writer re-reads after its
write and writes again until its own slot is there (bounded); a store that never keeps it is a failed publish.
6: the saved-plan re-read period is 10 seconds, not 15 or 20.
"""
from __future__ import annotations

import datetime
import json

from ofo_app import background, monitoring_state
from test_background_cycle import Calls, Prov, _watched, _worker, scn  # noqa: F401 - the module fixture
from test_monitoring_state import T0, _Client

TEN_SECONDS = 10
THREE = 3
TWO_WRITES = 2


class _LoseFirstWrite(_Client):
    """Another monitor's write that read the old report lands right after this monitor's FIRST write."""

    def __init__(self, stale_body: str) -> None:
        super().__init__()
        self.stale_body = stale_body
        self.writes = 0

    async def set(self, k, v, **kw):
        await super().set(k, v, **kw)
        self.writes += 1
        if self.writes == 1:
            self.data[k] = self.stale_body


class _LoseEveryWrite(_LoseFirstWrite):
    async def set(self, k, v, **kw):
        await _Client.set(self, k, v, **kw)
        self.writes += 1
        self.data[k] = self.stale_body


def _stale_report() -> str:
    slot = {"at": T0.isoformat(), "not_run": {}, "watching": [7]}
    return json.dumps({"at": T0.isoformat(), "owners": {"b": slot}})


def _owners(client) -> dict:
    return json.loads(client.data[monitoring_state.exits_key()])["owners"]


async def test_a_slot_lost_to_a_simultaneous_writer_is_written_again():
    client = _LoseFirstWrite(_stale_report())
    pub = monitoring_state.ExitsPublisher(client, "a")
    assert await pub.publish([100], {}, T0) is True
    owners = _owners(client)
    print("OWNERS", sorted(owners), "WRITES", client.writes)
    assert sorted(owners) == ["a", "b"] and owners["a"]["watching"] == [100]
    assert client.writes == TWO_WRITES


async def test_a_store_that_never_keeps_the_slot_is_a_failed_publish_and_is_tried_again_next_pass():
    client = _LoseEveryWrite(_stale_report())
    pub = monitoring_state.ExitsPublisher(client, "a")
    assert await pub.publish([100], {}, T0) is False
    assert client.writes == monitoring_state.WRITE_TRIES == THREE
    client.stale_body = json.dumps({"at": T0.isoformat(), "owners": {}})
    assert await pub.publish([100], {}, T0 + datetime.timedelta(seconds=1)) is False  # not recorded: tried again


async def test_an_undisturbed_write_is_one_write():
    client = _Client()
    assert await monitoring_state.ExitsPublisher(client, "a").publish([100], {}, T0) is True
    assert client.sets == 1


async def test_the_saved_plan_reread_period_is_ten_seconds_exactly(scn):  # noqa: F811
    assert background.REBUILD_SECONDS == TEN_SECONDS
    asked: list[float] = []
    w = _worker(Prov(scn), _watched(scn), [scn.clock_at], Calls())

    async def sleeper(seconds):
        asked.append(seconds)
        w.stop()
    w._rebuild_sleep = sleeper
    await w._rebuild_loop()
    assert asked == [TEN_SECONDS], asked
