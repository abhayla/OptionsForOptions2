"""Lane RA2 item 3, F7 (Lane FE3 review; ADR-330 (64), REQ-115 AC-4): the clean-up of a long-dead monitor's slot in the
index-exit report is ONE atomic step (a Lua compare-and-delete), not a read then a delete.

Real case: monitor ``old`` last wrote its slot 10 minutes ago (long dead); monitor ``new`` cleans up. Between ``new``'s
read of the hash and its delete, ``old`` comes back and writes a FRESH slot (a restart that kept its owner id). The
two-step clean-up deleted that fresh slot: its trades read "not watched" until the next write (up to 10 s). The script
deletes a field only if it still holds the exact text that was judged dead. Needs fakeredis with Lua (``lupa``)."""
from __future__ import annotations

import datetime
import json

import fakeredis
from ofo_app import monitoring_state

NOW = datetime.datetime(2026, 11, 28, 11, 0, tzinfo=datetime.UTC)


def _slot(at: datetime.datetime, watching: list[int]) -> str:
    return json.dumps({"at": at.isoformat(), "not_run": {}, "watching": watching}, sort_keys=True)


class _Racing(fakeredis.FakeAsyncRedis):
    """After the read of the whole hash, the long-dead monitor writes a fresh slot (the window between the steps)."""

    race = None

    async def hgetall(self, name):
        got = await super().hgetall(name)
        if self.race is not None:
            owner, text = self.race
            self.race = None
            await self.hset(name, owner, text)
        return got


async def test_a_monitor_that_writes_between_the_read_and_the_delete_keeps_its_fresh_slot():
    client = _Racing()
    key = monitoring_state.exits_key
    dead = NOW - datetime.timedelta(seconds=monitoring_state.OWNER_KEEP_S + 60)
    await client.hset(monitoring_state.exit_slots_key(), "old", _slot(dead, [9]))
    client.race = ("old", _slot(NOW, [9]))
    cleaner = monitoring_state.ExitsPublisher(client, "new")
    assert await cleaner.publish([1], {}, NOW) is True
    left = {k.decode() if isinstance(k, bytes) else k: v for k, v in (await client.hgetall(
        monitoring_state.exit_slots_key())).items()}
    assert sorted(left) == ["new", "old"], "the fresh slot of the monitor that came back was kept"
    assert json.loads(left["old"])["at"] == NOW.isoformat()
    assert key is not None


async def test_a_slot_long_dead_is_still_removed_with_the_script():
    client = _Racing()
    dead = NOW - datetime.timedelta(seconds=monitoring_state.OWNER_KEEP_S + 60)
    await client.hset(monitoring_state.exit_slots_key(), "old", _slot(dead, [9]))
    assert await monitoring_state.ExitsPublisher(client, "new").publish([1], {}, NOW) is True
    owners = [k.decode() if isinstance(k, bytes) else k for k in await client.hkeys(monitoring_state.exit_slots_key())]
    assert owners == ["new"]
