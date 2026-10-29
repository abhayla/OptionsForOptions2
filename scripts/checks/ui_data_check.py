# ruff: noqa: PLR0913, PLR2004, C901, PLR0912, PLR0915 - textbook BSM signatures (S, K, T, r, q, sigma, kind);
# check_outcome is one long figure list on purpose (each block is one reply section), split in round 2 if asked
"""Independent UI data checker (GC-UI step 1): re-derives every number the builder's outcome reply and the paper
tracking reply show, from the same market inputs, with its OWN formulas, and names each figure that differs.

README (read first)
-------------------
Spec basis: spec/business-rules/scenario-calculations.md sections 1-5; ADR-061 (parity forward / implied q), ADR-063
(BSM with q, theta per day), ADR-082 (2) + ADR-167 (scenario values before charges, max profit / loss include the
round-trip charges), ADR-172 (IV from the bid-ask mid when two-sided, else the LTP).

Independence: this file imports nothing from `ofo` or `ofo_app` (a test parses it and fails on such an import). Its
inputs are DATA only: the reply itself, the option chain (bid/ask) captured around it, the risk-free rate (the
configured value 0.065 read from backend/ofo_app/live_market.py LIVE_RATE, passed in as a number) and the published
charge-rate table (the 2026-10-15 seed rows of migration 0012, copied here as data).

Known bypasses (not chased; the threat model is "one altered figure in the reply"):
- A wrong MARKET input that both sides share (spot, a leg's LTP, bid/ask, funds, the broker's margin figure) is not
  detected: the checker takes it from the reply. That is the market data's own check.
- Estimated-Now figures are priced with the reply's own per-leg IV (after checking that IV against our own solve), so
  an IV that is wrong by less than the IV tolerance passes through to the model figures.
- The implied q comes from a chain captured a second or two before the reply, not the server's own snapshot; the model
  tolerance is widened by the measured q movement between the chain captured before and after the reply.
- GC-UI step 4 (`--both`): the SD block takes the reply's ATM IV and spot (market inputs) and re-derives the horizon,
  the moves, percents, levels, bands and texts itself; the Estimated Now curve is compared with the Estimated Now
  single-view points (re-priced by this file's BSM) and the payoff table's Estimated Now cells are re-priced the same
  way; the At Expiry curve and cells are the closed-form payoff. Mixed expiries: the At Expiry figures are not checked.
- Charge rates are the seed table; an admin rate row added later is not seen (the reply's `rates_read_on` is checked
  against the seed date and flagged when it differs).

CLI: python scripts/checks/ui_data_check.py --strategy-legs <legs.json> [--paper <id>] [--replay <dir>] --out <dir>
     python scripts/checks/ui_data_check.py --strategy-legs <legs.json> --target-level <L> --target-at <ISO>
     [--booked <rs>] --out <dir>   (GC-TP 6c: what-if target P&L, breakevens, Greeks)
     python scripts/checks/ui_data_check.py --paper-orders <id> [--replay <dir>] --out <dir>   (GC-TP 1b: net quantity,
     average, booked, unbooked and total recomputed from the orderbook rows of GET /paper/strategies/{id})
Live mode (no --replay) fetches the replies from the running API (read-only GETs + POST outcome; never an order route).
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from decimal import ROUND_FLOOR, ROUND_HALF_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_UP, Decimal
from fractions import Fraction
from pathlib import Path

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
RISK_FREE_RATE = 0.065  # configured input: backend/ofo_app/live_market.py LIVE_RATE (read, not imported)
PAISA = Decimal("0.01")
# Published Zerodha F&O options rates, seed of migration 0012 (read on 2026-10-15; F-35). Data, not engine code.
CHARGE_RATES = {
    "read_on": "2026-10-15",
    "brokerage_per_order": Decimal("20"),
    "stt_sell_rate": Decimal("0.0015"),
    "stt_exercise_rate": Decimal("0.0015"),
    "transaction_rate_nse_fo": Decimal("0.0003553"),
    "transaction_rate_bse_fo": Decimal("0.000325"),  # migration 0012: "BSE 0.0325% of premium" (SENSEX options)
    "sebi_rate": Decimal("0.000001"),
    "stamp_buy_rate": Decimal("0.00003"),
    "gst_rate": Decimal("0.18"),
}
MIN_PARITY_STRIKES = 3  # ADR-061: fewer than 3 two-sided strikes -> spot fallback

MATCH, MISMATCH, NOT_CHECKABLE = "match", "mismatch", "not checkable"


# ---------------------------------------------------------------- figures


@dataclass
class Figure:
    name: str
    ours: object
    independent: object
    tolerance: object = 0
    verdict: str = ""
    abs_diff: object = None
    note: str = ""


@dataclass
class Report:
    strategy: str
    figures: list = field(default_factory=list)
    data_rows: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    def add(self, name, ours, independent, tol=Decimal("0"), note="", alt=None, alt_label=""):
        """Compare one figure. A missing value on either side is never a match. `alt` is a second basis: it never
        turns a mismatch into a match, it only names the basis the reply's figure does equal."""
        fig = self._compare(name, ours, independent, tol, note)
        if fig.verdict == MISMATCH and alt is not None:
            try:
                if abs(Decimal(str(ours)) - Decimal(str(alt))) <= Decimal(str(tol)):
                    fig.note = (fig.note + "; " if fig.note else "") + f"reply equals the {alt_label} basis ({alt})"
            except ArithmeticError:
                pass
        return fig

    def _compare(self, name, ours, independent, tol, note):
        fig = Figure(name, _s(ours), _s(independent), _s(tol), note=note)
        if ours is None:
            fig.verdict = NOT_CHECKABLE
            fig.note = (note + "; " if note else "") + "reply gives no value"
        elif independent is None:
            fig.verdict = NOT_CHECKABLE
            fig.note = note or "no independent value"
        else:
            try:
                a, b = Decimal(str(ours)), Decimal(str(independent))
            except ArithmeticError:
                fig.verdict = MATCH if str(ours) == str(independent) else MISMATCH
            else:
                diff = abs(a - b)
                fig.abs_diff = str(diff)
                fig.verdict = MATCH if diff <= Decimal(str(tol)) else MISMATCH
        self.figures.append(fig)
        return fig

    def add_list(self, name, ours, independent, tol=Decimal("0"), note=""):
        """Numeric list compare: same length and every element within tol."""
        if ours is None or independent is None:
            return self.add(
                name, None if ours is None else str(ours), None if independent is None else str(independent)
            )
        a, b = [Decimal(str(x)) for x in ours], [Decimal(str(x)) for x in independent]
        ok = len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))
        fig = Figure(name, [str(x) for x in a], [str(x) for x in b], str(tol), MATCH if ok else MISMATCH, note=note)
        if len(a) == len(b) and a:
            fig.abs_diff = str(max(abs(x - y) for x, y in zip(a, b, strict=True)))
        self.figures.append(fig)
        return fig

    def skip(self, name, reason, ours=None):
        self.figures.append(Figure(name, _s(ours), None, None, NOT_CHECKABLE, note=reason))

    def counts(self):
        c = {MATCH: 0, MISMATCH: 0, NOT_CHECKABLE: 0}
        for f in self.figures:
            c[f.verdict] += 1
        return c


def _s(v):
    if v is None or isinstance(v, (str, bool, int, list)):
        return v
    return str(v)


def D(v) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def money(v, mode=ROUND_HALF_UP) -> Decimal:
    return Decimal(str(v)).quantize(PAISA, rounding=mode)


# ---------------------------------------------------------------- display strings (this checker's OWN formatting)

MINUS_SIGN = "\N{MINUS SIGN}"  # the server's minus on summary money and breakevens (REQ-152)
DASH = "—"  # what a cell prints for "no value"


def _indian(whole: str) -> str:
    """Indian grouping of a digit string: last three digits, then pairs ("1,89,000")."""
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join([*groups, tail])


def display_whole(value: Decimal, signed: bool) -> str:
    """REQ-152 AC-1..AC-4: whole rupees, half-up on the magnitude, Indian grouping; signed: plus on a profit, U+2212 on
    a loss; a figure that rounds to zero is "0" with no sign."""
    whole = abs(value).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    if whole == 0:
        return "0"
    mark = (MINUS_SIGN if value < 0 else "+") if signed else ""
    return mark + _indian(f"{whole:f}")


def display_breakeven(level: Decimal, spot: Decimal | None) -> str:
    """REQ-153 AC-1: the level in whole points with its signed percent from spot to one decimal ("22,688 (-0.1%)");
    a non-zero percent that rounds to 0.0 keeps its sign ("22,688 (-0.0%)", F-4); only a TRUE zero is "0.0" with no
    sign (REQ-152 AC-4); no usable spot: the level alone."""
    text = _indian(f"{level.quantize(Decimal(1), rounding=ROUND_HALF_UP):f}")
    if spot is None or spot <= 0:
        return text
    raw = (level - spot) / spot * 100
    pct = raw.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    shown = "0.0" if raw == 0 else (MINUS_SIGN if raw < 0 else "+") + f"{abs(pct):f}"
    return f"{text} ({shown}%)"


GREEK_PLACES = {"delta": 2, "gamma": 4, "theta": 2, "vega": 2}


def display_cell(kind: str, value: Decimal, half_down: bool = False) -> str:
    """REQ-145 AC-3 / GC-UI round 2b: IV as a percent with two decimals ("0.183667" -> "18.37%"); delta, theta, vega
    2 dp, gamma 4 dp, half-up (`half_down`: the other neighbour of an exact half step); never "-0.00"."""
    mode = ROUND_HALF_DOWN if half_down else ROUND_HALF_UP
    if kind == "iv":
        return f"{_plain((value * 100).quantize(Decimal('0.01'), rounding=mode))}%"
    return _plain(value.quantize(Decimal(1).scaleb(-GREEK_PLACES[kind]), rounding=mode))


def _plain(q: Decimal) -> str:
    return f"{abs(q):f}" if q == 0 else f"{q:f}"


def _is_half_step(value: Decimal, places: int) -> bool:
    """True when `value` lies exactly on the half step of `places` decimals. The server rounds the position figure
    from its unrounded value and the reply carries it at 4 dp, so a 4 dp tie may have been rounded either way."""
    scaled = abs(value) * Decimal(10) ** places
    return scaled - scaled.to_integral_value(rounding=ROUND_FLOOR) == Decimal("0.5")


def check_text(rep, name, shown, exact, expected, also=()):
    """One display string against its exact figure: exact text, tolerance 0. Answer states: text present and equal;
    both null (a dash counts as null) = match; null text while the exact exists = mismatch (missing text); a text
    while there is no exact = mismatch. `also`: other texts accepted for an exact half step."""
    fig = Figure(name, shown, expected)
    if exact is None:
        fig.verdict = MATCH if shown in (None, DASH) else MISMATCH
        fig.note = "" if fig.verdict == MATCH else "text shown where the reply has no exact figure"
    elif shown is None:
        fig.verdict, fig.note = MISMATCH, "missing text: the exact figure exists but its display is null"
    else:
        fig.verdict = MATCH if shown == expected or shown in also else MISMATCH
        if fig.verdict == MATCH and shown != expected:
            fig.note = "exact half step at the 4 dp print: either rounding accepted"
    rep.figures.append(fig)
    return fig


def check_displays(rep, view, reply) -> int:
    """Every server display string of an outcome reply against its exact figure, formatted by this file's own rules.
    Returns the figures added."""
    n0 = len(rep.figures)
    s, m = reply.get("summary"), reply.get("margin")
    if s is not None:
        for key, base, signed, neg in (
            ("max_profit_display", "max_profit", True, False),
            ("max_loss_display", "max_loss", True, True),
            ("time_value_display", "time_value", True, False),
            ("intrinsic_value_display", "intrinsic_value", True, False),
        ):
            ex = D(s.get(base))
            exp = None if ex is None else display_whole(-ex if neg else ex, signed)
            check_text(rep, f"[{view}] summary.{key}", s.get(key), ex, exp)
        bes, shown = s.get("breakevens") or [], s.get("breakevens_display") or []
        spot = D(reply.get("spot_level"))
        for i in range(max(len(bes), len(shown))):
            ex = D(bes[i]) if i < len(bes) else None
            exp = None if ex is None else display_breakeven(ex, spot)
            check_text(rep, f"[{view}] summary.breakevens_display[{i}]", shown[i] if i < len(shown) else None, ex, exp)
        np_ = s.get("net_premium")
        if np_ is not None:
            ex = D(np_.get("amount"))
            check_text(
                rep,
                f"[{view}] summary.net_premium.amount_display",
                np_.get("amount_display"),
                ex,
                None if ex is None else display_whole(ex, False),
            )
    if m is not None:
        for base in ("needed", "broker_needed", "available"):
            ex = D(m.get(base))
            check_text(
                rep,
                f"[{view}] margin.{base}_display",
                m.get(f"{base}_display"),
                ex,
                None if ex is None else display_whole(ex, False),
            )
    for row in (reply.get("table") or {}).get("rows") or []:
        who = "TOTAL" if row.get("row_id") == "TOTAL" else f"leg{row.get('row_id')}"
        for kind in ("iv", *GREEK_KEYS):
            cell = (row.get("cells") or {}).get(kind)
            if cell is None:
                continue
            for field_, shown_key in (("value", "display"), ("per_unit", "per_unit_display")):
                if field_ == "per_unit" and kind == "iv":
                    continue
                ex = D(cell.get(field_))
                places = GREEK_PLACES.get(kind, 4)
                tie = kind != "iv" and ex is not None and places < 4 and _is_half_step(ex, places)
                check_text(
                    rep,
                    f"[{view}] {who} {kind} {shown_key}",
                    cell.get(shown_key),
                    ex,
                    None if ex is None else display_cell(kind, ex),
                    also=(display_cell(kind, ex, half_down=True),) if tie else (),
                )
    return len(rep.figures) - n0


# ---------------------------------------------------------------- GC-UI step 4: second curve, payoff table, SD block

#: REQ-137 AC-1 (read as text, not imported): the payoff table's intervals, and with none picked "default the
#: underlying's strike step: NIFTY 50, SENSEX 100" (not the scenario grid's Admin step)
PAYOFF_STEPS = (Decimal(10), Decimal(25), Decimal(50), Decimal(100))
STRIKE_STEP = {"NIFTY": Decimal(50), "SENSEX": Decimal(100)}
SD_HORIZON_DAYS = 7  # D-B20 Fixed SD: a 7-day horizon, the days to the nearest expiry when fewer
TENTH = Decimal("0.1")


def display_rupees(value: Decimal) -> str:
    """A payoff-table / curve cell: rupees to the paisa, Indian grouping, U+2212 on a loss ("−₹4,056.00")."""  # noqa: RUF002 - user text
    q = abs(value).quantize(PAISA, rounding=ROUND_HALF_UP)
    whole, frac = f"{q:f}".split(".")
    return (MINUS_SIGN if value < 0 and q != 0 else "") + "₹" + _indian(whole) + "." + frac


def display_points(level: Decimal) -> str:
    """A payoff-table level: whole index points, Indian grouping ("21,500")."""
    return _indian(f"{level.quantize(Decimal(1), rounding=ROUND_HALF_UP):f}")


def sd_rows(spot: Decimal, iv: Decimal, days: int) -> list[dict]:
    """scenario-calculations section 4 written out: 1 SD = spot x IV x sqrt(days / 365) (calendar days); 2 SD = twice
    it; percent of spot; the levels spot -/+ the move; each half-up to 0.1 from the exact figure."""
    one = spot * iv * (Decimal(days) / Decimal(365)).sqrt()
    rows = []
    for n in (1, 2):
        m = one * n
        rows.append({"sd": n, "move": m.quantize(TENTH, ROUND_HALF_UP),
                     "percent": (m / spot * 100).quantize(TENTH, ROUND_HALF_UP),
                     "lower": (spot - m).quantize(TENTH, ROUND_HALF_UP),
                     "upper": (spot + m).quantize(TENTH, ROUND_HALF_UP)})
    return rows


def sd_horizon(valuation: dt.datetime, expiries) -> int:
    """Calendar days from the valuation date in India to the nearest expiry, at least 1, at most the 7-day horizon."""
    near = min(dt.date.fromisoformat(e) for e in expiries)
    return min(max((near - valuation.astimezone(IST).date()).days, 1), SD_HORIZON_DAYS)


def table_levels(start: Decimal, end: Decimal, step: Decimal) -> list[Decimal]:
    """The payoff table's levels: every multiple of `step` from the first at or above the range start to the end."""
    first = -((-start) // step) * step  # ceiling to a multiple
    out, lvl = [], first
    while lvl <= end:
        out.append(lvl)
        lvl += step
    return out


def check_curves(rep, both, est, atx, legs, single_expiry) -> None:
    """REQ-083 AC-1: the two curves sit on the same levels; At Expiry is the closed-form payoff (single expiry) and
    equals the At Expiry single-view reply's points; Estimated Now equals the Estimated Now single-view points (which
    this file re-prices with its own BSM in check_outcome)."""
    curves = both.get("curves")
    if not curves:
        rep.skip("[both] curves", "reply has no curves block")
        return
    ax, en = curves.get("at_expiry") or {}, curves.get("estimated_now") or {}
    lx = [p["level"] for p in ax.get("points") or []]
    le = [p["level"] for p in en.get("points") or []]
    if ax.get("available") and en.get("available"):
        rep.add("[both] curves on the same levels", str(le), str(lx))
    for key, single in (("at_expiry", atx), ("estimated_now", est)):
        cur = curves.get(key) or {}
        if not cur.get("available"):
            rep.skip(f"[both] curves.{key}", f"unavailable: {cur.get('unavailable_reason')!r}")
            continue
        mine = [(p["level"], p["pnl"]) for p in cur.get("points") or []]
        sv = [(p["level"], p["pnl"]) for p in ((single or {}).get("payoff") or {}).get("points") or []]
        rep.add(f"[both] curves.{key} = the {key} single-view points", str(mine), str(sv) if sv else None)
        for p in cur.get("points") or []:
            check_text(rep, f"[both] curves.{key} display @{p['level']}", p.get("display"), D(p.get("pnl")),
                       display_rupees(D(p["pnl"])))
    if single_expiry and ax.get("available"):
        for p in ax.get("points") or []:
            rep.add(f"[both] curves.at_expiry @{p['level']}", p.get("pnl"), money(payoff(legs, D(p["level"]))))


def check_payoff_table(rep, both, legs, single_expiry, step_asked) -> list:
    """REQ-137 AC-1: rows at the picked interval (absent: the strike step), both columns, nearest-spot row, displays.
    Returns the (level, Estimated Now pnl) pairs for the model check."""
    t = both.get("payoff_table")
    if t is None:
        rep.skip("[both] payoff_table", "reply has no payoff_table block")
        return []
    step = Decimal(step_asked) if step_asked is not None else STRIKE_STEP.get(both.get("underlying"))
    rep.add("[both] payoff_table step (asked, else the strike step)", t.get("step"), step)
    sc = both.get("scenario") or {}
    start, end = D(sc.get("start")), D(sc.get("end"))
    levels = [D(r["level"]) for r in t.get("rows") or []]
    if start is None or end is None or step is None:
        rep.skip("[both] payoff_table levels", "reply scenario has no range")
    else:
        rep.add_list("[both] payoff_table levels", levels, table_levels(start, end, step))
    spot = D(both.get("spot_level"))
    near = None if spot is None or not levels else min(levels, key=lambda x: (abs(x - spot), x))
    rep.add("[both] payoff_table nearest_spot row", str([D(r["level"]) for r in t["rows"] if r.get("nearest_spot")]),
            str([near] if near is not None else []))
    cols = {c["view"]: c for c in t.get("columns") or []}
    est_pts = []
    for r in t.get("rows") or []:
        lvl = D(r["level"])
        check_text(rep, f"[both] payoff_table level_display @{r['level']}", r.get("level_display"), lvl,
                   display_points(lvl))
        for key in ("at_expiry", "estimated_now"):
            cell, col = r.get(key), cols.get(key) or {}
            if not col.get("available"):
                rep.add(f"[both] payoff_table {key} @{r['level']} empty (column unavailable)",
                        "null" if cell is None else "value", "null")
                continue
            if cell is None:
                rep.add(f"[both] payoff_table {key} @{r['level']}", None, "a value")
                continue
            check_text(rep, f"[both] payoff_table {key} display @{r['level']}", cell.get("display"), D(cell["pnl"]),
                       display_rupees(D(cell["pnl"])))
            if key == "at_expiry" and single_expiry:
                rep.add(f"[both] payoff_table at_expiry @{r['level']}", cell["pnl"], money(payoff(legs, lvl)))
            if key == "estimated_now":
                est_pts.append({"level": r["level"], "pnl": cell["pnl"]})
    return est_pts


def check_sd(rep, both, legs, valuation) -> None:
    """REQ-083 AC-4 / REQ-137 AC-3: the SD table and the four bands from this file's own formula (section 4) on the
    fixed horizon, with the reply's spot and ATM IV (market inputs, known bypass); displays from this file's rules."""
    sd = both.get("standard_deviation")
    if sd is None:
        rep.skip("[both] standard_deviation", "reply has no standard_deviation block")
        return
    spot, iv = D(sd.get("spot")), D(sd.get("iv"))
    if not sd.get("available"):
        rep.add("[both] standard_deviation unavailable has a reason and no rows",
                str((sd.get("reason") is not None, sd.get("rows"), sd.get("bands"))), str((True, [], [])))
        return
    days = sd_horizon(valuation, sorted({leg["expiry"] for leg in legs}))
    rep.add("[both] standard_deviation horizon_days", sd.get("horizon_days"), days)
    rep.add("[both] standard_deviation spot = reply spot", sd.get("spot"), both.get("spot_level"))
    if spot is None or iv is None:
        rep.skip("[both] standard_deviation rows", "available but no spot or IV in the block")
        return
    want = sd_rows(spot, iv, days)
    rows = sd.get("rows") or []
    rep.add("[both] standard_deviation row count", len(rows), len(want))
    for got, w in zip(rows, want, strict=False):
        n = w["sd"]
        for k in ("move", "percent", "lower", "upper"):
            rep.add(f"[both] SD {n} {k}", got.get(k), w[k])
        check_text(rep, f"[both] SD {n} label", got.get("label"), n, f"{n}SD")
        check_text(rep, f"[both] SD {n} move_display", got.get("move_display"), w["move"],
                   f"{w['move']:f} ({w['percent']:f}%)")
        for k in ("lower", "upper"):
            check_text(rep, f"[both] SD {n} {k}_display", got.get(f"{k}_display"), w[k], f"{w[k]:f}")
    if len(want) == 2:
        one, two = want
        bands = [(-2, two["lower"]), (-1, one["lower"]), (1, one["upper"]), (2, two["upper"])]
        got_b = sd.get("bands") or []
        rep.add("[both] SD bands", str([(b.get("sd"), b.get("level")) for b in got_b]),
                str([(n, f"{lvl:f}") for n, lvl in bands]))
        for b in got_b:
            check_text(rep, f"[both] SD band {b.get('sd')} label", b.get("label"), b.get("sd"), f"{b.get('sd')}SD")
            check_text(rep, f"[both] SD band {b.get('sd')} display", b.get("display"), D(b.get("level")),
                       f"{D(b['level']):f}" if b.get("level") is not None else None)


# ---------------------------------------------------------------- Black-Scholes-Merton (own implementation)


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _npdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bsm_price(s, k, t, r, q, sigma, kind) -> float:
    """European BSM with continuous dividend yield q. kind 'CE' or 'PE'."""
    if t <= 0 or sigma <= 0:
        return max(0.0, s - k) if kind == "CE" else max(0.0, k - s)
    sq = sigma * math.sqrt(t)
    d1 = (math.log(s / k) + (r - q + 0.5 * sigma * sigma) * t) / sq
    d2 = d1 - sq
    if kind == "CE":
        return s * math.exp(-q * t) * _ncdf(d1) - k * math.exp(-r * t) * _ncdf(d2)
    return k * math.exp(-r * t) * _ncdf(-d2) - s * math.exp(-q * t) * _ncdf(-d1)


def bsm_greeks(s, k, t, r, q, sigma, kind) -> dict:
    """Per unit: delta, gamma, theta per calendar day (annual / 365), vega per 1 vol point (per 0.01 sigma)."""
    sq = sigma * math.sqrt(t)
    d1 = (math.log(s / k) + (r - q + 0.5 * sigma * sigma) * t) / sq
    d2 = d1 - sq
    eq, er = math.exp(-q * t), math.exp(-r * t)
    gamma = eq * _npdf(d1) / (s * sq)
    vega = s * eq * _npdf(d1) * math.sqrt(t) / 100.0
    common = -s * eq * _npdf(d1) * sigma / (2 * math.sqrt(t))
    if kind == "CE":
        delta = eq * _ncdf(d1)
        theta = common - r * k * er * _ncdf(d2) + q * s * eq * _ncdf(d1)
    else:
        delta = -eq * _ncdf(-d1)
        theta = common + r * k * er * _ncdf(-d2) - q * s * eq * _ncdf(-d1)
    return {"delta": delta, "gamma": gamma, "theta": theta / 365.0, "vega": vega}


def implied_vol(price, s, k, t, r, q, kind, lo=1e-4, hi=5.0) -> float | None:
    """Bisection on [lo, hi]; None when the price is outside the no-arbitrage band."""
    if price is None or t <= 0:
        return None
    if not (bsm_price(s, k, t, r, q, lo, kind) <= price <= bsm_price(s, k, t, r, q, hi, kind)):
        return None
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if bsm_price(s, k, t, r, q, mid, kind) < price:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return 0.5 * (lo + hi)


def years_to_expiry(valuation: dt.datetime, expiry: str) -> float:
    """Calendar time to expiry at 15:30 IST, in years of 365 days (spec section 4)."""
    exp = dt.datetime.fromisoformat(expiry).replace(hour=15, minute=30, tzinfo=IST)
    return max(0.0, (exp - valuation).total_seconds() / (365.0 * 86400.0))


# ---------------------------------------------------------------- put-call parity forward


def is_live(quote: dict | None) -> bool:
    """A quote counts as live when its health says `available`; a quote with no health key (an older reply, a
    synthetic chain) is treated as live, a stale / unavailable one is not."""
    return (quote or {}).get("health", "available") == "available"


def iv_price(leg: dict, quote: dict | None):
    """ADR-172: the price a leg's IV is implied from -> (price, source). The bid-ask mid only when BOTH sides are live
    and ask >= bid; otherwise the last traded price (after hours: the closing price, ADR-197); nothing usable ->
    (None, None). A side is live only when it is present, above 0 AND the quote's health is `available` (GC-UI F-5:
    a stale / delayed / unavailable book stopped ticking, so its bid and ask are not live sides). The health is the
    quote's own, else the leg's; with neither (an older reply, a synthetic chain) it is treated as live, as is_live
    does. Derived from the spec text on its own, never from the server's code."""
    q = quote or {}
    bid, ask = q.get("bid"), q.get("ask")
    health = q.get("health", (leg or {}).get("health", "available"))
    two_sided = bid is not None and ask is not None and float(bid) > 0 and float(ask) > 0 and float(ask) >= float(bid)
    if health == "available" and two_sided:
        return (float(bid) + float(ask)) / 2, "mid"
    if leg.get("ltp"):
        return float(leg["ltp"]), "ltp"
    return None, None


def parity_forward(chain: dict, t: float, r: float):
    """ADR-061: F = median over LIVE two-sided strikes of K + e^(rT)(Cmid - Pmid); fewer than 3 -> spot fallback
    (F = S e^(rT), q = 0). Returns (F, q, n, reason)."""
    spot = D(chain.get("spot")) if chain else None
    if not chain or chain.get("state") != "LIVE" or spot is None:
        return None, None, 0, "chain not live"
    vals = []
    for row in chain.get("rows") or []:
        ce, pe = row.get("ce") or {}, row.get("pe") or {}
        if not (is_live(ce) and is_live(pe)):  # a stale quote is not a market: it cannot give a forward (ADR-061)
            continue
        quotes = [ce.get("bid"), ce.get("ask"), pe.get("bid"), pe.get("ask")]
        if any(x is None for x in quotes):
            continue
        cb, ca, pb, pa = (float(x) for x in quotes)
        if ca < cb or pa < pb or cb <= 0 or pb <= 0:
            continue
        vals.append(float(row["strike"]) + math.exp(r * t) * ((cb + ca) / 2 - (pb + pa) / 2))
    s = float(spot)
    if len(vals) < MIN_PARITY_STRIKES:
        return s * math.exp(r * t), 0.0, len(vals), f"parity impossible: {len(vals)} two-sided strikes"
    f = statistics.median(vals)
    return f, r - math.log(f / s) / t, len(vals), None


# ---------------------------------------------------------------- expiry payoff (exact Decimal)


def leg_expiry_pnl(leg: dict, level: Decimal) -> Decimal:
    k, entry, qty = D(leg["strike"]), D(leg["planned_entry"]), D(leg["quantity"])
    intrinsic = max(Decimal(0), level - k) if leg["instrument"] == "CE" else max(Decimal(0), k - level)
    per_unit = intrinsic - entry if leg["action"] == "BUY" else entry - intrinsic
    return per_unit * qty


def payoff(legs, level: Decimal) -> Decimal:
    return sum((leg_expiry_pnl(leg, level) for leg in legs), Decimal(0))


def upper_slope(legs) -> Decimal:
    """d(pnl)/d(level) above the highest strike: only calls contribute."""
    s = Decimal(0)
    for leg in legs:
        if leg["instrument"] == "CE":
            s += D(leg["quantity"]) * (1 if leg["action"] == "BUY" else -1)
    return s


def kinks(legs):
    return sorted({Decimal(0)} | {D(leg["strike"]) for leg in legs})


def breakevens(legs, offset=Decimal(0)):
    """Levels > 0 where payoff == offset, solved exactly on each linear segment, half-even to 0.01."""
    ks = kinks(legs)
    top = ks[-1] + Decimal(1000)
    pts = [*ks, top]
    out = []
    for a, b in itertools.pairwise(pts):
        fa, fb = payoff(legs, a) - offset, payoff(legs, b) - offset
        if fa == 0 and a > 0:
            out.append(a)
        if (fa < 0 < fb) or (fa > 0 > fb):
            out.append(a + (b - a) * (-fa) / (fb - fa))
    fb = payoff(legs, top) - offset
    slope = upper_slope(legs)
    if fb != 0 and slope != 0 and (fb < 0) == (slope > 0):
        out.append(top - fb / slope)
    return sorted({x.quantize(PAISA, rounding=ROUND_HALF_EVEN) for x in out})


def extremes(legs):
    """(max_pnl, min_pnl, profit_unlimited, loss_unlimited) of the expiry payoff, before charges."""
    ks = kinks(legs)
    vals = [payoff(legs, k) for k in ks]
    slope = upper_slope(legs)
    return max(vals), min(vals), slope > 0, slope < 0


# ---------------------------------------------------------------- charges (round trip at the planned entry)


CHARGE_PARTS = ("brokerage", "stt", "exchange_transaction", "gst", "stamp", "sebi")
HALF_PAISA = Decimal("0.005")  # a shown part is a correct paisa rounding of its exact value within this


def round_trip_charges(legs, rates=CHARGE_RATES) -> dict:
    """Enter every leg and square it off at the same price: 2 orders per leg; STT on each sell side; stamp on each
    buy side; exchange + SEBI on all premium turnover; GST on brokerage + exchange + SEBI.

    ADR-082 (1): every amount is exact Decimal (no part is rounded, GST is on the EXACT brokerage + exchange + SEBI);
    the total is the exact sum rounded UP to the paisa once (ADR-082 worked example "214.95956479500 rounded up";
    the run1 replies discriminate: condor exact 263.140937 -> 263.15, calendar 172.670651 -> 172.68, so ROUND_UP,
    not half-up). The parts returned here are EXACT; compare a shown part within HALF_PAISA of them."""
    turnover = sell_side = buy_side = exch = Decimal(0)
    for leg in legs:
        v = D(leg["planned_entry"]) * D(leg["quantity"])
        turnover += 2 * v
        sell_side += v
        buy_side += v
        # ADR-082 (1): exchange transaction charges per exchange - a BSE_FO contract (SENSEX) at the BSE rate
        bse = str(leg.get("instrument_id", "")).startswith("BSE_FO:")
        exch += rates["transaction_rate_bse_fo" if bse else "transaction_rate_nse_fo"] * 2 * v
    brokerage = rates["brokerage_per_order"] * 2 * len(legs)
    sebi = rates["sebi_rate"] * turnover
    parts = {
        "brokerage": brokerage,
        "stt": rates["stt_sell_rate"] * sell_side,
        "exchange_transaction": exch,
        "gst": rates["gst_rate"] * (brokerage + exch + sebi),
        "stamp": rates["stamp_buy_rate"] * buy_side,
        "sebi": sebi,
    }
    exact_total = sum(parts.values(), Decimal(0))
    return {**parts, "exact_total": exact_total, "total": exact_total.quantize(PAISA, rounding=ROUND_UP)}


# ---------------------------------------------------------------- the check


def _cells(reply, row_id):
    for row in (reply.get("table") or {}).get("rows") or []:
        if row["row_id"] == row_id:
            return {k: v.get("value") for k, v in row["cells"].items()}
    return None


def _sign(leg):
    return 1 if leg["action"] == "BUY" else -1


FORWARD_BAND_POINTS = 1.0  # parity F from mids moved 0.5-0.7 points between two reads ~2 s apart (2026-10-28 live)


def _q_band(chain, fb, fa, qb, t, r, fallback: bool = False) -> dict:
    """The model's q: the mid of the F read before and after the reply; the band: +/- (half their gap + 1 point).
    The server reads its own snapshot between the two, so its q lies in the band, not at our point. On the spot
    fallback (both reads, ADR-061) F = S e^(rT) and q = 0 exactly: no mid noise, so no fixed 1-point band (GC-UI F-5:
    the 1-point band let a stale-mid IV, 0.0005 off the closing-price IV, pass as a match)."""
    if fb is None or chain is None or chain.get("spot") is None or t <= 0:
        return {"q_mid": qb, "q_hi": qb, "F_band_points": None}
    fa = fa if fa is not None else fb
    s = float(chain["spot"])
    fmid, half = (fb + fa) / 2, abs(fb - fa) / 2 + (0.0 if fallback else FORWARD_BAND_POINTS)
    return {"q_mid": r - math.log(fmid / s) / t, "q_hi": r - math.log((fmid - half) / s) / t, "F_band_points": half}


GREEK_KEYS = ("delta", "gamma", "theta", "vega")


def check_per_unit_signs(rep, view, reply) -> int:
    """GC-UI F-2: for every leg row and Greek, per_unit x quantity == the per-position value, sign included
    (a SELL leg's per unit is negative like its per position). Needs no market data and no model: a reply's own
    cells only. Tolerance: the 4 dp print of per_unit x quantity, plus the 4 dp of the value. A null per_unit or
    value is not compared here (the answer states are checked elsewhere). Returns the figures added."""
    added = 0
    for row in (reply.get("table") or {}).get("rows") or []:
        cells = row.get("cells") or {}
        qty = (cells.get("quantity") or {}).get("value")
        if row.get("row_id") == "TOTAL" or qty is None:
            continue
        for gk in GREEK_KEYS:
            cell = cells.get(gk) or {}
            if cell.get("value") is None or cell.get("per_unit") is None:
                continue
            q = Decimal(str(qty))
            rep.add(
                f"[{view}] leg{row['row_id']} {gk} per_unit x quantity = per position (signed)",
                cell["value"],
                Decimal(str(cell["per_unit"])) * q,
                abs(q) * Decimal("0.00005") + Decimal("0.0001"),
                note="signed: SELL per unit is negative like its per position",
            )
            added += 1
            shown = cell.get("per_unit_display")
            if shown is not None:
                rep.add(
                    f"[{view}] leg{row['row_id']} {gk} per_unit_display = per_unit",
                    cell["per_unit"],
                    shown,
                    Decimal("0.0051"),
                    note="the printed per unit equals per_unit to its print places",
                )
                added += 1
    return added


def check_total_per_unit_greeks(rep, view, reply) -> int:
    """GC-UI T-1: the TOTAL row's per-unit Greek (delta, gamma, theta, decay, vega) = the sum over leg rows of
    (lots / gcd of all lots) x the leg row's own signed per_unit (already signed: never negated again), within the
    4 dp print of each term; absent when any leg row has no per-unit figure (never a partial sum). Quantities share
    the lot size, so quantity / gcd(quantities) is the lot weight. Reads only the reply's own cells."""
    rows = (reply.get("table") or {}).get("rows") or []
    legs = [r["cells"] for r in rows if r.get("row_id") != "TOTAL"]
    total = next((r["cells"] for r in rows if r.get("row_id") == "TOTAL"), None)
    qtys = [(c.get("quantity") or {}).get("value") for c in legs]
    if total is None or not legs or any(q is None or int(q) <= 0 for q in qtys):
        rep.skip(f"[{view}] total per-unit Greeks", "no TOTAL row, no legs or a leg without a quantity")
        return 0
    divisor = 0
    for q in qtys:
        divisor = math.gcd(divisor, int(q))
    weights = [Decimal(int(q) // divisor) for q in qtys]
    added = 0
    for gk in (*GREEK_KEYS, "decay"):
        cell = total.get(gk) or {}
        units = [(c.get(gk) or {}).get("per_unit") for c in legs]
        if any(u is None for u in units):
            if gk == "decay":
                continue  # decay's absent states (no IV, holiday) are the Decay rule's own, with its notes
            rep.add(f"[{view}] total {gk} per unit (absent: a leg has none)",
                    ABSENT if cell.get("per_unit") is None else cell.get("per_unit"), ABSENT,
                    )
        else:
            expected = sum((w * Decimal(str(u)) for w, u in zip(weights, units, strict=True)), Decimal(0))
            rep.add(f"[{view}] total {gk} per unit = lot-weighted sum of the legs' per units",
                    cell.get("per_unit"), expected, Decimal("0.00005") * (sum(weights) + 1),
                    note="legs' per units already carry the side's sign")
        added += 1
    return added


# ---------------------------------------------------------------- round 4: OI rows, TOTAL net per-unit, Decay
SESSION_OPEN = dt.time(9, 15)
ABSENT = "absent"
DASH = "\u2014"


def next_weekday_open(valuation: dt.datetime) -> dt.datetime:
    """The checker's OWN next-open rule: 09:15 IST of the first weekday whose 09:15 is after ``valuation``. It knows no
    exchange holiday: a caller passes ``holidays`` to check_outcome, and Decay across one is marked not checkable."""
    local = valuation.astimezone(IST)
    day = local.date()
    while True:
        opens = dt.datetime.combine(day, SESSION_OPEN, IST)
        if day.weekday() < 5 and opens > local:
            return opens
        day += dt.timedelta(days=1)


def decay_per_unit(s, k, t, r, q, sigma, kind, valuation: dt.datetime, until: dt.datetime) -> float:
    """F-63 / REQ-145 AC-2, unsigned per unit: BSM with (t - elapsed) left minus BSM now, same S, K, r, q, sigma; time
    in calendar seconds / (365 x 86400). An expiry before ``until`` values at intrinsic (bsm_price at t <= 0)."""
    elapsed = (until - valuation).total_seconds() / (365.0 * 86400.0)
    return bsm_price(s, k, t - elapsed, r, q, sigma, kind) - bsm_price(s, k, t, r, q, sigma, kind)


def check_total_net_per_unit(rep, view, reply) -> None:
    """GC-UI D-B28: the TOTAL row's Entry Price / LTP = sells + buys - of the legs' per-unit prices, shown as a
    magnitude with side Cr / Dr (None at 0); absent with a futures leg, unequal quantities or a leg with no price."""
    legs = reply.get("legs") or []
    total = next((r["cells"] for r in (reply.get("table") or {}).get("rows") or [] if r["row_id"] == "TOTAL"), None)
    if not legs or total is None:
        rep.skip(f"[{view}] total net per-unit", "no legs or no TOTAL row")
        return
    for column, source in (("entry_price", "planned_entry"), ("ltp", "ltp")):
        cell = total.get(column) or {}
        prices = [D(leg.get(source)) for leg in legs]
        if (any(leg.get("instrument") == "FUT" for leg in legs) or len({leg.get("quantity") for leg in legs}) != 1
                or any(p is None or (source == "ltp" and p == 0) for p in prices)):
            rep.add(f"[{view}] total {column} per unit (absent)",
                    ABSENT if cell.get("value") is None else cell.get("value"), ABSENT,
                    note="futures leg, unequal quantities or a leg without a price")
            continue
        net = sum(((p if leg["action"] == "SELL" else -p) for leg, p in zip(legs, prices, strict=True)), Decimal(0))
        rep.add(f"[{view}] total {column} per unit (net magnitude)", cell.get("value"), abs(net))
        side = "Cr" if net > 0 else "Dr" if net < 0 else None
        if cell.get("value") is not None:  # a reply recorded before D-B28 has no value: not checkable, above
            rep.add(f"[{view}] total {column} side", str(cell.get("side")), str(side))


def _chain_side_oi(chain: dict, strike: Decimal, side: str) -> int | None:
    """One contract's OI in a chain reply; None when the chain has no usable quote (in hours: not a live quote)."""
    row = next((x for x in chain.get("rows") or [] if D(x.get("strike")) == strike), None)
    quote = (row or {}).get(side.lower())
    if not quote or quote.get("oi") is None:
        return None
    if quote.get("health") != "available" and not chain.get("market_closed"):
        return None
    return int(quote["oi"])


def check_open_interest(rep, view, reply, chains_before, chains_after) -> None:
    """REQ-083 AC-5 / AC-6: every ``open_interest`` row's call / put OI equals the chain snapshot's OI for the same
    contract (the chain read before or after the reply: OI can tick between reads); a side the chain has no usable
    quote for is null with the dash, never 0; an unavailable block has no rows."""
    oi = (reply or {}).get("open_interest")
    if oi is None:
        return  # flag off: no block
    if not oi.get("available"):
        rep.add(f"[{view}] open_interest unavailable has no rows", len(oi.get("rows") or []), 0,
                note=f"reason: {oi.get('unavailable_reason')}")
        return
    expiry = str(oi.get("expiry"))
    chains = [c for c in ((chains_before or {}).get(expiry), (chains_after or {}).get(expiry)) if c]
    if not chains:
        rep.skip(f"[{view}] open_interest rows", f"no chain read for expiry {expiry}")
        return
    for row in oi.get("rows") or []:
        strike = D(row.get("strike"))
        for side, key in (("CE", "call_oi"), ("PE", "put_oi")):
            want = [_chain_side_oi(c, strike, side) for c in chains]
            got = row.get(key)
            name = f"[{view}] open_interest {strike} {side}"
            if got is None or all(w is None for w in want):
                rep.add(name + " (no usable quote: null, never 0)", ABSENT if got is None else got,
                        ABSENT if all(w is None for w in want) else next(w for w in want if w is not None))
                if got is None:
                    rep.add(name + " display", row.get(f"{key}_display"), DASH)
                continue
            best = min((w for w in want if w is not None), key=lambda w: abs(w - got))
            rep.add(name, got, best, note="the chain before / after the reply")


def check_outcome(name, est, atx, chains_before, chains_after, futures=None, r=RISK_FREE_RATE, both=None,
                  step_asked=None, holidays=()) -> Report:
    """est / atx: the outcome replies for view=estimated_now / at_expiry; chains_*: {expiry: chain reply}. both: the
    reply asked with both_views / payoff_step / sd_bands (GC-UI step 4), step_asked its payoff_step (None: absent)."""
    rep = Report(name)
    for view, reply in (("estimated_now", est), ("at_expiry", atx)):
        state = (reply or {}).get("state")
        if state != "COMPUTED":
            rep.skip(f"[{view}] every figure", f"reply state {state} ({(reply or {}).get('reason')})")
    if (est or {}).get("state") != "COMPUTED":
        return rep
    for view, reply in (("estimated_now", est), ("at_expiry", atx)):
        if (reply or {}).get("state") == "COMPUTED":
            check_per_unit_signs(rep, view, reply)
            check_displays(rep, view, reply)
            check_total_net_per_unit(rep, view, reply)
            check_total_per_unit_greeks(rep, view, reply)
            check_open_interest(rep, view, reply, chains_before, chains_after)
    if (both or {}).get("state") == "COMPUTED":
        check_open_interest(rep, "both", both, chains_before, chains_after)
    legs = est.get("legs") or []
    for i, leg in enumerate(legs):
        for key in ("strike", "expiry", "quantity", "planned_entry", "instrument", "action"):
            if leg.get(key) is None:
                rep.skip(f"leg{i + 1} {key}", "reply leg field null")
                return rep
    expiries = sorted({leg["expiry"] for leg in legs})
    single_expiry = len(expiries) == 1
    spot = D(est.get("spot_level"))
    valuation = dt.datetime.fromisoformat(est["valuation"])

    risk_base = None
    if single_expiry:
        _mx, _mn, _pu, _lu = extremes(legs)
        risk_base = None if _lu or _mn >= 0 else -_mn  # pre-charges max loss: a second P&L % basis
    # --- leg rows (live P&L, section 2): exact money
    for view, reply in (("estimated_now", est), ("at_expiry", atx)):
        if (reply or {}).get("state") != "COMPUTED":
            continue
        tot_entry = tot_cur = tot_pnl = Decimal(0)
        cur_ok = True
        for i, leg in enumerate(reply["legs"]):
            c = _cells(reply, str(i + 1)) or {}
            qty, entry, ltp = D(leg["quantity"]), D(leg["planned_entry"]), D(leg.get("ltp"))
            ev = money(entry * qty)
            rep.add(f"[{view}] leg{i + 1} entry_value", c.get("entry_value"), ev)
            tot_entry += _sign(leg) * ev
            if ltp is None:
                rep.skip(f"[{view}] leg{i + 1} current_value", "leg ltp null", c.get("current_value"))
                rep.skip(f"[{view}] leg{i + 1} unrealized_pnl", "leg ltp null", c.get("unrealized_pnl"))
                cur_ok = False
                continue
            cv = money(ltp * qty)
            pnl = money((ltp - entry) * qty * _sign(leg))
            rep.add(f"[{view}] leg{i + 1} current_value", c.get("current_value"), cv)
            rep.add(f"[{view}] leg{i + 1} unrealized_pnl", c.get("unrealized_pnl"), pnl)
            pct = c.get("pnl_percent")
            dp = len(pct.split(".")[1]) if pct and "." in pct else 0
            rep.add(
                f"[{view}] leg{i + 1} pnl_percent",
                pct,
                (pnl / ev * 100).quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP) if ev else None,
                note=f"compared at the reply's {dp} dp",
            )
            tot_cur += _sign(leg) * cv
            tot_pnl += pnl
        t = _cells(reply, "TOTAL") or {}
        rep.add(f"[{view}] total entry_value (net, magnitude)", t.get("entry_value"), abs(tot_entry))
        if cur_ok:
            rep.add(f"[{view}] total current_value (net, magnitude)", t.get("current_value"), abs(tot_cur))
            rep.add(f"[{view}] total unrealized_pnl", t.get("unrealized_pnl"), tot_pnl)
            pct = t.get("pnl_percent")
            dp = len(pct.split(".")[1]) if pct and "." in pct else 0
            q_ = Decimal(1).scaleb(-dp)
            rep.add(
                f"[{view}] total pnl_percent",
                pct,
                # C-1: REQ-035 owner Q233 "TOTAL P&L % = unrealized P&L / max loss" ("-" when unlimited, zero or
                # mixed expiries, Q242); the leg rows keep their own basis (unrealized / the leg's entry value)
                (tot_pnl / risk_base * 100).quantize(q_, rounding=ROUND_HALF_UP) if risk_base else None,
                note=f"ours = unrealized / pre-charges max loss (REQ-035 Q233), at the reply's {dp} dp",
                alt=(tot_pnl / abs(tot_entry) * 100).quantize(q_, rounding=ROUND_HALF_UP) if tot_entry else None,
                alt_label="unrealized / net entry value (the old, wrong basis)",
            )

    # --- strategy-level exact money (section 3)
    summ = est.get("summary") or {}
    net = sum((-_sign(leg) * D(leg["planned_entry"]) * D(leg["quantity"]) for leg in legs), Decimal(0))
    npr = summ.get("net_premium") or {}
    rep.add("net_premium amount", npr.get("amount"), money(abs(net)))
    rep.add("net_premium side", npr.get("side"), "get" if net > 0 else "pay" if net < 0 else "none")
    qtys = {D(leg["quantity"]) for leg in legs}
    rep.add("net_premium per_unit", npr.get("per_unit"), money(abs(net) / qtys.pop()) if len(qtys) == 1 else None)
    intrinsic_now = sum(
        (
            _sign(leg)
            * D(leg["quantity"])
            * (
                max(Decimal(0), spot - D(leg["strike"]))
                if leg["instrument"] == "CE"
                else max(Decimal(0), D(leg["strike"]) - spot)
            )
            for leg in legs
        ),
        Decimal(0),
    )
    rep.add("intrinsic_value (at reply spot)", summ.get("intrinsic_value"), money(intrinsic_now))
    if all(leg.get("ltp") is not None for leg in legs):
        cur_net = sum((_sign(leg) * D(leg["ltp"]) * D(leg["quantity"]) for leg in legs), Decimal(0))
        rep.add("time_value (current net value - intrinsic)", summ.get("time_value"), money(cur_net - intrinsic_now))

    ch = round_trip_charges(legs)
    cb = est.get("charges_breakdown") or {}
    for k in CHARGE_PARTS:  # ADR-082 (1): each shown part within half a paisa of its exact value
        rep.add(f"charges {k}", cb.get(k), ch[k], tol=HALF_PAISA, note="ours = exact (ADR-082 (1)); tol = rounding")
    rep.add("charges total", cb.get("total"), ch["total"], note="exact sum rounded up once (ADR-082 (1))")
    comps = [cb.get(k) for k in CHARGE_PARTS]
    if all(c is not None for c in comps):
        # each shown part is rounded on its own, so the shown parts may differ from the total by a paisa or two
        rep.add(
            "charges total = sum of the reply's own shown components",
            cb.get("total"),
            sum((D(c) for c in comps), Decimal(0)),
            tol=HALF_PAISA * len(CHARGE_PARTS) + PAISA,
            note="tol = 6 parts x half a paisa + the one round-up",
        )
    if cb.get("rates_read_on") and cb["rates_read_on"] != CHARGE_RATES["read_on"]:
        rep.notes.append(f"reply rates_read_on {cb['rates_read_on']} differs from the seed {CHARGE_RATES['read_on']}")
    rep.add("summary charges", summ.get("charges"), ch["total"])

    if single_expiry:
        mx, mn, pu, lu = extremes(legs)
        rep.add("max_profit_unlimited", summ.get("max_profit_unlimited"), pu)
        rep.add("max_loss_unlimited", summ.get("max_loss_unlimited"), lu)
        mp = None if pu else money(mx - ch["total"])
        ml = None if lu else money(max(Decimal(0), -mn) + ch["total"])
        rep.add("max_profit (incl. charges)", summ.get("max_profit"), mp, note="unlimited" if pu else "")
        rep.add("max_loss (incl. charges)", summ.get("max_loss"), ml, note="unlimited" if lu else "")
        bes = breakevens(legs)
        ours_be = [D(x) for x in summ.get("breakevens") or []]
        rep.add_list("breakevens (pre-charges payoff)", ours_be, bes)
        if mp is not None and ml:
            rr = (mp / ml).quantize(PAISA, rounding=ROUND_HALF_UP)
            rep.add("reward_risk", summ.get("reward_risk"), rr)
            rep.add(
                "risk_reward",
                summ.get("risk_reward"),
                (ml / mp).quantize(PAISA, rounding=ROUND_HALF_UP) if mp else None,
            )
        # REQ-081 AC-9 (ADR-207 (8)): the percentages are of the margin needed, to one decimal, half-up
        fs = summ.get("funds_share") or {}
        base = D(fs.get("margin_needed"))
        for label, side in (("max_profit_percent", mp), ("max_loss_percent", ml)):
            if base and side is not None:
                rep.add(f"funds_share {label}", fs.get(label),
                        (side / base * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP),
                        note="percent of margin needed")
        # D-A46
        be_incl = breakevens(legs, offset=ch["total"])
        rep.data_rows["D-A46"] = {
            "shown_breakevens": [str(x) for x in ours_be],
            "breakevens_pre_charges": [str(x) for x in bes],
            "breakevens_incl_charges": [str(x) for x in be_incl],
            "pnl_at_shown_breakeven_incl_charges": [str(money(payoff(legs, b) - ch["total"])) for b in ours_be],
            "max_loss_includes_charges": ml is not None
            and summ.get("max_loss") is not None
            and D(summ["max_loss"]) == ml,
        }
        # at-expiry payoff points (exact)
        if (atx or {}).get("state") == "COMPUTED":
            pts = (atx.get("payoff") or {}).get("points") or []
            if not pts:
                rep.skip("[at_expiry] payoff points", "empty payoff")
            for p in pts:
                rep.add(f"[at_expiry] payoff @{p['level']}", p.get("pnl"), money(payoff(legs, D(p["level"]))))
            sc = atx.get("scenario") or {}
            for lv, tot in zip(sc.get("levels") or [], sc.get("totals") or [], strict=False):
                rep.add(f"[at_expiry] scenario total @{lv['level']}", tot, money(payoff(legs, D(lv["level"]))))
    else:
        for k in ("max_profit", "max_loss", "breakevens"):
            v = summ.get(k)
            rep.skip(
                k,
                "mixed expiries: no closed-form expiry payoff (the near expiry leaves the far leg open)",
                v if v not in ([], None) else None,
            )
        if (atx or {}).get("state") == "COMPUTED":
            sc = atx.get("scenario") or {}
            rep.skip(
                "[at_expiry] scenario",
                f"reply: available={sc.get('available')} reason={sc.get('unavailable_reason')!r}; mixed expiries",
            )
        rep.data_rows["D-A46"] = {
            "note": "mixed expiries: no breakeven shown",
            "summary_breakevens": summ.get("breakevens"),
        }

    # --- margin (D-A47): recorded, not a figure check
    m = est.get("margin") or {}
    # C-2: needed = broker_needed + the ADR-094 top-up max(0, qty x planned price - option_premium) per BUY leg; the
    # per-leg option_premium is not in the reply, so `needed` cannot be derived independently: never matched.
    if m.get("needed") is not None:
        rep.skip(
            "margin needed",
            "needs each BUY leg's Zerodha option_premium (ADR-094 top-up), not in the reply",
            m.get("needed"),
        )
    rep.data_rows["D-A47"] = {
        "needed": m.get("needed"),
        "broker_needed": m.get("broker_needed"),
        "broker_needed_plus_debit": str(money(D(m["broker_needed"]) + (-net if net < 0 else 0)))
        if m.get("broker_needed")
        else None,
        "net_premium_signed": str(money(net)),
        "reason": m.get("reason"),
        "needed_equals_broker_needed": m.get("needed") == m.get("broker_needed"),
    }

    # --- model figures (Estimated Now): forward/q per expiry, IV, Greeks, scenario points
    qinfo = {}
    for e in expiries:
        t = years_to_expiry(valuation, e)
        fb, qb, nb, why_b = parity_forward(chains_before.get(e), t, r)
        fa, qa, na, why_a = parity_forward(chains_after.get(e), t, r)
        qinfo[e] = {
            "T_years": t,
            "F_before": fb,
            "q_before": qb,
            "n_before": nb,
            "reason_before": why_b,
            "F_after": fa,
            "q_after": qa,
            "n_after": na,
            "reason_after": why_a,
        }
        fallback = why_b is not None and (why_a is not None or fa is None)  # spot fallback on every read we have
        qinfo[e].update(_q_band(chains_before.get(e), fb, fa, qb, t, r, fallback))
        # C-4: the basis the reply states (the chain's greeks_basis, else the reply's "estimated from spot" label)
        # against the basis OUR rule gives from the live quotes (ADR-061: fewer than 3 live two-sided strikes = spot)
        label = f"{est.get('status_label') or ''} {est.get('output_label') or ''}"
        stated = (chains_after.get(e) or {}).get("greeks_basis") or (
            "SPOT_FALLBACK" if "estimated from spot" in label else None
        )
        n_live = na if chains_after.get(e) else nb
        ours_basis = "SPOT_FALLBACK" if n_live < MIN_PARITY_STRIKES else "PARITY"
        qinfo[e]["stated_basis"], qinfo[e]["our_basis"] = stated, ours_basis
        if stated is not None and chains_after.get(e) and fa is not None:
            rep.add(
                f"pricing basis {e} (stated by the reply vs ours from the live quotes)",
                stated,
                ours_basis,
                note=f"ours: {n_live} live two-sided strikes (needs {MIN_PARITY_STRIKES}); spot fallback means q = 0",
            )
    rep.data_rows["forwards"] = qinfo
    # D-C33
    if futures:
        dc = {}
        fwd = {f["expiry"]: f for f in futures.get("forwards") or []}
        fut = {f["expiry"]: f for f in futures.get("futures") or []}
        fspot = float(futures["spot"]) if futures.get("spot") else None
        for e in sorted(set(fwd) | set(fut)):
            t = years_to_expiry(valuation, e)
            dc[e] = {
                "future_ltp": (fut.get(e) or {}).get("ltp"),
                "future_ltp_reason": (fut.get(e) or {}).get("ltp_reason"),
                "server_forward": (fwd.get(e) or {}).get("forward"),
                "server_source": (fwd.get(e) or {}).get("source"),
                "spot_fallback_S_e^rT": round(fspot * math.exp(r * t), 2) if fspot else None,
                "our_parity_forward": round(qinfo[e]["F_after"], 2) if e in qinfo and qinfo[e]["F_after"] else None,
            }
        rep.data_rows["D-C33"] = dc

    table_est = []
    if (both or {}).get("state") == "COMPUTED":  # GC-UI step 4: the new figures, from this file's own maths
        check_curves(rep, both, est, atx, legs, single_expiry)
        table_est = check_payoff_table(rep, both, legs, single_expiry, step_asked)
        check_sd(rep, both, legs, valuation)
    elif both is not None:
        rep.skip("[both] every figure", f"reply state {both.get('state')} ({both.get('reason')})")
    if est.get("status_label") or est.get("output_label"):
        rep.notes.append(f"reply label: {est.get('status_label') or est.get('output_label')}")
    s = float(spot)
    quotes = {q["instrument_id"]: q for q in est.get("leg_quotes") or []}
    leg_model = []
    no_chain = [e for e in expiries if qinfo[e]["q_mid"] is None]
    if no_chain:
        rep.skip("model figures (IV, Greeks, Estimated Now)", f"no option chain for expiry {', '.join(no_chain)}")
        return rep
    decay_until = next_weekday_open(valuation)
    decay_ok = decay_until.date() not in set(holidays)
    decay_parts: list = []  # (value, tol) per leg, or None when the checker has no value for the leg
    for i, leg in enumerate(legs):
        e = leg["expiry"]
        qi = qinfo[e]
        q = qi["q_mid"]
        t = qi["T_years"]
        k = float(leg["strike"])
        iv_reply = leg.get("iv")
        lq = quotes.get(leg["instrument_id"]) or {}
        bid, ask = lq.get("bid"), lq.get("ask")
        mid = (
            (float(bid) + float(ask)) / 2 if bid is not None and ask is not None and float(ask) >= float(bid) else None
        )
        px_basis, src = iv_price(leg, lq)  # F-5: mid only with two live (available) sides, else the LTP (ADR-172)
        iv_mid = implied_vol(mid, s, k, t, r, q, leg["instrument"]) if mid is not None else None
        iv_ltp = implied_vol(float(leg["ltp"]), s, k, t, r, q, leg["instrument"]) if leg.get("ltp") else None
        iv_mid_spot = implied_vol(mid, s, k, t, r, 0.0, leg["instrument"]) if mid is not None else None
        ours_iv = implied_vol(px_basis, s, k, t, r, q, leg["instrument"]) if px_basis is not None else None
        q_note = "q=0 (spot fallback)" if qi["our_basis"] == "SPOT_FALLBACK" else "parity q"
        used = f"{src}, {q_note}" if src else "no price"
        # IV tolerance: 0.0001 for the 6 dp print + the IV change across the q read before and after the reply.
        qa_ = qi["q_hi"] if qi["q_hi"] is not None else q
        iv_alt = implied_vol(px_basis, s, k, t, r, qa_, leg["instrument"]) if px_basis is not None else None
        iv_tol = Decimal("0.0001") + Decimal(str(round(abs((iv_alt or ours_iv or 0) - (ours_iv or 0)), 6)))
        if iv_reply is None:
            rep.skip(f"leg{i + 1} iv", "reply iv null")
        else:
            rep.add(
                f"leg{i + 1} iv (fraction; ours from {used})",
                iv_reply,
                None if ours_iv is None else round(ours_iv, 6),
                iv_tol,
                note="6 dp print + IV change across the forward band",
            )
        rep.data_rows.setdefault("D-B35/36 iv basis", {})[f"leg{i + 1}"] = {
            "reply_iv": iv_reply,
            "used": used,
            "stated_basis": qi["stated_basis"],
            "ours_mid_parity": iv_mid and round(iv_mid, 6),
            "ours_ltp_parity": iv_ltp and round(iv_ltp, 6),
            "ours_mid_spot_q0": iv_mid_spot and round(iv_mid_spot, 6),
            "mid": mid,
            "ltp": leg.get("ltp"),
        }
        leg_model.append((leg, float(iv_reply) if iv_reply is not None else None, q, t, k))
        c = _cells(est, str(i + 1)) or {}
        if iv_reply is not None and t > 0:
            g = bsm_greeks(s, k, t, r, q, float(iv_reply), leg["instrument"])
            g2 = bsm_greeks(s, k, t, r, qa_, float(iv_reply), leg["instrument"])
            qty = float(leg["quantity"]) * _sign(leg)
            for gk in ("delta", "gamma", "theta", "vega"):
                if c.get(gk) is None:
                    rep.skip(f"leg{i + 1} {gk}", "reply greek null")
                    continue
                # 4 dp per unit x qty (rounding) + the spread across the q read before / after the reply
                tol = abs(qty) * 0.00005 + abs(g[gk] - g2[gk]) * abs(qty) + 0.0001
                rep.add(
                    f"leg{i + 1} {gk} (per position = per unit x signed qty)",
                    c[gk],
                    round((g[gk] + g2[gk]) / 2 * qty, 4),
                    Decimal(str(round(tol + abs(g[gk] - g2[gk]) * abs(qty) / 2, 4))),
                    note="ours at the forward mid; tol = 4 dp x qty + forward band",
                )
            if not decay_ok:
                rep.skip(f"leg{i + 1} decay", f"next weekday {decay_until.date()} is an exchange holiday: the checker "
                         "has no calendar to find the next open (not checkable)", c.get("decay"))
                decay_parts.append(None)
            else:
                d1 = decay_per_unit(s, k, t, r, q, float(iv_reply), leg["instrument"], valuation, decay_until)
                d2 = decay_per_unit(s, k, t, r, qa_, float(iv_reply), leg["instrument"], valuation, decay_until)
                dtol = abs(qty) * 0.00005 + abs(d1 - d2) * abs(qty) + 0.0001
                want = (d1 + d2) / 2 * qty
                rep.add(f"leg{i + 1} decay (Rs to {decay_until:%a %d-%b %H:%M} IST, signed)", c.get("decay"),
                        round(want, 4), Decimal(str(round(dtol, 4))),
                        note="own BSM revaluation at the next weekday 09:15 IST; assumes no holiday in between")
                decay_parts.append((want, dtol))
        else:
            decay_parts.append(None)
        if iv_reply is not None and t > 0:
            rep.data_rows.setdefault("D-B35/36 greek unit", {})[f"leg{i + 1}"] = {
                "reply_delta": c.get("delta"),
                "ours_per_unit_delta": round(g["delta"], 4),
                "ours_per_position_delta": round(g["delta"] * qty, 4),
            }

    total_cells = _cells(est, "TOTAL") or {}
    if decay_parts and all(part is not None for part in decay_parts):
        rep.add("TOTAL decay (sum of the legs)", total_cells.get("decay"),
                round(sum(part[0] for part in decay_parts), 4),
                Decimal(str(round(sum(part[1] for part in decay_parts), 4))))
    elif decay_ok and any(leg.get("iv") is None for leg in legs):
        rep.add("TOTAL decay absent (a leg has none: never a partial sum)",
                ABSENT if total_cells.get("decay") is None else total_cells.get("decay"), ABSENT)

    # Estimated-Now scenario points; the payoff table's Estimated Now cells by the same model (GC-UI step 4)
    _model_points(rep, "[estimated_now] payoff", (est.get("payoff") or {}).get("points") or [], legs, leg_model,
                  qinfo, expiries, r)
    if table_est:
        _model_points(rep, "[both] payoff_table estimated_now", table_est, legs, leg_model, qinfo, expiries, r)

    # D-B33/38: table now-values and Greeks identical in both views?
    if (atx or {}).get("state") == "COMPUTED":
        same = {}
        for row in ("1", "2", "TOTAL"):
            a, b = _cells(est, row), _cells(atx, row)
            if a and b:
                same[row] = {k: (a.get(k), b.get(k)) for k in ("unrealized_pnl", "delta", "theta", "vega")}
        rep.data_rows["D-B33/38"] = {
            "table_heading_est": (est.get("table") or {}).get("scenario_heading"),
            "scenario_label_atx": (atx.get("scenario") or {}).get("label"),
            "cells (est, at_expiry)": same,
        }
    return rep


def _model_points(rep, label, pts, legs, leg_model, qinfo, expiries, r) -> None:
    """Each Estimated Now point re-priced with this file's BSM at the reply's per-leg IV and the parity q."""
    if not pts:
        rep.skip(f"{label} points", "empty payoff")
        return
    if any(m[1] is None for m in leg_model):
        rep.skip(f"{label} points", "a leg has no IV")
        return
    tol = Decimal(str(round(sum(float(leg["quantity"]) for leg in legs) * 0.0051, 2)))
    for p in pts:
        lvl = float(p["level"])
        tot = Decimal(0)
        for leg, sig, q, t, k in leg_model:
            px = money(bsm_price(lvl, k, t, r, q, sig, leg["instrument"]))
            tot += (px - D(leg["planned_entry"])) * D(leg["quantity"]) * _sign(leg)
        # forward band: move each expiry's q to its band edge on its own; the effects add in the worst case
        drift = 0.0
        for e in expiries:
            tot2 = Decimal(0)
            for leg, sig, _q, t, k in leg_model:
                qa2 = qinfo[e]["q_hi"] if leg["expiry"] == e and qinfo[e]["q_hi"] is not None else _q
                px2 = money(bsm_price(lvl, k, t, r, qa2, sig, leg["instrument"]))
                tot2 += (px2 - D(leg["planned_entry"])) * D(leg["quantity"]) * _sign(leg)
            drift += float(abs(tot2 - tot))
        rep.add(
            f"{label} @{p['level']}",
            p.get("pnl"),
            money(tot),
            tol + Decimal(str(round(drift, 2))),
            note="0.005/unit/leg rounding + forward band (before/after gap/2 + 1 pt)",
        )


def display_paisa_signed(value: Decimal) -> str:
    """REQ-109 AC-2: a paper P&L to the paisa, half-up on the magnitude, Indian grouping; plus on a profit, U+2212 on a
    loss; a figure that rounds to zero is "0.00" with no sign."""
    mag = abs(value).quantize(PAISA, rounding=ROUND_HALF_UP)
    whole, _, frac = f"{mag:f}".partition(".")
    text = f"{_indian(whole)}.{frac}"
    if mag == 0:
        return text
    return (MINUS_SIGN if value < 0 else "+") + text


def check_paper(tracking: dict, planned_legs: list) -> Report:
    rep = Report(f"paper strategy {tracking.get('strategy_id')}")
    if not tracking or tracking.get("state") not in ("LIVE", "PAUSED", "EXITED", "CLOSED"):
        rep.skip("paper totals", f"tracking state {tracking.get('state') if tracking else None}")
        return rep
    tot = booked = unbooked = Decimal(0)
    rows = {}
    for i, leg in enumerate(tracking.get("legs") or []):
        entry, qty = D(leg["entry_price"]), D(leg["quantity"])
        px = D(leg.get("exit_price")) or D(leg.get("current_price"))
        if px is None:
            rep.skip(f"paper leg{i + 1}", "no current or exit price")
            return rep
        pnl = (px - entry) * qty * (1 if leg["action"] == "BUY" else -1)
        tot += pnl
        (booked if leg.get("exit_price") else unbooked)
        if leg.get("exit_price"):
            booked += pnl
        else:
            unbooked += pnl
        # D-B48: the reply's own per-leg figure against this checker's (px - entry) x qty, sign by side; a reply with
        # no per-leg figure is a mismatch (a missing value never matches), and an exited leg must say "booked"
        rep.add(f"paper leg{i + 1} pnl", leg.get("pnl"), money(pnl))
        rep.add(
            f"paper leg{i + 1} pnl kind", leg.get("pnl_kind"), "booked" if leg.get("exit_price") else "unbooked"
        )
        # the leg's own text against the same figure to the paisa; a missing text is not a match
        rep.add(f"paper leg{i + 1} pnl text", leg.get("pnl_text"), display_paisa_signed(pnl))
        planned = planned_legs[i]["planned_entry"] if i < len(planned_legs) else None
        rows[f"leg{i + 1}"] = {
            "planned_entry": planned,
            "paper_entry": leg["entry_price"],
            "current": leg.get("current_price"),
            "pnl_paper_entry": str(money(pnl)),
            "pnl_planned_entry": str(money((px - D(planned)) * qty * (1 if leg["action"] == "BUY" else -1)))
            if planned
            else None,
        }
    rep.add("paper_pnl", tracking.get("paper_pnl", tracking.get("total")), money(tot))
    rep.add("paper booked", tracking.get("booked"), money(booked))
    rep.add("paper unbooked", tracking.get("unbooked"), money(unbooked))
    rep.data_rows["D-B51"] = rows
    return rep


def _book_by_contract(orders: list) -> dict:
    """GC-TP 1b: the net quantity, exact average cost and booked P&L of each contract, from the ORDERBOOK rows alone
    (own arithmetic, exact Fractions). Zerodha's average rule: the average is the weighted average of the orders that
    increased the quantity on the current side; an order against the position books (exit - average) x qty for a long
    and (average - exit) x qty for a short and leaves the average; an order through zero books the closing part and
    opens the rest at its own price."""
    books: dict = {}
    for o in orders:
        b = books.setdefault(o["contract_id"], {"net": 0, "cost": Fraction(0), "booked": Fraction(0)})
        qty, price = int(o["quantity"]), Fraction(D(o["price"]))
        signed = qty if o["side"] == "BUY" else -qty
        if b["net"] == 0 or (b["net"] > 0) == (signed > 0):
            b["net"] += signed
            b["cost"] += price * qty
            continue
        closing = min(qty, abs(b["net"]))
        average = b["cost"] / abs(b["net"])
        gain = (price - average) if b["net"] > 0 else (average - price)
        b["booked"] += gain * closing
        b["cost"] -= average * closing
        b["net"] += -closing if b["net"] > 0 else closing
        if qty > closing:
            b["net"] = (qty - closing) * (1 if signed > 0 else -1)
            b["cost"] = price * (qty - closing)
    return books


def _paisa_of(value: Fraction) -> Decimal:
    """An exact Fraction to the paisa, half up on the magnitude (the same rule as display)."""
    return money(Decimal(value.numerator) / Decimal(value.denominator))


def check_paper_orders(reply: dict) -> Report:
    """GC-TP 1b (REQ-109 AC-4, AC-5; ADR-207): GET /paper/strategies/{id} recomputed from the orderbook rows and the
    reply's own live prices. A contract with no live price has no unbooked or total, and the reply must say so (absent),
    never 0. The prices are market inputs taken from the reply (see the known bypasses); the average shown is compared
    to the paisa, never used to derive anything."""
    rep = Report(f"paper orders strategy {reply.get('strategy_id') if reply else None}")
    if not reply or reply.get("state") == "REFUSED" or not reply.get("orders"):
        rep.skip("paper orders", f"no book: {(reply or {}).get('reason', 'no orders in the reply')}")
        return rep
    books = _book_by_contract(reply["orders"])
    shown = {p["contract_id"]: p for p in reply.get("positions") or []}
    rep.add("contracts in the reply", len(shown), len(books))
    booked_sum, unbooked_sum, known = Fraction(0), Fraction(0), True
    for cid, b in books.items():
        name, pos = f"contract {cid}", shown.get(cid)
        if pos is None:
            rep.skip(name, "the orderbook has this contract but the net positions do not")
            known = False
            continue
        rep.add(f"{name} net quantity", pos["net_quantity"], b["net"])
        average = None if b["net"] == 0 else b["cost"] / abs(b["net"])
        shown_avg = pos.get("average")  # a flat contract has no average: both sides must say "none", never a number
        rep.add(f"{name} average (to the paisa)", "none" if shown_avg is None else shown_avg,
                "none" if average is None else _paisa_of(average))
        rep.add(f"{name} booked", money(pos["booked"]), _paisa_of(b["booked"]))
        rep.add(f"{name} booked text", pos.get("booked_text"), display_paisa_signed(_paisa_of(b["booked"])))
        live = D(pos.get("ltp")) if pos.get("price_state") == "live" else None
        booked_sum += b["booked"]
        if b["net"] == 0:
            unbooked = Fraction(0)
        elif live is None:
            unbooked = None
        else:
            unbooked = (Fraction(live) - average) * b["net"]
        if unbooked is None:
            known = False
            rep.add(f"{name} unbooked absent without a live price",
                    "absent" if pos.get("unbooked") is None else "shown", "absent")
            rep.add(f"{name} total absent without a live price", "absent" if pos.get("total") is None else "shown",
                    "absent")
            continue
        unbooked_sum += unbooked
        rep.add(f"{name} unbooked", money(pos["unbooked"]) if pos.get("unbooked") is not None else None,
                _paisa_of(unbooked))
        rep.add(f"{name} total", money(pos["total"]) if pos.get("total") is not None else None,
                _paisa_of(b["booked"] + unbooked))
        rep.add(f"{name} total text", pos.get("total_text"), display_paisa_signed(_paisa_of(b["booked"] + unbooked)))
    rep.add("strategy booked", money(reply["booked"]), _paisa_of(booked_sum))
    rep.add("strategy booked text", reply.get("booked_text"), display_paisa_signed(_paisa_of(booked_sum)))
    if known:
        rep.add("strategy unbooked", money(reply["unbooked"]) if reply.get("unbooked") is not None else None,
                _paisa_of(unbooked_sum))
        rep.add("strategy total", money(reply["total"]) if reply.get("total") is not None else None,
                _paisa_of(booked_sum + unbooked_sum))
        total = _paisa_of(booked_sum + unbooked_sum)
        rep.add("strategy total text", reply.get("total_text"), display_paisa_signed(total))
    else:
        rep.add("strategy unbooked absent when a contract is not live",
                "absent" if reply.get("unbooked") is None else "shown", "absent")
        rep.add("strategy total absent when a contract is not live",
                "absent" if reply.get("total") is None else "shown", "absent")
    return rep


# ---------------------------------------------------------------- GC-TP step 6c: the what-if target (REQ-084 AC-4)

TARGET_GREEKS = ("delta", "gamma", "theta", "vega")
Q_LOW, Q_HIGH = -0.5, 0.5  # the band the implied dividend yield is searched in


def _implied_q(price, s, k, t, r, sigma, kind) -> float | None:
    """The dividend yield q at which this file's BSM prices the leg at `price` with the leg's own IV (bisection;
    a call falls and a put rises as q grows). None when `price` is outside the band."""
    if price is None or t <= 0 or not sigma:
        return None
    sign = 1 if kind == "CE" else -1
    if (bsm_price(s, k, t, r, Q_LOW, sigma, kind) - price) * sign < 0:
        return None
    if (bsm_price(s, k, t, r, Q_HIGH, sigma, kind) - price) * sign > 0:
        return None
    lo, hi = Q_LOW, Q_HIGH
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if (bsm_price(s, k, t, r, mid, sigma, kind) - price) * sign > 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def target_q_by_expiry(reply: dict, r: float) -> dict:
    """Per expiry (q, spread). q is solved from the reply's own legs (their IV and the two-sided mid, else the LTP the
    IV was solved from) at the reply's valuation; spread = max - min over the legs and widens the tolerance. An
    expiry with no solvable leg is absent."""
    s = float(reply["spot_level"])
    valuation = dt.datetime.fromisoformat(reply["valuation"])
    quotes = {x["instrument_id"]: x for x in reply.get("leg_quotes") or []}
    found: dict = {}
    for lg in reply.get("legs") or []:
        if lg.get("iv") is None:
            continue
        px, _src = iv_price(lg, quotes.get(lg["instrument_id"]) or {})
        t = years_to_expiry(valuation, lg["expiry"])
        q = _implied_q(px, s, float(lg["strike"]), t, r, float(lg["iv"]), lg["instrument"])
        if q is not None:
            found.setdefault(lg["expiry"], []).append(q)
    return {e: (statistics.median(v), max(v) - min(v)) for e, v in found.items()}


def _target_model(legs, qmap, level, at, r, dq=0.0):
    """(open-leg P&L, {greek: total}, [per-leg greeks]) at `level` and `at`: every leg valued at the target time with
    its own IV and its expiry's q (+ dq). The price per unit is rounded to the paisa like the Estimated Now check."""
    tot, gtot, per_leg = Decimal(0), dict.fromkeys(TARGET_GREEKS, 0.0), []
    for lg in legs:
        t = years_to_expiry(at, lg["expiry"])
        k, sig, q = float(lg["strike"]), float(lg["iv"]), qmap[lg["expiry"]][0] + dq
        px = money(bsm_price(level, k, t, r, q, sig, lg["instrument"]))
        tot += (px - D(lg["planned_entry"])) * D(lg["quantity"]) * _sign(lg)
        g = bsm_greeks(level, k, t, r, q, sig, lg["instrument"]) if t > 0 else dict.fromkeys(TARGET_GREEKS, 0.0)
        w = float(lg["quantity"]) * _sign(lg)
        per_leg.append({n: g[n] * w for n in TARGET_GREEKS})
        for n in TARGET_GREEKS:
            gtot[n] += g[n] * w
    return tot, gtot, per_leg


def target_breakevens(legs, qmap, at, r, lo, hi, step=5.0, shift=0.0) -> list:
    """This file's own crossings of the recomputed target curve: scan [lo, hi], bisect each sign change. `shift` is
    added to the curve first (ADR-209: a paper strategy's booked P&L), so the crossings are where open P&L = -shift."""

    def f(x):
        return float(_target_model(legs, qmap, x, at, r)[0]) + shift

    out, x, fx = [], lo, f(lo)
    while x < hi:
        nx = min(x + step, hi)
        fn = f(nx)
        if fx * fn < 0:
            a, b, fa = x, nx, fx
            for _ in range(60):
                m = 0.5 * (a + b)
                fm = f(m)
                if fa * fm <= 0:
                    b = m
                else:
                    a, fa = m, fm
            out.append(0.5 * (a + b))
        elif fn == 0:
            out.append(nx)
        x, fx = nx, fn
    return out


def check_target(reply: dict, r: float = RISK_FREE_RATE, booked=None) -> Report:
    """REQ-084 AC-4: recompute the reply's `target` block (P&L, breakevens, the four Greeks at the target level and
    date) with this file's own BSM and compare. No target figures in the reply -> not checkable, never a match.
    With `booked` (the strategy's booked P&L, given by the caller) the expected basis is open legs plus booked, as
    ADR-209 decides for a paper strategy with Add Booked P&L ON: the P&L and the breakevens (crossings of the curve
    shifted by booked) are compared on that basis, and the open-legs-only P&L is printed as a note. Without it the
    expected basis is open legs only."""
    rep = Report("target what-if")
    tg = (reply or {}).get("target") or {}
    if not tg.get("level") or not tg.get("at") or (tg.get("pnl") or {}).get("value") is None:
        rep.skip("target figures", "the reply has no target P&L (no target asked, refused, or unavailable)")
        return rep
    legs = reply.get("legs") or []
    if not legs or any(lg.get("iv") is None for lg in legs):
        rep.skip("target figures", "a leg has no IV")
        return rep
    qmap = target_q_by_expiry(reply, r)
    if any(lg["expiry"] not in qmap for lg in legs):
        rep.skip("target figures", "no dividend yield could be solved from the reply's legs")
        return rep
    level, at = float(tg["level"]), dt.datetime.fromisoformat(tg["at"])
    pnl, gtot, per_leg = _target_model(legs, qmap, level, at, r)
    spread = max(v[1] for v in qmap.values())
    qty = sum(abs(float(lg["quantity"])) for lg in legs)
    wide = _target_model(legs, qmap, level, at, r, spread / 2)
    # the Estimated Now tolerance rule: 0.005/unit/leg rounding + the move from the q spread across the legs
    tol = Decimal(str(round(qty * 0.0051 + abs(float(wide[0] - pnl)), 2)))
    qtxt = ", ".join(f"{e}: {v[0]:.5f}" for e, v in sorted(qmap.items()))
    rep.notes.append(f"target level {tg['level']} at {tg['at']}; q solved per expiry {qtxt}")
    if booked is None:
        rep.add("target P&L (open legs only)", tg["pnl"]["value"], money(pnl), tol, note="this file's BSM, target time")
    else:
        rep.notes.append(f"open legs only (not compared, ADR-209): {money(pnl)}")
        both = money(pnl + D(booked))
        rep.add("target P&L (open legs + booked)", tg["pnl"]["value"], both, tol, note=f"booked {booked}")
    shift = float(D(booked)) if booked is not None else 0.0
    want_be = target_breakevens(legs, qmap, at, r, level * 0.5, level * 1.5, shift=shift)
    if tg.get("breakevens") is None:
        rep.skip("target breakevens", tg.get("breakevens_reason") or "reply gives no breakevens")
    else:
        slopes = [
            abs(float(_target_model(legs, qmap, x + 1, at, r)[0] - _target_model(legs, qmap, x - 1, at, r)[0])) / 2
            for x in want_be
        ]
        be_tol = Decimal(str(round(max(float(tol) / max(min(slopes, default=1.0), 1.0), 0.05), 2)))
        rep.add_list("target breakevens", tg["breakevens"], [Decimal(str(round(x, 2))) for x in want_be], be_tol,
                     note="crossings of this file's recomputed target curve; tol = P&L tol / slope")
    greeks = tg.get("greeks") or {}
    g_tol = {n: Decimal(str(round(0.001 + abs(wide[1][n] - gtot[n]), 4))) for n in TARGET_GREEKS}
    for n in TARGET_GREEKS:
        got = (greeks.get("total") or {}).get(n)
        if got is None:
            rep.skip(f"target {n}", greeks.get("unavailable_text") or "reply gives no value")
        else:
            rep.add(f"target {n}", got, round(Decimal(str(gtot[n])), 4), g_tol[n], note="total over the legs")
    for i, row in enumerate(greeks.get("legs") or []):
        for n in TARGET_GREEKS:
            if row and row.get(n) is not None and i < len(per_leg):
                rep.add(f"target leg{i + 1} {n}", row[n], round(Decimal(str(per_leg[i][n])), 4), g_tol[n])
    return rep


def print_table(rep: Report) -> None:
    """The match / mismatch table of one report on stdout (the paper-orders mode)."""
    print(f"## {rep.strategy}: {rep.counts()}")
    print("| figure | reply | recomputed | verdict |")
    print("|---|---|---|---|")
    for f in rep.figures:
        print(f"| {f.name} | {f.ours} | {f.independent} | {f.verdict} |")



# ---------------------------------------------------------------- output


def write_report(reports, out: Path, stem: str):
    out.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "strategy": r.strategy,
            "counts": r.counts(),
            "notes": r.notes,
            "figures": [asdict(f) for f in r.figures],
            "data_rows": r.data_rows,
        }
        for r in reports
    ]
    (out / f"{stem}.json").write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    lines = []
    for r in reports:
        c = r.counts()
        lines += [
            f"## {r.strategy}",
            "",
            f"match {c[MATCH]} / mismatch {c[MISMATCH]} / not checkable {c[NOT_CHECKABLE]}",
            "",
        ]
        lines += [f"- note: {n}" for n in r.notes]
        lines += [
            "| figure | ours (API) | independent | abs diff | tolerance | verdict | note |",
            "|---|---|---|---|---|---|---|",
        ]
        for f in r.figures:
            lines.append(
                f"| {f.name} | {f.ours} | {f.independent} | {f.abs_diff} | {f.tolerance} | {f.verdict} | {f.note} |"
            )
        lines += ["", "### Data rows", "", "```json", json.dumps(r.data_rows, indent=1, default=str), "```", ""]
    (out / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- live fetch / replay


def _http(base, path, body=None):
    if not base.startswith("http://127.0.0.1"):
        raise SystemExit("refusing a non-local API base: the checker reads only the local app")
    req = urllib.request.Request(  # noqa: S310 - base checked to be local http above
        base + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - base checked to be local http above
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"state": "REFUSED", "reason": f"HTTP {e.code}", "_body": e.read().decode()[:500]}


def fetch_live(base, legs_doc, outdir: Path):
    # the legs file names each expiry its legs use (meta[]._expiry or expiries[]): the chain is read per expiry
    meta = legs_doc.get("meta", [])
    expiries = sorted({m["_expiry"] for m in meta if "_expiry" in m}) or legs_doc.get("expiries", [])
    if not expiries:  # learn the legs' expiries from one read-only outcome call
        probe = _http(
            base,
            "/api/strategies/outcome",
            {"underlying": legs_doc["underlying"], "view": "at_expiry", "legs": legs_doc["legs"]},
        )
        expiries = sorted({lg["expiry"] for lg in probe.get("legs") or [] if lg.get("expiry")})

    def chain(e):
        q = f"underlying={legs_doc['underlying']}&expiry={e}&strikes_each_side=10&bid_and_ask=true"
        return _http(base, f"/api/market/chain?{q}")

    for e in expiries:
        _http(base, f"/api/leg-picker/strikes?underlying={legs_doc['underlying']}&expiry={e}&width=10")
    time.sleep(4)
    saved = {f"chain_before_{e}": chain(e) for e in expiries}
    for view in ("estimated_now", "at_expiry"):
        saved[f"outcome_{view}"] = _http(
            base,
            "/api/strategies/outcome",
            {"underlying": legs_doc["underlying"], "view": view, "legs": legs_doc["legs"]},
        )
    saved.update({f"chain_after_{e}": chain(e) for e in expiries})
    saved["futures"] = _http(base, f"/api/leg-picker/futures?underlying={legs_doc['underlying']}")
    outdir.mkdir(parents=True, exist_ok=True)
    for k, v in saved.items():
        (outdir / f"{k}.json").write_text(json.dumps(v, indent=1), encoding="utf-8")
    return outdir


def load_replay(d: Path):
    def j(name):
        p = d / name
        return json.loads(p.read_text()) if p.exists() else None

    est, atx = j("outcome_estimated_now.json"), j("outcome_at_expiry.json")
    before, after = {}, {}
    for p in sorted(d.glob("chain_*.json")):
        c = json.loads(p.read_text())
        store = before if p.name.startswith("chain_before") else after
        if c.get("expiry"):
            store[c["expiry"]] = c
    return est, atx, before, after, j("futures.json")


def load_both(d: Path):
    """GC-UI step 4: the reply asked with the new options (outcome_both.json) and the request's options
    (request_both.json, its payoff_step read from there); (None, None) when the folder has none."""
    p, q = d / "outcome_both.json", d / "request_both.json"
    if not p.exists():
        return None, None
    req = json.loads(q.read_text(encoding="utf-8")) if q.exists() else {}
    return json.loads(p.read_text(encoding="utf-8")), req.get("payoff_step")


def fetch_both(base, legs_doc, outdir: Path, flags: dict):
    """Live: one read-only POST outcome with the new options, saved beside the other replies."""
    body = {"underlying": legs_doc["underlying"], "view": "at_expiry", "legs": legs_doc["legs"], **flags}
    (outdir / "outcome_both.json").write_text(json.dumps(_http(base, "/api/strategies/outcome", body), indent=1),
                                              encoding="utf-8")
    (outdir / "request_both.json").write_text(json.dumps(flags), encoding="utf-8")


def fetch_target(base, legs_doc, outdir: Path, level, at, paper_id=None) -> None:
    """Live: one read-only POST outcome asking the what-if target, saved as outcome_target.json. With `paper_id` the
    request names the paper strategy, as the builder does with Add Booked P&L ON (ADR-209): the server adds booked."""
    body = {"underlying": legs_doc["underlying"], "view": "estimated_now", "legs": legs_doc["legs"]}
    if paper_id is not None:
        body["paper_strategy_id"] = int(paper_id)
    if level:
        body["target_level"] = str(level)
    if at:
        body["target_at"] = at
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "outcome_target.json").write_text(json.dumps(_http(base, "/api/strategies/outcome", body), indent=1),
                                                encoding="utf-8")


def main_paper_orders(a) -> int:
    """--paper-orders <id>: one read-only GET of /paper/strategies/{id} (or <replay>/paper_<id>.json), recomputed from
    its orderbook rows; prints the match / mismatch table; exit 1 when any figure differs or none could be checked."""
    path = f"paper_{a.paper_orders}.json"
    if a.replay:
        reply = json.loads((Path(a.replay) / path).read_text(encoding="utf-8"))
    else:
        reply = _http(a.api, f"/paper/strategies/{a.paper_orders}")
    rep = check_paper_orders(reply)
    write_report([rep], Path(a.out), f"paper-orders-{a.paper_orders}")
    print_table(rep)
    counts = rep.counts()
    return 1 if counts[MISMATCH] or not counts[MATCH] else 0


def main(argv=None):
    # The server's display text carries U+2212 minus; a cp1252 console cannot print it (GC-TP 2026-10-29), so every
    # mode writes UTF-8 whatever the console's code page.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--strategy-legs")
    ap.add_argument("--paper", type=int)
    ap.add_argument("--paper-orders", type=int, help="GC-TP 1b: recompute a paper strategy from its orders")
    ap.add_argument("--replay")
    ap.add_argument("--out", required=True)
    ap.add_argument("--api", default="http://127.0.0.1:8765")
    ap.add_argument("--both", action="store_true", help="live: also ask both_views + sd_bands (GC-UI step 4)")
    ap.add_argument("--payoff-step", type=int, help="live with --both: the payoff_step asked (absent: none sent)")
    ap.add_argument("--target-level", help="GC-TP 6c: ask the what-if target level (points) and recompute its figures")
    ap.add_argument("--target-at", help="GC-TP 6c: ask the what-if target time (ISO, with offset) and recompute")
    ap.add_argument("--booked", help="GC-TP 6c: the strategy's booked P&L, for the open + booked P&L basis")
    ap.add_argument("--paper-strategy-id", help="GC-TP R-18: send paper_strategy_id with the target request (ADR-209)")
    a = ap.parse_args(argv)
    if a.paper_orders is not None:
        return main_paper_orders(a)
    if not a.strategy_legs:
        ap.error("--strategy-legs is required unless --paper-orders is given")
    legs_doc = json.loads(Path(a.strategy_legs).read_text())
    name = Path(a.strategy_legs).resolve().parent.name
    src = Path(a.replay) if a.replay else fetch_live(a.api, legs_doc, Path(a.out) / f"raw-{name}")
    if a.both and not a.replay:
        flags = {"both_views": True, "sd_bands": True}
        if a.payoff_step is not None:
            flags["payoff_step"] = a.payoff_step
        fetch_both(a.api, legs_doc, src, flags)
    if (a.target_level or a.target_at) and not a.replay:
        fetch_target(a.api, legs_doc, src, a.target_level, a.target_at, a.paper_strategy_id)
    est, atx, before, after, fut = load_replay(src)
    both, step_asked = load_both(src)
    reports = [check_outcome(name, est, atx, before, after, fut, both=both, step_asked=step_asked)]
    if a.target_level or a.target_at or (src / "outcome_target.json").exists():
        tj = src / "outcome_target.json"
        reports.append(check_target(json.loads(tj.read_text(encoding="utf-8")) if tj.exists() else {}, booked=a.booked))
        print_table(reports[-1])
    if a.paper:
        tp = src / f"tracking_{a.paper}.json"
        tr = (
            json.loads(tp.read_text())
            if a.replay and tp.exists()
            else (None if a.replay else _http(a.api, f"/strategies/{a.paper}/tracking"))
        )
        if tr is None and a.replay:
            tp2 = src.parent / f"tracking_{a.paper}.json"
            tr = json.loads(tp2.read_text()) if tp2.exists() else None
        reports.append(check_paper(tr or {}, (est or {}).get("legs") or []))
    write_report(reports, Path(a.out), name)
    for r in reports:
        print(r.strategy, r.counts())
    return 0


if __name__ == "__main__":
    sys.exit(main())
