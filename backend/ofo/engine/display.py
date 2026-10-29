# ruff: noqa: RUF002
"""Display formatting without false precision (REQ-032 AC-5; ADR-008 Q15; scenario-calculations.md §5).

- Exact money shows to the paisa with Indian digit grouping: ``₹17,19,000.00``; a loss uses the minus sign
  U+2212 as the spec writes it: ``−₹322.50``.
- Index levels are points, never rupees: ``23,047.35``.
- An estimate is approximate and says so: ``~73%``, ``~₹1,235`` (whole rupees; never ``73.48291%``), and a line that
  shows one is labelled "Estimated" and lists its assumptions. An estimate without assumptions is refused.

Rounding is half-even throughout (to the paisa for money, to the whole unit for estimates).
"""
from __future__ import annotations
from ofo.errors.explanations import render_explanation

from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from typing import Final, Sequence

from ofo.engine.estimate import EstimatedNow
from ofo.money import PAISE as _PAISA

MINUS: Final = "−"
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


_LAKH: Final = 100_000
_CRORE: Final = 10_000_000
_LAKHS_IN_A_CRORE: Final = 100 * 10  # 100.0L at one decimal: shown as crore from here


def _in_unit(count: int, unit: int, places: int) -> tuple[int, str]:
    """``count / unit`` rounded half-up to ``places`` decimals, integer arithmetic only (no float at a .5 edge)."""
    scale = 10 ** places
    rounded = (count * scale * 2 + unit) // (unit * 2)
    return rounded, f"{rounded // scale}.{str(rounded % scale).zfill(places)}"


def format_oi_compact(count: int) -> str:
    """GC-UI D-B16 (the strike drawer's compact form, S-032): an open interest is a CONTRACT COUNT, not money, in Indian
    units: "1.23Cr" from 1,00,00,000, "74.9L" from 1,00,000, Indian grouping ("62,075") below; a real 0 is "0"."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"an open interest must be a whole count of 0 or more, got {count!r}")
    lakh_rounded, lakh_text = _in_unit(count, _LAKH, 1)
    if count >= _CRORE or (count >= _LAKH and lakh_rounded >= _LAKHS_IN_A_CRORE):
        return f"{_in_unit(count, _CRORE, 2)[1]}Cr"
    if count >= _LAKH:
        return f"{lakh_text}L"
    return _group_indian(str(count))


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


def format_index_level(level: Decimal) -> str:
    """An index or trigger level with Indian grouping and ALWAYS two decimals (no currency): ``22,850.00``,
    ``22,976.80``. The same grouping and half-even rounding as :func:`format_points`; the paper stop texts use it."""
    sign, text = _number(_finite(level, "level"), _PAISA)
    return f"{sign}{text}"


def format_whole_rupees(amount: Decimal, *, signed: bool) -> str:
    """REQ-152 AC-1/AC-3/AC-4: a summary money figure in whole rupees, Indian grouping, rounded HALF-UP from the exact
    Decimal (6025.50 -> ``+6,026``; a loss rounds on its magnitude, -104.50 -> ``−105``). ``signed``: a plus on
    a positive figure, U+2212 on a negative one; unsigned shows the magnitude only. A figure that rounds to zero is
    ``0`` with no sign. Display only: the exact Decimal stays in the reply."""
    value = _finite(amount, "amount")
    whole = abs(value).quantize(_WHOLE, rounding=ROUND_HALF_UP)
    if whole == 0:
        return "0"
    mark = (MINUS if value < 0 else "+") if signed else ""
    return mark + _group_indian(f"{whole:f}")


def format_signed_paisa(amount: Decimal) -> str:
    """GC-UI D-B48 / REQ-109 AC-2: a paper P&L figure to the paisa with Indian grouping, "+" on a profit, U+2212 on a
    loss (``+5,053.75``, ``−3,285.75``); a figure that rounds to zero is ``0.00`` with no sign. Display only."""
    sign, text = _number(_finite(amount, "amount"), _PAISA)
    if text == "0.00":
        return text
    return (sign or "+") + text


def format_whole_points(level: Decimal) -> str:
    """REQ-152 / D-A04: an index level in whole points with Indian grouping, half-up: ``22,688``."""
    return _group_indian(f"{_finite(level, 'level').quantize(_WHOLE, rounding=ROUND_HALF_UP):f}")


def breakeven_percent_exact(level: Decimal, spot: Decimal | None) -> Decimal | None:
    """REQ-153 AC-1: (level - spot) / spot x 100, NOT rounded, so a percent that rounds to 0.0 keeps its sign (F-4);
    None when there is no usable spot (None or not above 0), so the caller shows the level alone."""
    value = _finite(level, "level")
    if spot is None or _finite(spot, "spot") <= 0:
        return None
    return (value - spot) / spot * 100


def breakeven_percent(level: Decimal, spot: Decimal | None) -> Decimal | None:
    """The breakeven percent to one decimal, half-up (None when there is no usable spot)."""
    exact = breakeven_percent_exact(level, spot)
    return None if exact is None else exact.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def format_signed_percent(percent: Decimal) -> str:
    """A percent with one decimal and a sign: ``+0.9``, ``−0.1``. Only a true zero is ``0.0`` with no sign; a non-zero
    figure that rounds to 0.0 keeps its sign, ``−0.0`` / ``+0.0`` (REQ-153 AC-1, F-4). Pass the UNROUNDED figure."""
    raw = _finite(percent, "percent")
    value = raw.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if raw == 0:
        return f"{0:.1f}"
    return f"{MINUS if raw < 0 else '+'}{abs(value)}"


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
    return render_explanation("estimate_line", label=label, value=value, assumptions="; ".join(stated))


def describe_estimate(estimate: EstimatedNow, underlying: str) -> str:
    """The labelled Estimated Now line for one level, with the model, IVs, rate and valuation time it assumes."""
    if not isinstance(estimate, EstimatedNow):
        raise ValueError(f"estimate must be an EstimatedNow, got {estimate!r}")
    a = estimate.assumptions
    ivs = ", ".join(_percent(iv) for iv in a.ivs if iv is not None) or render_explanation("estimate_ivs_none")
    return estimate_line(
        render_explanation("estimate_label_pnl_now", underlying=underlying, level=format_points(estimate.level)),
        format_approx_rupees(estimate.total),
        [
            render_explanation("estimate_assume_model", model=a.model),
            render_explanation("estimate_assume_iv", ivs=ivs),
            render_explanation("estimate_assume_rate", rate=_percent(a.rate)),
            render_explanation("estimate_assume_valued", time=a.valuation_time.strftime("%Y-%m-%d %H:%M %Z")),
        ],
    )
