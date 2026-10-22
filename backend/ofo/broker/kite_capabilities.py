"""What Zerodha can do, as named flags (REQ-117 AC-2, W-132; ADR-016 Zerodha is the authority).

Each flag is declared with the source it rests on and the date it was checked. A source is a Kite docs address or a
path in this repo (the real reply or the module that makes the call). ``broker_held_triggers`` stays OFF until
REQ-100 AC-1's core proof has passed; turning it on is a deliberate edit here, with that proof as its new source.
The flags only describe Zerodha: feature code asks the flag by name and never compares the broker's name (REQ-117 AC-3,
``tests/test_no_broker_name_in_feature_code.py``). Declared data: nothing is fetched at runtime.
"""
from __future__ import annotations

import datetime
from types import MappingProxyType
from typing import Final

from ofo.broker.capabilities import CapabilitySet, load_capabilities

CHECKED: Final = datetime.date(2026, 10, 22)

ZERODHA_DECLARED: Final = MappingProxyType({
    "basket_page_orders": (True, "https://kite.trade/docs/connect/v3/publisher/ (the Kite publisher basket, ADR-054)",
                           CHECKED),
    "broker_held_triggers": (False, "REQ-100 AC-1: the core proof has not passed (checked 2026-10-22)", CHECKED),
    "intraday_product": (True, "tests/fixtures/kite_replies/user-profile-2026-10-22-redacted.json "
                               "(the real profile reply: products include MIS)", CHECKED),
    "order_update_stream": (True, "https://kite.trade/docs/connect/v3/websocket/#postbacks-and-non-trade-updates "
                                  "(Kite Connect order updates over the WebSocket and postbacks)", CHECKED),
    "funds_read": (True, "backend/ofo_app/kite_reads.py (GET /user/margins, row 3 of the builder sequence)", CHECKED),
    "positions_read": (True, "backend/ofo_app/kite_reads.py (GET /portfolio/positions, row 3 of the builder sequence)",
                       CHECKED),
    "basket_margin_quote": (True, "backend/ofo_app/kite_margin.py (POST /margins/basket)", CHECKED),
})


def load_zerodha_capabilities() -> CapabilitySet:
    """Zerodha's declared flags. Raises ``CapabilityLoadError`` if the declaration is malformed (callers that must not
    fail use ``load_or_off``)."""
    return load_capabilities(ZERODHA_DECLARED)


__all__ = ["CHECKED", "ZERODHA_DECLARED", "load_zerodha_capabilities"]
