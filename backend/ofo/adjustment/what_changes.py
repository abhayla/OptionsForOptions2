"""D-21 (ADR-320 (3), GC-ICLIVE-C): the "What changes" block of every built approach, before against after.

An adjustment approach is never judged, flagged or hidden on max loss or max profit alone (a lower max profit and a
higher max loss can come with a wider profit range). Each approach shows eight measures, the position as it stands
against the position after the approach, each marked up, down or unchanged, with no verdict and no word such as
better or worse (ADR-003):

1. profit range (both breakevens and the width in points), 2. the distance from the index to each breakeven,
3. probability of profit, 4. max profit, 5. max loss, 6. the credit or debit of the adjustment, 7. margin,
8. net delta.

Nothing is worked out a second time. Measures 1, 3, 4, 5 and 8 read the Compare's own cells (``compare.Rows``) of the
before column and of the approach, so the block and the table can never differ; 6 reads the credit cell; 7 reads the
margin of each side; 2 is ``adjust_money.index_distance`` per breakeven of the whole-trade After (all after charges).
A measure that cannot be worked out on either side is "Not available" with that side's reason, never a filled default
(no position left after an exit -> no net delta, no range).

``reason_line``: one plain sentence, only where a number moves against the action's name (rule below), else None.
Rule by approach kind (the owner reads it, ``pending owner read``): Reduce and Close part (kind ``reduce`` /
``close_part``) are named for cutting exposure, so when max loss after is above max loss before the line says why:
closing legs of ONE side removes that side's credit, and when the other side then carries the larger loss at expiry
it is named; otherwise the plain "removes credit" line. Exit (kind ``exit``): max loss after (the loss it books,
after every charge) above max loss before gets the "books today's prices" line. Roll, Convert and No change carry no
reason line: their names promise no direction.

D-61 (ADR-320 point 5): for every approach whose resulting legs leave one (the buy-backs A-26, A-27 among them) the same line also carries the sentence naming a long
call or put left with no short of its type against it (``lone_long_line``, read from the approach's resulting legs).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from ofo.adjustment.approaches import PositionLeg
from ofo.adjustment.compare import INFINITE, Cell, Column, Context, MarginRead, Rows, pnl_at
from ofo.engine import adjust_money
from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.money import PAISE

MEASURES: tuple[str, ...] = ("profit_range", "breakeven_distance", "pop", "max_profit", "max_loss", "credit",
                             "margin", "net_delta")
UP, DOWN, SAME, NOT_AVAILABLE = "up", "down", "same", "not_available"
_DIRECTION_TEXT = {UP: "adjust_wc_dir_up", DOWN: "adjust_wc_dir_down", SAME: "adjust_wc_dir_same",
                   NOT_AVAILABLE: "adjust_wc_dir_na"}
_SIDE_WORD = {"PE": "put", "CE": "call"}


@dataclass(frozen=True)
class Side:
    """One side (before or after) of a measure: its text and a number to order by (``INFINITE``: unlimited), or the
    reason it is not available (then ``text`` and ``number`` are None)."""

    text: ExplanationText | None
    number: Decimal | None
    reason: ExplanationText | None = None


@dataclass(frozen=True)
class Row:
    id: str
    label: ExplanationText
    before_text: ExplanationText
    after_text: ExplanationText
    direction: str
    direction_text: ExplanationText
    unavailable_reason: ExplanationText | None


@dataclass(frozen=True)
class Block:
    title: ExplanationText
    rows: tuple[Row, ...]
    reason_line: ExplanationText | None


def _unknown() -> Side:
    return Side(None, None, render_explanation("adjust_wc_unknown"))


def _of_cell(cell: Cell) -> Side:
    """A Compare cell as a side: a "-" is not available with its reason; a figure with no number (unlimited, or a
    profit at every level) orders as infinite."""
    if cell.unavailable_reason is not None:
        return Side(None, None, cell.unavailable_reason)
    if cell.value is None and cell.text == render_explanation("adjust_cmp_dash"):
        return _unknown()
    if cell.value is not None:
        return Side(cell.text, cell.value)
    return Side(cell.text, INFINITE if cell.rank is None else cell.rank)  # an open side ranks below INFINITE


def _of_margin(read: MarginRead, before: bool) -> Side:
    if read.value is None:
        reason = read.reason or render_explanation("adjust_cmp_margin_before_unknown" if before
                                                   else "adjust_wc_unknown")
        return Side(None, None, reason)
    shown = read.value.quantize(PAISE, rounding=ROUND_HALF_EVEN)
    return Side(render_explanation("adjust_cmp_rupees", amount=shown), shown)


def _credit(value: Decimal) -> Side:
    if value > 0:
        return Side(render_explanation("adjust_wc_credit", amount=value), value)
    if value < 0:
        return Side(render_explanation("adjust_wc_debit", amount=-value), value)
    return Side(render_explanation("adjust_wc_no_trade"), Decimal(0))


def _join(first: ExplanationText, second: ExplanationText) -> ExplanationText:
    return render_explanation("adjust_wc_join", first=first, second=second)


def _distance_text(index: Decimal, level: Decimal) -> ExplanationText:
    away = adjust_money.index_distance(index, level)
    if away < 0:
        return render_explanation("adjust_wc_below", level=level, distance=-away)
    if away > 0:
        return render_explanation("adjust_wc_above", level=level, distance=away)
    return render_explanation("adjust_wc_at", level=level)


def _distances(col: Column, rows: Rows, index: Decimal) -> Side:
    """Measure 2: each breakeven's distance from the index; the nearest one orders the side (up = farther away)."""
    cell = rows.breakevens()
    if cell.unavailable_reason is not None:
        return Side(None, None, cell.unavailable_reason)
    levels = col.whole.after_charges.breakevens  # type: ignore[union-attr]  # a cell without a reason has a whole trade
    if not levels:
        return Side(None, None, render_explanation("adjust_wc_no_breakeven"))
    text = _distance_text(index, levels[0])
    for level in levels[1:]:
        text = _join(text, _distance_text(index, level))
    return Side(text, min(abs(adjust_money.index_distance(index, x)) for x in levels))


def _direction(before: Side, after: Side) -> str:
    if before.number is None or after.number is None:
        return NOT_AVAILABLE
    if after.number > before.number:
        return UP
    return DOWN if after.number < before.number else SAME


def _row(measure: str, before: Side, after: Side) -> Row:
    direction = _direction(before, after)
    na = render_explanation("adjust_wc_not_available")
    if before.reason is not None and before.reason == after.reason:
        reason: ExplanationText | None = render_explanation("adjust_wc_reason_both", reason=before.reason)
    else:
        reasons = [render_explanation(f"adjust_wc_reason_{name}", reason=side.reason)
                   for name, side in (("before", before), ("after", after)) if side.reason is not None]
        reason = None if not reasons else reasons[0] if len(reasons) == 1 else _join(reasons[0], reasons[1])
    return Row(measure, render_explanation(f"adjust_wc_row_{measure}"), before.text or na, after.text or na,
               direction, render_explanation(_DIRECTION_TEXT[direction]), reason)


def _loss_tail(col: Column, ctx: Context) -> str | None:
    """Which end of the payoff carries the larger loss after charges: "PE" (index falls to 0) or "CE" (index rises to
    twice the highest strike), by the engine's own P&L at each; None on a tie or without a whole trade."""
    if col.whole is None or not col.charges_known or not col.built.after:
        return None
    top = (max(x.strike for x in col.built.after) * 2).quantize(PAISE, rounding=ROUND_HALF_EVEN)
    low, high = (pnl_at(col.built.after, ctx.position.lot, col.whole, level) for level in (Decimal(0), top))
    if low == high:
        return None
    return "PE" if low < high else "CE"


def reason_line(col: Column, ctx: Context, before_col: Column, loss_before: Side,
                loss_after: Side) -> ExplanationText | None:
    """The module docstring's rule, by approach kind; None when no number moves against the action's name."""
    if loss_before.number is None or loss_after.number is None or loss_after.number <= loss_before.number:
        return None
    kind = col.built.kind
    if kind == "exit":
        return render_explanation("adjust_wc_reason_exit")
    if kind not in ("reduce", "close_part"):
        return None
    closed = {c.type for c in col.built.closed}
    tail = _loss_tail(col, ctx)
    # the side line says the other side "becomes" the largest loss: true only if before the closed side carried the
    # larger loss or the two ends tied (D-21 round 2); otherwise it already was, and the plain line stands
    was = _loss_tail(before_col, ctx)
    if len(closed) == 1 and tail is not None and tail not in closed and (was is None or was in closed):
        return render_explanation("adjust_wc_reason_side", closed=_SIDE_WORD[next(iter(closed))],
                                  remaining=_SIDE_WORD[tail])
    return render_explanation("adjust_wc_reason_credit")


def lone_long_line(after: Sequence[PositionLeg] | None) -> ExplanationText | None:
    """D-61 (ADR-320 point 5): one line when the legs that stay open hold a long call or put with no short of the same
    type against it, decided from the approach's own resulting legs; None when a short stays against each long, when
    nothing stays open (``()``) and when no after-state was built (``None``). One sentence per such type, call first."""
    if not after:
        return None
    shorts = {x.type for x in after if x.side == "SELL"}
    lines = [render_explanation("adjust_lone_long", kind=_SIDE_WORD[t]) for t in ("CE", "PE")
             if t not in shorts and any(x.side == "BUY" and x.type == t for x in after)]
    return render_explanation("adjust_wc_lines", first=lines[0], second=lines[1]) if len(lines) > 1 else next(
        iter(lines), None)


def _with_lone_long(col: Column, reason: ExplanationText | None) -> ExplanationText | None:
    """The reason line, then the D-61 line when the approach's resulting legs leave a long with no short (any approach)."""
    lone = lone_long_line(col.built.after)
    if lone is None or reason is None:
        return lone or reason
    return render_explanation("adjust_wc_lines", first=reason, second=lone)


def block(col: Column, ctx: Context, before_col: Column) -> Block:
    """The eight measures of one built approach against the position as it stands (``before_col``)."""
    b, a = Rows(before_col, ctx), Rows(col, ctx)
    loss_b, loss_a = _of_cell(b.max_loss()), _of_cell(a.max_loss())
    credit = a.credit()
    delta_b, delta_a = b.greeks(), a.greeks()
    rows = (
        _row("profit_range", _of_cell(b.breakevens()), _of_cell(a.breakevens())),
        _row("breakeven_distance", _distances(before_col, b, ctx.spot), _distances(col, a, ctx.spot)),
        _row("pop", _of_cell(b.pop()), _of_cell(a.pop())),
        _row("max_profit", _of_cell(b.max_profit()), _of_cell(a.max_profit())),
        _row("max_loss", loss_b, loss_a),
        _row("credit", _credit(Decimal(0)), _credit(credit.value if credit.value is not None else Decimal(0))),
        _row("margin", _of_margin(ctx.before_margin, True), _of_margin(col.margin, False)),
        _row("net_delta", _of_cell(delta_b if isinstance(delta_b, Cell) else delta_b["delta"]),
             _of_cell(delta_a if isinstance(delta_a, Cell) else delta_a["delta"])),
    )
    return Block(render_explanation("adjust_wc_title"), rows,
                 _with_lone_long(col, reason_line(col, ctx, before_col, loss_b, loss_a)))


def blocks(columns: Sequence[Column], ctx: Context, before_col: Column) -> Mapping[str, Block]:
    """One block per built approach (a refused approach is never a column: it states its refusal instead)."""
    return {c.built.id: block(c, ctx, before_col) for c in columns}


__all__ = ["MEASURES", "Block", "Row", "Side", "block", "blocks", "lone_long_line", "reason_line"]
