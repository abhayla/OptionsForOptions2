"""Item 1 (Lane Y): the one read route that tells the page whether each running trade is being watched.

Spec basis: REQ-115 AC-4 / AC-6 (no usable price, or no worker heartbeat for 2 minutes: "Monitoring paused"),
REQ-049 line 38 (the badge and the grey "Health unknown" dot), REQ-165 lines 52 and 72, domain-model line 71 (the
strategy state does not change; its monitoring status shows paused). Every answer state: stated (active / paused with
a worker reason), absent (strategy not named by the snapshot), not found (no strategy), failed (store unreadable),
empty (no strategies), ambiguous (unknown status or reason code: fail closed to paused)."""
from __future__ import annotations

import asyncio
import datetime
import json

from ofo.errors.explanations import render_explanation
from ofo.timeutil import IST
from ofo_app import feed_bus
from ofo_app import monitoring_state as ms
from ofo_app.routes import monitoring_status as route

NOW = datetime.datetime(2026, 11, 27, 11, 0, tzinfo=IST)


class _Client:
    def __init__(self, store: dict | None = None, boom: bool = False):
        self.store, self.boom = store or {}, boom

    async def get(self, key):
        if self.boom:
            raise OSError("down")
        return self.store.get(key)


def _read(client, ids, now=NOW):
    return asyncio.run(ms.read_states(client, ids, now))


def test_core_no_worker_record_for_two_minutes_reads_paused_with_a_reason():
    """REQ-115 AC-6: a heartbeat 3 minutes old -> paused, reason workers_down, never active."""
    old = (NOW - datetime.timedelta(minutes=3)).isoformat()
    out = route.compose(_read(_Client({feed_bus.heartbeat_key(): old}), [7]), [7], NOW)
    assert [(o.strategy_id, o.watch_state, o.reason) for o in out] == [(7, "paused", "workers_down")]
    assert out[0].badge_text == "Monitoring paused"
    assert out[0].reason_text.startswith("Not being watched")
    assert out[0].health_text == "Health unknown"


def test_no_heartbeat_at_all_and_unreadable_store_are_paused():
    for client in (_Client(), _Client(boom=True)):
        out = route.compose(_read(client, [1, 2]), [1, 2], NOW)
        assert {o.watch_state for o in out} == {"paused"}
        assert len(out) == len([1, 2])


def test_fresh_worker_names_each_strategy_and_active_shows_no_badge():
    live_monitor = json.dumps({"at": NOW.isoformat(), "owners": {"m": {  # coordinator item (a): no report = not watched
        "at": NOW.isoformat(), "not_run": {}, "watching": []}}})
    fresh = {ms.key(): ms.encode([ms.Entry(1, ms.ACTIVE, "", "", NOW - datetime.timedelta(minutes=5)),
                                  ms.Entry(2, ms.PAUSED, "stale", "", NOW - datetime.timedelta(minutes=1))], NOW),
             ms.exits_key(): live_monitor, feed_bus.heartbeat_key(): NOW.isoformat()}
    a, b = route.compose(_read(_Client(fresh), [1, 2]), [1, 2], NOW)
    assert (a.watch_state, a.badge_text, a.reason_text, a.health_text) == ("active", None, None, None)
    assert a.since_text == "Since 10:55"
    assert b.watch_state == "paused" and b.badge_text == "Monitoring paused" and b.reason == "stale"
    assert "price" in b.reason_text and b.since_text == "Since 10:59"


def test_a_strategy_the_worker_does_not_list_is_not_being_watched():
    fresh = {ms.key(): ms.encode([ms.Entry(1, ms.ACTIVE, "", "", NOW)], NOW), feed_bus.heartbeat_key(): NOW.isoformat()}
    (o,) = route.compose(_read(_Client(fresh), [9]), [9], NOW)
    assert (o.watch_state, o.reason) == ("paused", "not_listed") and o.reason_text.startswith("Not being watched")


def test_unknown_status_or_reason_fails_closed_and_empty_is_empty():
    odd = {9: ms.Entry(9, "weird", "???", "", None)}
    (o,) = route.compose(odd, [9], NOW)
    assert o.watch_state == "paused" and o.badge_text == "Monitoring paused" and o.reason_text
    assert route.compose({}, [], NOW) == []
    (m,) = route.compose({}, [4], NOW)  # asked but no answer at all
    assert m.watch_state == "paused"


def test_a_non_ascii_reason_code_never_fails_the_whole_reply():
    (o,) = route.compose({3: ms.Entry(3, ms.PAUSED, "stale\u00e9", "", None)}, [3], NOW)
    assert (o.watch_state, o.reason) == ("paused", "unknown")


def test_asked_ids_are_cleaned_and_capped():
    assert route.parse_ids("3, 1,x,-2,0,1,\u0663,") == [1, 3]
    assert route.parse_ids("") == []
    assert len(route.parse_ids(",".join(str(i) for i in range(1, 80)))) == route.MAX_IDS


WORKER_CODES = ("index_not_live", "leg_not_live", "exit_not_priced", "index_exits_not_run", "exits_not_checked_yet",
                "expiry_kind_unknown")


def test_every_why_code_the_worker_now_sends_is_a_known_reason_with_a_sentence_never_a_blank_badge():
    """FD4 (coordinator 10:25): the six codes the worker sends are in the reason map; the sentence comes from the
    catalogue by key (``monitoring_why_<code>``); a code whose sentence the catalogue does not hold yet answers the
    plain "reason is not known" line, never an empty badge (the code itself is still served in ``reason``)."""
    from ofo.errors.explanations import EXPLANATIONS  # noqa: PLC0415
    for code in WORKER_CODES:
        # RA item 2: the worker's codes ride as the ``why`` of ``stale``; expiry_kind_unknown is a reason of its own
        reason, why = ("expiry_kind_unknown", "") if code == "expiry_kind_unknown" else ("stale", code)
        assert ms.sentence_code(ms.Entry(5, ms.PAUSED, reason, why, None)) == code, code
        (o,) = route.compose({5: ms.Entry(5, ms.PAUSED, reason, why, None)}, [5], NOW)
        assert (o.watch_state, o.reason, o.badge_text) == ("paused", reason, "Monitoring paused"), code
        assert f"monitoring_why_{code}" in EXPLANATIONS, code
        assert o.reason_text == render_explanation(f"monitoring_why_{code}") and str(o.reason_text).strip(), code


def test_ra_every_reason_the_worker_and_the_monitor_publish_reaches_its_own_sentence():
    """Lane RA item 2 (review N2): the route read only ``reason`` (always ``stale``), so every why read "The last price
    is too old". An entry (reason ``stale``, why X) reads the sentence of X for each why the worker and the monitor
    send; the badge and the code in ``reason`` are unchanged."""
    from ofo.errors.explanations import EXPLANATIONS  # noqa: PLC0415
    whys = ["index_not_live", "leg_not_live", "exit_not_priced", "index_exits_not_run", "exits_not_checked_yet",
            "book_not_read", "exit_not_applicable"]
    for why in whys:
        assert f"monitoring_why_{why}" in EXPLANATIONS, why
        (o,) = route.compose({5: ms.Entry(5, ms.PAUSED, "stale", why, None)}, [5], NOW)
        assert o.reason == "stale" and o.badge_text == "Monitoring paused", why
        assert o.reason_text == render_explanation(f"monitoring_why_{why}"), why
        assert o.reason_text != render_explanation("monitoring_why_stale"), why  # never the generic line


def test_ra_a_paused_reason_with_its_own_sentence_and_the_plain_fallback():
    (closed,) = route.compose({5: ms.Entry(5, ms.PAUSED, "market_closed", "", None)}, [5], NOW)
    assert str(closed.reason_text) == "The market is closed."
    (kind,) = route.compose({5: ms.Entry(5, ms.PAUSED, "expiry_kind_unknown", "", None)}, [5], NOW)
    assert kind.reason_text == render_explanation("monitoring_why_expiry_kind_unknown")
    # an unknown reason, and an unknown why on a known reason: the plain line (or the reason's own), never blank
    (odd,) = route.compose({5: ms.Entry(5, ms.PAUSED, "no_such_reason", "", None)}, [5], NOW)
    assert str(odd.reason_text) == "Not being watched: the reason is not known."
    (free,) = route.compose({5: ms.Entry(5, ms.PAUSED, "stale", "a REST detail, free text", None)}, [5], NOW)
    assert free.reason_text == render_explanation("monitoring_why_stale")


def test_ra_an_unset_or_in_process_feed_mode_reads_as_its_own_plain_reason_never_as_no_worker(monkeypatch):
    """Lane TG finding (RESULTS-lane-tg line 38): with FEED_MODE unset, ``read_found`` said "no worker has reported in
    the last 2 minutes" for every trade even with a worker running: a wrong reason. Without the bus the API cannot know
    anything about a worker, and says exactly that (paused, fail closed; never "watched")."""
    for mode in (None, "inprocess"):
        if mode is None:
            monkeypatch.delenv("FEED_MODE", raising=False)
        else:
            monkeypatch.setenv("FEED_MODE", mode)
        found = asyncio.run(route.read_found([4, 5], NOW))
        out = route.compose(found, [4, 5], NOW)
        assert [(o.watch_state, o.reason) for o in out] == [("paused", "no_bus")] * 2, mode
        assert all(str(o.reason_text) == "Not being watched here: this server is not set up to share prices with its "
                   "background worker, so it cannot tell." for o in out), mode
        assert "no worker has reported" not in " ".join(str(o.reason_text) for o in out)
