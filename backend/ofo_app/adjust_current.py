"""GC-ICGUIDE g16/g20 (#651, #647; REQ-046 AC-2, ADR-008, ADR-003): the drawer's current-position figures, as texts.

One signed max loss (the paper book's own template, so every screen shows one sign), the margin utilisation (T-15's
measure, ``ofo.engine.adjust_ratios.margin_used_pct``) and each held option's IV / OI / LTP. Every figure is a text the
server made: a stated value, or "not available: <reason>"; a price-derived figure on stale prices says so. The browser
shows these as they are and works nothing out."""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from ofo.adjustment.approaches import NO_CHANGE
from ofo.engine.adjust_ratios import margin_used_pct
from ofo.engine.metrics import UNLIMITED
from ofo.errors.explanations import render_explanation
from ofo.money import PAISE

_TENTH = Decimal("0.1")
_HUNDREDTH = PAISE  # two decimals
_HUNDRED = Decimal(100)


def _na(reason: Any) -> Any:
    return render_explanation("adjust_current_na", reason=reason)


def _max_loss(before: Any) -> dict:
    after = getattr(before, "after", None)
    if after is None or not getattr(before, "charges_known", False):
        why = getattr(before, "reason", None)
        absent = render_explanation("adjust_current_loss_absent")
        return {"text": None, "reason": _na(why if why is not None else absent)}
    loss = after.after_charges.max_loss
    if loss is UNLIMITED:
        return {"text": render_explanation("adjust_cmp_unlimited"), "reason": None}
    # the engine's sign: a loss is negative, as on the paper book
    return {"text": render_explanation("summary_paisa_signed", amount=-loss), "reason": None}


def _utilisation(approaches: list[dict], regime: Any) -> dict:
    item = next((a for a in approaches if a.get("id") == NO_CHANGE), None)
    margin = None if item is None else item.get("margin")
    if not margin or margin.get("state") != "stated" or margin.get("value") is None:
        why = margin.get("reason") if margin and margin.get("reason") is not None \
            else render_explanation("adjust_current_util_no_margin")
        return {"text": None, "reason": _na(why)}
    available = getattr(regime, "available_margin", None)
    if available is None:
        return {"text": None, "reason": _na(render_explanation("adjust_current_util_no_funds"))}
    try:
        num, den = margin_used_pct(margin["value"], available)
    except ValueError:
        return {"text": None, "reason": _na(render_explanation("adjust_current_util_no_room"))}
    return {"text": render_explanation("adjust_cmp_percent", value=(num / den).quantize(_TENTH, ROUND_HALF_EVEN)),
            "reason": None}


def _leg(leg: Any, market: Any) -> dict:
    row = next((r for r in market.chain if r.tradingsymbol == leg.tradingsymbol), None)
    older = bool(market.prices_stale)

    def priced(value: Any, absent: str, make: Any) -> Any:
        if value is None:
            return _na(render_explanation(absent))
        text = make(value)
        return render_explanation("adjust_current_older", value=text) if older else text
    iv_text = priced(market.leg_ivs.get(leg.tradingsymbol), "adjust_current_iv_absent", lambda v: render_explanation(
        "adjust_cmp_percent", value=(v * _HUNDRED).quantize(_HUNDREDTH, ROUND_HALF_EVEN)))
    oi = None if row is None else row.oi
    oi_text = _na(render_explanation("adjust_current_oi_absent")) if oi is None \
        else render_explanation("outcome_oi_count", count=oi)
    ltp_text = priced(None if row is None else row.ltp, "adjust_current_ltp_absent",
                      lambda v: render_explanation("adjust_cmp_rupees", amount=v))
    return {"tradingsymbol": leg.tradingsymbol,
            "label": render_explanation("adjust_current_leg", action=leg.side, strike=leg.strike, kind=leg.type),
            "iv": iv_text, "oi": oi_text, "ltp": ltp_text,
            "text": render_explanation("adjust_current_leg_line", iv=iv_text, oi=oi_text, ltp=ltp_text)}


def block(position: Any, market: Any, before: Any, approaches: list[dict]) -> dict:
    return {"max_loss": _max_loss(before), "margin_utilisation": _utilisation(approaches, market.regime),
            "legs": [_leg(x, market) for x in position.legs]}
