"""GC-ICFIX (ADR-008, ADR-263, ADR-306, issue 707): every money text in the adjustment review reply has exactly two
decimals, whatever shape the booked figure has. No database. The reply is read as the client reads it: the route's
block, validated and dumped through the reply models.
"""
from __future__ import annotations

import datetime
import re
from decimal import Decimal as D

import pytest
from ofo.adjustment.approaches import Position, PositionLeg
from ofo.charges import ChargeRates
from ofo_app.api_models import AdjustChargesOut, AdjustAfterOut
from ofo_app.routes import adjustment as route

EXPIRY = datetime.date(2026, 11, 3)
T0 = datetime.datetime(2026, 10, 29, 4, 0, tzinfo=datetime.UTC)
LOT = 65
RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=datetime.date(2026, 10, 15),
    source_url="https://zerodha.com/charges")
MARKET = route.MarketInputs((), {}, None, None, None, None, None,
                            datetime.datetime(2026, 11, 2, 5, 0, tzinfo=datetime.UTC))
LEGS = (PositionLeg("BUY", "PE", D("22400"), EXPIRY, 1, D("20.10"), "X1"),
        PositionLeg("SELL", "PE", D("22500"), EXPIRY, 1, D("35.25"), "X2"),
        PositionLeg("SELL", "CE", D("23050"), EXPIRY, 1, D("40.40"), "X3"),
        PositionLeg("BUY", "CE", D("23100"), EXPIRY, 1, D("22.30"), "X4"))
TWO_DECIMALS = re.compile(r"^-?\d+\.\d{2}$")


def _reply(booked: D, paid: D | None) -> dict:
    priced = route.price_after(LEGS, Position("NIFTY", LOT, "weekly", T0.date(), LEGS), booked, paid, (), RATES,
                               MARKET, paid)
    block = route._after_block(priced, False)
    after = AdjustAfterOut.model_validate(block["after"]).model_dump(mode="json")
    charges = AdjustChargesOut.model_validate(block["charges"]).model_dump(mode="json")
    return {"after": after, "charges": charges, "known": priced.charges_known}


def _texts(reply: dict) -> list[str]:
    after = reply["after"]
    out = [after["booked_pnl"]]
    for side in ("gross", "after_charges"):
        if after[side] is not None:
            out += [after[side]["max_profit"], after[side]["max_loss"]]
    out += [v for k, v in reply["charges"].items() if k != "not_available" and v is not None]
    return [t for t in out if t != "UNLIMITED"]


@pytest.mark.parametrize("booked", [D("962"), D("962.005"), D("216.125"), D(131) + D(1) / D(12), D("0"), D("-45.5"),
                                    D("19175.81000000000000000000033")],
                         ids=["whole rupee", "sub-paisa 962.005", "sub-paisa 216.125", "repeating", "zero",
                              "negative", "28-digit tail"])
def test_every_money_text_has_exactly_two_decimals(booked: D) -> None:
    reply = _reply(booked, D("100.00"))
    assert reply["known"]
    texts = _texts(reply)
    assert len(texts) >= 8, texts
    assert [t for t in texts if not TWO_DECIMALS.match(t)] == []


def test_charges_not_computable_still_gives_a_two_decimal_booked_and_gross() -> None:
    reply = _reply(D("962"), None)
    assert not reply["known"]
    assert reply["after"]["after_charges"] is None
    assert [t for t in _texts(reply) if not TWO_DECIMALS.match(t)] == []
