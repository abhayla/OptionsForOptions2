# ruff: noqa: F811
"""Lane B1b (coordinator, PC check W-34): after a worker restart a trade's "watched" badge returns when ITS OWN first
check ends, not at the end of the whole first cycle. Nine running trades, one worker: the snapshot is written after
each of the first checks, so the first write already names the first trade, every later write names the earlier ones
again (a trade never goes back to "not listed" while the worker is up and reading), and the last write names all
nine."""
from __future__ import annotations

import itertools
import json

from ofo_app import monitoring_state
from test_background_cycle import FIRST_ID, Prov, _watched, scn  # noqa: F401
from test_market_closed_fe3_1128 import _worker_with
from test_monitoring_state import _Client

NINE = 9


class _Recorder(_Client):
    """Every snapshot written, as the set of trade ids it names."""

    def __init__(self) -> None:
        super().__init__()
        self.writes: list[set[int]] = []

    async def set(self, k, v, **kw):
        await super().set(k, v, **kw)
        if k == monitoring_state.key():
            self.writes.append({int(i) for i in json.loads(v)["strategies"]})


async def test_each_trades_badge_comes_back_when_its_own_first_check_ends(scn):
    client = _Recorder()
    prov, now = Prov(scn), [scn.clock_at]
    w = _worker_with(scn, client, prov, now, watched=_watched(scn, NINE))
    await w.cycle()
    ids = {FIRST_ID + i for i in range(NINE)}
    named = [wr for wr in client.writes if wr]
    assert named[0] and len(named[0]) < NINE, "the first report already waited for every trade"
    assert named[-1] == ids, named[-1]
    for earlier, later in itertools.pairwise(named):
        assert earlier <= later, "a trade went back to not listed while the worker was up"
    assert len({frozenset(n) for n in named}) >= 3, "one write per cycle, not per check"  # noqa: PLR2004
