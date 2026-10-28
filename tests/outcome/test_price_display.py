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

