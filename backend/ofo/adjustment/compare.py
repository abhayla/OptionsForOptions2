"""Compare the adjustment approaches on named criteria (REQ-156 AC-1..AC-4, ADR-214 (2a); GC-ADJ1 row 13).

Each approach that was built (REQ-155 AC-8 refusals take no part) is one column, "No change" (A-36) first, then the
catalogue order of ``approaches.APPROACH_IDS`` (never sorted by how many rows it leads). Every row names its leader in
plain words; a tie names every leader; a value that cannot be computed is "-" with its reason and cannot lead; a row
no approach can compute names no leader. No overall winner, score or rank exists here (ADR-003).

Every number comes from the one engine (ADR-008): the whole-trade After (``whole_trade.whole_trade_after``) for max
loss, max profit, breakevens and POP; ``Strategy.expiry_pnl_at`` plus the booked shift less every charge line for the
spot moves and the payoff curves (no second formula); the charge calculator for the fresh trade. This module only
reads those answers, compares them and words them through the catalogue (``render_explanation``).

Definitions (technical calls of the GC-ADJ1 contract, "Found during the run" row 13):

- Credit or debit: the approach's own trades, SELL +, BUY -, at the planned prices (no trade: 0).
- Charges plus bid-ask cost: this adjustment's own charges plus half the bid-ask spread of each traded contract times
  its quantity (the cost of trading at bid or ask rather than mid). A traded row without a bid or an ask -> "-".
- Margin change: Zerodha's basket margin of the After minus that of the current legs; an After with no open leg needs
  0. Either side not stated -> "-" with that side's reason.
- Max loss, max profit, breakevens: the whole-trade After AFTER charges; charges unknown -> "-" with that reason.
  An unlimited max loss shows "Unlimited" and cannot lead "Smallest max loss"; an unlimited max profit leads
  "Highest max profit" (it is above every finite one).
- Spot moves: whole-trade at-expiry P&L after charges at spot x (1 + p), p = -2, -1, +1, +2 %, the level rounded
  half-even to the paisa (finding interpolated-level-finer-than-paise-refused: a derived level never carries more
  than 2 decimals into the engine).
- Breakevens: leader = the widest profit range: two or more breakevens -> upper minus lower; one -> its distance from
  spot; none -> 0 when the trade loses at every level, unlimited when it profits at every level.
- Premium still left to earn: over the After's open legs, short legs' current price x quantity minus long legs'
  (current price = the planned-price rule of ADR-068 (1)); a leg without a price -> "-".
- POP: the whole-trade After's POP; held switch OFF or unavailable -> "-" with the reason (the route's POP words).
- Greeks after: the After's open legs' per-unit engine Greeks (``leg_greeks``, by trading symbol) x signed quantity,
  summed unrounded then rounded once to 4 dp; theta per calendar day, vega per 1 vol point. A leg without Greeks ->
  "-". Leader: |delta| lowest, |gamma| lowest, theta highest, |vega| lowest.
- Adjustments used: the position's count, +1 when this approach trades; no plan maximum exists yet (playbooks are
  GC-ADJ2), so the text says so; leader = fewest.
- Strike liquidity: the widest (ask - bid) / mid in % among the contracts the approach OPENS; no new contract -> "-"
  (nothing to measure); a new contract without a bid or an ask -> "-". The low-OI warnings stay on the approach.
- Would you open this fresh: the After's open legs as a new trade at current prices (round-trip charges, no booked
  P&L): fresh max profit and fresh max loss; leader = smallest fresh max loss (unlimited cannot lead).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

from ofo.adjustment.approaches import (
    APPROACH_IDS,
    NO_CHANGE,
    ApproachLegs,
    ChainRow,
    Position,
    PositionLeg,
    planned_price,
)
from ofo.charges import ChargeRates
from ofo.charges.calculator import ChargeOrder, charges_for_orders
from ofo.charges.round_trip import charge_segment, to_paise_up
from ofo.engine import adjust_money
from ofo.engine.black_scholes import GREEK_STEP, Greeks
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import UNLIMITED
from ofo.engine.pop import Why
from ofo.engine.strategy import Strategy
from ofo.engine.whole_trade import WholeTradeAfter, whole_pnl_at, whole_trade_after
from ofo.errors.explanations import (
    ADJUSTMENT_CRITERION_LABEL_TEXT,
    ExplanationText,
    render_explanation,
)
from ofo.money import HUNDREDTH, PAISE

MONEY_NOW, RISK_AFTER, REWARD_AFTER, GREEKS_AFTER, PRACTICAL = (
    "money_now", "risk_after", "reward_after", "greeks_after", "practical")
HIGH, LOW, LOW_ABS = "high", "low", "low_abs"
#: (row id, group, leader direction), in REQ-156 AC-2's order; the shown words are the catalogue's
ROWS: tuple[tuple[str, str, str], ...] = (
    ("credit", MONEY_NOW, HIGH), ("cost", MONEY_NOW, LOW), ("margin_change", MONEY_NOW, LOW),
    ("max_loss", RISK_AFTER, LOW), ("move_m2", RISK_AFTER, HIGH), ("move_m1", RISK_AFTER, HIGH),
    ("move_p1", RISK_AFTER, HIGH), ("move_p2", RISK_AFTER, HIGH), ("breakevens", RISK_AFTER, HIGH),
    ("max_profit", REWARD_AFTER, HIGH), ("premium_left", REWARD_AFTER, HIGH), ("pop", REWARD_AFTER, HIGH),
    ("delta", GREEKS_AFTER, LOW_ABS), ("gamma", GREEKS_AFTER, LOW_ABS), ("theta", GREEKS_AFTER, HIGH),
    ("vega", GREEKS_AFTER, LOW_ABS),
    ("adjustments", PRACTICAL, LOW), ("liquidity", PRACTICAL, LOW), ("fresh", PRACTICAL, LOW),
)
MOVES: Mapping[str, int] = {"move_m2": -2, "move_m1": -1, "move_p1": 1, "move_p2": 2}  # spot moves, in percent
CURVE_RANGE = Decimal("0.06")  # the payoff curves span spot -6 % .. +6 %
CURVE_STEPS = 48  # the fixed step of the curve grid = the range / 48, plus every strike inside it
INFINITE = Decimal("Infinity")  # the rank of an unlimited figure in a "highest" row

#: POP's named reasons -> the catalogue's words (shared with the route, one home)
POP_TEXT: Mapping[Why, str] = {Why.NO_VOLATILITY: "adjust_pop_no_volatility", Why.NO_FORWARD: "adjust_pop_no_forward",
                               Why.MIXED_EXPIRIES: "adjust_pop_different_expiries",
                               Why.SPOT_STALE_OR_MISSING: "adjust_pop_spot_stale_or_missing"}

if tuple(r for r, _, _ in ROWS) != tuple(ADJUSTMENT_CRITERION_LABEL_TEXT):  # fail closed at import
    raise RuntimeError("compare ROWS and the catalogue's criterion rows differ")


@dataclass(frozen=True)
class MarginRead:
    """Zerodha's basket margin answer: ``value`` when stated (0 when nothing stays open), else ``reason``."""

    value: Decimal | None
    reason: ExplanationText | None = None


@dataclass(frozen=True)
class Column:
    """One built approach (no refusal) with its engine answers. ``whole`` None -> ``no_whole_reason`` says why."""

    built: ApproachLegs
    whole: WholeTradeAfter | None
    no_whole_reason: ExplanationText | None
    charges_known: bool
    margin: MarginRead


@dataclass(frozen=True)
class Context:
    position: Position
    spot: Decimal
    chain: Sequence[ChainRow]
    rates: ChargeRates | None
    pop_on: bool
    before_margin: MarginRead
    leg_greeks: Mapping[str, Greeks]  # trading symbol -> per-unit engine Greeks
    adjustments_used: int | None  # None: could not be read


@dataclass(frozen=True)
class Cell:
    text: ExplanationText
    value: Decimal | None = None
    unavailable_reason: ExplanationText | None = None
    rank: Decimal | None = None  # what the leader rule compares; None -> cannot lead


@dataclass(frozen=True)
class Criterion:
    id: str
    group: str
    label: ExplanationText
    leader_label: ExplanationText
    leaders: tuple[str, ...]
    values: Mapping[str, Cell]


@dataclass(frozen=True)
class Comparison:
    criteria: tuple[Criterion, ...]
    leads: Mapping[str, tuple[int, int]]  # approach id -> (rows it leads, rows with a leader)
    curves: Mapping[str, tuple[tuple[Decimal, Decimal], ...]]  # "before" / approach id -> (level, P&L after charges)


# ---- cells -------------------------------------------------------------------------------------------------------

def _dash(reason: ExplanationText | None) -> Cell:
    return Cell(render_explanation("adjust_cmp_dash"), None, reason, None)


def _rupees(value: Decimal, rank: Decimal | None = None) -> Cell:
    shown = value.quantize(PAISE, rounding=ROUND_HALF_EVEN)
    return Cell(render_explanation("adjust_cmp_rupees", amount=shown), shown, None, shown if rank is None else rank)


def _number(value: Decimal, rank: Decimal) -> Cell:
    return Cell(render_explanation("adjust_cmp_value", value=value), value, None, rank)


def leaders(cells: Mapping[str, Cell], direction: str) -> tuple[str, ...]:
    """REQ-156 AC-3: the column(s) whose rank is highest (HIGH) or lowest (LOW / LOW_ABS, the rank already absolute);
    a cell without a rank cannot lead; every tied column leads; no rankable cell -> no leader. Order = column order."""
    ranked = {k: c.rank for k, c in cells.items() if c.rank is not None}
    if not ranked:
        return ()
    target = max(ranked.values()) if direction == HIGH else min(ranked.values())
    return tuple(k for k in cells if k in ranked and ranked[k] == target)


# ---- engine reads ------------------------------------------------------------------------------------------------

def _strategy(legs: Sequence[PositionLeg], lot: int, price: Callable[[PositionLeg], Decimal] | None = None) -> Strategy:
    return Strategy(tuple(Leg(Action(x.side), Instrument(x.type), x.strike, x.expiry, x.lots * lot,
                              x.entry if price is None else price(x)) for x in legs))


def _pnl_at(legs: Sequence[PositionLeg], lot: int, whole: WholeTradeAfter, level: Decimal) -> Decimal:
    """The engine's whole-trade P&L after charges at ``level`` (``whole_trade.whole_pnl_at``)."""
    return whole_pnl_at(_strategy(legs, lot) if legs else None, whole, level)


def _move_level(spot: Decimal, percent: int) -> Decimal:
    return (spot * (100 + percent) / 100).quantize(PAISE, rounding=ROUND_HALF_EVEN)


class _Rows:
    """Every cell of one column."""

    def __init__(self, col: Column, ctx: Context) -> None:
        self.col, self.ctx, self.b = col, ctx, col.built
        self.lot = ctx.position.lot
        self.rows = {(r.expiry, r.type, r.strike): r for r in ctx.chain}

    def _row(self, leg: PositionLeg | object) -> ChainRow | None:
        return self.rows.get((leg.expiry, leg.type, leg.strike))  # type: ignore[attr-defined]

    def _after_reason(self) -> ExplanationText | None:
        """Why no after-charges figure exists (no whole trade, or charges unknown); None when it does."""
        if self.col.whole is None:
            return self.col.no_whole_reason
        if not self.col.charges_known:
            return render_explanation("adjust_charges_unknown")
        return None

    def credit(self) -> Cell:
        return _rupees(adjust_money.trade_credit((t.action, t.price, t.quantity) for t in self.b.trades))

    def cost(self) -> Cell:
        if not self.b.trades:
            return _rupees(Decimal(0))
        if self.col.whole is None or not self.col.charges_known:
            return _dash(self._after_reason())
        quotes = []
        for t in self.b.trades:
            row = self._row(t)
            if row is None or row.bid is None or row.ask is None or row.bid <= 0 or row.ask < row.bid:
                return _dash(render_explanation("adjust_cmp_no_bid_ask", leg=t.tradingsymbol))
            quotes.append((row.bid, row.ask, t.quantity))
        return _rupees(adjust_money.cost_with_spread(self.col.whole.adjustment_charges, quotes))

    def margin_change(self) -> Cell:
        before, after = self.ctx.before_margin, self.col.margin
        if after.value is None:
            return _dash(after.reason)
        if before.value is None:
            return _dash(render_explanation("adjust_cmp_margin_before_unknown"))
        return _rupees(adjust_money.margin_change(after.value, before.value))

    def max_loss(self) -> Cell:
        reason = self._after_reason()
        if reason is not None:
            return _dash(reason)
        loss = self.col.whole.after_charges.max_loss  # type: ignore[union-attr]
        if loss is UNLIMITED:
            return Cell(render_explanation("adjust_cmp_unlimited"))  # shown, cannot lead (AC-3, attack 4)
        return _rupees(loss)  # type: ignore[arg-type]

    def move(self, p: int) -> Cell:
        reason = self._after_reason()
        if reason is not None:
            return _dash(reason)
        return _rupees(_pnl_at(self.b.after, self.lot, self.col.whole, _move_level(self.ctx.spot, p)))  # type: ignore[arg-type]

    def breakevens(self) -> Cell:
        reason = self._after_reason()
        if reason is not None:
            return _dash(reason)
        f = self.col.whole.after_charges  # type: ignore[union-attr]
        levels = f.breakevens
        if not levels:
            if f.loss_regions:
                return Cell(render_explanation("adjust_cmp_no_breakeven_loss"), Decimal(0), None, Decimal(0))
            return Cell(render_explanation("adjust_cmp_no_breakeven_profit"), None, None, INFINITE)
        width = levels[-1] - levels[0] if len(levels) > 1 else abs(levels[0] - self.ctx.spot)
        text = render_explanation("adjust_cmp_breakevens", levels="/".join(format(x, "f") for x in levels),
                                  width=width)
        return Cell(text, width, None, width)

    def max_profit(self) -> Cell:
        reason = self._after_reason()
        if reason is not None:
            return _dash(reason)
        top = self.col.whole.after_charges.max_profit  # type: ignore[union-attr]
        if top is UNLIMITED:
            return Cell(render_explanation("adjust_cmp_unlimited"), None, None, INFINITE)
        return _rupees(top)  # type: ignore[arg-type]

    def premium_left(self) -> Cell:
        legs = []
        for x in self.b.after:
            price = planned_price(self._row(x))
            if price is None:
                return _dash(render_explanation("adjust_cmp_no_price", leg=x.tradingsymbol))
            legs.append((x.side, price, x.lots * self.lot))
        return _rupees(adjust_money.premium_left(legs))

    def pop(self) -> Cell:
        if not self.ctx.pop_on:
            return _dash(render_explanation("adjust_pop_held"))
        if self.col.whole is None:
            return _dash(self.col.no_whole_reason)
        if self.col.whole.pop is None:
            return _dash(render_explanation(POP_TEXT[self.col.whole.pop_unavailable or Why.NO_VOLATILITY]))
        pct = (self.col.whole.pop * 100).quantize(HUNDREDTH, rounding=ROUND_HALF_UP)
        return Cell(render_explanation("adjust_cmp_percent", value=pct), self.col.whole.pop, None, pct)

    def greeks(self) -> Mapping[str, Cell] | Cell:
        total = {"delta": Decimal(0), "gamma": Decimal(0), "theta": Decimal(0), "vega": Decimal(0)}
        for x in self.b.after:
            g = self.ctx.leg_greeks.get(x.tradingsymbol)
            if g is None:
                return _dash(render_explanation("adjust_cmp_no_greeks", leg=x.tradingsymbol))
            qty = x.lots * self.lot * (1 if x.side == "BUY" else -1)
            total["delta"] += g.delta * qty
            total["gamma"] += g.gamma * qty
            total["theta"] += g.theta * qty
            total["vega"] += g.vega * qty
        out = {}
        for name, v in total.items():
            shown = v.quantize(GREEK_STEP, rounding=ROUND_HALF_EVEN)
            out[name] = _number(shown, shown if name == "theta" else abs(shown))
        return out

    def adjustments(self) -> Cell:
        if self.ctx.adjustments_used is None:
            return _dash(render_explanation("adjust_cmp_adjustments_unknown"))
        used = self.ctx.adjustments_used + (1 if self.b.trades else 0)
        return Cell(render_explanation("adjust_cmp_adjustments", used=used), Decimal(used), None, Decimal(used))

    def liquidity(self) -> Cell:
        before = {(x.type, x.strike, x.expiry, x.side) for x in self.ctx.position.legs}
        new = [x for x in self.b.after if (x.type, x.strike, x.expiry, x.side) not in before]
        if not new:
            return _dash(render_explanation("adjust_cmp_no_new_leg"))
        widest = Decimal(0)
        unknown_oi: list[str] = []
        for x in new:
            row = self._row(x)
            if row is None or row.bid is None or row.ask is None or row.bid <= 0 or row.ask < row.bid:
                return _dash(render_explanation("adjust_cmp_no_bid_ask", leg=x.tradingsymbol))
            if row.low_oi_state != "stated":  # the builder's low-OI warning, carried into this cell too
                unknown_oi.append(x.tradingsymbol)
            mid = (row.bid + row.ask) / 2
            widest = max(widest, (row.ask - row.bid) / mid * 100)
        pct = widest.quantize(HUNDREDTH, rounding=ROUND_HALF_UP)
        text = render_explanation("adjust_cmp_low_oi", value=pct, legs=",".join(unknown_oi)) if unknown_oi else \
            render_explanation("adjust_cmp_percent", value=pct)
        return Cell(text, pct, None, pct)

    def fresh(self) -> Cell:
        legs = self.b.after
        if not legs:
            return _dash(render_explanation("adjust_cmp_nothing_open"))
        prices = {}
        for x in legs:
            price = planned_price(self._row(x))
            if price is None:
                return _dash(render_explanation("adjust_cmp_no_price", leg=x.tradingsymbol))
            prices[x.tradingsymbol] = price
        if self.ctx.rates is None:
            return _dash(render_explanation("adjust_charges_unknown"))
        segment = charge_segment(self.ctx.position.underlying)
        try:
            entry = to_paise_up(charges_for_orders([ChargeOrder(segment, x.side, x.lots * self.lot,
                                                                prices[x.tradingsymbol]) for x in legs],
                                                   self.ctx.rates).total)
            exits = to_paise_up(charges_for_orders([ChargeOrder(segment, "SELL" if x.side == "BUY" else "BUY",
                                                                x.lots * self.lot, prices[x.tradingsymbol])
                                                    for x in legs], self.ctx.rates).total)
            w = whole_trade_after(_strategy(legs, self.lot, lambda x: prices[x.tradingsymbol]), booked_pnl=Decimal(0),
                                  paid_charges=Decimal(0), adjustment_charges=entry, open_exit_charges=exits)
        except ValueError:  # MultiExpiryError is a ValueError; a rate the table cannot price
            return _dash(render_explanation("adjust_needs_one_expiry" if not _single(legs)
                                            else "adjust_charges_unknown"))
        top, loss = w.after_charges.max_profit, w.after_charges.max_loss

        def shown(v: object) -> ExplanationText:
            return render_explanation("adjust_cmp_unlimited") if v is UNLIMITED else \
                render_explanation("adjust_cmp_rupees", amount=v)

        rank = None if loss is UNLIMITED else loss
        return Cell(render_explanation("adjust_cmp_fresh", profit=shown(top), loss=shown(loss)), rank, None, rank)  # type: ignore[arg-type]


def _single(legs: Sequence[PositionLeg]) -> bool:
    return len({x.expiry for x in legs}) == 1


# ---- the comparison ------------------------------------------------------------------------------------------------

def column_order(ids: Sequence[str]) -> list[str]:
    """AC-4: "No change" first, then the catalogue order; never sorted by how many rows a column leads."""
    last = len(APPROACH_IDS)
    return sorted(ids, key=lambda a: (a != NO_CHANGE, APPROACH_IDS.index(a) if a in APPROACH_IDS else last))


def _curve_levels(ctx: Context, cols: Sequence[Column]) -> list[Decimal]:
    lo = (ctx.spot * (1 - CURVE_RANGE)).quantize(PAISE, rounding=ROUND_HALF_EVEN)
    hi = (ctx.spot * (1 + CURVE_RANGE)).quantize(PAISE, rounding=ROUND_HALF_EVEN)
    step = (hi - lo) / CURVE_STEPS
    grid = {(lo + step * k).quantize(PAISE, rounding=ROUND_HALF_EVEN) for k in range(CURVE_STEPS)} | {lo, hi}
    strikes = {x.strike for x in ctx.position.legs} | {x.strike for c in cols for x in c.built.after}
    return sorted(grid | {k for k in strikes if lo <= k <= hi})


def compare(columns: Sequence[Column], ctx: Context, before: WholeTradeAfter | None = None,
            before_charges_known: bool = False) -> Comparison:
    """The criteria rows, each column's leads and the payoff curves of the built approaches (refused ones are never
    passed in: AC-1). ``before`` = the current legs' whole-trade answer, for the Before curve only."""
    ids = [c.built.id for c in columns]
    if len(set(ids)) != len(ids):
        raise ValueError(f"an approach appears twice in the compare: {ids}")
    if any(c.built.refusal is not None for c in columns):
        raise ValueError("a refused approach takes no part in the criteria (REQ-156 AC-1)")
    by_id = {c.built.id: c for c in columns}
    order = column_order(ids)
    cells: dict[str, dict[str, Cell]] = {r: {} for r, _, _ in ROWS}
    for a in order:
        r = _Rows(by_id[a], ctx)
        cells["credit"][a], cells["cost"][a], cells["margin_change"][a] = r.credit(), r.cost(), r.margin_change()
        cells["max_loss"][a] = r.max_loss()
        for row, p in MOVES.items():
            cells[row][a] = r.move(p)
        cells["breakevens"][a], cells["max_profit"][a] = r.breakevens(), r.max_profit()
        cells["premium_left"][a], cells["pop"][a] = r.premium_left(), r.pop()
        g = r.greeks()
        for name in ("delta", "gamma", "theta", "vega"):
            cells[name][a] = g if isinstance(g, Cell) else g[name]
        cells["adjustments"][a], cells["liquidity"][a], cells["fresh"][a] = r.adjustments(), r.liquidity(), r.fresh()
    criteria = tuple(Criterion(row, group, render_explanation(f"adjust_cmp_row_{row}"),
                               render_explanation(f"adjust_cmp_lead_{row}"), leaders(cells[row], direction),
                               cells[row]) for row, group, direction in ROWS)
    m = sum(1 for c in criteria if c.leaders)
    leads = {a: (sum(1 for c in criteria if a in c.leaders), m) for a in order}
    return Comparison(criteria, leads, _curves(columns, ctx, before, before_charges_known))


def _curves(columns: Sequence[Column], ctx: Context, before: WholeTradeAfter | None,
            before_charges_known: bool) -> dict[str, tuple[tuple[Decimal, Decimal], ...]]:
    """At-expiry whole-trade P&L after charges on one grid; a column with no after-charges figure has no curve."""
    levels = _curve_levels(ctx, columns)
    out: dict[str, tuple[tuple[Decimal, Decimal], ...]] = {}
    if before is not None and before_charges_known:
        out["before"] = tuple((k, _pnl_at(ctx.position.legs, ctx.position.lot, before, k)) for k in levels)
    for c in columns:
        if c.whole is not None and c.charges_known:
            out[c.built.id] = tuple((k, _pnl_at(c.built.after, ctx.position.lot, c.whole, k)) for k in levels)
    return out


__all__ = ["POP_TEXT", "Cell", "Column", "Comparison", "Context", "Criterion", "MarginRead", "column_order", "compare",
           "leaders"]
