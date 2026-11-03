"""Test helper (ADR-237 (6)): records opened and lapsed the way the background worker stores them, never by the screen.

The screen's adjustment check writes no suggestion record any more; tests that need records open them through the
worker's own store path: ``playbook_store.open_suggestion`` with the fields ``background.DbGateStore.apply`` writes
(trigger, stage, 4-place value and threshold, comparison, the trigger's label and unit from the evaluated body, the
T-19 approach / cost / unpriced count through the route's ``t19_record``), and lapses through
``background.DbGateStore.apply`` itself with the gate's ``Lapsed`` event. One call is one gate step (one group).
The group key here is ``<strategy>-<UTC stamp>``: the worker's own ``<strategy>:<isoformat>`` fails the inbox reply's
Identifier pattern (GC-ALERT1 step 5 finding, proven red by test_worker_group_key.py), so it is not copied.
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from ofo.adjustment import alert_gate
from ofo_app import adjustment_check as check
from ofo_app import playbook_store
from ofo_app.background import DbGateStore, Watched
from ofo_app.routes.adjustment_check import t19_record

AT = datetime.datetime(2026, 11, 2, 10, 0, tzinfo=datetime.UTC)


def _dec(v: str | None) -> Decimal | None:
    return None if v is None else Decimal(v)


async def open_flags(engine: Any, sid: int, reply: Mapping, body: Mapping | None, *,  # noqa: PLR0913
                     rules: set[str] | None = None, user_ref: str = "owner",
                     cheapest: tuple[str, Decimal, int] | None = None, at: datetime.datetime = AT) -> dict[str, int]:
    """Opens one record per flag of a screen check ``reply`` (only ``rules`` when given), as the worker's gate step
    would for each crossing it opens; rule id -> record id. ``body`` = the playbook body the check evaluated."""
    source = playbook_store.SOURCE_SYSTEM if reply["playbook"]["source"] == "system" else playbook_store.SOURCE_OWN
    stage = reply["stage"]["name"]  # the evaluated stage's name (the worker stores Flag.stage_name)
    opened: dict[str, int] = {}
    async with engine.begin() as conn:
        for x in reply["results"]:
            if x["kind"] != "flag" or (rules is not None and x["rule_id"] not in rules):
                continue
            label, unit = check.trigger_words(body, x["trigger_id"])
            rec = await playbook_store.open_suggestion(
                conn, user_ref, sid, x["rule_id"], trigger_id=x["trigger_id"], stage=stage, value=_dec(x["value"]),
                threshold=_dec(x["threshold"]), group=f"{sid}-{at:%Y%m%dT%H%M%S}", source=source, cmp=x["cmp"],
                label=label, unit=unit, **t19_record(x["trigger_id"], cheapest))
            opened[x["rule_id"]] = rec.id
    return opened


async def lapse_through_worker(sid: int, rule_id: str, *, user_ref: str = "owner",
                               at: datetime.datetime = AT) -> None:
    """The worker's own store applies the gate's Lapsed event (the app engine must point at the test database)."""
    w = Watched(user_ref=user_ref, strategy_id=sid, tracked=None, body={}, is_system=True, feed_owner=user_ref)
    await DbGateStore().apply(w, [alert_gate.Lapsed(rule_id, at, None)], None)
