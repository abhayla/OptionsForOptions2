"""The extra Option Chain values of one contract: per-lot premium, intrinsic value, time value, breakeven and
breakeven %, and the engine's Greeks (W-124; REQ-087 AC-1/AC-4/AC-5, REQ-029 AC-3). Standard library plus the engine.

Copy from: none - no algochanakya row. Taken from branch build/W-124-a3-chain (PR #509, row 33-35 code; ADR-171
reuse rule: this file and its test only) with ``iv`` added to ``ChainGreeks`` for the leg picker (REQ-080 AC-2).
Money is ``Decimal`` end to end (ADR-008); the browser only draws the strings.

- intrinsic value is measured against the SPOT (the index price), labelled so on the screen: call max(S - K, 0),
  put max(K - S, 0); time value is LTP minus intrinsic and may be negative (a stale deep in-the-money price is shown
  as it is, never clamped); breakeven is K + LTP for a call and K - LTP for a put; breakeven % is
  (breakeven - S) / S x 100, signed, half-up to 0.01.
- A value whose input is missing is None (the screen draws a dash), never 0 (REQ-087 AC-5): no LTP -> every
  LTP-dependent value is None; no spot -> intrinsic, time value and breakeven % are None. A breakeven at or below zero
  (a deep put) is None: the contract cannot break even inside the index's range.
- Greeks come from the engine's own model at the live spot with the expiry's forward (ADR-056/063), never from the
  vendor's numbers: the contract's implied volatility from the engine's one IV price (``iv_price``, ADR-172: the mid
  when both sides are live and not crossed, else the LTP - the same number the outcome leg shows), then
  ``bs_greeks``. Any refusal gives no Greeks.
- Row 33 (REQ-029 AC-2/AC-3): :func:`chain_model` is the same calculation with its answer state said: the forward's
  basis (``PARITY``, or ``SPOT_FALLBACK`` - ADR-061's "estimated from spot", never silent) or why there are no Greeks
  at all (``SPOT_REFUSED``: no live, healthy spot; ``FORWARD_UNAVAILABLE``: the forward is refused, e.g. at or after
  the expiry close). :func:`chain_greeks` is its map only, so the chain and the leg picker share one calculator.
"""
from __future__ import annotations

import datetime
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from ofo.engine.legs import Instrument
from ofo.engine.model import data_label, expiry_model, greeks, greeks_unrounded, implied_vol, iv_price
from ofo.errors.explanations import ExplanationText
from ofo.marketdata.forward import PARITY, ForwardUnavailable, parity_forward
from ofo.marketdata.quote import NormalizedQuote, is_live_price
from ofo.money import HUNDREDTH, PAISE
from ofo.rules.inputs import DataHealth
from ofo.scenario.spot import SpotRefused, spot_reading

_HUNDRED = Decimal(100)
#: a spot of this health is refused by the forward (ADR-061): no Greeks, said as SPOT_REFUSED
_SPOT_REFUSED_HEALTH = frozenset({DataHealth.UNHEALTHY, DataHealth.UNAVAILABLE})


@dataclass(frozen=True)
class CellValues:
    """Each field None = "not computable now" (drawn as a dash)."""

    per_lot: Decimal | None  # LTP x the contract's lot size
    intrinsic: Decimal | None
    time_value: Decimal | None
    breakeven: Decimal | None
    breakeven_pct: Decimal | None


@dataclass(frozen=True)
class ChainGreeks:
    iv: Decimal  # the engine's implied volatility as a fraction (0.1134 = 11.34 %), from the contract's price
    delta: Decimal
    gamma: Decimal
    theta: Decimal
    vega: Decimal
    #: the unrounded gamma, set only when the 4 dp gamma reads 0.0000 but the real one is not zero (deep OTM ~0.00001)
    gamma_exact: Decimal | None = None


def cell_values(kind: str, strike: Decimal, ltp: Decimal | None, spot: Decimal | None, lot_size: int) -> CellValues:
    """The extra values of one option cell. ``ltp`` is the price as shown (None: no live price); ``spot`` None: none."""
    if kind not in ("CE", "PE"):
        raise ValueError(f"an option side is CE or PE, got {kind!r}")
    priced = ltp is not None and is_live_price(ltp)
    per_lot = ltp * lot_size if priced else None
    intrinsic = None
    if spot is not None and is_live_price(spot):
        intrinsic = max(spot - strike, Decimal(0)) if kind == "CE" else max(strike - spot, Decimal(0))
    breakeven = None
    if priced:
        breakeven = strike + ltp if kind == "CE" else strike - ltp
        if breakeven <= 0:
            breakeven = None
    time_value = ltp - intrinsic if priced and intrinsic is not None else None
    pct = None
    if breakeven is not None and spot is not None and is_live_price(spot):
        pct = ((breakeven - spot) / spot * _HUNDRED).quantize(HUNDREDTH, rounding=ROUND_HALF_UP)
    return CellValues(
        per_lot=None if per_lot is None else per_lot.quantize(PAISE, rounding=ROUND_HALF_UP),
        intrinsic=None if intrinsic is None else intrinsic.quantize(PAISE, rounding=ROUND_HALF_UP),
        time_value=None if time_value is None else time_value.quantize(PAISE, rounding=ROUND_HALF_UP),
        breakeven=None if breakeven is None else breakeven.quantize(PAISE, rounding=ROUND_HALF_UP),
        breakeven_pct=pct)


def in_the_money(kind: str, strike: Decimal, spot: Decimal | None) -> bool | None:
    """REQ-087 AC-2: calls with a strike below the spot, puts with a strike above it. None without a live spot (the
    shading is then off, with the reason on the screen), never False."""
    if kind not in ("CE", "PE"):
        raise ValueError(f"an option side is CE or PE, got {kind!r}")
    if spot is None or not is_live_price(spot):
        return None
    return strike < spot if kind == "CE" else strike > spot


#: REQ-029 AC-9 (row 33): a chain row's place against the ATM strike, read on the calls' side (puts: the opposite)
Moneyness = Literal["ITM", "ATM", "OTM"]


def moneyness(strike: Decimal, atm: Decimal) -> Moneyness:
    """The calls' side: a strike below the ATM strike is in the money, the ATM strike is ATM, above it is out."""
    if strike < atm:
        return "ITM"
    return "ATM" if strike == atm else "OTM"


GreeksBasis = Literal["PARITY", "SPOT_FALLBACK"]
GreeksMissing = Literal["SPOT_REFUSED", "FORWARD_UNAVAILABLE"]


@dataclass(frozen=True)
class ChainModel:
    """The engine's values of one expiry's chain with the answer state: ``greeks`` (instrument_id -> values; a contract
    the model refuses is absent), and exactly one of ``basis`` (what the forward rests on) or ``missing`` (why none)."""

    greeks: Mapping[str, ChainGreeks]
    basis: GreeksBasis | None
    missing: GreeksMissing | None
    #: REQ-072 AC-2: "stale since HH:MM IST" / "delayed, as of HH:MM IST" when the spot is STALE / DELAYED, else None
    label: ExplanationText | None = None


def chain_model(chain: Iterable[NormalizedQuote], spot_quote: NormalizedQuote | None, expiry: datetime.date,  # noqa: PLR0913
                valuation: datetime.datetime, rate: Decimal, *, market_closed: bool = False) -> ChainModel:
    """instrument_id -> engine Greeks for each option of the expiry whose price gives an implied volatility, with the
    forward's basis; no Greeks (and the reason) when the spot or the expiry's forward is refused. ``market_closed``
    (ADR-119 calendar): the held close is the answer (ADR-197, ADR-200 (2)), so no "stale since" label is made; the
    one market-closed banner carries the time."""
    quotes = list(chain)
    try:
        reading = spot_reading(spot_quote)
    except (SpotRefused, ValueError):
        return ChainModel({}, None, "SPOT_REFUSED")
    if reading.health in _SPOT_REFUSED_HEALTH:  # the forward's own spot gate, named as a spot problem
        return ChainModel({}, None, "SPOT_REFUSED")
    try:
        fwd = parity_forward(quotes, spot_quote, expiry, valuation, rate)
        em = expiry_model(reading, fwd)
    except (ForwardUnavailable, ValueError, ArithmeticError):
        return ChainModel({}, None, "FORWARD_UNAVAILABLE")
    out: dict[str, ChainGreeks] = {}
    for q in quotes:
        if q.instrument_type not in (Instrument.CE, Instrument.PE) or q.strike is None or not is_live_price(q.ltp):
            continue
        price = iv_price(q)
        if price is None:
            continue
        try:
            vol = implied_vol(em, q.instrument_type, price, q.strike).iv
            g = greeks(em, q.instrument_type, q.strike, vol).greeks
            exact = greeks_unrounded(em, q.instrument_type, q.strike, vol).gamma if g.gamma == 0 else None
        except (ValueError, ArithmeticError):
            continue
        out[q.instrument_id] = ChainGreeks(vol, g.delta, g.gamma, g.theta, g.vega,
                                           exact if exact is not None and exact > 0 else None)
    return ChainModel(out, "PARITY" if fwd.source == PARITY else "SPOT_FALLBACK", None,
                      None if market_closed else data_label(reading))


def chain_greeks(chain: Iterable[NormalizedQuote], spot_quote: NormalizedQuote | None, expiry: datetime.date,
                 valuation: datetime.datetime, rate: Decimal) -> Mapping[str, ChainGreeks]:
    """instrument_id -> engine Greeks (the map of :func:`chain_model`). Empty when the spot or the expiry's forward is
    refused; a contract the model refuses is simply left out."""
    return chain_model(chain, spot_quote, expiry, valuation, rate).greeks
