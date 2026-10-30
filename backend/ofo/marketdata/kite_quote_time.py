"""A Kite REST quote's own timestamp, read in one place (REQ-155 AC-5, ADR-016..019 order-path closure).

Pure market-data parsing: no order code. It lives here, not in ``ofo_app.execute_plan``, so a read path (the REST
index spot in ``ofo_app.live_market``) can use it without its import closure reaching an order module; the order
path imports it from here too.
"""
from __future__ import annotations

import datetime
import re
from collections.abc import Mapping

from ofo.timeutil import IST

#: Kite's quote ``timestamp`` text: IST wall time, no zone (``2026-10-30 11:00:00``); any other shape is refused.
_QUOTE_TIME = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", re.ASCII)


def quote_time(quote: Mapping[str, object]) -> datetime.datetime | None:
    """The quote's own timestamp (Kite's IST wall time), aware; None when absent, of another shape or not a real
    date and time (``2026-13-01 10:00:00``)."""
    raw = quote.get("timestamp")
    if not isinstance(raw, str) or _QUOTE_TIME.fullmatch(raw) is None:
        return None
    try:
        return datetime.datetime.fromisoformat(raw).replace(tzinfo=IST)
    except ValueError:
        return None
