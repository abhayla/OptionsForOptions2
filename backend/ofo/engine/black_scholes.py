"""Black-Scholes pricing, implied volatility and Greeks for European index options (REQ-032 AC-3).

Textbook formulas (Hull, *Options, Futures and Other Derivatives*: Black-Scholes-Merton and the Greek letters),
written for this project in the
standard library only; nothing is copied from a legacy repo. The model assumes no dividend yield.

Boundary policy (ADR-008, REQ-032 AC-4):

- Every public input and output is a ``Decimal``; binary floats exist only inside this module's arithmetic.
  An option ``price``, a ``spot`` level and a ``strike`` must be finite, > 0 and have at most 2 decimal places
  (:func:`~ofo.engine.legs.require_price`, the same guard a leg's prices get), so a Decimal built from a float
  (``Decimal(4.76)``) or a sub-paisa value (``4.765``) is refused. Spot and strike are index points, not rupees; they
  share the 2-decimal rule because NSE/BSE quote index levels and strikes to 0.01. ``rate``, ``vol`` and ``years``
  are model parameters, only required to be finite (and > 0 for ``vol`` and ``years``).
- ``rate`` is the annual risk-free rate with **continuous compounding** (``0.10`` = 10 %), ``vol`` the annualised
  volatility as a fraction (``0.20`` = 20 %), ``years`` the time to expiry in years. None has a default: the caller
  always states them. Turning a clock time into ``years`` is :func:`year_fraction`, whose day count
  (``days_in_year``, default :data:`DAYS_IN_YEAR` = 365 calendar days) and expiry close time (default
  :data:`EXPIRY_CLOSE` = 15:30 IST) are explicit parameters.
- Rounding (half-even): a price to :data:`PRICE_STEP` (0.01 rupee); an implied volatility to :data:`IV_STEP`
  (0.000001); Greeks to :data:`GREEK_STEP` (4 decimal places). Theta is per calendar day (annual theta divided by
  ``days_in_year``); vega is per 1 volatility point (per 0.01 of ``vol``).
"""
from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final

from ofo.engine.legs import Instrument, require_price

PRICE_STEP: Final = Decimal("0.01")
IV_STEP: Final = Decimal("0.000001")
GREEK_STEP: Final = Decimal("0.0001")
DAYS_IN_YEAR: Final = 365
IST: Final = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")
EXPIRY_CLOSE: Final = datetime.time(15, 30, tzinfo=IST)
IV_LOWER: Final = 0.0001
IV_UPPER: Final = 5.0
_IV_TOLERANCE: Final = 1e-12
_IV_MAX_ITERATIONS: Final = 200


class NoImpliedVolatilityError(ValueError):
    """No volatility in [IV_LOWER, IV_UPPER] reproduces the given option price."""


@dataclass(frozen=True)
class Greeks:
    """Option sensitivities per unit: delta, gamma, theta per calendar day, vega per 1 volatility point."""

    delta: Decimal
    gamma: Decimal
    theta: Decimal
    vega: Decimal

    def __post_init__(self) -> None:
        for name in ("delta", "gamma", "theta", "vega"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"greek {name} must be a finite decimal.Decimal, got {value!r}")


def _positive(value: object, name: str) -> float:
    if not isinstance(value, Decimal):
        raise ValueError(f"{name} must be a decimal.Decimal, got {type(value).__name__}")
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a finite number > 0, got {value}")
    return float(value)


def _paise(value: object, name: str) -> float:
    return float(require_price(value, name, allow_zero=False))


def _rate(value: object) -> float:
    if not isinstance(value, Decimal):
        raise ValueError(f"rate must be a decimal.Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"rate must be finite, got {value}")
    return float(value)


def _kind(option: object) -> Instrument:
    if option not in (Instrument.CE, Instrument.PE):
        raise ValueError(f"Black-Scholes prices a CE or PE option, got {option!r}")
    return option  # type: ignore[return-value]


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _d1_d2(s: float, k: float, t: float, r: float, v: float) -> tuple[float, float]:
    d1 = (math.log(s / k) + (r + 0.5 * v * v) * t) / (v * math.sqrt(t))
    return d1, d1 - v * math.sqrt(t)


def _price(option: Instrument, s: float, k: float, t: float, r: float, v: float) -> float:
    """Unrounded model price (float, internal only)."""
    d1, d2 = _d1_d2(s, k, t, r, v)
    discounted_k = k * math.exp(-r * t)
    if option is Instrument.CE:
        return s * _norm_cdf(d1) - discounted_k * _norm_cdf(d2)
    return discounted_k * _norm_cdf(-d2) - s * _norm_cdf(-d1)


def _to_decimal(value: float, step: Decimal) -> Decimal:
    if not math.isfinite(value):
        raise ValueError(f"the model produced a non-finite value: {value}")
    return Decimal(repr(value)).quantize(step, rounding=ROUND_HALF_EVEN)


def year_fraction(
    valuation: datetime.datetime,
    expiry: datetime.date,
    *,
    days_in_year: int = DAYS_IN_YEAR,
    close: datetime.time = EXPIRY_CLOSE,
) -> Decimal:
    """Years from ``valuation`` (timezone-aware) to ``close`` on ``expiry``, calendar days / ``days_in_year``."""
    if not isinstance(valuation, datetime.datetime) or valuation.tzinfo is None:
        raise ValueError(f"valuation must be a timezone-aware datetime, got {valuation!r}")
    if not isinstance(expiry, datetime.date) or isinstance(expiry, datetime.datetime):
        raise ValueError(f"expiry must be a datetime.date, got {expiry!r}")
    if isinstance(days_in_year, bool) or not isinstance(days_in_year, int) or days_in_year <= 0:
        raise ValueError(f"days_in_year must be a positive integer, got {days_in_year!r}")
    if close.tzinfo is None:
        raise ValueError("close must be a timezone-aware time")
    seconds = (datetime.datetime.combine(expiry, close) - valuation).total_seconds()
    if seconds <= 0:
        raise ValueError(f"valuation {valuation.isoformat()} is at or after the {expiry} expiry close")
    return Decimal(int(seconds)) / Decimal(days_in_year * 86400)


def bs_price(
    option: Instrument, spot: Decimal, strike: Decimal, years: Decimal, rate: Decimal, vol: Decimal
) -> Decimal:
    """Black-Scholes price per unit of a European CE/PE, rounded half-even to 0.01 rupee."""
    s, k = _paise(spot, "spot"), _paise(strike, "strike")
    t, v, r = _positive(years, "years"), _positive(vol, "vol"), _rate(rate)
    return _to_decimal(_price(_kind(option), s, k, t, r, v), PRICE_STEP)


def forward_price(spot: Decimal, years: Decimal, rate: Decimal) -> Decimal:
    """Cost-of-carry fair value of an index future, ``S e^(rT)`` (same no-dividend assumption), to 0.01."""
    s, t, r = _paise(spot, "spot"), _positive(years, "years"), _rate(rate)
    return _to_decimal(s * math.exp(r * t), PRICE_STEP)


def implied_volatility(
    option: Instrument, price: Decimal, spot: Decimal, strike: Decimal, years: Decimal, rate: Decimal
) -> Decimal:
    """Volatility in [IV_LOWER, IV_UPPER] whose model price equals ``price``; bracketed bisection.

    The model price rises strictly with volatility, so a solution exists exactly when ``price`` lies between the
    prices at the two bounds. Otherwise (for example a price below the discounted intrinsic value) this raises
    :class:`NoImpliedVolatilityError`; it never returns a clipped bound.
    """
    kind = _kind(option)
    target = _paise(price, "price")
    s, k, t, r = _paise(spot, "spot"), _paise(strike, "strike"), _positive(years, "years"), _rate(rate)
    return _to_decimal(_solve_iv(kind, target, s, k, t, r), IV_STEP)


def _solve_iv(kind: Instrument, target: float, s: float, k: float, t: float, r: float) -> float:
    """Bisection on [IV_LOWER, IV_UPPER] for the volatility whose model price is ``target`` (float, internal)."""
    lo, hi = IV_LOWER, IV_UPPER
    p_lo, p_hi = _price(kind, s, k, t, r, lo), _price(kind, s, k, t, r, hi)
    if target < p_lo:
        raise NoImpliedVolatilityError(
            f"price {target} is below the lowest model price {p_lo:.4f} (at or under intrinsic value); no IV"
        )
    if target > p_hi:
        raise NoImpliedVolatilityError(f"price {target} is above the model price at vol {IV_UPPER} ({p_hi:.4f}); no IV")
    for _ in range(_IV_MAX_ITERATIONS):
        mid = 0.5 * (lo + hi)
        if _price(kind, s, k, t, r, mid) < target:
            lo = mid
        else:
            hi = mid
        if hi - lo < _IV_TOLERANCE:
            break
    return 0.5 * (lo + hi)


def _greek_floats(kind: Instrument, s: float, k: float, t: float, r: float, v: float,
                   days_in_year: int) -> dict[str, float]:
    """The four raw (unrounded) Greek floats. Shared by :func:`bs_greeks` and :func:`bs_greeks_unrounded`."""
    d1, d2 = _d1_d2(s, k, t, r, v)
    pdf = _norm_pdf(d1)
    decay = -s * pdf * v / (2.0 * math.sqrt(t))
    carry = r * k * math.exp(-r * t)
    if kind is Instrument.CE:
        delta, theta_year = _norm_cdf(d1), decay - carry * _norm_cdf(d2)
    else:
        delta, theta_year = _norm_cdf(d1) - 1.0, decay + carry * _norm_cdf(-d2)
    return {
        "delta": delta,
        "gamma": pdf / (s * v * math.sqrt(t)),
        "theta": theta_year / days_in_year,
        "vega": s * pdf * math.sqrt(t) / 100.0,
    }


def _check_greek_inputs(option: Instrument, spot: Decimal, strike: Decimal, years: Decimal, rate: Decimal,
                         vol: Decimal, days_in_year: int) -> tuple[Instrument, float, float, float, float, float]:
    kind = _kind(option)
    s, k = _paise(spot, "spot"), _paise(strike, "strike")
    t, v, r = _positive(years, "years"), _positive(vol, "vol"), _rate(rate)
    if isinstance(days_in_year, bool) or not isinstance(days_in_year, int) or days_in_year <= 0:
        raise ValueError(f"days_in_year must be a positive integer, got {days_in_year!r}")
    return kind, s, k, t, r, v


def bs_greeks(
    option: Instrument,
    spot: Decimal,
    strike: Decimal,
    years: Decimal,
    rate: Decimal,
    vol: Decimal,
    *,
    days_in_year: int = DAYS_IN_YEAR,
) -> Greeks:
    """Delta, gamma, theta (per calendar day) and vega (per 1 vol point) per unit, each rounded to 4 dp.

    This is the DISPLAY boundary rounding (spec §4 "Greeks to 4 dp at the boundary") for a single option shown on
    its own. A caller that AGGREGATES several legs' Greeks (e.g. the table's position-level totals, REQ-035 AC-6)
    must use :func:`bs_greeks_unrounded` and round only once, after scaling and summing — rounding here first and
    then multiplying by quantity (round-then-scale) compounds the rounding error (fix round finding: a golden
    Iron Condor leg's Gamma was off by 0.0035 at position level from exactly this bug).
    """
    kind, s, k, t, r, v = _check_greek_inputs(option, spot, strike, years, rate, vol, days_in_year)
    raw = _greek_floats(kind, s, k, t, r, v, days_in_year)
    return Greeks(**{name: _to_decimal(value, GREEK_STEP) for name, value in raw.items()})


def bs_greeks_unrounded(
    option: Instrument,
    spot: Decimal,
    strike: Decimal,
    years: Decimal,
    rate: Decimal,
    vol: Decimal,
    *,
    days_in_year: int = DAYS_IN_YEAR,
) -> Greeks:
    """The same per-unit Greeks as :func:`bs_greeks`, WITHOUT the 4 dp display rounding.

    ``Decimal(repr(float))`` is exact (no further precision lost converting the model's float to Decimal); only the
    display-boundary quantize step is skipped. For internal aggregation only — a caller that scales by quantity and
    sums several legs, then rounds once at its own boundary (never displayed to a user directly).
    """
    kind, s, k, t, r, v = _check_greek_inputs(option, spot, strike, years, rate, vol, days_in_year)
    raw = _greek_floats(kind, s, k, t, r, v, days_in_year)
    for name, value in raw.items():
        if not math.isfinite(value):
            raise ValueError(f"the model produced a non-finite {name}: {value}")
    return Greeks(**{name: Decimal(repr(value)) for name, value in raw.items()})
