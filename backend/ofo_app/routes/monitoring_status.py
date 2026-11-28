"""GET /api/monitoring-state: whether each running trade is being watched (Lane Y item 1).

Spec basis: REQ-115 AC-4 / AC-6 (no usable price, or no worker heartbeat for 2 minutes: "Monitoring paused"),
REQ-049 line 38 (the badge and the grey "Health unknown" dot), REQ-165 lines 52 and 72, domain-model line 71 (the
strategy state does not change; only its monitoring status shows paused). One computation:
``monitoring_state.read_states`` (Lane J2); this module only words it. Every sentence is built here from the
catalogue; the page prints them. The page asks for the ids it shows (``?ids=1,2``, at most 50); the answer names each.
Answer states: active -> no badge, ``since_text`` only; paused -> badge, health dot word, reason sentence, since;
a running trade the worker does not name, a heartbeat older than 2 minutes, an unreadable snapshot -> paused, "Not being
watched"; an unknown status or reason code -> paused (fail closed, never healthy); no running trades -> empty list.
Writes nothing. Suggest-only (ADR-003)."""
from __future__ import annotations

import datetime
import logging
import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.errors.explanations import EXPLANATIONS, render_explanation
from ofo.timeutil import IST

from ofo_app import feed_bus, feed_mode, settings_store
from ofo_app import monitoring_state as ms
from ofo_app.api_models import ApiModel, CatalogueText, Identifier
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute

log = logging.getLogger(__name__)
router = APIRouter(route_class=ClosedRoute)
_SAFE = re.compile(r"[A-Za-z0-9_]{1,64}")  # ASCII only: the Identifier type's own pattern
_WHY = {ms.WORKERS_DOWN, ms.STATE_UNREADABLE, ms.NOT_LISTED, "expiry_kind_unknown", "stale", "disconnected", "leg_missing", "check_failed",
        "market_closed", "user_paused"}


class MonitoringOut(ApiModel):
    strategy_id: int
    watch_state: Literal["active", "paused"]
    reason: Identifier
    badge_text: CatalogueText | None
    health_text: CatalogueText | None
    reason_text: CatalogueText | None
    since_at: datetime.datetime | None
    since_text: CatalogueText | None


class MonitoringListOut(ApiModel):
    strategies: list[MonitoringOut]


def compose(found: Mapping[int, ms.Entry], ids: list[int], now: datetime.datetime) -> list[MonitoringOut]:
    """One answer per asked id, in order; an id with no entry, or an entry not clearly active, is paused."""
    out = []
    for sid in ids:
        e = found.get(sid) or ms.Entry(sid, ms.PAUSED, ms.NOT_LISTED, "", None)
        since = e.since.astimezone(IST) if e.since is not None else None
        clock = None if since is None else since.time().replace(second=0, microsecond=0)
        since_text = None if clock is None else render_explanation("monitoring_since", time=clock)
        if e.status == ms.ACTIVE:
            out.append(MonitoringOut(strategy_id=sid, watch_state="active", reason="active", badge_text=None,
                                     health_text=None, reason_text=None, since_at=since, since_text=since_text))
            continue
        code = e.reason if e.reason in _WHY else "unknown"
        if f"monitoring_why_{code}" not in EXPLANATIONS:  # FD2 item 4: a code whose sentence is not in the catalogue yet
            code = "unknown"
        reason = e.reason if _SAFE.fullmatch(e.reason or "") else "unknown"
        out.append(MonitoringOut(strategy_id=sid, watch_state="paused", reason=reason,
                                 badge_text=render_explanation("monitoring_badge"),
                                 health_text=render_explanation("monitoring_health_unknown"),
                                 reason_text=render_explanation(f"monitoring_why_{code}"),
                                 since_at=since, since_text=since_text))
    return out


async def read_found(ids: list[int], now: datetime.datetime) -> dict[int, ms.Entry]:
    """The seam a test replaces: the Redis read. No bus (in-process feed) = no worker = every trade paused."""
    if feed_mode.feed_mode() != feed_mode.BUS:
        return {i: ms.Entry(i, ms.PAUSED, ms.WORKERS_DOWN, "", None) for i in ids}
    client = feed_bus.new_client(feed_mode.redis_url())
    try:
        return await ms.read_states(client, ids, now)
    finally:
        await client.aclose()  # type: ignore[attr-defined]


Reader = Any


async def get_reader() -> Reader:
    return read_found


MAX_IDS = 50


def parse_ids(raw: str) -> list[int]:
    """The asked ids: positive integers only, no repeats, at most MAX_IDS; anything else is dropped (the page treats an
    id the answer does not name as paused)."""
    out: list[int] = []
    for piece in raw.split(","):
        part = piece.strip()
        if part.isascii() and part.isdigit() and int(part) > 0 and int(part) not in out:
            out.append(int(part))
    return sorted(out)[:MAX_IDS]


@router.get("/api/monitoring-state", response_model=MonitoringListOut)
async def monitoring_state(db: Annotated[Any, Depends(get_db)], reader: Annotated[Reader, Depends(get_reader)],
                           ids: str = "") -> MonitoringListOut:
    ask = parse_ids(ids)
    now = await settings_store.database_now(db)
    return MonitoringListOut(strategies=compose(await reader(ask, now), ask, now) if ask else [])
