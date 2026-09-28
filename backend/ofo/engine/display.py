"""Display formatting without false precision (REQ-032 AC-5; ADR-008 Q15; scenario-calculations.md §5).

- Exact money shows to the paisa with Indian digit grouping: ``₹17,19,000.00``; a loss uses the minus sign
  U+2212 as the spec writes it: ``−₹322.50``.
- Index levels are points, never rupees: ``23,047.35``.
- An estimate is approximate and says so: ``~73%``, ``~₹1,235`` (whole rupees; never ``73.48291%``), and a line that
  shows one is labelled "Estimated" and lists its assumptions. An estimate without assumptions is refused.

Rounding is half-even throughout (to the paisa for money, to the whole unit for estimates).
"""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final, Sequence

from ofo.engine.estimate import EstimatedNow

MINUS: Final = "−"
_PAISA: Final = Decimal("0.01")
_WHOLE: Final = Decimal("1")


def _finite(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite decimal.Decimal, got {value!r}")
    return value


def _group_indian(digits: str) -> str:
    """'1719000' -> '17,19,000': the last three digits, then groups of two."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    groups.insert(0, head)
    return ",".join(groups) + "," + tail


def _number(value: Decimal, step: Decimal) -> tuple[str, str]:
    """(sign, grouped absolute value) of ``value`` rounded half-even to ``step``."""
    rounded = value.quantize(step, rounding=ROUND_HALF_EVEN)
    sign = MINUS if rounded < 0 else ""
    whole, _, fraction = f"{abs(rounded):f}".partition(".")
    return sign, _group_indian(whole) + (f".{fraction}" if fraction else "")


def format_rupees(amount: Decimal) -> str:
    """Exact money to the paisa: ``₹17,19,000.00``, ``−₹8,175.00``."""
    sign, text = _number(_finite(amount, "amount"), _PAISA)
    return f"{sign}₹{text}"


def format_points(level: Decimal) -> str:
    """An index level in points with Indian grouping and no currency: ``23,047.35``, ``22,909``."""
    value = _finite(level, "level")
    step = _WHOLE if value == value.to_integral_value() else _PAISA
    sign, text = _number(value, step)
    return f"{sign}{text}"


def format_approx_rupees(amount: Decimal) -> str:
    """An estimated amount, to the whole rupee and marked approximate: ``~₹1,235``, ``~−₹8,175``."""
    sign, text = _number(_finite(amount, "amount"), _WHOLE)
    return f"~{sign}₹{text}"


def format_approx_percent(percent: Decimal) -> str:
    """An estimated percentage (given in percent), to the whole percent: ``~73%`` for 73.48291."""
    sign, text = _number(_finite(percent, "percent"), _WHOLE)
    return f"~{sign}{text}%"


def _percent(fraction: Decimal) -> str:
    """An assumption rate as a percent to one decimal: 0.065 -> '6.5%'."""
    value = (fraction * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN)
    return f"{MINUS if value < 0 else ''}{abs(value)}%"


def estimate_line(label: str, value: str, assumptions: Sequence[str]) -> str:
    """``Estimated <label>: <value> (estimate; assumes <a>; <b>)``. Refuses an estimate with no assumptions."""
    if not isinstance(label, str) or not label.strip():
        raise ValueError("an estimate needs a label")
    stated = [a for a in assumptions if isinstance(a, str) and a.strip()]
    if not stated or len(stated) != len(assumptions):
        raise ValueError("an estimate must state its assumptions (non-empty text each)")
    return f"Estimated {label}: {value} (estimate; assumes {'; '.join(stated)})"


def describe_estimate(estimate: EstimatedNow, underlying: str) -> str:
    """The labelled Estimated Now line for one level, with the model, IVs, rate and valuation time it assumes."""
    if not isinstance(estimate, EstimatedNow):
        raise ValueError(f"estimate must be an EstimatedNow, got {estimate!r}")
    a = estimate.assumptions
    ivs = ", ".join(_percent(iv) for iv in a.ivs if iv is not None) or "none (futures only)"
    return estimate_line(
        f"P&L now at {underlying} {format_points(estimate.level)}",
        format_approx_rupees(estimate.total),
        [
            f"{a.model} model",
            f"IV {ivs}",
            f"rate {_percent(a.rate)}",
            f"valued {a.valuation_time.strftime('%Y-%m-%d %H:%M %Z')}",
        ],
    )
