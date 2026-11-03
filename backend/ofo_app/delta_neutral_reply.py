"""A-23 in the approaches reply (GC-IC1 step 4a): the delta-neutral figures as a non-trade block, no After.

Technical call (builder, recorded in the report): A-23 is NOT added to ``approaches.APPROACH_IDS``: a column there is
built, priced and compared as a trade, and A-23 has no trade and no After. It rides the same reply as its own block.

The per-unit deltas are the engine's (``MarketInputs.leg_greeks``: ``chain_values.chain_model``, the figures the
Compare's Greeks read); a chain row's own delta is used only for an ATM contract absent there. Nothing is priced here.
Answer states: every leg has a delta -> the figures; a leg with no delta (no IV) -> known False naming it (never 0);
no ATM option with a delta -> the option figures None, the future figures still given.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from ofo.adjustment import delta_neutral as dn
from ofo.errors.explanations import render_explanation


def _atm_delta(chain: Sequence[Any], greeks: Mapping[str, Any], kind: str,
               spot: Decimal) -> tuple[Decimal | None, Decimal | None]:
    """(strike, per-unit delta) of the listed ``kind`` nearest the spot (a tie: the lower strike); (None, None)."""
    rows = [r for r in chain if r.type == kind and r.listed]
    if not rows:
        return None, None
    row = min(rows, key=lambda r: (abs(r.strike - spot), r.strike))
    g = greeks.get(row.tradingsymbol)
    return row.strike, g.delta if g is not None else row.delta


def block(position: Any, chain: Sequence[Any], leg_greeks: Mapping[str, Any], spot: Decimal) -> dict[str, Any]:
    """The reply's ``delta_neutral`` block (``api_models.AdjustDeltaNeutralOut``)."""
    label = render_explanation("delta_neutral_label")
    legs = [dn.LegDelta(x.tradingsymbol, x.side, x.lots,
                        None if leg_greeks.get(x.tradingsymbol) is None else leg_greeks[x.tradingsymbol].delta)
            for x in position.legs]
    ce_strike, ce = _atm_delta(chain, leg_greeks, "CE", spot)
    pe_strike, pe = _atm_delta(chain, leg_greeks, "PE", spot)
    got = dn.figures(legs, position.lot, ce, pe)
    if isinstance(got, dn.NotKnown):
        return {"label": label, "known": False, "missing_leg": got.leg,
                "reason": render_explanation("delta_neutral_not_known")}
    option = got.option
    return {"label": label, "known": True, "net_delta": got.net_delta, "option_type": got.option_type,
            "option_strike": None if option is None else (ce_strike if got.option_type == "CE" else pe_strike),
            "option_lots": None if option is None else option.lots,
            "option_remaining": None if option is None else option.remaining,
            "future_lots": got.future.lots, "future_remaining": got.future.remaining}
