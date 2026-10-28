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
- Charge rates are the seed table; an admin rate row added later is not seen (the reply's `rates_read_on` is checked
  against the seed date and flagged when it differs).

CLI: python scripts/checks/ui_data_check.py --strategy-legs <legs.json> [--paper <id>] [--replay <dir>] --out <dir>
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
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
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


def parity_forward(chain: dict, t: float, r: float):
    """ADR-061: F = median over two-sided strikes of K + e^(rT)(Cmid - Pmid). Returns (F, q, n, reason)."""
    spot = D(chain.get("spot")) if chain else None
    if not chain or chain.get("state") != "LIVE" or spot is None:
        return None, None, 0, "chain not live"
    vals = []
    for row in chain.get("rows") or []:
        ce, pe = row.get("ce") or {}, row.get("pe") or {}
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


def round_trip_charges(legs, rates=CHARGE_RATES, mode=ROUND_HALF_UP, gst_on_unrounded=False) -> dict:
    """Enter every leg and square it off at the same price: 2 orders per leg; STT on each sell side; stamp on each
    buy side; exchange + SEBI on all premium turnover; GST on brokerage + exchange + SEBI."""
    turnover = sell_side = buy_side = Decimal(0)
    for leg in legs:
        v = D(leg["planned_entry"]) * D(leg["quantity"])
        turnover += 2 * v
        sell_side += v
        buy_side += v
    orders = 2 * len(legs)
    brokerage = money(rates["brokerage_per_order"] * orders, mode)
    stt = money(rates["stt_sell_rate"] * sell_side, mode)
    exch = money(rates["transaction_rate_nse_fo"] * turnover, mode)
    sebi = money(rates["sebi_rate"] * turnover, mode)
    stamp = money(rates["stamp_buy_rate"] * buy_side, mode)
    gst_base = (
        brokerage + rates["transaction_rate_nse_fo"] * turnover + rates["sebi_rate"] * turnover
        if gst_on_unrounded
        else brokerage + exch + sebi
    )
    gst = money(rates["gst_rate"] * gst_base, mode)
    return {
        "brokerage": brokerage,
        "stt": stt,
        "exchange_transaction": exch,
        "gst": gst,
        "stamp": stamp,
        "sebi": sebi,
        "total": brokerage + stt + exch + gst + stamp + sebi,
    }


# ---------------------------------------------------------------- the check


def _cells(reply, row_id):
    for row in (reply.get("table") or {}).get("rows") or []:
        if row["row_id"] == row_id:
            return {k: v.get("value") for k, v in row["cells"].items()}
    return None


def _sign(leg):
    return 1 if leg["action"] == "BUY" else -1


FORWARD_BAND_POINTS = 1.0  # parity F from mids moved 0.5-0.7 points between two reads ~2 s apart (2026-10-28 live)


def _q_band(chain, fb, fa, qb, t, r) -> dict:
    """The model's q: the mid of the F read before and after the reply; the band: +/- (half their gap + 1 point).
    The server reads its own snapshot between the two, so its q lies in the band, not at our point."""
    if fb is None or chain is None or chain.get("spot") is None or t <= 0:
        return {"q_mid": qb, "q_hi": qb, "F_band_points": None}
    fa = fa if fa is not None else fb
    s = float(chain["spot"])
    fmid, half = (fb + fa) / 2, abs(fb - fa) / 2 + FORWARD_BAND_POINTS
    return {"q_mid": r - math.log(fmid / s) / t, "q_hi": r - math.log((fmid - half) / s) / t, "F_band_points": half}


def check_outcome(name, est, atx, chains_before, chains_after, futures=None, r=RISK_FREE_RATE) -> Report:
    """est / atx: the outcome replies for view=estimated_now / at_expiry; chains_*: {expiry: chain reply}."""
    rep = Report(name)
    for view, reply in (("estimated_now", est), ("at_expiry", atx)):
        state = (reply or {}).get("state")
        if state != "COMPUTED":
            rep.skip(f"[{view}] every figure", f"reply state {state} ({(reply or {}).get('reason')})")
    if (est or {}).get("state") != "COMPUTED":
        return rep
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
                (tot_pnl / abs(tot_entry) * 100).quantize(q_, rounding=ROUND_HALF_UP) if tot_entry else None,
                note=f"ours = unrealized / net entry value, at the reply's {dp} dp",
                alt=(tot_pnl / risk_base * 100).quantize(q_, rounding=ROUND_HALF_UP) if risk_base else None,
                alt_label="unrealized / pre-charges max loss",
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
    ch_unr = round_trip_charges(legs, gst_on_unrounded=True)
    for k, v in ch.items():
        rep.add(f"charges {k}", cb.get(k), v, alt=ch_unr[k], alt_label="GST-on-unrounded-components")
    comps = [cb.get(k) for k in ("brokerage", "stt", "exchange_transaction", "gst", "stamp", "sebi")]
    if all(c is not None for c in comps):
        rep.add(
            "charges total = sum of the reply's own shown components",
            cb.get("total"),
            sum((D(c) for c in comps), Decimal(0)),
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
        fs = summ.get("funds_share") or {}
        funds = D(fs.get("funds"))
        if funds and mp is not None:
            rep.add(
                "funds_share max_profit_percent",
                fs.get("max_profit_percent"),
                (mp / funds * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP),
                note="whole percent",
            )
        if funds and ml is not None:
            rep.add(
                "funds_share max_loss_percent",
                fs.get("max_loss_percent"),
                (ml / funds * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP),
                note="whole percent",
            )
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
        qinfo[e].update(_q_band(chains_before.get(e), fb, fa, qb, t, r))
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

    if est.get("status_label") or est.get("output_label"):
        rep.notes.append(f"reply label: {est.get('status_label') or est.get('output_label')}")
    s = float(spot)
    quotes = {q["instrument_id"]: q for q in est.get("leg_quotes") or []}
    leg_model = []
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
        iv_mid = implied_vol(mid, s, k, t, r, q, leg["instrument"]) if mid is not None else None
        iv_ltp = implied_vol(float(leg["ltp"]), s, k, t, r, q, leg["instrument"]) if leg.get("ltp") else None
        iv_mid_spot = implied_vol(mid, s, k, t, r, 0.0, leg["instrument"]) if mid is not None else None
        ours_iv = iv_mid if iv_mid is not None else iv_ltp
        # IV tolerance: 0.0001 for the 6 dp print + the IV change across the q read before and after the reply.
        qa_ = qi["q_hi"] if qi["q_hi"] is not None else q
        px_basis = mid if mid is not None else (float(leg["ltp"]) if leg.get("ltp") else None)
        iv_alt = implied_vol(px_basis, s, k, t, r, qa_, leg["instrument"]) if px_basis is not None else None
        iv_tol = Decimal("0.0001") + Decimal(str(round(abs((iv_alt or ours_iv or 0) - (ours_iv or 0)), 6)))
        if iv_reply is None:
            rep.skip(f"leg{i + 1} iv", "reply iv null")
        else:
            rep.add(
                f"leg{i + 1} iv (fraction; ours from {'mid' if iv_mid is not None else 'ltp'}, parity q)",
                iv_reply,
                None if ours_iv is None else round(ours_iv, 6),
                iv_tol,
                note="6 dp print + IV change across the forward band",
            )
        rep.data_rows.setdefault("D-B35/36 iv basis", {})[f"leg{i + 1}"] = {
            "reply_iv": iv_reply,
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
            rep.data_rows.setdefault("D-B35/36 greek unit", {})[f"leg{i + 1}"] = {
                "reply_delta": c.get("delta"),
                "ours_per_unit_delta": round(g["delta"], 4),
                "ours_per_position_delta": round(g["delta"] * qty, 4),
            }

    # Estimated-Now scenario points
    pts = (est.get("payoff") or {}).get("points") or []
    if not pts:
        rep.skip("[estimated_now] payoff points", "empty payoff")
    elif any(m[1] is None for m in leg_model):
        rep.skip("[estimated_now] payoff points", "a leg has no IV")
    else:
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
                f"[estimated_now] payoff @{p['level']}",
                p.get("pnl"),
                money(tot),
                tol + Decimal(str(round(drift, 2))),
                note="0.005/unit/leg rounding + forward band (before/after gap/2 + 1 pt)",
            )

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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--strategy-legs", required=True)
    ap.add_argument("--paper", type=int)
    ap.add_argument("--replay")
    ap.add_argument("--out", required=True)
    ap.add_argument("--api", default="http://127.0.0.1:8765")
    a = ap.parse_args(argv)
    legs_doc = json.loads(Path(a.strategy_legs).read_text())
    name = Path(a.strategy_legs).resolve().parent.name
    src = Path(a.replay) if a.replay else fetch_live(a.api, legs_doc, Path(a.out) / f"raw-{name}")
    est, atx, before, after, fut = load_replay(src)
    reports = [check_outcome(name, est, atx, before, after, fut)]
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
