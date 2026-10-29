# ruff: noqa: E501, PLC0415
"""Review fix 3 (REQ-152 AC-3): the outcome route sends bid_display / ask_display from the server."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace


def test_the_leg_quotes_carry_bid_and_ask_texts_at_two_decimals_for_a_one_decimal_price() -> None:
    """Review fix 3 (REQ-152 AC-3): bid 99.8 leaves as "99.80" in bid_display, ask 100.5 as "100.50"; a leg with no quote
    has None texts (the browser prints the dash)."""
    from ofo_app.routes.outcome import _leg_quotes

    quote = SimpleNamespace(bid=Decimal("99.8"), ask=Decimal("100.5"), health=SimpleNamespace(value="available"))
    snapshot = SimpleNamespace(legs={"A": SimpleNamespace(quote=quote)})
    definition = SimpleNamespace(legs=[SimpleNamespace(instrument_id="A"), SimpleNamespace(instrument_id="B")])
    rows = _leg_quotes(snapshot, definition, {"A": "NIFTY X", "B": None})
    assert (rows[0]["bid"], rows[0]["bid_display"], rows[0]["ask"], rows[0]["ask_display"]) == ("99.8", "99.80", "100.5", "100.50")
    assert (rows[1]["bid_display"], rows[1]["ask_display"]) == (None, None)
