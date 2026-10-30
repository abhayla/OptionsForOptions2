"""A Kite REST quote's own timestamp, read in one place (REQ-155 AC-5, ADR-016..019 order-path closure).

Pure market-data parsing: no order code. It lives here, not in ``ofo_app.execute_plan``, so a read path (the REST
index spot in ``ofo_app.live_market``) can use it without its import closure reaching an order module; the order
path imports it from here too.
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping

from ofo.timeutil import IST

#: Kite's quote ``timestamp`` text: IST wall time, no zone.
QUOTE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def quote_time(quote: Mapping[str, object]) -> datetime.datetime | None:
    """The quote's own timestamp (Kite's IST wall time), aware; None when absent or unreadable."""
    raw = quote.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.datetime.strptime(raw, QUOTE_TIME_FORMAT).replace(tzinfo=IST)
    except ValueError:
        return None
