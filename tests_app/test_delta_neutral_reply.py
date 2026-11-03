"""A-23 in the approaches reply (GC-IC1 4a): engine deltas per leg, the ATM option nearest the spot, figures only;
a leg with no engine delta is named, never 0. Pure: fakes of the route's own position, chain and leg Greeks."""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace as NS

from ofo_app import delta_neutral_reply as reply
from ofo_app.api_models import AdjustDeltaNeutralOut

EXP = datetime.date(2026, 11, 10)


def _row(strike: str, kind: str, delta: str | None = None) -> NS:
    return NS(strike=D(strike), type=kind, listed=True, tradingsymbol=f"NIFTY{strike}{kind}", delta=None
              if delta is None else D(delta))


CHAIN = [_row("23400", "CE"), _row("23450", "CE"), _row("23400", "PE"), _row("23450", "PE")]
GREEKS = {"NIFTY23500CE": NS(delta=D("0.55")), "NIFTY22700PE": NS(delta=D("-0.05")),
          "NIFTY23400CE": NS(delta=D("0.50")), "NIFTY23400PE": NS(delta=D("-0.50"))}
POSITION = NS(lot=65, legs=(NS(tradingsymbol="NIFTY23500CE", side="SELL", lots=3),
                            NS(tradingsymbol="NIFTY22700PE", side="SELL", lots=3)))


def test_the_block_sums_engine_deltas_and_names_the_atm_option():
    got = reply.block(POSITION, CHAIN, GREEKS, D("23420"))
    out = AdjustDeltaNeutralOut.model_validate(got).model_dump(mode="json")
    assert (out["known"], out["net_delta"], out["option_type"], out["option_strike"]) == (True, "-97.50", "CE", "23400")
    assert (out["option_lots"], out["option_remaining"]) == (3, "0.00")
    assert (out["future_lots"], out["future_remaining"]) == (2, "32.50")
    assert out["label"] == "Delta-neutral figures (a calculation, not a suggestion to trade)"


def test_a_leg_with_no_engine_delta_is_named_not_known():
    greeks = {k: v for k, v in GREEKS.items() if k != "NIFTY22700PE"}
    out = AdjustDeltaNeutralOut.model_validate(reply.block(POSITION, CHAIN, greeks, D("23420"))).model_dump(mode="json")
    assert (out["known"], out["missing_leg"], out["net_delta"]) == (False, "NIFTY22700PE", None)
    assert out["reason"] == "Net delta is not known: a leg has no implied volatility now."


def test_an_atm_with_no_delta_gives_the_future_only():
    greeks = {k: v for k, v in GREEKS.items() if "23400" not in k}
    out = reply.block(POSITION, CHAIN, greeks, D("23420"))
    assert (out["option_lots"], out["future_lots"]) == (None, 2)
