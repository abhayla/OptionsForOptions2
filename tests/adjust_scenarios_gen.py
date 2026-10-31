# ruff: noqa: E501, PLR2004, PLR0913, PERF401, C416, RUF005 - generator data tables (one scenario or catalogue row per line)
"""Generator of the adjustment scenario library (tests/fixtures/adjust_scenarios/, owner 2026-10-30: "Create test data
for all scenarios and use it for testing as getting live market data for all scenarios is not possible").

Run: ``python tests/adjust_scenarios_gen.py [out_dir]`` (default: the fixture folder). The output is deterministic:
the same inputs give byte-identical files (tests/test_adjust_scenarios.py regenerates into a temp dir and compares).

Two independent paths, on purpose:

- MARKET data (chains: LTP, bid/ask, IV, delta, gamma) is synthetic and comes from the repo's own Black-Scholes
  (``ofo.engine.black_scholes``), the one model the app prices with. Nothing here is a captured quote (public repo).
- EXPECTED values (at-expiry max profit, max loss, breakevens, stage, triggers, approaches, day rules) are derived
  here by plain, readable code from the inputs: intrinsic values in exact fractions, no ``ofo.engine`` metrics, P&L
  or strategy import. The test then asks the engine for the same numbers, so the two paths check each other.

Conventions (also written into ``_playbooks.json`` -> ``conventions``):

- Rate 6.5% (admin default, Q248), calendar days / 365 to 15:30 IST, no dividend yield.
- IV smile per strike: ATM IV + 0.012 per 1% the strike is below spot, + 0.004 per 1% above (one IV per strike for
  CE and PE). ATM IV 13% NIFTY weekly, 14% SENSEX, calibrated to the real 30 Oct 2026 NIFTY chain of the core proof
  (spot 23,020, lot 65; spec/findings.md F-73). SENSEX lot 20.
- Price = BS rounded to the 0.05 tick (minimum 0.05); bid/ask = mid -/+ max(0.05, 0.5% of mid) rounded up to the tick.
- Days left = calendar days from the clock's date to the expiry date (0 on expiry day), as the mockup's stages use.
- P&L now marks every open leg at its LTP and adds booked P&L of closed legs (whole trade, F-74).
"""
from __future__ import annotations

import datetime
import json
import math
import sys
from decimal import ROUND_CEILING, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:  # run as a script
    sys.path.insert(0, str(ROOT / "backend"))

from ofo.adjustment.playbook_eval import T14_PENDING, reason_text  # noqa: E402
from ofo.engine.black_scholes import IST, bs_greeks_unrounded, bs_price, year_fraction  # noqa: E402
from ofo.engine.legs import Instrument  # noqa: E402

D = Decimal
OUT_DIR = ROOT / "tests" / "fixtures" / "adjust_scenarios"
CALENDAR = ROOT / "backend" / "ofo" / "market_calendar.json"
RATE = D("0.065")
TICK = D("0.05")
UNDERLYINGS = {
    "NIFTY": {"lot": 65, "step": 50, "exchange": "NFO", "atm_iv": "0.13", "weekly_weekday": 1},
    "SENSEX": {"lot": 20, "step": 100, "exchange": "BFO", "atm_iv": "0.14", "weekly_weekday": 3},
}
MONTH_CODE = "123456789OND"

# ---------------------------------------------------------------------------------------------------------------------
# The DRAFT system playbooks, copied from the published mockup screen 4 (ADR-214 (4a)-(4d), catalogue Part 3 incl.
# variants, PB-04). Stages: weekly Early 5+, Middle 2-4, Last day 0-1; monthly Early 10+, Middle 3-9, Last 2 days 0-2.
# ---------------------------------------------------------------------------------------------------------------------
FAMILIES = [
    ("strangle", "Short strangle"), ("straddle", "Short straddle"), ("ic", "Iron condor"), ("ifly", "Iron butterfly"),
    ("credit", "Credit spreads"), ("debit", "Debit spreads"), ("longopt", "Single long option"),
    ("longvol", "Long straddle / strangle"), ("calendar", "Calendar / diagonal"), ("ratio", "Ratio and back-spreads"),
    ("dirfly", "Directional butterflies / condors"), ("other", "Naked shorts, futures, others"),
]
SHORTS = ["strangle", "straddle", "ic", "ifly", "credit", "ratio", "other", "calendar"]
TWO_SIDED = ["strangle", "straddle", "ic", "ifly"]
NAKED = ["strangle", "straddle", "ratio", "other"]
LONGS = ["longopt", "longvol"]
DATA_NOTE = {"ok": "", "hist": "Needs price history (not in V1)", "vix": "Needs India VIX feed (owner: later)",
             "user": "You type the level"}
# id, label, unit, cmp, weekly, monthly, on by default, data, fit (mode, families, reason) or None
TRIGGERS = [
    ("T-01", "Spot within this % of a short strike", "%", "le", ["0.75", "0.5", "0.3"], ["1.5", "1.0", "0.5"], True, "ok", ("not", LONGS, "No short strike")),
    ("T-01b", "Spot within this many points of a short strike", "pts", "le", ["180", "120", "70"], ["350", "240", "120"], False, "ok", ("not", LONGS, "No short strike")),
    ("T-02", "Spot crosses a breakeven", "", "", None, None, True, "ok", None),
    ("T-12", "Spot has moved this many expected moves (SD) since entry", "SD", "ge", ["1", "1", "1"], ["1", "1", "1"], False, "ok", None),
    ("T-13", "Gap at the open of at least this %", "%", "ge", ["0.75", "0.75", "0.5"], ["1", "1", "0.75"], True, "ok", None),
    ("T-20", "Spot crosses a level you set (support / resistance)", "pts", "", None, None, False, "user", None),
    ("T-20b", "Market trending vs range-bound", "", "", None, None, False, "hist", None),
    ("T-03", "Tested short's delta reaches", "delta", "ge", ["0.30", "0.35", "0.40"], ["0.25", "0.30", "0.35"], True, "ok", ("not", LONGS, "No short leg")),
    ("T-04", "Net delta beyond +/- this per lot", "delta/lot", "ge", ["0.15", "0.15", "0.20"], ["0.15", "0.15", "0.20"], False, "ok", None),
    ("T-14", "Loss from a 1% move (gamma) at least this % of margin", "%", "ge", ["3", "3", "2"], ["4", "3", "2"], True, "ok", None),
    ("T-14v", "Loss from +1 IV point (vega) at least this % of max profit", "%", "ge", ["10", "10", "10"], ["15", "15", "10"], False, "ok", None),
    ("T-14t", "Theta per day falls below this % of premium left", "%", "le", ["5", "5", "5"], ["3", "3", "3"], False, "ok", ("not", LONGS, "Long options pay theta")),
    ("T-11", "Options' IV changed this many points since entry", "pts", "ge", ["3", "3", "4"], ["3", "3", "4"], True, "ok", None),
    ("T-11b", "India VIX up this % today", "%", "ge", ["10", "10", "10"], ["10", "10", "10"], False, "vix", None),
    ("T-11c", "IV percentile above", "%", "ge", ["80", "80", "80"], ["80", "80", "80"], False, "hist", None),
    ("T-06", "Loss reaches this % of max loss", "%", "ge", ["50", "50", "40"], ["50", "50", "40"], True, "ok", None),
    ("T-06b", "Loss reaches this many x the credit received", "x", "ge", ["1", "1", "0.75"], ["1.5", "1", "0.75"], False, "ok", ("only", SHORTS, "No credit received")),
    ("T-07", "Profit reaches this % of max profit", "%", "ge", ["50", "50", "80"], ["50", "50", "75"], True, "ok", None),
    ("T-05", "One side's value is this many x the other side's", "x", "ge", ["3", "3", "4"], ["3", "3", "4"], False, "ok", ("only", TWO_SIDED, "Needs a call side and a put side")),
    ("T-08", "A leg's premium reaches this many x its entry (leg stop)", "x", "ge", ["2", "2", "2.5"], ["2", "2", "2.5"], False, "ok", None),
    ("T-09", "A short leg's premium falls below Rs (close for pennies)", "Rs", "le", ["3", "3", "2"], ["3", "3", "2"], True, "ok", ("only", SHORTS, "No short leg")),
    ("T-19", "Premium still left to earn is below this many x the adjustment's cost", "x", "le", ["2", "2", "2"], ["2", "2", "2"], True, "ok", ("only", SHORTS, "No premium to earn")),
    ("T-16", "Loss reaches this % of the margin blocked", "%", "ge", ["4", "4", "3"], ["4", "4", "3"], True, "ok", None),
    ("T-10b", "Clock time reached (checked in this stage)", "time", "ge", ["", "", "14:30"], ["", "", "14:30"], True, "ok", None),
    ("T-15", "Margin used reaches this % of available", "%", "ge", ["80", "80", "80"], ["80", "80", "80"], False, "ok", None),
    ("T-18", "Adjustments used reach the plan's maximum", "", "", None, None, True, "ok", None),
    ("T-21", "Prices stale or missing (no suggestion is made)", "", "", None, None, True, "ok", None),
]
# Triggers this library evaluates. T-14 is on in the draft but its formula (loss from a 1% move) is not settled; the
# GC-ADJ1 build defines it, so it is listed as not evaluated rather than guessed.
EVALUATED = ["T-01", "T-02", "T-03", "T-06", "T-07", "T-09", "T-10b", "T-11", "T-13", "T-16", "T-18", "T-19", "T-21"]
NOT_EVALUATED = {"T-14": reason_text(T14_PENDING)}  # the catalogue text of the evaluator's reason code
TIGHTENED = ["T-01", "T-03", "T-06", "T-07", "T-09", "T-11", "T-13", "T-16", "T-19"]
# Per-family values that differ from the catalogue (screen 4) values, and the families whose numbers the owner approved.
# ADR-216 (owner 2026-10-31): the iron condor ships screen 4's per-stage values except T-19 = 1x the adjustment's cost.
FAMILY_TRIGGER_VALUES = {"ic": {"T-19": {"weekly": ["1", "1", "1"], "monthly": ["1", "1", "1"]}}}
APPROVED = {"ic": "ADR-216"}
# F-71: distance triggers are judged on the crossing, not the level - one that already holds at entry is "already
# true" until a check finds it false. Every library scenario is a first check, so held at entry and now = already true.
CROSSING = ["T-01"]
# id, label, on by default, note, fit
APPROACHES = [
    ("A-01", "Roll the untested side toward spot", True, "", ("only", TWO_SIDED, "Needs two sides")),
    ("A-02", "Roll the tested short away", True, "", ("only", SHORTS, "No short leg")),
    ("A-05", "Roll the tested spread (keep width)", True, "", ("only", ["ic", "ifly", "credit", "debit", "dirfly"], "No spread to roll")),
    ("A-03", "Roll out in time (same strikes, next expiry)", False, "Avoid if an event falls before the new expiry", None),
    ("A-04", "Roll up/down and out (diagonal roll)", True, "", ("only", SHORTS, "No short leg")),
    ("A-06", "Shift a leg by +/- N strikes", True, "Building block for every roll", None),
    ("A-07", "Re-centre / reset around spot", False, "Max once per expiry", ("only", ["straddle", "ifly", "ic", "strangle", "calendar", "dirfly"], "Not a range trade")),
    ("A-08", "Straddle-ise (move the untested short to the tested strike)", False, "", ("only", ["strangle"], "Strangles only")),
    ("A-09", "Add wings (cap the loss)", True, "Before an event or overnight", ("only", NAKED, "Loss already capped")),
    ("A-10", "Inverted strangle", False, "Locks in the strike gap as a loss", ("only", ["strangle"], "Strangles only")),
    ("A-11", "Convert to iron butterfly", True, "Only with 3+ days left", ("only", ["ic"], "Iron condors only")),
    ("A-12", "Convert to a (broken-wing) butterfly", False, "", ("only", ["credit", "ic"], "Needs a credit spread")),
    ("A-13", "Jade lizard (no risk on one side)", False, "Only when credit > call-spread width", ("only", ["credit", "ic", "other"], "Needs a short put")),
    ("A-14", "Calendar / diagonal on the tested side", False, "Shows the expiry-day margin change", ("only", SHORTS, "No short leg")),
    ("A-15", "Ratio fix (buy back the extra short or add a far long)", True, "", ("only", ["ratio"], "Ratio spreads only")),
    ("A-16", "Long option to debit spread", True, "", ("only", ["longopt"], "Long options only")),
    ("A-17", "Roll a winning long up and take capital out", True, "", ("only", ["longopt"], "Long options only")),
    ("A-18", "Gamma scalp with futures", True, "", ("only", ["longvol"], "Long volatility only")),
    ("A-19", "Add a second calendar at the new spot", True, "", ("only", ["calendar"], "Calendars only")),
    ("A-20", "Delta hedge with futures", False, "For large size; margin heavy", None),
    ("A-21", "Delta hedge with a synthetic future", False, "", None),
    ("A-22", "Debit spread in the direction of the breach", False, "", ("only", SHORTS, "No short side to protect")),
    ("A-23", "Delta-neutral helper (calculator)", True, "A tool, not an order", None),
    ("A-24", "Take profit, whole strategy", True, "", None),
    ("A-25", "Take partial profit (close X%)", True, "", None),
    ("A-26", "Close the untested side for profit", True, "", ("only", TWO_SIDED, "Needs two sides")),
    ("A-27", "Buy back cheap shorts", True, "", ("only", SHORTS, "No short leg")),
    ("A-28", "Close the tested leg or spread", True, "", None),
    ("A-29", "Reduce lots on the tested side", True, "", None),
    ("A-31", "Exit whole strategy", True, "", None),
    ("A-35", "Time exit", True, "", None),
    ("A-32", "Stop-loss per leg", False, "Mostly an intraday style", None),
    ("A-33", "Move stop to cost after one stop", False, "", None),
    ("A-34", "Re-enter after a stop", False, "", None),
    ("A-30", "Add lots to the tested side", False, "Adds risk at the worst time", None),
    ("A-36", "No change (always shown as the baseline)", True, "", None),
    ("A-37", "Alert only / watch a level", True, "", None),
    ("A-38", "Pause monitoring until a time", True, "e.g. after a gap, until 09:30", None),
]
EXIT_REDUCE = ["A-23", "A-24", "A-25", "A-26", "A-27", "A-28", "A-29", "A-31", "A-35", "A-36", "A-37", "A-38"]
DAY_RULE_KINDS = [
    ("weekday", "Every week on"), ("beforeWeekend", "The last session before a weekend"),
    ("beforeHoliday", "The day before a market holiday"), ("afterBreak", "The first session after a weekend or holiday"),
    ("expiry", "Expiry day"), ("beforeExpiry", "The day before expiry"), ("monthlyWeek", "Monthly-expiry week"),
    ("dom", "Day of the month"), ("date", "A specific date"), ("event", "A known event day (needs the admin event list)"),
    ("away", "My unavailable days (fires the session before the first day)"),
]
DAY_ACTIONS = ["Run the carry check (overnight margin, gap loss)", "Show reduce / partial profit / exit",
               "Show add-hedge where it applies", "Pause suggestions", "Tighten every trigger by this %",
               "Prepare an exit for review", "Do not suggest rolls"]
SYSTEM_DAY_RULES = [
    {"on": True, "when": "beforeWeekend", "at": "15:00", "action": 0},
    {"on": True, "when": "beforeHoliday", "at": "15:00", "action": 0},
    {"on": True, "when": "expiry", "at": "13:00", "action": 4, "percent": "20"},
    {"on": False, "when": "away", "at": "14:30", "action": 1, "from": "", "to": ""},
    {"on": False, "when": "event", "at": "14:30", "action": 1},
]
SITUATIONS = [
    ("S-01", "Gap at the open", "Wait until 09:30 before suggesting, unless a short opens in the money"),
    ("S-02", "Trending day", "Show early rolls when net delta grows past 0.15 per lot"),
    ("S-03", "Range day", "Show only the profit target; no adjustments"),
    ("S-04", "IV jumps without a big move", "Show where the P&L came from; suggest No change unless an event is within 1 session"),
    ("S-05", "IV crush after an event", "Show take-profit at 40% of max profit"),
    ("S-06", "Afternoon carry check", "At 15:00: show overnight margin and the loss at +/-2% gap"),
    ("S-07", "Expiry day", "From 13:00: buy back shorts below Rs 2; close a position whose short is within 0.3% by 14:30; warn about STT on in-the-money options"),
    ("S-10", "Broker or data outage", "No suggestion; show the last good data and its age"),
    ("S-11", "Adjustment limit reached", "Only exit and reduce are offered"),
    ("S-12", "Big win early", "If profit reaches 40% of max profit on day 1, show take profit"),
]
GUARDS = {"profit_target_pct_of_max_profit": "50", "stop_line_pct_of_max_loss": "50", "max_adjustments": 2,
          "entry_guide": "shorts at 0.15 to 0.20 delta, wings 200 to 400 points out",
          "warn_cost_pct_of_premium_left": "50", "roll_debit_limit": "Rs 500 or 10% of max profit",
          "hide_spread_pct_of_mid_above": "5", "hide_oi_below": 10000, "order_sequence": "buy legs first; buy back shorts before selling hedges"}
STAGES = {"weekly": [{"name": "Early", "from": 5, "to": None}, {"name": "Middle", "from": 2, "to": 4},
                     {"name": "Last day", "from": 0, "to": 1}],
          "monthly": [{"name": "Early", "from": 10, "to": None}, {"name": "Middle", "from": 3, "to": 9},
                      {"name": "Last 2 days", "from": 0, "to": 2}]}
CONVENTIONS = {
    "rate": "0.065 continuous (admin default, Q248)",
    "time": "calendar days / 365 to 15:30 IST on the expiry date",
    "days_left": "calendar days from the clock's date to the expiry date; 0 on expiry day",
    "iv_smile": "ATM IV + 0.012 per 1% the strike is below spot + 0.004 per 1% above; one IV per strike; 4 dp",
    "atm_iv": "NIFTY 0.13 weekly, SENSEX 0.14 (calibrated to the real 30 Oct 2026 NIFTY chain, F-73)",
    "price": "Black-Scholes (ofo.engine.black_scholes) rounded half-up to the 0.05 tick, minimum 0.05",
    "bid_ask": "mid -/+ max(0.05, 0.5% of mid) rounded up to the tick; bid floored at 0",
    "oi": "lot x round(4000 / (1 + (strike steps from ATM / 5)^2))",
    "pnl_now": "open legs marked at LTP plus booked P&L of closed legs (whole trade, F-74)",
    "max_profit_loss_breakevens": "whole trade at expiry: sum of side x qty x (intrinsic - entry) plus booked P&L; "
                                  "evaluated at 0 and every strike plus the upper-tail slope; a breakeven that does not "
                                  "terminate in decimal is rounded half-even to 0.01",
    "premium_left": "sum over open short legs of LTP x qty minus the same over open long legs",
    "adjustment_cost": "sum over open legs of (ask - bid) x qty plus Rs 40 per open leg (close and reopen once)",
    "tighten": "'Tighten every trigger by X%': an 'le' limit is multiplied by (1 + X/100), a 'ge' limit by (1 - X/100); "
               "applies to " + ", ".join(TIGHTENED),
    "close": "a trigger not fired is 'close' when value >= 0.8 x limit (ge) or value <= 1.25 x limit (le)",
    "margin": "synthetic broker answer (not a Zerodha SPAN figure); stated per scenario",
    "symbols": "synthetic Kite-style tradingsymbols for the shape only; not in the instrument slice",
}


def _fit_reason(fit: tuple | None, fam: str) -> str:
    if fit is None:
        return ""
    mode, fams, why = fit
    return why if (fam in fams) == (mode == "not") else ""


def playbooks() -> dict:
    """The DRAFT system playbook of every family (mockup screen 4), weekly and monthly stage values."""
    fams = {}
    for fam, name in FAMILIES:
        trig_on, trig_greyed = [], []
        for tid, *_rest in TRIGGERS:
            on, data, fit = _rest[5], _rest[6], _rest[7]
            why = _fit_reason(fit, fam) or (DATA_NOTE[data] if data in ("hist",) else "")
            if why:
                trig_greyed.append({"id": tid, "reason": why})
            elif on:
                trig_on.append(tid)
        applicable, off, greyed = [], [], []
        for aid, _label, on, _note, fit in APPROACHES:
            why = _fit_reason(fit, fam)
            if why:
                greyed.append({"id": aid, "reason": why})
            elif on:
                applicable.append(aid)
            else:
                off.append(aid)
        fams[fam] = {"name": f"{name}: system default", "system": True,
                     "status": "APPROVED" if fam in APPROVED else "DRAFT",
                     **({"approved_by": APPROVED[fam]} if fam in APPROVED else {}),
                     "triggers_on": trig_on, "triggers_greyed": trig_greyed,
                     "trigger_values": FAMILY_TRIGGER_VALUES.get(fam, {}),
                     "approaches": {"applicable": applicable, "off_in_playbook": off, "greyed": greyed}}
    return {
        "source": "Published mockup screen 4 (claude.ai artifact RwzCxhDod7yVCk6TWrQc9e) and "
                  "docs/research/adjustments-catalogue-2026-10-30.md Part 3 (incl. variants) and PB-04; ADR-214 (4a)-(4d)",
        "status": "Iron condor (ic) APPROVED (ADR-216); every other family DRAFT: its numbers await owner approval "
                  "(catalogue Part 9b question 1)",
        "stages": STAGES,
        "triggers": {t[0]: {"label": t[1], "unit": t[2], "cmp": t[3], "weekly": t[4], "monthly": t[5],
                            "on_by_default": t[6], "data": t[7]} for t in TRIGGERS},
        "evaluated_in_library": EVALUATED,
        "tightened_by_day_rule": TIGHTENED,
        "crossing_triggers": CROSSING,
        "not_evaluated_in_library": NOT_EVALUATED,
        "approaches": {a[0]: {"label": a[1], "on_by_default": a[2], "note": a[3]} for a in APPROACHES},
        "exit_or_reduce_after_limit": EXIT_REDUCE,
        "day_rule_kinds": dict(DAY_RULE_KINDS),
        "day_rule_actions": DAY_ACTIONS,
        "day_rules": SYSTEM_DAY_RULES,
        "situations": {s[0]: {"name": s[1], "rule": s[2]} for s in SITUATIONS},
        "guards": GUARDS,
        "families": fams,
        "conventions": CONVENTIONS,
    }


# ---------------------------------------------------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------------------------------------------------
def holidays() -> dict[datetime.date, str]:
    data = json.loads(CALENDAR.read_text(encoding="utf-8"))
    return {datetime.date.fromisoformat(d): n for year in data["holidays"].values() for d, n in year}


HOLIDAYS = holidays()


def is_session(day: datetime.date) -> bool:
    return day.weekday() < 5 and day not in HOLIDAYS


def next_session(day: datetime.date) -> datetime.date:
    day += datetime.timedelta(days=1)
    while not is_session(day):
        day += datetime.timedelta(days=1)
    return day


def prev_session(day: datetime.date) -> datetime.date:
    day -= datetime.timedelta(days=1)
    while not is_session(day):
        day -= datetime.timedelta(days=1)
    return day


def check_expiry(underlying: str, expiry: datetime.date, kind: str) -> None:
    """NIFTY expires Tuesday, SENSEX Thursday (monthly = the last such weekday); a holiday moves it to the previous
    session (catalogue M-01, M-02)."""
    wd = UNDERLYINGS[underlying]["weekly_weekday"]
    nominal = expiry
    while nominal.weekday() != wd:
        nominal += datetime.timedelta(days=1)
    assert prev_session(nominal + datetime.timedelta(days=1)) == expiry, (underlying, expiry)
    if kind == "monthly":
        assert (nominal + datetime.timedelta(days=7)).month != nominal.month, (underlying, expiry, "not the last")


# ---------------------------------------------------------------------------------------------------------------------
# Synthetic market
# ---------------------------------------------------------------------------------------------------------------------
def to_tick(x: Decimal) -> Decimal:
    return max((x / TICK).quantize(D(1), rounding=ROUND_HALF_UP) * TICK, TICK).quantize(D("0.01"))


def up_tick(x: Decimal) -> Decimal:
    return ((x / TICK).quantize(D(1), rounding=ROUND_CEILING) * TICK).quantize(D("0.01"))


def iv_at(spot: Decimal, strike: Decimal, atm: Decimal) -> Decimal:
    pct = (strike - spot) / spot * 100
    skew = D("0.012") * -pct if pct < 0 else D("0.004") * pct
    return (atm + skew).quantize(D("0.0001"), rounding=ROUND_HALF_EVEN)


def option_row(kind: str, spot: Decimal, strike: Decimal, years: Decimal, atm: Decimal) -> dict:
    inst = Instrument(kind)
    iv = iv_at(spot, strike, atm)
    mid = to_tick(bs_price(inst, spot, strike, years, RATE, iv))
    half = up_tick(max(D("0.05"), mid * D("0.005")))
    g = bs_greeks_unrounded(inst, spot, strike, years, RATE, iv)
    return {"ltp": mid, "bid": max(mid - half, D("0.00")), "ask": mid + half, "iv": iv,
            "delta": g.delta.quantize(D("0.0001"), rounding=ROUND_HALF_EVEN),
            "gamma": g.gamma.quantize(D("0.000001"), rounding=ROUND_HALF_EVEN)}


def symbol(underlying: str, expiry: datetime.date, kind: str, strike: Decimal | None, monthly: bool) -> str:
    yy = expiry.strftime("%y")
    head = f"{underlying}{yy}{expiry.strftime('%b').upper()}" if monthly else \
        f"{underlying}{yy}{MONTH_CODE[expiry.month - 1]}{expiry.day:02d}"
    return f"{head}FUT" if kind == "FUT" else f"{head}{int(strike)}{kind}"


def futures_price(spot: Decimal, clock: datetime.datetime, expiry: datetime.date) -> Decimal:
    days = D((expiry - clock.date()).days)
    return to_tick(spot * (1 + RATE * days / 365))


def chain(underlying: str, spot: Decimal, clock: datetime.datetime, expiry: datetime.date, atm: Decimal,
          strikes_needed: list[Decimal]) -> list[dict]:
    u = UNDERLYINGS[underlying]
    step, lot = D(u["step"]), u["lot"]
    years = year_fraction(clock, expiry)
    atm_strike = (spot / step).quantize(D(1), rounding=ROUND_HALF_UP) * step
    lo = min([atm_strike, *strikes_needed]) - 8 * step
    hi = max([atm_strike, *strikes_needed]) + 8 * step
    rows = []
    k = lo
    while k <= hi:
        steps = abs(k - atm_strike) / step
        oi = lot * int((D(4000) / (1 + (steps / 5) ** 2)).quantize(D(1), rounding=ROUND_HALF_UP))
        for kind in ("CE", "PE"):
            r = option_row(kind, spot, k, years, atm)
            rows.append({"strike": k, "type": kind, **r, "oi": oi, "listed": True, "tradable": True,
                         "low_oi": {"state": "stated", "blocked": False}})
        k += step
    return rows


def entry_prices(underlying: str, legs: list[dict], clock: datetime.datetime, spot: Decimal, atm: Decimal) -> None:
    """Fill each leg's entry with the synthetic LTP at the entry moment (unless the scenario fixed it)."""
    for leg in legs:
        if "entry" in leg:
            continue
        if leg["type"] == "FUT":
            leg["entry"] = futures_price(spot, clock, leg["expiry"])
        else:
            years = year_fraction(clock, leg["expiry"])
            leg["entry"] = option_row(leg["type"], spot, leg["strike"], years, atm)["ltp"]


# ---------------------------------------------------------------------------------------------------------------------
# Hand-derived expected values (no engine import): exact fractions from intrinsic values
# ---------------------------------------------------------------------------------------------------------------------
def sign(side: str) -> int:
    return 1 if side == "BUY" else -1


def intrinsic(kind: str, strike: Fraction | None, x: Fraction) -> Fraction:
    if kind == "CE":
        return max(x - strike, Fraction(0))
    if kind == "PE":
        return max(strike - x, Fraction(0))
    return x


def hand_pnl_at(legs: list[dict], booked: Fraction, x: Fraction) -> Fraction:
    total = booked
    for leg in legs:
        strike = None if leg["strike"] is None else Fraction(leg["strike"])
        total += sign(leg["side"]) * leg["quantity"] * (intrinsic(leg["type"], strike, x) - Fraction(leg["entry"]))
    return total


def dec_text(value: Fraction) -> str:
    """Exact decimal text when ``value`` terminates in base 10, else rounded half-even to 0.01."""
    with localcontext() as ctx:
        ctx.prec = 60
        d = D(value.numerator) / D(value.denominator)
    if Fraction(d) != value:
        d = d.quantize(D("0.01"), rounding=ROUND_HALF_EVEN)
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text if text not in ("-0", "") else "0"


def hand_expiry(legs: list[dict], booked: Fraction, shift: Fraction = Fraction(0)) -> dict:
    """Whole-trade at-expiry max profit, max loss and breakevens of single-expiry ``legs`` plus ``booked``."""
    if len({leg["expiry"] for leg in legs}) != 1:
        return {"exact": False, "reason": "legs on more than one expiry: no exact at-expiry payoff (MultiExpiryError)"}
    base = booked + shift
    points = [Fraction(0)] + sorted({Fraction(leg["strike"]) for leg in legs if leg["strike"] is not None})
    values = [hand_pnl_at(legs, base, p) for p in points]
    slope = sum(sign(leg["side"]) * leg["quantity"] for leg in legs if leg["type"] in ("CE", "FUT"))
    max_profit = "UNLIMITED" if slope > 0 else dec_text(max(values))
    if slope < 0:
        max_loss = "UNLIMITED"
    else:
        low = min(values)
        max_loss = dec_text(-low) if low < 0 else "0"
    zeros = set()
    for i, v in enumerate(values):
        if v == 0:
            zeros.add(points[i])
        if i + 1 < len(values):
            w = values[i + 1]
            if (v < 0 < w) or (w < 0 < v):
                zeros.add(points[i] + (0 - v) * (points[i + 1] - points[i]) / (w - v))
    if slope != 0:
        x = points[-1] - values[-1] / slope
        if x > points[-1]:
            zeros.add(x)
    return {"exact": True, "max_profit": max_profit, "max_loss": max_loss,
            "breakevens": [dec_text(z) for z in sorted(z for z in zeros if z > 0)]}



# ---------------------------------------------------------------------------------------------------------------------
# Hand-derived approach legs (REQ-155 AC-1, AC-8; GC-ADJ1 design decisions). Written independently of
# backend/ofo/adjustment/approaches.py: the same stated rules over the plain scenario dicts, so the two paths check
# each other. Only the admin config FILE is shared (data, not code).
# ---------------------------------------------------------------------------------------------------------------------
APPROACH_CONFIG = json.loads((ROOT / "backend" / "ofo" / "adjustment" / "approach_config.json").read_text(encoding="utf-8"))
IC_APPROACHES = ["A-36", "A-01", "A-05", "A-29", "A-28", "A-11", "A-31"]


def hand_price(row: dict | None) -> Decimal | None:
    if row is None:
        return None
    if row["ltp"] is not None and row["ltp"] > 0:
        return row["ltp"].quantize(D("0.01"), rounding=ROUND_HALF_UP)
    if row["bid"] is not None and row["ask"] is not None and row["bid"] > 0 and row["ask"] > 0:
        return ((row["bid"] + row["ask"]) / 2).quantize(D("0.01"), rounding=ROUND_HALF_UP)
    return None


class HandRefused(Exception):
    pass


def hand_approaches(u: str, lot: int, kind: str, today: datetime.date, spot: Decimal, legs: list[dict],  # noqa: C901, PLR0912, PLR0915
                    rows: list[dict], booked: Fraction) -> tuple[dict, dict]:
    """Per approach: trades / After legs / closed legs (or the refusal), and the whole-trade at-expiry After."""
    expiry = legs[0]["expiry"]
    by = {(r["type"], r["strike"]): r for r in rows}
    listed = {(r["type"], r["strike"]) for r in rows if r["listed"]}
    pos = {("call" if x["type"] == "CE" else "put", "short" if x["side"] == "SELL" else "wing"): i for i, x in enumerate(legs)}
    cs, ps = legs[pos[("call", "short")]]["strike"], legs[pos[("put", "short")]]["strike"]
    tested = "call" if abs(cs - spot) <= abs(spot - ps) else "put"
    untested = "put" if tested == "call" else "call"
    target = D(APPROACH_CONFIG["target_short_delta"][kind])

    def name(x):
        """The catalogue's leg reference: 'Leg 4 (SELL NIFTY 23,700 CE, expiry 03 Nov 2026)' (number = position order)."""
        n = next(i for i, y in enumerate(legs) if y["tradingsymbol"] == x["tradingsymbol"]) + 1
        return f"Leg {n} ({x['side']} {u} {x['strike']:,} {x['type']}, expiry {x['expiry'].strftime('%d %b %Y')})"

    def price(x):
        p = hand_price(by.get((x["type"], x["strike"])))
        if p is None:
            raise HandRefused(f"{name(x)} has no price, and this approach trades it.")
        return p

    def close(x, lots):
        p = price(x)
        t = {"action": "BUY" if x["side"] == "SELL" else "SELL", "type": x["type"], "strike": x["strike"],
             "expiry": x["expiry"], "lots": lots, "quantity": lots * lot, "price": p, "tradingsymbol": x["tradingsymbol"]}
        c = {"side": x["side"], "type": x["type"], "strike": x["strike"], "expiry": x["expiry"], "lots": lots,
             "quantity": lots * lot, "entry": x["entry"], "exit": p, "tradingsymbol": x["tradingsymbol"]}
        return t, c

    def check_listed(targets):
        for i in sorted(targets):
            if (legs[i]["type"], targets[i]) not in listed:
                raise HandRefused(f"No {targets[i]:,} {legs[i]['type']} is listed for {expiry.strftime('%d %b %Y')}, "
                                  f"so leg {i + 1} cannot move there.")

    def reopen(targets, warnings):
        trades, after, closed = [], [], []
        for i, x in enumerate(legs):
            if i in targets and targets[i] != x["strike"]:
                t, c = close(x, x["lots"])
                new = {**x, "strike": targets[i]}
                r = by[(x["type"], targets[i])]
                if not r["tradable"]:
                    raise HandRefused(f"{name(new)} cannot be traded from Zerodha's current data.")
                if r["low_oi"]["state"] == "stated" and r["low_oi"]["blocked"]:
                    raise HandRefused(f"Zerodha blocks fresh orders in {name(new)} because its open interest is low.")
                if r["low_oi"]["state"] != "stated":
                    warnings.append(f"Zerodha may refuse fresh orders in {name(new)}: its low open interest state is not known.")
                p = price(new)
                new = {**new, "entry": p, "tradingsymbol": r["tradingsymbol"]}
                trades += [t, {"action": x["side"], "type": x["type"], "strike": targets[i], "expiry": x["expiry"],
                               "lots": x["lots"], "quantity": x["lots"] * lot, "price": p, "tradingsymbol": r["tradingsymbol"]}]
                closed.append(c)
                after.append(new)
            else:
                after.append(x)
        return trades, after, closed

    def distance(short, out, basis):
        up = (short["type"] == "CE") == out
        cands = [r for r in rows if r["type"] == short["type"] and (r["strike"] > short["strike"] if up else r["strike"] < short["strike"])]
        with_delta = [r for r in cands if r["delta"] is not None]
        if not with_delta:
            pts = D(APPROACH_CONFIG["roll_points_without_delta"][u])
            basis.update(step_basis="points", step_value=pts)
            return pts if up else -pts
        basis.update(step_basis="delta", step_value=target)
        fit = [r for r in with_delta if abs(r["delta"]) <= target]
        if not fit:
            raise HandRefused(f"No strike in the chain brings {name(short)} to the target delta.")
        if out:  # the first strike beyond the short
            best = sorted(fit, key=lambda r: abs(r["strike"] - short["strike"]))[0]
        else:  # the strike nearest spot
            best = sorted(fit, key=lambda r: abs(r["strike"] - spot))[0]
        return best["strike"] - short["strike"]

    legs_out, after_out = {}, {}
    for aid in IC_APPROACHES:
        side = {"A-36": "none", "A-31": "both", "A-11": "both", "A-01": untested}.get(aid, tested)
        warnings: list[str] = []
        basis = {"step_basis": None, "step_value": None}
        try:
            trades, after, closed = [], list(legs), []
            if aid == "A-31":
                for x in legs:
                    t, c = close(x, x["lots"])
                    trades.append(t)
                    closed.append(c)
                after = []
            elif aid in ("A-05", "A-01"):
                s = tested if aid == "A-05" else untested
                si, wi = pos[(s, "short")], pos[(s, "wing")]
                dist = distance(legs[si], aid == "A-05", basis)
                targets = {si: legs[si]["strike"] + dist, wi: legs[wi]["strike"] + dist}
                check_listed(targets)
                if aid == "A-01":
                    other = cs if s == "put" else ps
                    if (s == "put" and targets[si] > other) or (s == "call" and targets[si] < other):
                        raise HandRefused(f"Moving {name(legs[si])} to {targets[si]:,} would cross the other short leg at {other:,}.")
                trades, after, closed = reopen(targets, warnings)
            elif aid == "A-28":
                gone = [pos[(tested, "short")], pos[(tested, "wing")]]
                for i in sorted(gone):
                    t, c = close(legs[i], legs[i]["lots"])
                    trades.append(t)
                    closed.append(c)
                after = [x for i, x in enumerate(legs) if i not in gone]
            elif aid == "A-29":
                cut = [pos[(tested, "short")], pos[(tested, "wing")]]
                if min(legs[i]["lots"] for i in cut) < 2:
                    short = legs[pos[(tested, "short")]]
                    raise HandRefused(f"{name(short)} holds {short['lots']} lot, so half of it is not a whole lot.")
                after = []
                for i, x in enumerate(legs):
                    if i in cut:
                        n = x["lots"] // APPROACH_CONFIG["reduce_divisor"]
                        t, c = close(x, n)
                        trades.append(t)
                        closed.append(c)
                        after.append({**x, "lots": x["lots"] - n})
                    else:
                        after.append(x)
            elif aid == "A-11":
                days = (expiry - today).days
                need = APPROACH_CONFIG["iron_fly_min_days_left"]
                if days < need:
                    raise HandRefused(f"This approach needs at least {need} days left; days left now: {max(days, 0)}.")
                both = sorted({k for t, k in listed if t == "CE"} & {k for t, k in listed if t == "PE"})
                atm = sorted(both, key=lambda k: (abs(k - spot), -k))[0]
                targets = {}
                for s in ("call", "put"):
                    si, wi = pos[(s, "short")], pos[(s, "wing")]
                    targets[si] = atm
                    targets[wi] = atm + legs[wi]["strike"] - legs[si]["strike"]
                check_listed(targets)
                trades, after, closed = reopen(targets, warnings)
        except HandRefused as e:
            legs_out[aid] = {"side": side, "refused": str(e), **basis}
            continue
        trades = [t for t in trades if t["action"] == "BUY"] + [t for t in trades if t["action"] == "SELL"]
        keys = ("side", "type", "strike", "expiry", "lots", "quantity", "entry", "tradingsymbol")
        after = [{k: x["lots"] * lot if k == "quantity" else x[k] for k in keys} for x in after]
        legs_out[aid] = {"side": side, **basis, "trades": trades, "after": after, "closed": closed,
                         "warnings": warnings}
        total = booked + sum(Fraction(sign(c["side"]) * c["quantity"] * (c["exit"] - c["entry"])) for c in closed)
        if after:
            after_out[aid] = {**hand_expiry(after, total), "booked_pnl": dec_text(total)}
        else:  # nothing open: the whole trade is what was booked
            after_out[aid] = {"exact": True, "max_profit": dec_text(total), "max_loss": dec_text(-total) if total < 0 else "0",
                              "breakevens": [], "booked_pnl": dec_text(total)}
    return legs_out, after_out

# ---------------------------------------------------------------------------------------------------------------------
# Scenario builder
# ---------------------------------------------------------------------------------------------------------------------
def dt(text: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(text).replace(tzinfo=IST)


def day(text: str) -> datetime.date:
    return datetime.date.fromisoformat(text)


def L(side: str, kind: str, strike: int | None, expiry: str, lots: int, entry: str | None = None) -> dict:
    leg = {"side": side, "type": kind, "strike": None if strike is None else D(strike), "expiry": day(expiry),
           "lots": lots}
    if entry is not None:
        leg["entry"] = D(entry)
    return leg


def day_type(clock: datetime.datetime, expiry: datetime.date, events: list[dict]) -> list[str]:
    today = clock.date()
    kinds = []
    if today == expiry:
        kinds.append("expiry day")
    if next_session(today) == expiry:
        kinds.append("day before expiry")
    nxt = next_session(today)
    if any((today + datetime.timedelta(days=i)).weekday() == 5 for i in range(1, (nxt - today).days)):
        kinds.append("last session before weekend")
    if today + datetime.timedelta(days=1) in HOLIDAYS:
        kinds.append("day before holiday")
    if (today - prev_session(today)).days > 1:
        kinds.append("first session after a break")
    if any(day(e["date"]) == today for e in events):
        kinds.append("event day")
    return kinds or ["normal"]


def limit_for(pb: dict, tid: str, expiry_kind: str, stage_ix: int, overrides: dict, family: str) -> str:
    """Precedence: the strategy's plan > the family's own value (ADR-216) > the catalogue (screen 4) value."""
    vals = (overrides.get("triggers", {}).get(tid, {}).get(expiry_kind)
            or pb["families"][family]["trigger_values"].get(tid, {}).get(expiry_kind)
            or pb["triggers"][tid][expiry_kind])
    return vals[stage_ix]


def tighten(limit: Decimal, cmp: str, pct: Decimal) -> Decimal:
    return limit * (1 + pct / 100) if cmp == "le" else limit * (1 - pct / 100)


def build(spec: dict, pb: dict) -> dict:  # noqa: C901, PLR0912, PLR0915 - one readable walk of the derivation
    u = spec["underlying"]
    meta = UNDERLYINGS[u]
    lot = meta["lot"]
    clock = dt(spec["clock"])
    kind = spec.get("expiry_kind", "weekly")
    legs = [dict(leg) for leg in spec["legs"]]
    for leg in legs:
        leg["quantity"] = leg["lots"] * lot
    expiries = sorted({leg["expiry"] for leg in legs})
    expiry = expiries[0]
    for e in expiries:
        check_expiry(u, e, spec.get("expiry_kinds", {}).get(e.isoformat(), kind))
    assert is_session(clock.date()), spec["id"]
    entry_clock = dt(spec["entry"]["clock"])
    entry_spot = D(spec["entry"]["spot"])
    entry_atm = D(spec["entry"].get("atm_iv", meta["atm_iv"]))
    entry_prices(u, legs, entry_clock, entry_spot, entry_atm)
    spot = D(spec["spot"])
    atm = D(spec.get("atm_iv", meta["atm_iv"]))
    family = spec["family"]
    fpb = pb["families"][family]
    overrides = spec.get("plan_overrides", {})
    events = spec.get("events", [])

    # market
    chains = []
    for e in expiries:
        strikes = [leg["strike"] for leg in legs if leg["strike"] is not None and leg["expiry"] == e]
        strikes += [D(s) for s in spec.get("extra_strikes", [])]
        rows = chain(u, spot, clock, e, atm, strikes or [spot])
        monthly = spec.get("expiry_kinds", {}).get(e.isoformat(), kind) == "monthly"
        for r in rows:
            r["tradingsymbol"] = symbol(u, e, r["type"], r["strike"], monthly)
        for change in spec.get("chain_changes", []):
            if day(change["expiry"]) == e:
                for r in rows:
                    if r["strike"] == D(change["strike"]) and r["type"] == change["type"]:
                        r.update({k: v for k, v in change.items() if k not in ("expiry", "strike", "type")})
        chains.append({"expiry": e, "kind": "monthly" if monthly else "weekly", "rows": rows})
    futures = []
    for leg in legs:
        if leg["type"] == "FUT":
            futures.append({"expiry": leg["expiry"], "ltp": D(spec["futures_ltp"]),
                            "tradingsymbol": symbol(u, leg["expiry"], "FUT", None, True)})

    def row_of(leg: dict) -> dict | None:
        if leg["type"] == "FUT":
            return futures[0]
        for c in chains:
            if c["expiry"] == leg["expiry"]:
                for r in c["rows"]:
                    if r["strike"] == leg["strike"] and r["type"] == leg["type"]:
                        return r
        return None

    for leg in legs:
        leg["tradingsymbol"] = row_of(leg)["tradingsymbol"]

    # history and whole-trade numbers
    history = []
    booked = Fraction(0)
    for h in spec.get("history", []):
        q = h["lots"] * lot
        b = sign(h["side"]) * q * (Fraction(D(h["exit"])) - Fraction(D(h["entry"])))
        booked += b
        history.append({"adjustment": h["adjustment"], "side": h["side"], "type": h["type"], "strike": D(h["strike"]),
                        "expiry": day(h["expiry"]), "lots": h["lots"], "quantity": q, "entry": D(h["entry"]),
                        "exit": D(h["exit"]), "booked": dec_text(b)})
    adjustments_used = spec.get("adjustments_used", len({h["adjustment"] for h in history}))
    open_cash = sum(-sign(leg["side"]) * leg["quantity"] * leg["entry"] for leg in legs if leg["type"] != "FUT")
    hist_cash = sum(-sign(h["side"]) * h["quantity"] * (h["entry"] - h["exit"]) for h in history)
    credit_received = open_cash + hist_cash

    data_state = {"prices": "fresh", "age_seconds": 1, "spot_source": "feed", "feed": "ok", "rest": "ok",
                  **spec.get("data_state", {})}
    unpriced = spec.get("unpriced_leg")
    margin = spec.get("margin", {"state": "stated", "value": spec.get("margin_value", str(50000 * legs[0]["lots"]))})

    # stage
    days_left = (expiry - clock.date()).days
    stage_ix = next(i for i, s in enumerate(STAGES[kind]) if days_left >= s["from"] and (s["to"] is None or days_left <= s["to"]))
    stage = STAGES[kind][stage_ix]["name"]

    # day rules (system rules + plan overrides; precedence strategy plan > playbook, ADR-214 (4b))
    rules = [dict(r) for r in SYSTEM_DAY_RULES]
    for r in overrides.get("day_rules", []):
        rules = [x for x in rules if x["when"] != r["when"]] + [r]
    today = clock.date()
    applying = []
    for r in rules:
        if not r["on"]:
            continue
        hit = False
        when = r["when"]
        if when == "beforeWeekend":
            hit = "last session before weekend" in day_type(clock, expiry, events)
        elif when == "beforeHoliday":
            hit = today + datetime.timedelta(days=1) in HOLIDAYS
        elif when == "expiry":
            hit = today == expiry
        elif when == "away":
            hit = today == prev_session(day(r["from"]))
        elif when == "event":
            hit = any(day(e["date"]) == next_session(today) for e in events)
        if hit:
            due = clock.time().strftime("%H:%M") >= r["at"]
            applying.append({"rule": when, "at": r["at"], "action": DAY_ACTIONS[r["action"]], "due": due,
                             **({"percent": r["percent"]} if "percent" in r else {})})
    tighten_pct = next((D(a["percent"]) for a in applying if a["due"] and "percent" in a), None)

    # live numbers
    def ltp(leg):
        return None if unpriced and leg["tradingsymbol"] == unpriced else row_of(leg)["ltp"]
    priced = all(ltp(leg) is not None for leg in legs)
    pnl_now = None
    if priced:
        pnl_now = booked + sum(Fraction(sign(leg["side"]) * leg["quantity"] * (ltp(leg) - leg["entry"])) for leg in legs)
    expiry_metrics = hand_expiry(legs, booked)
    shorts = [leg for leg in legs if leg["side"] == "SELL" and leg["type"] != "FUT"]
    premium_left = None
    adj_cost = None
    if priced and family in SHORTS and any(leg["type"] != "FUT" for leg in legs):
        premium_left = sum(-sign(leg["side"]) * leg["quantity"] * ltp(leg) for leg in legs if leg["type"] != "FUT")
        adj_cost = sum((row_of(leg)["ask"] - row_of(leg)["bid"]) * leg["quantity"] + 40 for leg in legs if leg["type"] != "FUT")

    suggest = data_state["prices"] == "fresh" and data_state["spot_source"] != "none"
    fired, near, skipped, already = [], [], [], []
    entry_days = (expiry - entry_clock.date()).days
    entry_stage = next(i for i, s in enumerate(STAGES[kind]) if entry_days >= s["from"] and (s["to"] is None or entry_days <= s["to"]))

    def held_at_entry(tid: str) -> bool:
        """F-71: the crossing trigger evaluated on the entry spot with the entry stage's value (only T-01 here:
        the scenario's entry carries a spot, not a full set of entry prices). The entry is never on expiry day after
        the day rule's time in this library, so no tightening applies at entry."""
        assert tid == "T-01" and entry_clock.date() != expiry, (spec["id"], tid)
        raw = limit_for(pb, tid, kind, entry_stage, overrides, family)
        if raw == "" or not shorts:
            return False
        return min(Fraction(abs(leg["strike"] - entry_spot)) / Fraction(entry_spot) * 100 for leg in shorts) <= Fraction(D(raw))
    if suggest:
        trig_on = [t for t in fpb["triggers_on"] if t in EVALUATED] + [
            t for t in overrides.get("triggers_on", []) if t not in fpb["triggers_on"]]
        for tid in [t for t in fpb["triggers_on"] if t not in EVALUATED]:
            skipped.append({"id": tid, "reason": NOT_EVALUATED.get(tid, "not evaluated")})
        for tid in trig_on:
            cmp = pb["triggers"][tid]["cmp"]
            value = None
            lim = None
            why = ""
            if tid in ("T-01", "T-03", "T-06", "T-07", "T-09", "T-11", "T-13", "T-16", "T-19", "T-10b"):
                raw = limit_for(pb, tid, kind, stage_ix, overrides, family)
                if raw == "":
                    skipped.append({"id": tid, "reason": f"no value in the {stage} stage"})
                    continue
                if tid != "T-10b":
                    lim = D(raw)
                    if tighten_pct is not None and tid in TIGHTENED:
                        lim = tighten(lim, cmp, tighten_pct)
            if tid == "T-01":
                if not shorts:
                    continue
                value = min(abs(leg["strike"] - spot) / spot * 100 for leg in shorts)
            elif tid == "T-02":
                if not expiry_metrics["exact"]:
                    why = "multi-expiry: no exact breakeven"
                else:
                    pnl_spot = hand_pnl_at(legs, booked, Fraction(spot))
                    if pnl_spot < 0:
                        fired.append({"id": tid, "value": dec_text(pnl_spot), "limit": "0", "cmp": "lt"})
                    continue
            elif tid in ("T-03", "T-09") and not shorts:
                continue
            elif tid == "T-03":
                value = max(abs(row_of(leg)["delta"]) for leg in shorts)
            elif tid == "T-06":
                if pnl_now is None or not expiry_metrics.get("exact") or expiry_metrics["max_loss"] in ("UNLIMITED", "0"):
                    why = "leg unpriced" if pnl_now is None else "max loss not finite (unlimited or multi-expiry)"
                else:
                    value = max(-pnl_now, Fraction(0)) / Fraction(D(expiry_metrics["max_loss"])) * 100
            elif tid == "T-07":
                if pnl_now is None or not expiry_metrics.get("exact") or expiry_metrics["max_profit"] == "UNLIMITED":
                    why = "leg unpriced" if pnl_now is None else "max profit not finite (unlimited or multi-expiry)"
                else:
                    value = max(pnl_now, Fraction(0)) / Fraction(D(expiry_metrics["max_profit"])) * 100
            elif tid == "T-09":
                prices = [ltp(leg) for leg in shorts]
                if any(p is None for p in prices):
                    why = "leg unpriced"
                else:
                    value = min(prices)
            elif tid == "T-10b":
                if clock.time().strftime("%H:%M") >= raw:
                    fired.append({"id": tid, "value": clock.time().strftime("%H:%M"), "limit": raw, "cmp": "ge"})
                continue
            elif tid == "T-11":
                value = abs(atm - entry_atm) * 100
            elif tid == "T-13":
                if clock.time().strftime("%H:%M") > "09:30":
                    continue
                value = abs(D(spec["day_open"]) - D(spec["prev_close"])) / D(spec["prev_close"]) * 100
            elif tid == "T-16":
                if margin["state"] != "stated" or pnl_now is None:
                    why = f"margin {margin['state']}" if margin["state"] != "stated" else "leg unpriced"
                else:
                    value = max(-pnl_now, Fraction(0)) / Fraction(D(margin["value"])) * 100
            elif tid == "T-18":
                mx = overrides.get("max_adjustments", GUARDS["max_adjustments"])
                if adjustments_used >= mx:
                    fired.append({"id": tid, "value": str(adjustments_used), "limit": str(mx), "cmp": "ge"})
                continue
            elif tid == "T-19":
                if premium_left is None or premium_left < 0:
                    why = "leg unpriced" if not priced else "no premium to earn (net long premium)"
                else:
                    value = Fraction(premium_left) / Fraction(adj_cost)
            elif tid == "T-21":
                continue
            if why:
                skipped.append({"id": tid, "reason": why})
                continue
            if value is None:
                continue
            fv, fl = Fraction(value), Fraction(lim)
            hit = fv <= fl if cmp == "le" else fv >= fl
            row = {"id": tid, "value": dec_text_round(fv), "limit": dec_text_round(fl), "cmp": cmp}
            if hit and tid in CROSSING and held_at_entry(tid):
                already.append(tid)
            elif hit:
                fired.append(row)
            elif (cmp == "ge" and fv >= fl * Fraction(4, 5)) or (cmp == "le" and fv <= fl * Fraction(5, 4)):
                near.append(row)

    # situations
    sits = list(spec.get("situations", []))
    if not suggest:
        sits.append("S-10")
    if today == expiry:
        sits.append("S-07")
    if adjustments_used >= overrides.get("max_adjustments", GUARDS["max_adjustments"]):
        sits.append("S-11")
    gap_hold = None
    if "day_open" in spec and clock.time().strftime("%H:%M") <= "09:30" and suggest:
        gap = abs(D(spec["day_open"]) - D(spec["prev_close"])) / D(spec["prev_close"]) * 100
        if gap >= D(limit_for(pb, "T-13", kind, stage_ix, overrides, family)):
            sits.append("S-01")
            itm = any((leg["type"] == "CE" and spot > leg["strike"]) or (leg["type"] == "PE" and spot < leg["strike"])
                      for leg in shorts)
            gap_hold = {"wait_until": "09:30", "held_back": not itm,
                        "reason": "a short opened in the money" if itm else "opening noise"}
    if pnl_now is not None and today == entry_clock.date() and expiry_metrics.get("exact") \
            and expiry_metrics["max_profit"] != "UNLIMITED" and pnl_now >= Fraction(D(expiry_metrics["max_profit"])) * Fraction(2, 5):
        sits.append("S-12")
    sits = sorted(set(sits))

    # approaches
    if suggest:
        applicable = list(fpb["approaches"]["applicable"])
        off = [a for a in fpb["approaches"]["off_in_playbook"] if a not in overrides.get("approaches_on", [])]
        applicable += [a for a in overrides.get("approaches_on", []) if a in fpb["approaches"]["off_in_playbook"]]
        refused = []
        if "S-11" in sits:
            refused += [{"id": a, "reason": f"Adjustment limit reached ({adjustments_used} of "
                         f"{overrides.get('max_adjustments', GUARDS['max_adjustments'])}): only exit and reduce are offered"}
                        for a in applicable if a not in EXIT_REDUCE]
        if "A-11" in applicable and days_left < 3 and "A-11" not in {r["id"] for r in refused}:
            refused.append({"id": "A-11", "reason": f"Only with 3+ days left ({days_left} left)"})
        refused += [r for r in spec.get("refused", []) if r["id"] not in {x["id"] for x in refused}]
        gone = {r["id"] for r in refused}
        approaches = {"applicable": [a for a in applicable if a not in gone], "refused": refused,
                      "greyed": fpb["approaches"]["greyed"], "off_in_playbook": off,
                      "warnings": spec.get("warnings", [])}
    else:
        approaches = {"applicable": [], "refused": [], "greyed": [], "off_in_playbook": [],
                      "withheld": "No suggestion: " + ("spot not available" if data_state["spot_source"] == "none"
                                                       else f"prices stale ({data_state['age_seconds']} s)")}

    # self-checks against the scenario's intent (generator refuses to write a scenario that does not hold)
    ids = {f["id"] for f in fired}
    for t in spec.get("must_fire", []):
        assert t in ids, (spec["id"], "must fire", t, fired, near, skipped)
    for t in spec.get("must_not_fire", []):
        assert t not in ids, (spec["id"], "must not fire", t, fired)
    if spec.get("exact_fire") is not None:
        assert ids == set(spec["exact_fire"]), (spec["id"], "exact", ids, fired)
    for s in spec.get("must_situations", []):
        assert s in sits, (spec["id"], "situation", s, sits)
    if "check" in spec:
        spec["check"](locals())

    stage_count = len(STAGES[kind])
    out = {
        "id": spec["id"], "title": spec["title"], "group": spec["group"], "refs": spec["refs"],
        "family": family, "playbook_ref": {"file": "_playbooks.json", "family": family, "expiry_kind": kind,
                                           "plan_overrides": {k: v for k, v in overrides.items()}},
        "underlying": u, "lot": lot, "tick": "0.05", "strike_step": meta["step"], "exchange": meta["exchange"],
        "clock": {"ist": clock.isoformat(), "weekday": clock.strftime("%A"),
                  "day_type": day_type(clock, expiry, events)},
        "expiry": expiry, "expiry_kind": kind, "dte": days_left,
        "market": {"spot": spot, "prev_close": D(spec["prev_close"]) if "prev_close" in spec else None,
                   "day_open": D(spec["day_open"]) if "day_open" in spec else None,
                   "india_vix": spec.get("india_vix"), "atm_iv": atm, "rate": RATE,
                   "futures": futures, "chains": chains},
        "events": events,
        "data_state": data_state,
        "position": {
            "entry": {"clock": entry_clock.isoformat(), "spot": entry_spot, "atm_iv": entry_atm},
            "legs": [{k: leg[k] for k in ("side", "type", "strike", "expiry", "lots", "quantity", "entry", "tradingsymbol")}
                     for leg in legs],
            "history": history, "booked_pnl": dec_text(booked), "adjustments_used": adjustments_used,
            "credit_received": credit_received,
            **({"charges_round_trip": spec["charges"]} if "charges" in spec else {}),
        },
        "broker": {
            "margin": {"state": margin["state"], "value": margin.get("value"), "reply": margin_reply(margin),
                       "funds_reply": funds_reply(margin)},
            "quote": quote_reply(u, legs, row_of, unpriced, clock, lot),
            "low_oi": [{"tradingsymbol": leg["tradingsymbol"], **row_of(leg).get("low_oi", {"state": "stated", "blocked": False})}
                       for leg in legs if leg["type"] != "FUT"],
        },
        "expected": {
            "stage": stage, "stage_index": stage_ix, "stage_count": stage_count, "suggest": suggest,
            "pnl_now": None if pnl_now is None else dec_text_round(pnl_now),
            "premium_left": None if premium_left is None else premium_left,
            "adjustment_cost": None if adj_cost is None else adj_cost,
            "triggers_fired": fired, "triggers_close": near, "triggers_not_evaluated": skipped,
            **({"already_true_at_entry": already} if already else {}),
            "day_rules": applying, "tighten_percent": None if tighten_pct is None else tighten_pct,
            "situations": sits, "gap_hold": gap_hold,
            "approaches": approaches,
            "at_expiry_whole_trade": expiry_metrics,
            "notes": spec.get("notes", []),
        },
    }
    if family == "ic":
        # the unpriced leg's quote answered "not found": its row has no price for the approach builder either
        ic_rows = [{**r, "ltp": None, "bid": None, "ask": None} if r["tradingsymbol"] == unpriced else r
                   for c in chains if c["expiry"] == expiry for r in c["rows"]]
        out["expected"]["approach_legs"], out["expected"]["approach_after"] = hand_approaches(
            u, lot, kind, today, spot, legs, ic_rows, booked)
    if "charges" in spec:
        out["expected"]["at_expiry_after_charges"] = hand_expiry(legs, booked, -Fraction(D(spec["charges"])))
    return out


def dec_text_round(value: Fraction) -> str:
    """A derived ratio or amount shown to 4 decimals (half-even); comparisons use the exact value."""
    with localcontext() as ctx:
        ctx.prec = 60
        d = D(value.numerator) / D(value.denominator)
    return format(d.quantize(D("0.0001"), rounding=ROUND_HALF_EVEN), "f")


FUNDS_AVAILABLE = 10_000_000.0  # synthetic funds, far above any scenario basket: the scenario's margin state decides


def funds_reply(margin: dict) -> dict:
    """Kite ``GET /user/margins`` reply shape (tests/fixtures/kite_margins/funds-*); the figure is synthetic."""
    # every margin state: the funds read is answered normally, only the BASKET reply varies
    return {"status": "success", "data": {"equity": {"net": FUNDS_AVAILABLE}}}


def margin_reply(margin: dict) -> dict:
    """Kite basket-margin reply shape (tests/fixtures/kite_margins); numbers synthetic."""
    if margin["state"] == "stated":
        v = float(margin["value"])
        return {"status": "success", "data": {"initial": {"total": v}, "final": {"total": v}, "orders": [],
                                              "charges": {"total": 0}}}
    if margin["state"] == "empty":
        return {"status": "success", "data": {}}
    return {"status": "error", "error_type": "NetworkException", "message": "Gateway timed out", "data": None}


def quote_reply(u: str, legs: list[dict], row_of, unpriced: str | None, clock: datetime.datetime, lot: int) -> dict:
    """Kite quote shape (tests/fixtures/kite_quotes): one depth level per side, numbers synthetic."""
    out = []
    for leg in legs:
        r = row_of(leg)
        if leg["tradingsymbol"] == unpriced:
            out.append({"tradingsymbol": leg["tradingsymbol"], "side": leg["side"], "quantity": leg["quantity"],
                        "last_price": None, "timestamp": None, "depth": {"buy": [], "sell": []}, "state": "not found"})
            continue
        bid = r.get("bid", r["ltp"])
        ask = r.get("ask", r["ltp"])
        out.append({"tradingsymbol": leg["tradingsymbol"], "side": leg["side"], "quantity": leg["quantity"],
                    "last_price": float(r["ltp"]), "timestamp": clock.strftime("%Y-%m-%d %H:%M:%S"),
                    "depth": {"buy": [{"price": float(bid), "quantity": lot * 10, "orders": 5}],
                              "sell": [{"price": float(ask), "quantity": lot * 10, "orders": 5}]},
                    "state": "stated"})
    return {"state": "stated" if not unpriced else "partial", "lot": lot, "tick": 0.05, "legs": out}


# ---------------------------------------------------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------------------------------------------------
N3, N9, N23 = "2026-11-03", "2026-11-09", "2026-11-23"
IC3 = [L("BUY", "PE", 22400, N3, 2), L("SELL", "PE", 22600, N3, 2), L("SELL", "CE", 23450, N3, 2), L("BUY", "CE", 23650, N3, 2)]
IC9 = [L("BUY", "PE", 22500, N9, 2), L("SELL", "PE", 22700, N9, 2), L("SELL", "CE", 23500, N9, 2), L("BUY", "CE", 23700, N9, 2)]
E3 = {"clock": "2026-10-28T10:00:00", "spot": "23020"}
E9 = {"clock": "2026-11-03T10:00:00", "spot": "23100"}
ICW = "IC weekly, NIFTY 2 lots"
OTHER = "Other strategy types"


def ic_spec(sid: str, title: str, refs: list[str], clock: str, spot: str, **kw) -> dict:
    base = {"id": sid, "title": title, "group": kw.pop("group", ICW), "refs": refs, "underlying": "NIFTY",
            "family": "ic", "clock": clock, "spot": spot, "legs": IC3, "entry": E3}
    base.update(kw)
    return base


def scenarios() -> list[dict]:  # noqa: PLR0915 - a flat list of scenario specs
    s = []
    s.append(ic_spec("ADJ-01", "Calm, early stage: nothing fires", ["PB-04", "P-10"], "2026-10-28T14:00:00", "23050",
                     exact_fire=[], situations=["S-03"]))
    s.append(ic_spec("ADJ-02", "Drift up, middle stage: spot within 0.5% of the short CE and its delta >= 0.35",
                     ["T-01", "T-03", "S-02", "PB-04"], "2026-11-06T11:40:00", "23420", legs=IC9, entry=E9,
                     must_fire=["T-01", "T-03"], must_not_fire=["T-02"], situations=["S-02"],
                     notes=["Expiry moved from Tue 10 Nov (Diwali-Balipratipada) to Mon 9 Nov (M-01)."]))
    s.append(ic_spec("ADJ-03", "Drift down, middle stage: mirror on the put side", ["T-01", "T-03", "S-02", "PB-04"],
                     "2026-11-06T11:40:00", "22785", legs=IC9, entry=E9, must_fire=["T-01", "T-03"],
                     must_not_fire=["T-02"], situations=["S-02"]))
    gap_ic = [L("BUY", "PE", 22600, N3, 2), L("SELL", "PE", 22800, N3, 2), L("SELL", "CE", 23300, N3, 2), L("BUY", "CE", 23500, N3, 2)]
    s.append(ic_spec("ADJ-04", "Gap up 1.2% at 09:15 through the short CE (short opens ITM: no 09:30 wait)",
                     ["S-01", "T-13", "A-38"], "2026-10-29T09:16:00", "23340", legs=gap_ic, entry=E3,
                     prev_close="23060", day_open="23340", must_fire=["T-13"], must_situations=["S-01"],
                     check=lambda v: _assert(v["gap_hold"]["held_back"] is False, "ADJ-04 must not hold back")))
    gap_dn = [L("BUY", "PE", 22500, N3, 2), L("SELL", "PE", 22700, N3, 2), L("SELL", "CE", 23400, N3, 2), L("BUY", "CE", 23600, N3, 2)]
    s.append(ic_spec("ADJ-05", "Gap down 1.5% past the lower breakeven", ["S-01", "T-02", "T-13"],
                     "2026-10-30T09:16:00", "22645", legs=gap_dn, entry=E3, prev_close="22990", day_open="22645",
                     must_fire=["T-02", "T-13"], must_situations=["S-01"]))
    s.append(ic_spec("ADJ-06", "IV +4 points with spot unchanged", ["S-04", "T-11"], "2026-10-29T12:00:00", "23020",
                     atm_iv="0.17", exact_fire=["T-11"], situations=["S-04"]))
    s.append(ic_spec("ADJ-07", "IV crush after an event, profit at least 60% of max profit", ["S-05", "T-07", "A-24"],
                     "2026-10-30T10:00:00", "23000", entry={**E3, "atm_iv": "0.17"}, atm_iv="0.12",
                     must_fire=["T-07"], situations=["S-05"],
                     check=lambda v: _assert(v["pnl_now"] >= Fraction(D(v["expiry_metrics"]["max_profit"])) * Fraction(3, 5),
                                             "ADJ-07 profit below 60%")))
    s.append(ic_spec("ADJ-08", "Expiry day 13:30: spot within 0.25% of a short, far short at Rs 1.5 or less",
                     ["S-07", "T-09", "T-01", "A-27"], "2026-11-03T13:30:00", "23400", must_fire=["T-01", "T-09"],
                     must_not_fire=["T-10b"], must_situations=["S-07"],
                     notes=["Expiry-day day rule tightens every trigger by 20% from 13:00."]))
    s.append(ic_spec("ADJ-09", "Expiry day 14:45: time exit", ["T-10b", "A-35", "S-07"], "2026-11-03T14:45:00", "23050",
                     must_fire=["T-10b"]))
    s.append(ic_spec("ADJ-10", "Big win on day 1: profit 45% of max profit", ["S-12", "T-07", "A-24", "A-25"],
                     "2026-10-28T15:00:00", "23030", entry={**E3, "atm_iv": "0.16"}, atm_iv="0.115",
                     must_not_fire=["T-07"], must_situations=["S-12"]))
    s.append(ic_spec("ADJ-11", "Loss 55% of max loss: stop line", ["T-06", "A-31"], "2026-10-30T11:00:00", "23620",
                     must_fire=["T-06"],
                     check=lambda v: _assert(Fraction(53, 100) <= -v["pnl_now"] / Fraction(D(v["expiry_metrics"]["max_loss"])) <= Fraction(57, 100),
                                             "ADJ-11 loss not ~55%")))
    rolled = [L("BUY", "PE", 22800, N3, 2, "6.10"), L("SELL", "PE", 23000, N3, 2, "16.85"),
              L("SELL", "CE", 23450, N3, 2), L("BUY", "CE", 23650, N3, 2)]
    hist2 = [{"adjustment": 1, "side": "BUY", "type": "PE", "strike": 22400, "expiry": N3, "lots": 2, "entry": "10.45", "exit": "1.40"},
             {"adjustment": 1, "side": "SELL", "type": "PE", "strike": 22600, "expiry": N3, "lots": 2, "entry": "19.70", "exit": "3.25"},
             {"adjustment": 2, "side": "BUY", "type": "PE", "strike": 22500, "expiry": N3, "lots": 2, "entry": "4.10", "exit": "0.60"},
             {"adjustment": 2, "side": "SELL", "type": "PE", "strike": 22700, "expiry": N3, "lots": 2, "entry": "9.05", "exit": "1.15"}]
    s.append(ic_spec("ADJ-12", "Two adjustments already used: only exit / reduce offered", ["S-11", "T-18", "P-03"],
                     "2026-11-02T10:30:00", "23300", legs=rolled, history=hist2, must_fire=["T-18"],
                     must_situations=["S-11"]))
    hist1 = [{"adjustment": 1, "side": "BUY", "type": "PE", "strike": 22400, "expiry": N3, "lots": 2, "entry": "10.45", "exit": "1.40"},
             {"adjustment": 1, "side": "SELL", "type": "PE", "strike": 22600, "expiry": N3, "lots": 2, "entry": "19.70", "exit": "3.25"}]
    rolled1 = [L("BUY", "PE", 22700, N3, 2, "6.10"), L("SELL", "PE", 22900, N3, 2, "16.85"),
               L("SELL", "CE", 23450, N3, 2), L("BUY", "CE", 23650, N3, 2)]
    s.append(ic_spec("ADJ-13", "After one adjustment with booked P&L: whole-trade numbers include it", ["F-74", "F-06"],
                     "2026-10-30T13:00:00", "23250", legs=rolled1, history=hist1,
                     notes=["Put spread rolled up 300 points on 29 Oct; booked P&L carries into max profit, max loss "
                            "and breakevens (F-74)."]))
    s.append(ic_spec("ADJ-14", "Premium left below 1 x adjustment cost (ADR-216)", ["T-19", "P-04"], "2026-11-02T15:00:00",
                     "23020", must_fire=["T-19"],
                     check=lambda v: _assert(v["premium_left"] > 0, "ADJ-14 wants premium left > 0")))
    s.append(ic_spec("ADJ-15", "Last session before a weekend, Friday 15:00: carry check", ["S-06", "S-09", "F-15"],
                     "2026-10-30T15:00:00", "23100", situations=["S-06", "S-09"],
                     check=lambda v: _assert(any(r["rule"] == "beforeWeekend" and r["due"] for r in v["applying"]), "ADJ-15")))
    hol_ic = [L("BUY", "PE", 22400, "2026-12-29", 2), L("SELL", "PE", 22600, "2026-12-29", 2),
              L("SELL", "CE", 23450, "2026-12-29", 2), L("BUY", "CE", 23650, "2026-12-29", 2)]
    s.append(ic_spec("ADJ-16", "Day before a market holiday (Christmas, Fri 25 Dec 2026)", ["S-09", "F-15", "M-20"],
                     "2026-12-24T15:00:00", "23000", legs=hol_ic, expiry_kind="monthly",
                     entry={"clock": "2026-12-21T10:00:00", "spot": "23020"}, situations=["S-09"],
                     check=lambda v: _assert({"beforeHoliday", "beforeWeekend"} <= {r["rule"] for r in v["applying"]}, "ADJ-16")))
    s.append(ic_spec("ADJ-17", "User unavailable the next two sessions: fires the session before", ["ADR-214 (4c)", "P-09"],
                     "2026-10-30T14:30:00", "23050",
                     plan_overrides={"day_rules": [{"on": True, "when": "away", "at": "14:30", "action": 1,
                                                    "from": "2026-11-02", "to": "2026-11-03"}]},
                     check=lambda v: _assert(any(r["rule"] == "away" and r["due"] for r in v["applying"]), "ADJ-17")))
    s.append(ic_spec("ADJ-18", "Event tomorrow (synthetic RBI policy date): event rule fires", ["T-17", "S-08", "P-09", "F-09"],
                     "2026-11-04T14:30:00", "23120", legs=IC9, entry=E9,
                     events=[{"date": "2026-11-05", "name": "RBI policy (synthetic date for the test)",
                              "source": "admin event list", "state": "stated"}],
                     plan_overrides={"day_rules": [{"on": True, "when": "event", "at": "14:30", "action": 1}]},
                     situations=["S-08"],
                     notes=["T-17 needs the admin event list (D-07); with no list the rule cannot fire and the data "
                            "state is 'events: not available'."],
                     check=lambda v: _assert(any(r["rule"] == "event" and r["due"] for r in v["applying"]), "ADJ-18")))
    s.append(ic_spec("ADJ-19", "Stale data 60 s: no suggestion", ["S-10", "T-21", "F-21"], "2026-10-30T11:00:00", "23300",
                     data_state={"prices": "stale", "age_seconds": 60, "feed": "stale"}, must_situations=["S-10"]))
    broker_base = {"clock": "2026-11-02T11:00:00", "spot": "23380"}
    s.append(ic_spec("ADJ-20a", "Broker: margin request failed (approaches shown, margin unknown)", ["F-04", "ADR-016"],
                     broker_base["clock"], broker_base["spot"], group="IC weekly, broker answer states",
                     margin={"state": "failed", "value": None},
                     warnings=["Margin not available: Zerodha did not answer; every approach shows 'margin unknown'"]))
    s.append(ic_spec("ADJ-20b", "Broker: margin reply empty", ["F-04", "ADR-016"], broker_base["clock"], broker_base["spot"],
                     group="IC weekly, broker answer states", margin={"state": "empty", "value": None},
                     warnings=["Zerodha returned no margin; every approach shows 'margin unknown'"]))
    s.append(ic_spec("ADJ-20c", "Broker: one leg unpriced (long put wing)", ["F-21", "REQ-046 AC-5"], broker_base["clock"],
                     broker_base["spot"], group="IC weekly, broker answer states", unpriced_leg=symbol("NIFTY", day(N3), "PE", D(22400), False),
                     refused=[{"id": a, "reason": "Leg 1 (BUY NIFTY 22,400 PE, expiry 03 Nov 2026) has no price, and this approach trades it."}
                              for a in ("A-01", "A-24", "A-25", "A-31", "A-11")]))
    s.append(ic_spec("ADJ-20d", "Broker: landing strike not listed (that approach refused, others shown)", ["A-05", "M-15"],
                     broker_base["clock"], broker_base["spot"], group="IC weekly, broker answer states",
                     chain_changes=[{"expiry": N3, "strike": "23700", "type": "CE", "listed": False, "tradable": False,
                                    "ltp": None, "bid": None, "ask": None, "iv": None, "delta": None, "gamma": None}],
                     notes=["A-05 rolls the tested call spread out 50 points (23,450 CE delta 0.3566 -> 23,500 CE "
                            "0.2586, the first strike at the Early delta 0.30); its wing lands on 23,700 CE, not listed."],
                     refused=[{"id": "A-05", "reason": "No 23,700 CE is listed for 03 Nov 2026, so leg 4 cannot move there."}]))
    s.append(ic_spec("ADJ-20e", "Broker: low-OI state unknown (warning, not refusal)", ["M-15", "P-12", "F-12"],
                     broker_base["clock"], broker_base["spot"], group="IC weekly, broker answer states",
                     chain_changes=[{"expiry": N3, "strike": "23650", "type": "CE", "low_oi": {"state": "unknown", "blocked": None}}],
                     warnings=["Low-OI state unknown for NIFTY 3 Nov 23,650 CE: Zerodha may block a fresh order in it "
                               "(M-15); exits are always allowed"]))
    sx_ic = [L("BUY", "PE", 71000, "2026-11-26", 2), L("SELL", "PE", 72000, "2026-11-26", 2),
             L("SELL", "CE", 77500, "2026-11-26", 2), L("BUY", "CE", 78500, "2026-11-26", 2)]
    sx_entry = {"clock": "2026-11-02T10:00:00", "spot": "74800"}
    s.append({"id": "ADJ-21", "title": "SENSEX monthly, 20 days, calm", "group": "IC monthly, SENSEX 2 lots",
              "refs": ["M-02", "PB-04"], "underlying": "SENSEX", "family": "ic", "expiry_kind": "monthly",
              "clock": "2026-11-06T11:00:00", "spot": "74900", "legs": sx_ic, "entry": sx_entry, "exact_fire": [],
              "margin_value": "110000"})
    s.append({"id": "ADJ-22", "title": "SENSEX monthly, last 2 days stage", "group": "IC monthly, SENSEX 2 lots",
              "refs": ["M-02", "PB-04"], "underlying": "SENSEX", "family": "ic", "expiry_kind": "monthly",
              "clock": "2026-11-25T11:00:00", "spot": "77200", "legs": sx_ic, "entry": sx_entry,
              "must_fire": ["T-01"], "margin_value": "110000",
              "notes": ["Tue 24 Nov is a holiday (Guru Nanak), so Wed 25 Nov is the last session before expiry."]})
    pop_ic = [L("BUY", "PE", 22400, N3, 2, "13.15"), L("SELL", "PE", 22600, N3, 2, "38.70"),
              L("SELL", "CE", 23450, N3, 2, "41.35"), L("BUY", "CE", 23650, N3, 2, "12.85")]
    s.append(ic_spec("ADJ-23", "POP rounding: after-charges breakevens carry 3 decimals (F-75 regression)", ["F-75"],
                     "2026-10-30T14:56:00", "23020", legs=pop_ic, charges="199.94",
                     notes=["Charges chosen so (credit - charges) / 130 = 52.512: after-charges breakevens 22,547.488 "
                            "and 23,502.512, finer than paise (F-75)."]))
    s.append(ic_spec("ADJ-24a", "Spot source: feed missing, REST quote used", ["F-76"], "2026-10-30T11:00:00", "23100",
                     data_state={"feed": "missing", "spot_source": "rest", "rest": "ok"},
                     notes=["F-76: today the REST allow-list refuses 'NSE:NIFTY 50'; this expects the fixed path."]))
    s.append(ic_spec("ADJ-24b", "Spot source: all sources failed -> 'Spot not available'", ["F-76", "S-10"],
                     "2026-10-30T11:00:00", "23100",
                     data_state={"feed": "missing", "spot_source": "none", "rest": "failed", "prices": "fresh"},
                     must_situations=["S-10"]))
    s.append(ic_spec("ADJ-25a", "Boundary: tested short delta exactly at the limit 0.35 (fires)", ["T-03"],
                     "2026-11-06T11:40:00", spot_for_delta("0.3500"), legs=IC9, entry=E9, must_fire=["T-03"]))
    s.append(ic_spec("ADJ-25b", "Boundary: tested short delta 0.01 below the limit (does not fire)", ["T-03"],
                     "2026-11-06T11:40:00", spot_for_delta("0.3400"), legs=IC9, entry=E9, must_not_fire=["T-03"]))
    near_ic = [L("BUY", "PE", 22500, N9, 2), L("SELL", "PE", 22700, N9, 2), L("SELL", "CE", 23000, N9, 2), L("BUY", "CE", 23200, N9, 2)]
    s.append(ic_spec("ADJ-42", "F-71: short CE 0.35% from spot at entry and now (Middle stage): already true, not flagged",
                     ["F-71", "T-01", "REQ-045 AC-3"], "2026-11-06T11:00:00", "22920", legs=near_ic,
                     entry={"clock": "2026-11-06T10:00:00", "spot": "22920", "atm_iv": "0.07"}, atm_iv="0.07",
                     exact_fire=[],
                     check=lambda v: _assert(v["already"] == ["T-01"], "ADJ-42 must hold T-01 at entry"),
                     notes=["F-71 (live 30 Oct): a fresh iron condor's 1-step-OTM short sits inside T-01's Middle 0.5%. "
                            "The rule held at entry and still holds, so it is 'Already true when tracking started', "
                            "not a flag; it flags only after a check finds it clear and spot comes back.",
                            "ATM IV 7% (synthetic) keeps the near short's delta below T-03's Middle 0.35, so T-01 is "
                            "the only trigger that holds."]))

    # ---- other strategy types (NIFTY weekly unless stated) ----
    def o(sid, title, refs, family, clock, spot, legs, entry, **kw):
        return {"id": sid, "title": title, "group": OTHER, "refs": refs, "underlying": "NIFTY", "family": family,
                "clock": clock, "spot": spot, "legs": legs, "entry": entry, **kw}
    s.append(o("ADJ-30", "Short strangle, call side tested", ["PB-01", "A-08", "A-09"], "strangle",
               "2026-10-30T11:00:00", "23360", [L("SELL", "PE", 22600, N3, 2), L("SELL", "CE", 23450, N3, 2)], E3,
               must_fire=["T-01"], margin_value="300000", plan_overrides={"approaches_on": ["A-08"]},
               notes=["A-08 is off in the draft system playbook; this strategy's plan turns it on (precedence: "
                      "strategy plan > playbook, ADR-214 (4b))."]))
    s.append(o("ADJ-31", "Short straddle needing a re-centre", ["PB-03", "A-07"], "straddle", "2026-10-30T11:00:00",
               "23230", [L("SELL", "PE", 23000, N3, 1), L("SELL", "CE", 23000, N3, 1)], E3, margin_value="150000",
               plan_overrides={"approaches_on": ["A-07"]},
               notes=["A-07 re-centre is off in the draft system playbook; this strategy's plan turns it on."]))
    s.append(o("ADJ-32", "Iron butterfly, spot drifted toward the call wing", ["PB-05"], "ifly", "2026-10-30T11:00:00",
               "23180", [L("BUY", "PE", 22800, N3, 1), L("SELL", "PE", 23000, N3, 1), L("SELL", "CE", 23000, N3, 1),
                         L("BUY", "CE", 23200, N3, 1)], E3, margin_value="40000"))
    s.append(o("ADJ-33", "Bull put credit spread breached", ["PB-06", "T-02", "T-03"], "credit", "2026-10-30T11:00:00",
               "22820", [L("BUY", "PE", 22700, N3, 2), L("SELL", "PE", 22900, N3, 2)], E3,
               must_fire=["T-02", "T-03"], margin_value="50000"))
    s.append(o("ADJ-34", "Bull call debit spread at 75% of max value", ["PB-07", "T-07"], "debit", "2026-10-30T11:00:00",
               "23300", [L("BUY", "CE", 23000, N3, 1), L("SELL", "CE", 23200, N3, 1)], E3, must_fire=["T-07"],
               margin_value="15000",
               check=lambda v: _assert(140 <= v["ltp"](v["legs"][0]) - v["ltp"](v["legs"][1]) <= 160, "ADJ-34 not ~75%")))
    s.append(o("ADJ-35", "Single long call up 100%", ["PB-08", "A-17", "A-16"], "longopt", "2026-10-29T11:00:00",
               "23300", [L("BUY", "CE", 23200, N3, 1)], E3, margin_value="5000",
               check=lambda v: _assert(Fraction(v["ltp"](v["legs"][0])) >= 2 * Fraction(v["legs"][0]["entry"]), "ADJ-35 +100%"),
               notes=["The draft T-07 is '% of max profit'; a long call's max profit is unlimited, so T-07 cannot be "
                      "evaluated. PB-08's '+100% premium' has no row in the mockup trigger table (open for GC-ADJ1)."]))
    s.append(o("ADJ-36", "Long straddle after an IV crush", ["PB-09", "T-11", "S-05"], "longvol", "2026-10-30T11:00:00",
               "23040", [L("BUY", "PE", 23000, N3, 1), L("BUY", "CE", 23000, N3, 1)], {**E3, "atm_iv": "0.18"},
               atm_iv="0.12", must_fire=["T-11"], situations=["S-05"], margin_value="30000"))
    s.append(o("ADJ-37", "Calendar with the near leg 1 day from expiry", ["PB-10", "M-06", "A-19", "A-03"], "calendar",
               "2026-11-02T11:00:00", "23060", [L("SELL", "CE", 23000, N3, 1), L("BUY", "CE", 23000, N9, 1)], E3,
               margin_value="60000",
               notes=["Near-expiry margin note: the calendar margin benefit is removed on the near leg's expiry day "
                      "(M-06), i.e. tomorrow; show the margin change."]))
    s.append(o("ADJ-38", "Call ratio spread, naked side tested", ["PB-11", "A-15", "P-06"], "ratio",
               "2026-10-30T11:00:00", "23280", [L("BUY", "CE", 23000, N3, 1), L("SELL", "CE", 23300, N3, 2)], E3,
               must_fire=["T-01"], margin_value="120000"))
    s.append(o("ADJ-39", "Bull call butterfly, spot past the body", ["PB-12"], "dirfly", "2026-10-30T11:00:00",
               "23420", [L("BUY", "CE", 23100, N3, 1), L("SELL", "CE", 23250, N3, 2), L("BUY", "CE", 23400, N3, 1)], E3,
               margin_value="20000"))
    s.append(o("ADJ-40", "Naked short put at delta 0.35", ["PB-13", "T-03", "A-09"], "other", "2026-10-30T11:00:00",
               spot_for_delta("0.3500", kind="PE", strike=22900, expiry=N3, clock="2026-10-30T11:00:00", lo="22900", hi="23300"),
               [L("SELL", "PE", 22900, N3, 2)], E3, must_fire=["T-03"], margin_value="300000"))
    s.append(o("ADJ-41", "Long future, loss 2% of margin (PB-13 stop via the strategy plan)", ["PB-13", "T-16"], "other",
               "2026-11-02T11:00:00", "23020", [L("BUY", "FUT", None, N23, 1, "23165.00")], E3,
               expiry_kind="monthly", futures_ltp="23100.00", margin_value="211250",
               plan_overrides={"triggers": {"T-16": {"monthly": ["2", "2", "2"]}}}, must_fire=["T-16"],
               notes=["Futures expire on the monthly expiry: last Tuesday 24 Nov is a holiday, so Mon 23 Nov.",
                      "Loss 65 x 65 = 4,225 = 2.00% of the synthetic margin 2,11,250."]))
    return s


def _assert(cond: bool, what: str) -> None:
    assert cond, what


def spot_for_delta(target: str, kind: str = "CE", strike: int = 23500, expiry: str = N9,
                   clock: str = "2026-11-06T11:40:00", lo: str = "23100", hi: str = "23500") -> str:
    """The spot (on the 0.05 grid) where the chain's 4-dp delta of ``strike`` equals ``target`` exactly."""
    t = D(target)
    years = year_fraction(dt(clock), day(expiry))
    atm = D(UNDERLYINGS["NIFTY"]["atm_iv"])
    a, b = int(D(lo) * 20), int(D(hi) * 20)

    def delta(i: int) -> Decimal:
        sp = (D(i) / 20).quantize(D("0.01"))
        return abs(option_row(kind, sp, D(strike), years, atm)["delta"])
    rising = delta(b) > delta(a)
    while b - a > 1:
        m = (a + b) // 2
        if (delta(m) < t) == rising:
            a = m
        else:
            b = m
    for i in (a, b):
        if delta(i) == t:
            return format((D(i) / 20).quantize(D("0.01")), "f")
    raise AssertionError(f"no 0.05 spot gives delta {target}")


# ---------------------------------------------------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------------------------------------------------
def _plain(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, Fraction):
        return dec_text(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, float):
        assert math.isfinite(value)
    return value


def dump(obj) -> str:
    return json.dumps(_plain(obj), indent=1, ensure_ascii=True) + "\n"


def index(rows: list[dict]) -> str:
    lines = ["# Adjustment scenario library (generated: do not edit)", "",
             "Generated by `python tests/adjust_scenarios_gen.py`; checked by `tests/test_adjust_scenarios.py`.",
             "Synthetic prices (repo Black-Scholes), playbook values from `_playbooks.json` (iron condor approved, ADR-216;",
             "other families DRAFT). Expected values are",
             "derived by hand-written code; the test cross-checks them with the engine.", "",
             "| id | group | what it tests | stage | triggers fired |", "|---|---|---|---|---|"]
    for r in rows:
        e = r["expected"]
        fired = ", ".join(f["id"] for f in e["triggers_fired"]) or ("none" if e["suggest"] else "no suggestion")
        lines.append(f"| {r['id']} | {r['group']} | {r['title']} | {e['stage']} ({r['expiry_kind']}, {r['dte']} d) | {fired} |")
    return "\n".join(lines) + "\n"


def generate(out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pb = playbooks()
    pb_text = dump(pb)
    pb = json.loads(pb_text)
    written = {"_playbooks.json": pb_text}
    rows = []
    for spec in scenarios():
        sc = build(spec, pb)
        rows.append(sc)
        written[f"{sc['id']}.json"] = dump(sc)
    written["INDEX.md"] = index(rows)
    for name, text in written.items():
        (out_dir / name).write_bytes(text.encode("utf-8"))
    return sorted(written)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT_DIR
    names = generate(target)
    print(f"wrote {len(names)} files to {target}")
