"""Lane FE3 (28 Nov 2026), the coordinator's hand-overs of 12:00 (no database): the sentences for the
closed-market Add to Paper dialog (Lane FD4), a sentence for every "not being watched" why code, the unknown-expiry-kind
reason of the stop lines (Lane FR / FE2 hand-over 3), one number for the clock skew, and the worker's snapshot
written with a store-side expiry (Lane FR's review F1 of issue 879, the writer half)."""
from __future__ import annotations

import datetime
import inspect
import re

from ofo.adjustment import stop_lines as sl
from ofo.errors import CATALOGUE
from ofo.errors.explanations import EXPLANATIONS, render_explanation
from ofo_app import feed_bus, monitoring_state
from ofo_app.monitoring_state import Publisher
from test_monitoring_state import _Client

SNAPSHOTS = 2  # the restart snapshot and the first publish
AT = datetime.datetime(2026, 11, 28, 11, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))


def test_the_closed_market_entries_sentences_read_as_fd4_pins_them():
    assert str(render_explanation("exit_market_closed_entries", day=datetime.date(2026, 11, 30))) == \
        "Orders can be placed from 09:15 on Monday 30 Nov."
    assert str(render_explanation("exit_market_closed_entries_no_day")) == "Orders can be placed when it opens."


def test_every_why_code_has_its_own_sentence():
    codes = [monitoring_state.INDEX_NOT_LIVE, monitoring_state.LEG_NOT_LIVE, monitoring_state.EXIT_NOT_PRICED,
             monitoring_state.INDEX_EXITS_NOT_RUN, monitoring_state.EXITS_NOT_CHECKED_YET,
             monitoring_state.BOOK_NOT_READ, monitoring_state.EXIT_NOT_APPLICABLE, "expiry_kind_unknown"]
    missing = [c for c in codes if f"monitoring_why_{c}" not in EXPLANATIONS]
    assert missing == []
    for c in codes:
        assert str(render_explanation(f"monitoring_why_{c}")).strip()


def test_the_unknown_expiry_kind_of_a_stop_line_has_its_own_reason():
    code = sl.not_checked_code(sl.EXPIRY_KIND_UNKNOWN)
    assert code == "adjust_trigger_expiry_kind_unknown"
    assert code in CATALOGUE


def test_the_clock_skew_has_one_home():
    assert monitoring_state.CLOCK_SKEW_S == feed_bus.HEARTBEAT_SKEW_S
    assert re.search(r"^CLOCK_SKEW_S: Final = feed_bus\.HEARTBEAT_SKEW_S", inspect.getsource(monitoring_state), re.M)


async def test_the_workers_snapshot_is_written_with_a_store_side_expiry():
    """A worker whose clock runs ahead and then dies leaves a stamp that reads fresh by the reader's clock for longer
    than two minutes; the store's own expiry removes the snapshot after ``SNAPSHOT_STALE_S`` whatever the stamp says."""
    seen: list[dict] = []

    class Spy(_Client):
        async def set(self, k, v, **kw):
            seen.append({"key": k, **kw})
            return await super().set(k, v, **kw)
    pub = Publisher(Spy())
    assert await pub.restore(AT) is True
    assert await pub.publish({}, {}, {}, AT) is True
    snapshots = [s for s in seen if s["key"] == monitoring_state.key()]
    assert len(snapshots) == SNAPSHOTS, snapshots
    assert all(s.get("ex") == monitoring_state.SNAPSHOT_STALE_S for s in snapshots), snapshots
