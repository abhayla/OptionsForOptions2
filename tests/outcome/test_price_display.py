"""GC-UI D-PX (REQ-152 AC-2/AC-4, ADR-008): a per-unit price the browser prints arrives as the server's two-decimal text
beside its exact value ("99.8" is a Decimal's canonical form; the display text is "99.80"). Null -> null (the browser
prints the dash)."""
from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ofo.engine.legs import Action, Instrument
from ofo.outcome.serialize import _leg, _net_premium
from ofo.outcome.service import OutcomeLeg

NOW = datetime.datetime(2026, 10, 29, 6, 0, tzinfo=datetime.UTC)


def _outcome_leg(ltp, planned) -> OutcomeLeg:
    return OutcomeLeg(instrument_id="NSE_FO:1", symbol="NIFTY", action=Action.BUY, instrument=Instrument.CE,
                      strike=Decimal("23000"), expiry=datetime.date(2026, 11, 3), lots=1, lot_size=65, quantity=65,
                      planned_entry=planned, captured_at=NOW, ltp=ltp, iv=None, health=None, label=None)


@pytest.mark.parametrize(("ltp", "planned", "ltp_text", "planned_text"), [
    (Decimal("99.8"), Decimal("140.35"), "99.80", "140.35"),
    (Decimal("186.1"), Decimal("187"), "186.10", "187.00"),
    (None, None, None, None),
])
def test_the_outcome_leg_carries_two_decimal_price_texts(ltp, planned, ltp_text, planned_text) -> None:
    leg = _leg(_outcome_leg(ltp, planned), None)
    assert leg["ltp_display"] == ltp_text
    assert leg["planned_entry_display"] == planned_text


def test_the_value_fields_stay_exact() -> None:
    leg = _leg(_outcome_leg(Decimal("99.8"), Decimal("140.35")), None)
    assert leg["ltp"] == "99.8"
    assert leg["planned_entry"] == "140.35"


def test_the_net_premium_per_unit_carries_its_text() -> None:
    premium = SimpleNamespace(amount=Decimal("100"), side="get", per_unit=Decimal("1.5"), text=None, reason=None)
    assert _net_premium(premium)["per_unit_display"] == "1.50"
    empty = SimpleNamespace(amount=None, side=None, per_unit=None, text=None, reason="x")
    assert _net_premium(empty)["per_unit_display"] is None


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
