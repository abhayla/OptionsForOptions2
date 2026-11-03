"""Per-stage playbook evaluation (GC-ADJ2 step 1B; REQ-159 AC-1..AC-3, REQ-158 AC-2, REQ-045 AC-3, REQ-160 AC-3, F-71).

Spec basis: docs/design/playbook-body-v1.md (THE body shape and the three result types); REQ-159 AC-1 "Stages are kept
separately for weekly and monthly expiries; each stage has a user name and from and to days left"; REQ-159 AC-2 "A
trigger whose data is not available can be kept but never fires, and says why"; REQ-159 AC-3 "Triggers combine into
AND/OR rules"; ADR-216 (iron condor approved, T-19 = 1x cost); spec/findings.md F-71 (a condition already true at entry
is not a new event).

Pure: Decimal and the standard library only; no DB, no clock read, no app import. The caller states every input in a
:class:`StrategyState`; an input it could not get is ``None`` and every trigger that needs it answers
:class:`NotChecked` with the reason - never a pass, never a silent skip.

Comparisons are exact and inclusive (``le``: value <= limit, ``ge``: value >= limit), done by cross-multiplication
under a context that traps any inexact step, the way ``detection.py`` compares; a ratio is divided only for display.

F-71 memory (crossing, not level): ``memory`` maps rule id -> ``{"held_at_entry": bool, "seen_clear": bool}``. On a
rule's first check ``held_at_entry`` is the rule evaluated on ``entry_state`` (no entry state, or a rule whose entry
value cannot be computed, counts as not held). A rule that held at entry answers :class:`AlreadyTrue` until a check
finds it false; from then on it flags like any other rule. ``evaluate`` takes the memory and returns the new one.
"""
from __future__ import annotations

import dataclasses
import datetime
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Context, Decimal, DivisionByZero, Inexact, InvalidOperation, Overflow, localcontext
from typing import Final, Literal

from ofo import market_calendar as mc
from ofo.adjustment import level_watch
from ofo.adjustment.approaches import KINDS, ExitInputs
from ofo.adjustment.offered import offered_now
from ofo.engine import adjust_ratios as ratios
from ofo.engine.black_scholes import Greeks
from ofo.engine.legs import Action
from ofo.errors import render
from ofo.timeutil import IST

ExpiryKind = Literal["weekly", "monthly"]
Cmp = Literal["le", "ge", "lt"]
UNLIMITED: Final = "UNLIMITED"
#: T-14's formula (loss from a 1% move) is written in GC-ADJ2 step 2; until then it is never checked.
#: Reason codes: each is a catalogue template id (backend/ofo/errors/templates.py, ``adjust_trigger_*``). The
#: evaluator returns the code and its slots; ``reason_text`` renders it through render(), the one route to a user.
P: Final = "adjust_trigger_"
T14_PENDING: Final = f"{P}t14_pending"
ALREADY_TRUE: Final = f"{P}already_true"
_HUNDRED: Final = Decimal(100)
#: every step of a comparison must be exact; a rounding there would be a wrong flag at the boundary
_EXACT: Final = Context(prec=200, traps=[Inexact, InvalidOperation, DivisionByZero, Overflow])
_SHOW: Final = Context(prec=60)


# ---- inputs ----------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ShortLeg:
    """One open SELL option leg: strike, absolute delta, last price (``None`` = not available)."""

    strike: Decimal
    abs_delta: Decimal | None
    ltp: Decimal | None


@dataclass(frozen=True)
class CarryFigures:
    """The carry check's content (GC-IC1 1b, S-06): the whole-trade P&L (booked plus open legs) if spot gaps
    ``CARRY_GAP_PCT`` up / down at the next session's open, valued by the engine (``ofo.adjustment.carry.gap_pnl``),
    and the broker-stated overnight margin. A figure not known is None with its reason code, never a zero."""

    up: Decimal | None
    down: Decimal | None
    gap_reason: str | None = None  # why up / down are None (a catalogue reason code)
    margin: Decimal | None = None  # the broker-stated margin; None = not stated (``margin_reason``)
    margin_reason: str | None = None
    next_open: datetime.datetime | None = None  # the time the gap figures are valued at


@dataclass(frozen=True)
class HeldLeg:
    """One open option leg as S-02 reads it (GC-IC1 6a): its per-unit engine Greeks (``None`` = not available),
    BUY / SELL, and its lots."""

    greeks: Greeks | None
    side: str
    lots: int


@dataclass(frozen=True)
class StrategyState:
    """Everything the triggers read. Every input that can be missing is Optional (``None`` = not available)."""

    expiry_kind: ExpiryKind
    days_left: int | None = None
    hhmm: str | None = None  # IST clock time "HH:MM" of this check
    spot: Decimal | None = None
    shorts: tuple[ShortLeg, ...] = ()
    pnl: Decimal | None = None  # whole trade, open legs at LTP plus booked
    max_loss: Decimal | str | None = None  # Decimal, UNLIMITED or None
    max_profit: Decimal | str | None = None
    margin: Decimal | None = None  # None = the broker did not state it
    premium_left: Decimal | None = None
    adjustment_cost: Decimal | None = None  # ADR-221: the cheapest offered approach's Compare cost
    adjustment_approach: str | None = None  # that approach's id (A-xx), named on the T-19 flag
    adjustment_cost_reason: str | None = None  # why no cost: a catalogue reason code (``adjust_trigger_*``)
    adjustment_unpriced: int = 0  # offered approaches left out because they could not be priced
    atm_iv: Decimal | None = None
    entry_atm_iv: Decimal | None = None
    day_open: Decimal | None = None
    prev_close: Decimal | None = None
    adjustments_used: int | None = None
    expiry_pnl_at_spot: Decimal | None = None  # T-02: whole-trade P&L at expiry if spot stays here
    tighten_percent: Decimal | None = None  # the due day rule's X ("Tighten every trigger by X%")
    prices_fresh: bool | None = None  # T-21: True only when the prices are fresh; None = unknown
    #: GC-IC1 1b: today's carry day kinds (``carry_day_kinds``: "beforeWeekend" / "beforeHoliday"); None = the
    #: holiday list is not known for the days it needs (never assumed a session)
    carry_days: frozenset[str] | None = None
    carry: CarryFigures | None = None  # the carry check's figures; None = not computed (no carry rule due)
    #: GC-IC1 6a (ADR-240 (3)): every open option leg with its engine Greeks (S-02); None = the legs were not read
    held: tuple[HeldLeg, ...] | None = None
    today: datetime.date | None = None  # the IST session date of this check (S-12); None = not known
    entry_day: datetime.date | None = None  # the IST date the strategy was entered (first order); None = not known
    #: GC-IC1 4c (A-37, ADR-242): the user's active level watches, read on the rebuild with the gate load (never per
    #: check); () = none set
    watches: tuple[level_watch.LevelWatch, ...] = ()


# ---- results ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Hit:
    """One trigger's exact comparison."""

    trigger_id: str
    value: Decimal | str
    threshold: Decimal | str
    cmp: Cmp
    fired: bool


@dataclass(frozen=True)
class Flag:
    """The rule fired: "Your rule was triggered" / "Adjustment opportunity detected"."""

    rule_id: str
    trigger_id: str
    stage_name: str | None
    value: Decimal | str
    threshold: Decimal | str
    cmp: Cmp
    members: tuple[Hit, ...] = ()


@dataclass(frozen=True)
class NotChecked:
    """Data missing or not evaluable: never passed (REQ-160 AC-3)."""

    rule_id: str
    trigger_id: str
    code: str
    slots: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True)
class AlreadyTrue:
    """"Already true when tracking started" (F-71)."""

    rule_id: str
    trigger_id: str
    value: Decimal | str
    threshold: Decimal | str
    code: str = ALREADY_TRUE
    cmp: Cmp | None = None  # GC-ADJ2 step 5: the lead trigger's comparison, as a Flag carries it


def reason_text(code: str, slots: tuple[tuple[str, object], ...] = ()) -> str:
    """The user text of a reason code (NotChecked, AlreadyTrue, withheld), from the catalogue."""
    return render(code, **dict(slots)).what_happened


Result = Flag | NotChecked | AlreadyTrue


@dataclass(frozen=True)
class RuleValue:
    """One checked rule's value at this check, true AND false (GC-ALERT1: the alert gate reads values, not flags).

    Given for a Flag and for a rule evaluated false (``clear``) whose lead trigger has a value; never for NotChecked
    or AlreadyTrue (F-71: a condition true at entry is not a crossing). ``later`` = the lead trigger's limits at the
    later stages of this expiry kind, tightened as the current one is (a stage with no value is left out).
    """

    rule_id: str
    trigger_id: str
    value: Decimal | str
    threshold: Decimal | str
    cmp: Cmp
    fired: bool
    members: int = 1  # how many triggers the rule combines
    later: tuple[Decimal | str, ...] = ()
    yes_no: bool = False  # a day rule (GC-IC1 1a): the gate reads it yes/no, never on a ladder
    approaches: tuple[str, ...] = ()  # a day rule's approaches the record names (A-28 tested spread, A-27 far short)
    carry: CarryFigures | None = None  # a carry check's figures the record carries (GC-IC1 1b)


@dataclass(frozen=True)
class Evaluation:
    stage_name: str | None
    stage_index: int | None
    results: tuple[Result, ...]
    memory: dict[str, dict[str, bool]]
    clear: tuple[str, ...] = ()  # rule ids evaluated false at this check
    withheld: str | None = None  # T-21: why no suggestion is made
    notes: tuple[str, ...] = field(default=())
    values: tuple[RuleValue, ...] = ()  # every checked rule's value, true and false (additive, GC-ALERT1)


# ---- body ------------------------------------------------------------------------------------------------------------
def body_from_fixture(playbooks: Mapping, family: str) -> dict:
    """The v1 body of ``family`` from ``_playbooks.json`` data (the one derivation; the seed and the tests use it)."""
    fam = playbooks["families"][family]
    greyed = {g["id"]: g["reason"] for g in fam["triggers_greyed"]}
    own = fam.get("trigger_values", {})
    triggers = {}
    for tid, t in playbooks["triggers"].items():
        entry = {"on": tid in fam["triggers_on"], "label": t["label"], "unit": t["unit"], "cmp": t["cmp"],
                 "data": t["data"],
                 "weekly": _copy(own.get(tid, {}).get("weekly") or t["weekly"]),
                 "monthly": _copy(own.get(tid, {}).get("monthly") or t["monthly"])}
        if tid in greyed:
            entry["greyed"] = greyed[tid]
        triggers[tid] = entry
    body = {
        "schema": 1,
        "strategy_type": family,
        "status": "approved" if fam["status"] == "APPROVED" else "draft",
        "stages": {k: [dict(s) for s in v] for k, v in playbooks["stages"].items()},
        "triggers": triggers,
        "rules": [{"id": tid, "any_of": [tid]} for tid in fam["triggers_on"]],
        "tightened": list(playbooks["tightened_by_day_rule"]),
        "day_rules": [dict(r) for r in fam.get("day_rules", playbooks["day_rules"])],
        "situations": [{"id": sid, **s} for sid, s in playbooks["situations"].items()],
        "guards": {**playbooks["guards"], **fam.get("guards", {})},  # a family may state its own (ADR-216, ic)
        "approaches": {k: [dict(x) if isinstance(x, dict) else x for x in v] for k, v in fam["approaches"].items()},
    }
    validate_body(body)
    return body


def _copy(values: list | None) -> list | None:
    return None if values is None else list(values)


def _no_floats(value: object, path: str) -> None:
    if isinstance(value, float):
        raise ValueError(f"a float is not allowed in a playbook body ({path} = {value!r}); write a decimal string")
    if isinstance(value, Mapping):
        for k, v in value.items():
            _no_floats(v, f"{path}.{k}")
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _no_floats(v, f"{path}[{i}]")


def _is_value(text: object, tid: str) -> bool:
    if not isinstance(text, str):
        return False
    if text == "":
        return True
    if tid == "T-10b":
        return len(text) == 5 and text[2] == ":" and text[:2].isdigit() and text[3:].isdigit()  # noqa: PLR2004
    try:
        return Decimal(text).is_finite()
    except InvalidOperation:
        return False


def validate_body(body: Mapping) -> None:  # noqa: C901, PLR0912 - one check per shape rule, kept flat
    """Refuse a body the evaluator cannot read exactly (fail closed): ValueError naming what is wrong."""
    _no_floats(body, "body")
    if body.get("schema") != 1:
        raise ValueError(f"unsupported playbook body schema {body.get('schema')!r}")
    stages = body.get("stages")
    if not isinstance(stages, Mapping) or set(stages) != {"weekly", "monthly"}:
        raise ValueError("stages must hold exactly 'weekly' and 'monthly'")
    for kind, rows in stages.items():
        if not rows:
            raise ValueError(f"{kind} has no stage")
        for s in rows:
            if not isinstance(s.get("name"), str) or not isinstance(s.get("from"), int) or \
                    not (s.get("to") is None or isinstance(s.get("to"), int)):
                raise ValueError(f"{kind} stage {s!r} needs a name, an int 'from' and an int or null 'to'")
    for tid, t in body.get("triggers", {}).items():
        for kind in ("weekly", "monthly"):
            values = t.get(kind)
            if values is None:
                continue
            if not isinstance(values, list) or len(values) != len(stages[kind]):
                raise ValueError(f"trigger {tid}: {kind} has {len(values) if isinstance(values, list) else values!r} "
                                 f"values for {len(stages[kind])} stages")
            for v in values:
                if not _is_value(v, tid):
                    raise ValueError(f"trigger {tid}: {kind} value {v!r} is not a decimal string")
    for rule in body.get("rules", []):
        kinds = [k for k in ("any_of", "all_of") if k in rule]
        if not isinstance(rule.get("id"), str) or len(kinds) != 1 or not rule[kinds[0]] or \
                not all(isinstance(m, str) for m in rule[kinds[0]]):
            raise ValueError(f"rule {rule!r} needs an id and exactly one non-empty any_of or all_of list")


def stage_of(body: Mapping, kind: ExpiryKind, days_left: int) -> int | None:
    """The stage whose from..to (inclusive; to None = open) covers ``days_left``; None when none does."""
    for i, s in enumerate(body["stages"][kind]):
        if days_left >= s["from"] and (s["to"] is None or days_left <= s["to"]):
            return i
    return None


# ---- one trigger -----------------------------------------------------------------------------------------------------
class _Missing(Exception):
    """A trigger cannot be checked: ``code`` is the reason code, ``slots`` its values."""

    def __init__(self, code: str, **slots: object) -> None:
        super().__init__(code)
        self.code = code
        self.slots = tuple(sorted(slots.items()))


def _need(value, what: str):
    if value is None:
        raise _Missing(f"{P}missing_{what}")
    return value


@dataclass(frozen=True)
class _Ctx:
    body: Mapping
    state: StrategyState
    stage: int | None
    stage_name: str | None
    gap_until: str = ""  # set by _outcomes from evaluate's required gap_until (never read before)


_STAGE_NAME_MAX = 80  # the PlaybookName slot's bound
_STAGE_FALLBACK = "current"


def stage_words(name: object) -> str:
    """The stage's name for the refusal sentence; a missing or unusable name reads "current", never a gap or a brace."""
    if not isinstance(name, str):
        return _STAGE_FALLBACK
    name = name.strip()
    if not name or len(name) > _STAGE_NAME_MAX or '"' in name or "{" in name or "}" in name:
        return _STAGE_FALLBACK
    return name


def _limit(c: _Ctx, tid: str) -> Decimal | str:
    """This stage's value of ``tid``, tightened by the due day rule when ``tid`` is a tightened trigger."""
    t = c.body["triggers"][tid]
    values = t.get(c.state.expiry_kind)
    if values is None:
        raise _Missing(f"{P}no_expiry_values")
    if c.stage is None:
        if c.state.days_left is None:
            raise _Missing(f"{P}missing_days_left")
        raise _Missing(f"{P}no_stage", days=c.state.days_left)
    raw = values[c.stage]
    if raw == "":
        raise _Missing(f"{P}no_stage_value", stage=stage_words(c.stage_name))
    if tid == "T-10b":
        return raw
    lim = Decimal(raw)
    pct = c.state.tighten_percent
    if pct is not None and tid in c.body.get("tightened", ()):
        with localcontext(_EXACT):
            lim = lim * (1 + pct / _HUNDRED) if t["cmp"] == "le" else lim * (1 - pct / _HUNDRED)
    return lim


def _exact(tid: str, num: Decimal, den: Decimal, lim: Decimal, cmp: Cmp) -> Hit:
    """value = num / den (den > 0) against ``lim``, exact and inclusive (the one comparison every trigger and day
    rule uses)."""
    with localcontext(_EXACT):
        scaled = lim * den
        fired = num <= scaled if cmp == "le" else num >= scaled
    with localcontext(_SHOW):
        value = num / den
    return Hit(tid, value, lim, cmp, fired)


def _compare(c: _Ctx, tid: str, num: Decimal, den: Decimal = Decimal(1)) -> Hit:
    """value = num / den (den > 0) against this stage's limit, exact and inclusive."""
    lim = _limit(c, tid)
    return _exact(tid, num, den, lim, c.body["triggers"][tid]["cmp"])  # type: ignore[arg-type]


def _shorts(s: StrategyState) -> tuple[ShortLeg, ...]:
    if not s.shorts:
        raise _Missing(f"{P}no_short_leg")
    return s.shorts


def short_gap_pct(spot: Decimal, shorts: tuple[ShortLeg, ...]) -> tuple[Decimal, Decimal]:
    """T-01's measure, "spot within this % of a short strike": (num, den) of the NEAREST short's |strike - spot| x 100
    / spot, kept as a fraction for the exact comparison. One function: T-01 and the expiry-day close rule use it."""
    near = min(abs(x.strike - spot) for x in shorts)  # ambiguous (two shorts): the nearest one
    return near * _HUNDRED, spot


def _t01(c: _Ctx) -> Hit:
    spot = _need(c.state.spot, "spot")
    return _compare(c, "T-01", *short_gap_pct(spot, _shorts(c.state)))


def _t01b(c: _Ctx) -> Hit:
    spot = _need(c.state.spot, "spot")
    return _compare(c, "T-01b", min(abs(x.strike - spot) for x in _shorts(c.state)))


def _t02(c: _Ctx) -> Hit:
    pnl = _need(c.state.expiry_pnl_at_spot, "expiry_pnl")
    return Hit("T-02", pnl, Decimal(0), "lt", pnl < 0)


def _t03(c: _Ctx) -> Hit:
    deltas = [x.abs_delta for x in _shorts(c.state)]
    if any(d is None for d in deltas):
        raise _Missing(f"{P}missing_short_delta")
    return _compare(c, "T-03", max(deltas))  # ambiguous (two shorts): the largest absolute delta


def _finite(value, what: str) -> Decimal:
    value = _need(value, what)
    if value in (UNLIMITED, 0):
        raise _Missing(f"{P}{what}_not_finite")
    return value


def _t06(c: _Ctx) -> Hit:
    pnl = _need(c.state.pnl, "pnl")
    return _compare(c, "T-06", *ratios.loss_pct_of_max_loss(pnl, _finite(c.state.max_loss, "max_loss")))


def _t07(c: _Ctx) -> Hit:
    pnl = _need(c.state.pnl, "pnl")
    return _compare(c, "T-07", *ratios.profit_pct_of_max_profit(pnl, _finite(c.state.max_profit, "max_profit")))


def short_premium(shorts: tuple[ShortLeg, ...]) -> Decimal:
    """T-09's measure, "short premium at or below Rs X": the lowest short LTP; any short unpriced -> not checked.
    One function: T-09 and the expiry-day close rule's A-27 (catalogue: T-09 -> A-27) use it."""
    prices = [x.ltp for x in shorts]
    if any(p is None for p in prices):
        raise _Missing(f"{P}missing_short_price")
    return min(p for p in prices if p is not None)


def _t09(c: _Ctx) -> Hit:
    return _compare(c, "T-09", short_premium(_shorts(c.state)))


def _t10b(c: _Ctx) -> Hit:
    hhmm = _need(c.state.hhmm, "clock")
    lim = _limit(c, "T-10b")
    return Hit("T-10b", hhmm, lim, "ge", hhmm >= lim)


def _t11(c: _Ctx) -> Hit:
    now = _need(c.state.atm_iv, "atm_iv")
    then = _need(c.state.entry_atm_iv, "entry_atm_iv")
    return _compare(c, "T-11", abs(now - then) * _HUNDRED)


def _t13(c: _Ctx) -> Hit:
    hhmm = _need(c.state.hhmm, "clock")
    if hhmm > c.gap_until:
        raise _Missing(f"{P}gap_after_open")
    prev = _need(c.state.prev_close, "prev_close")
    if prev <= 0:
        raise _Missing(f"{P}prev_close_not_positive")
    return _compare(c, "T-13", abs(_need(c.state.day_open, "day_open") - prev) * _HUNDRED, prev)


def _t16(c: _Ctx) -> Hit:
    margin = _need(c.state.margin, "margin")
    pnl = _need(c.state.pnl, "pnl")
    try:
        pair = ratios.loss_pct_of_margin(pnl, margin)
    except ValueError:
        raise _Missing(f"{P}margin_not_positive") from None
    return _compare(c, "T-16", *pair)


def _t18(c: _Ctx) -> Hit:
    used = _need(c.state.adjustments_used, "adjustments_used")
    mx = c.body.get("guards", {}).get("max_adjustments")
    if not isinstance(mx, int):
        raise _Missing(f"{P}missing_max_adjustments")
    return Hit("T-18", Decimal(used), Decimal(mx), "ge", used >= mx)


def _t19(c: _Ctx) -> Hit:
    left = _need(c.state.premium_left, "premium_left")
    if left < 0:
        raise _Missing(f"{P}net_long_premium")
    cost = c.state.adjustment_cost
    if cost is None:  # ADR-221: no approach offered / none priceable -> not checked, with that reason
        raise _Missing(c.state.adjustment_cost_reason or f"{P}missing_adjustment_cost")
    try:
        pair = ratios.premium_left_per_cost(left, cost)
    except ValueError:
        raise _Missing(f"{P}cost_not_positive") from None
    return _compare(c, "T-19", *pair)


def _t14(_c: _Ctx) -> Hit:
    raise _Missing(T14_PENDING)


_EVALUATORS: Final[dict[str, Callable[[_Ctx], Hit]]] = {
    "T-01": _t01, "T-01b": _t01b, "T-02": _t02, "T-03": _t03, "T-06": _t06, "T-07": _t07, "T-09": _t09,
    "T-10b": _t10b, "T-11": _t11, "T-13": _t13, "T-14": _t14, "T-16": _t16, "T-18": _t18, "T-19": _t19,
}
_T21: Final = "T-21"


def _trigger(c: _Ctx, tid: str) -> Hit | _Missing:  # noqa: PLR0911 - one answer per reason a trigger is not checked
    """A Hit, or the reason it is not checked."""
    t = c.body["triggers"].get(tid)
    if t is None:
        return _Missing(f"{P}unknown")
    if t.get("greyed"):
        return _Missing(f"{P}greyed")
    if not t.get("on"):
        return _Missing(f"{P}switched_off")
    if t.get("data", "ok") != "ok":
        return _Missing(f"{P}data_unavailable")
    fn = _EVALUATORS.get(tid)
    if fn is None:
        return _Missing(f"{P}not_evaluated")
    try:
        return fn(c)
    except _Missing as e:
        return e


# ---- rules -----------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class _Outcome:
    rule_id: str
    lead: str  # the trigger the result names
    hits: tuple[Hit, ...] = ()
    reason: str | None = None  # NotChecked code
    slots: tuple[tuple[str, object], ...] = ()
    fired: bool = False


def _rule(c: _Ctx, rule: Mapping) -> _Outcome:
    rid = rule["id"]
    members = rule.get("any_of") or rule["all_of"]
    answers = [(m, _trigger(c, m)) for m in members]
    missing = [(m, a) for m, a in answers if isinstance(a, _Missing)]
    hits = tuple(a for _, a in answers if isinstance(a, Hit))
    if "all_of" in rule:
        if missing:  # a NotChecked member makes an all_of rule NotChecked, never fired; it names that member
            return _Outcome(rid, missing[0][0], hits, missing[0][1].code, missing[0][1].slots)
        return _Outcome(rid, members[0], hits, fired=all(h.fired for h in hits))
    fired = [h for h in hits if h.fired]
    if fired:
        return _Outcome(rid, fired[0].trigger_id, hits, fired=True)
    if missing:  # nothing fired, but a member could not be checked: not a pass
        return _Outcome(rid, missing[0][0], hits, missing[0][1].code, missing[0][1].slots)
    return _Outcome(rid, members[0], hits)


def _context(body: Mapping, state: StrategyState) -> _Ctx:
    stage = None if state.days_left is None else stage_of(body, state.expiry_kind, state.days_left)
    name = None if stage is None else body["stages"][state.expiry_kind][stage]["name"]
    return _Ctx(body, state, stage, name)


def _withheld(state: StrategyState) -> str | None:
    if state.prices_fresh is not True:
        return f"{P}withheld_stale" if state.prices_fresh is False else f"{P}withheld_fresh_unknown"
    if state.spot is None:
        return f"{P}withheld_no_spot"
    return None


def _later(c: _Ctx, tid: str) -> tuple[Decimal | str, ...]:
    """The limits of ``tid`` at the stages after this one (same tightening); a stage without a value is skipped."""
    if c.stage is None:
        return ()
    out = []
    for i in range(c.stage + 1, len(c.body["stages"][c.state.expiry_kind])):
        try:
            out.append(_limit(dataclasses.replace(c, stage=i), tid))
        except _Missing:
            continue
    return tuple(out)


def _value_of(c: _Ctx, rule: Mapping | None, o: _Outcome) -> RuleValue | None:
    lead = next((h for h in o.hits if h.trigger_id == o.lead), None)
    if lead is None:
        return None
    members = len((rule or {}).get("any_of") or (rule or {}).get("all_of") or [o.lead])
    return RuleValue(o.rule_id, lead.trigger_id, lead.value, lead.threshold, lead.cmp, o.fired, members,
                     _later(c, lead.trigger_id))


def _outcomes(body: Mapping, state: StrategyState, gap_until: str) -> tuple[_Ctx, str | None, list[_Outcome]]:
    c = dataclasses.replace(_context(body, state), gap_until=gap_until)
    why = _withheld(state)
    out = []
    for rule in body.get("rules", []):
        members = rule.get("any_of") or rule["all_of"]
        if why is not None:
            out.append(_Outcome(rule["id"], members[0], reason=why))
        elif members == [_T21]:  # the T-21 guard: prices are fresh, so its condition is false
            out.append(_Outcome(rule["id"], _T21))
        else:
            out.append(_rule(c, rule))
    return c, why, out


def evaluate(body: Mapping, state: StrategyState, memory: Mapping[str, Mapping[str, bool]] | None = None,
             entry_state: StrategyState | None = None, *, gap_until: str) -> Evaluation:
    """Evaluate every rule of ``body`` on ``state``; pure (takes the F-71 memory, returns the new one). ``gap_until``
    is the user's gap-at-open window end "HH:MM" (REQ-168 AC-1; required, never defaulted)."""
    validate_body(body)
    if not isinstance(gap_until, str) or not re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", gap_until):
        raise ValueError(f"gap_until must be HH:MM, got {gap_until!r}")
    c, why, outcomes = _outcomes(body, state, gap_until)
    entry = None
    new = {k: dict(v) for k, v in (memory or {}).items()}
    results: list[Result] = []
    clear = []
    values: list[RuleValue] = []
    rules = {r["id"]: r for r in body.get("rules", [])}
    for o in outcomes:
        if o.rule_id not in new:
            if entry is None:
                entry = ({} if entry_state is None else
                         {x.rule_id: x.fired for x in _outcomes(body, entry_state, gap_until)[2]})
            new[o.rule_id] = {"held_at_entry": bool(entry.get(o.rule_id, False)), "seen_clear": False}
        mem = new[o.rule_id]
        if o.reason is not None:
            results.append(NotChecked(o.rule_id, o.lead, o.reason, o.slots))
        elif not o.fired:
            mem["seen_clear"] = True
            clear.append(o.rule_id)
            rv = _value_of(c, rules.get(o.rule_id), o)
            if rv is not None:
                values.append(rv)
        else:
            lead = next((h for h in o.hits if h.trigger_id == o.lead), o.hits[0])
            if mem["held_at_entry"] and not mem["seen_clear"]:
                results.append(AlreadyTrue(o.rule_id, lead.trigger_id, lead.value, lead.threshold, cmp=lead.cmp))
            else:
                results.append(Flag(o.rule_id, lead.trigger_id, c.stage_name, lead.value, lead.threshold, lead.cmp,
                                    o.hits))
                rv = _value_of(c, rules.get(o.rule_id), o)
                if rv is not None:
                    values.append(rv)
    _add_day_rules(body, state, why, c.stage_name, (results, clear, values),
                   _t09_now(c))
    _add_situation_rules(body, state, why, c.stage_name, (results, clear, values))
    _add_watch_rules(state, why, c.stage_name, (results, clear, values))
    return Evaluation(c.stage_name, c.stage, tuple(results), new, tuple(clear), why, values=tuple(values))


# ---- day rules (GC-IC1 step 1a; REQ-159 AC-4, REQ-170) -----------------------------------------------------------
#: A day rule is reported as a rule of its own, id ``day.<when>.<HHMM>.<action>`` (from the rule's content, so a
#: reordered day_rules list keeps every id; GC-IC1 1a review B3). It goes to the alert gate as a yes/no value
#: (``RuleValue.yes_no``), so a record is opened only by ``alert_gate.step`` (edge, not level: one record per
#: episode). F-71 memory does not apply: the rule is checked only from its time on, so the time reaching ``at`` is
#: itself the event.
#: Not due (not expiry day, or before ``at``) -> no answer at all: no reading, so no record and no false clear.
DAY_RULE_PREFIX: Final = "day."
LEGACY_DAY_RULE_PREFIX: Final = "day:"  # ids stored before GC-IC1 fix (colons fail the Identifier pattern); read only
DAY_ACTION_PREPARE_EXIT: Final = 5  # PLAYBOOK_DAY_RULE_ACTION_TEXT["5"], "Prepare an exit for review"
DAY_RULE_INCOMPLETE: Final = f"{P}day_rule_incomplete"
CLOSE_WITHIN_KEY: Final = "close_if_short_within_pct"
TESTED_SPREAD: Final = "A-28"
FAR_SHORT: Final = "A-27"
_HHMM: Final = re.compile(r"[0-2][0-9]:[0-5][0-9]")


@dataclass(frozen=True)
class DayAnswer:
    """One due day rule's answer: a ``hit`` (value = the nearest short's distance from spot in %, threshold = the
    rule's %, ``le``) or a NotChecked ``reason``; ``approaches`` named when it fired."""

    rule_id: str
    action: int
    hit: Hit | None = None
    reason: str | None = None
    slots: tuple[tuple[str, object], ...] = ()
    approaches: tuple[str, ...] = ()


def day_rule_id(rule: Mapping) -> str:
    """The stable id of a day rule: its kind, time and action (``day.expiry.1430.5``)."""
    at = str(rule.get("at")).replace(":", "")
    return f"{DAY_RULE_PREFIX}{rule.get('when')}.{at}.{rule.get('action')}"


def is_day_rule_id(rule_id: object) -> bool:
    return isinstance(rule_id, str) and rule_id.startswith((DAY_RULE_PREFIX, LEGACY_DAY_RULE_PREFIX))


def day_rule_action(body: Mapping | None, rule_id: object) -> int | None:
    """The action index of the day rule ``rule_id`` names in ``body``; None when it names none."""
    if not is_day_rule_id(rule_id) or not isinstance(body, Mapping):
        return None
    rules = body.get("day_rules")
    for rule in rules if isinstance(rules, list) else []:
        if isinstance(rule, Mapping) and day_rule_id(rule) == rule_id:
            action = rule.get("action")
            return action if type(action) is int else None
    return None


def _decimal_text(value: object) -> Decimal | None:
    """A non-negative finite decimal string -> its Decimal; anything else (a float, a word, None) -> None."""
    if not isinstance(value, str):
        return None
    try:
        d = Decimal(value)
    except InvalidOperation:
        return None
    return d if d.is_finite() and d >= 0 else None


def _expiry_close(t09: tuple[Decimal, Cmp] | None, rule: Mapping, rid: str,  # noqa: PLR0911 - one answer per reason
                  state: StrategyState, why: str | None) -> DayAnswer | None:
    """``when: expiry`` + ``close_if_short_within_pct`` P: on expiry day from ``at``, True when a short's strike is
    within P% of spot (|strike - spot| * 100 <= P * spot, exact). None = not due (no reading at all)."""
    at, pct = rule.get("at"), _decimal_text(rule.get(CLOSE_WITHIN_KEY))
    if not isinstance(at, str) or not _HHMM.fullmatch(at) or pct is None:
        return DayAnswer(rid, DAY_ACTION_PREPARE_EXIT, reason=DAY_RULE_INCOMPLETE)
    if state.days_left is None:
        return DayAnswer(rid, DAY_ACTION_PREPARE_EXIT, reason=f"{P}missing_days_left")
    if state.days_left != 0:
        return None
    if state.hhmm is None:
        return DayAnswer(rid, DAY_ACTION_PREPARE_EXIT, reason=f"{P}missing_clock")
    if state.hhmm < at:
        return None
    if why is not None:
        return DayAnswer(rid, DAY_ACTION_PREPARE_EXIT, reason=why)
    if state.spot is None:
        return DayAnswer(rid, DAY_ACTION_PREPARE_EXIT, reason=f"{P}missing_spot")
    if not state.shorts:
        return DayAnswer(rid, DAY_ACTION_PREPARE_EXIT, reason=f"{P}no_short_leg")
    hit = _exact(rid, *short_gap_pct(state.spot, state.shorts), pct, "le")  # T-01's measure: nearest short within
    if not hit.fired:
        return DayAnswer(rid, DAY_ACTION_PREPARE_EXIT, hit)
    far = _far_short_named(t09, state, pct)
    return DayAnswer(rid, DAY_ACTION_PREPARE_EXIT, hit, approaches=(TESTED_SPREAD, *((FAR_SHORT,) if far else ())))


def _far_short_named(t09: tuple[Decimal, Cmp] | None, state: StrategyState, pct: Decimal) -> bool:
    """A-27 (ADR-238 (4)) for the shorts NOT within ``pct`` (each read with T-01's measure), when T-09's measure on
    them (lowest LTP, any unpriced -> not named) passes T-09's own comparison against T-09's threshold of the CURRENT
    stage (iron condor weekly Rs 3 / 3 / 2, ``le``): one value, no second body key. T-09 off or absent -> not named."""
    if t09 is None or state.spot is None:
        return False
    below, cmp = t09
    spot = state.spot
    others = tuple(x for x in state.shorts if not _exact("T-01", *short_gap_pct(spot, (x,)), pct, "le").fired)
    if not others:
        return False
    try:
        return _exact("T-09", short_premium(others), Decimal(1), below, cmp).fired
    except _Missing:
        return False


def day_answers(body: Mapping, state: StrategyState, why: str | None = None,
                t09: tuple[Decimal, Cmp] | None = None) -> tuple[DayAnswer, ...]:
    """Every switched-on day rule this version checks, answered on ``state`` (the one function: ``evaluate`` calls
    it for the screen and the worker alike). Only the expiry-day close rule (action 5 with
    ``close_if_short_within_pct``) is checked here; the tighten rule (action 4) stays ``tighten_percent``."""
    out: list[DayAnswer] = []
    rules = body.get("day_rules")
    for rule in rules if isinstance(rules, list) else []:
        if not isinstance(rule, Mapping) or rule.get("on") is not True:
            continue
        when, action = rule.get("when"), rule.get("action")
        answer = None
        if when == "expiry" and action == DAY_ACTION_PREPARE_EXIT:
            answer = _expiry_close(t09, rule, day_rule_id(rule), state, why)
        elif when in CARRY_WHENS and action == DAY_ACTION_CARRY_CHECK:
            answer = _carry_check(rule, day_rule_id(rule), state)
        if answer is not None:
            out.append(answer)
    return tuple(out)


def _t09_now(c: _Ctx) -> tuple[Decimal, Cmp] | None:
    """T-09's threshold of the current stage and its comparison (ADR-238 (4)); None when T-09 is off, absent, or has
    no value this stage (then A-27 is not named)."""
    triggers = c.body.get("triggers")
    t = triggers.get("T-09") if isinstance(triggers, Mapping) else None
    if not isinstance(t, Mapping) or t.get("on") is not True or t.get("cmp") not in ("le", "ge"):
        return None
    try:
        lim = _limit(c, "T-09")
    except (_Missing, InvalidOperation, IndexError):
        return None
    return (lim, t["cmp"]) if isinstance(lim, Decimal) else None


def exit_inputs(body: Mapping | None, guards: Mapping | None, state: StrategyState) -> ExitInputs:
    """A-27's and A-35's playbook inputs (ADR-238 (4), (5)) for the approach builder: T-09's threshold of the CURRENT
    stage through the expiry-day rule's own reader (``_t09_now``: one value, tightened as T-09 is), the guard
    ``time_exit`` when it is a valid "HH:MM", and the check's clock ``state.hhmm``. No body (or a body this reader
    cannot read) -> no T-09; never a default."""
    t09 = None
    if isinstance(body, Mapping):
        try:
            t09 = _t09_now(_context(body, state))
        except (KeyError, TypeError, IndexError):  # a body without this expiry kind's stages: no limit, never a guess
            t09 = None
    at = guards.get("time_exit") if isinstance(guards, Mapping) else None
    return ExitInputs(t09, at if isinstance(at, str) and _HHMM.fullmatch(at) else None, state.hhmm)


def _add_day_rules(body: Mapping, state: StrategyState, why: str | None, stage_name: str | None,  # noqa: PLR0913
                   out: tuple[list[Result], list[str], list[RuleValue]],
                   t09: tuple[Decimal, Cmp] | None = None) -> None:
    """The due day rules into ``evaluate``'s results / clear / values (a yes/no value each)."""
    results, clear, values = out
    for d in day_answers(body, state, why, t09):
        if d.hit is None:
            results.append(NotChecked(d.rule_id, d.rule_id, d.reason or DAY_RULE_INCOMPLETE, d.slots))
            continue
        hit = d.hit
        if hit.fired:
            results.append(Flag(d.rule_id, d.rule_id, stage_name, hit.value, hit.threshold, hit.cmp, (hit,)))
        else:
            clear.append(d.rule_id)
        carry = state.carry if d.action == DAY_ACTION_CARRY_CHECK else None
        values.append(RuleValue(d.rule_id, d.rule_id, hit.value, hit.threshold, hit.cmp, hit.fired,
                                yes_no=True, approaches=d.approaches, carry=carry))


# ---- level watch (GC-IC1 step 4c; A-37, ADR-242) -----------------------------------------------------------------
#: Each active watch is a yes/no rule ``watch.level.<direction>`` (``level_watch``): value = the spot, threshold = the
#: level, ``ge`` (above) / ``le`` (below), exact and inclusive. It goes to the alert gate as a yes/no value, so the
#: gate opens one record per episode. A withheld check (stale prices) or no spot -> NotChecked: no reading, never
#: False. F-71 memory does not apply (the user set the level to be told when it is reached).
WATCH_NO_SPOT: Final = f"{P}missing_spot"


def _add_watch_rules(state: StrategyState, why: str | None, stage_name: str | None,
                     out: tuple[list[Result], list[str], list[RuleValue]]) -> None:
    results, clear, values = out
    for w in state.watches:
        rid = level_watch.rule_id(w.direction)
        reached = None if why is not None else level_watch.answer(w, state.spot)
        if reached is None or state.spot is None:
            results.append(NotChecked(rid, rid, why or WATCH_NO_SPOT))
            continue
        cmp: Cmp = level_watch.CMP[w.direction]  # type: ignore[assignment]
        hit = Hit(rid, state.spot, w.level, cmp, reached)
        if reached:
            results.append(Flag(rid, rid, stage_name, hit.value, hit.threshold, hit.cmp, (hit,)))
        else:
            clear.append(rid)
        values.append(RuleValue(rid, rid, hit.value, hit.threshold, hit.cmp, reached, yes_no=True))


# ---- carry check (GC-IC1 step 1b; REQ-159 AC-4, S-06) ------------------------------------------------------------
#: ``beforeWeekend`` / ``beforeHoliday`` + action 0 ("Run the carry check"): on such a day from ``at`` the rule reads
#: True (a yes/no gate reading; the gate opens one record per episode, so later checks the same evening hold it).
#: The record carries ``StrategyState.carry`` (the 2% gap figures at the next open and the stated margin).
#: Not due (another day, or before ``at``) -> no answer. Holiday list not known -> NotChecked, never assumed a session.
#: A Thursday before a Friday holiday is both kinds: both switched-on rules answer, one record per rule id.
DAY_ACTION_CARRY_CHECK: Final = 0  # PLAYBOOK_DAY_RULE_ACTION_TEXT["0"], "Run the carry check"
BEFORE_WEEKEND: Final = "beforeWeekend"
BEFORE_HOLIDAY: Final = "beforeHoliday"
CARRY_WHENS: Final = (BEFORE_WEEKEND, BEFORE_HOLIDAY)
HOLIDAY_LIST_UNKNOWN: Final = f"{P}holiday_list_unknown"
_NOON: Final = datetime.time(12, 0)
_SATURDAY: Final = 5


def _status(day: datetime.date, holidays: mc.Holidays | None) -> mc.MarketStatus:
    """The day-level status (read at noon, inside the session hours)."""
    return mc.market_status(datetime.datetime.combine(day, _NOON, IST), holidays)


def carry_day_kinds(today: datetime.date, holidays: mc.Holidays | None = None) -> frozenset[str] | None:
    """Today's carry day kinds from the NSE holiday data (``market_calendar``; ``holidays`` for tests only).
    ``beforeWeekend``: today is a session and a Saturday lies before the next session (the generator's ``day_type``).
    ``beforeHoliday``: today is a session and the next calendar weekday is a listed holiday. Today not a session ->
    empty. None = a year the answer needs has no holiday data (``NO_CALENDAR``): not known, never a guess."""
    status = _status(today, holidays)
    if status is mc.MarketStatus.NO_CALENDAR:
        return None
    if status is not mc.MarketStatus.OPEN:  # a weekend or a holiday itself: no carry day
        return frozenset()
    opens = mc.next_open(datetime.datetime.combine(today, _NOON, IST), holidays)
    if opens is None:
        return None
    kinds: set[str] = set()
    if any((today + datetime.timedelta(days=i)).weekday() == _SATURDAY for i in range(1, (opens.date() - today).days)):
        kinds.add(BEFORE_WEEKEND)
    weekday = today + datetime.timedelta(days=1)
    while weekday.weekday() >= _SATURDAY:
        weekday += datetime.timedelta(days=1)
    after = _status(weekday, holidays)
    if after is mc.MarketStatus.NO_CALENDAR:
        return None
    if after is mc.MarketStatus.CLOSED_HOLIDAY:
        kinds.add(BEFORE_HOLIDAY)
    return frozenset(kinds)


def carry_due(body: Mapping | None, state: StrategyState) -> bool:
    """True when a switched-on carry rule is due on ``state`` (its day kind and its time): the caller computes the
    carry figures (``StrategyState.carry``) only then, so no other check pays for them."""
    return isinstance(body, Mapping) and any(
        d.hit is not None and d.action == DAY_ACTION_CARRY_CHECK for d in day_answers(body, state))


def _carry_check(rule: Mapping, rid: str, state: StrategyState) -> DayAnswer | None:
    at = rule.get("at")
    if not isinstance(at, str) or not _HHMM.fullmatch(at):
        return DayAnswer(rid, DAY_ACTION_CARRY_CHECK, reason=DAY_RULE_INCOMPLETE)
    if state.hhmm is None:
        return DayAnswer(rid, DAY_ACTION_CARRY_CHECK, reason=f"{P}missing_clock")
    if state.hhmm < at:
        return None
    if state.carry_days is None:
        return DayAnswer(rid, DAY_ACTION_CARRY_CHECK, reason=HOLIDAY_LIST_UNKNOWN)
    if rule.get("when") not in state.carry_days:
        return None
    return DayAnswer(rid, DAY_ACTION_CARRY_CHECK, Hit(rid, state.hhmm, at, "ge", True))


# ---- situation rules (GC-IC1 step 6a; REQ-159 AC-5, ADR-240 (3)) ---------------------------------------------------
#: S-02 "Trending day" and S-12 "Big win early" are rules when the playbook lists the situation (its ``situations``,
#: present in every saved body since v1; no new body key). Each answers as a yes/no gate reading, id ``sit.<S-id>``,
#: and names its approaches on the record (the gate opens one record per episode, ``alert_gate.step``).
#: The thresholds are ADR-240 (3)'s, named here until the editor exposes them; NEVER read from the body, so a body
#: saved before this step fires the same way.
SITUATION_RULE_PREFIX: Final = "sit."
LEGACY_SITUATION_RULE_PREFIX: Final = "sit:"
TRENDING_DAY: Final = "S-02"
BIG_WIN_EARLY: Final = "S-12"
S02_NET_DELTA_PER_LOT: Final = Decimal("0.15")  # ADR-240 (3): at or beyond +/-0.15 per lot
S12_PCT_OF_MAX_PROFIT: Final = Decimal(40)  # ADR-240 (3): profit at or above 40% of max profit, entry session only
S12_APPROACHES: Final = ("A-24", "A-25")  # ADR-240 (3): take profit / close the whole position
MISSING_LEG_DELTA: Final = f"{P}missing_leg_delta"
MISSING_ENTRY_DAY: Final = f"{P}missing_entry_day"
_ROLL: Final = "roll"
SITUATION_ACTION: Final = -1  # a situation rule has no day-rule action index


def situation_rule_id(situation: str) -> str:
    return f"{SITUATION_RULE_PREFIX}{situation}"


def is_situation_rule_id(rule_id: object) -> bool:
    return isinstance(rule_id, str) and rule_id.startswith((SITUATION_RULE_PREFIX, LEGACY_SITUATION_RULE_PREFIX))


def situation_of(body: Mapping | None, rule_id: object) -> Mapping | None:
    """The ``situations`` entry of ``body`` that ``rule_id`` (``sit.S-02``) names; None when it names none."""
    if not is_situation_rule_id(rule_id) or not isinstance(body, Mapping):
        return None
    sid = rule_id[len(SITUATION_RULE_PREFIX):]
    listed = body.get("situations")
    if not isinstance(listed, list):
        return None
    return next((x for x in listed if isinstance(x, Mapping) and x.get("id") == sid), None)


def _listed(body: Mapping, situation: str) -> bool:
    return situation_of(body, situation_rule_id(situation)) is not None


def _trending_day(body: Mapping, state: StrategyState, why: str | None) -> DayAnswer | None:
    """S-02: |net delta per lot| >= 0.15 (``ratios.net_delta_per_lot``, the engine sum). None = no answer: the
    playbook does not list S-02, or it offers no roll now (none on, or S-11's limit)."""
    rid = situation_rule_id(TRENDING_DAY)
    rolls = tuple(a for a in offered_now(body, state.adjustments_used) if KINDS.get(a) == _ROLL)
    if not _listed(body, TRENDING_DAY) or not rolls:
        return None
    if why is not None:
        return DayAnswer(rid, SITUATION_ACTION, reason=why)
    if not state.held or any(x.greeks is None or x.greeks.delta is None for x in state.held):
        return DayAnswer(rid, SITUATION_ACTION, reason=MISSING_LEG_DELTA)  # never a missing delta read as 0
    try:
        num, den = ratios.net_delta_per_lot(tuple((x.greeks, Action(x.side), x.lots) for x in state.held))
    except ValueError:
        return DayAnswer(rid, SITUATION_ACTION, reason=MISSING_LEG_DELTA)
    hit = _exact(rid, num, den, S02_NET_DELTA_PER_LOT, "ge")
    return DayAnswer(rid, SITUATION_ACTION, hit, approaches=rolls if hit.fired else ())


def _big_win_early(body: Mapping, state: StrategyState, why: str | None) -> DayAnswer | None:  # noqa: PLR0911
    """S-12: on the entry session (IST date of the first order) profit >= 40% of max profit (T-07's engine ratio).
    Another session -> no answer (day 1 only). Entry day or today not known -> NotChecked, never False."""
    rid = situation_rule_id(BIG_WIN_EARLY)
    offered = offered_now(body, state.adjustments_used)
    named = tuple(a for a in S12_APPROACHES if a in offered)
    if not _listed(body, BIG_WIN_EARLY) or not named:
        return None
    if state.entry_day is None:
        return DayAnswer(rid, SITUATION_ACTION, reason=MISSING_ENTRY_DAY)
    if state.today is None:
        return DayAnswer(rid, SITUATION_ACTION, reason=f"{P}missing_clock")
    if state.today != state.entry_day:
        return None
    if why is not None:
        return DayAnswer(rid, SITUATION_ACTION, reason=why)
    try:
        pnl = _need(state.pnl, "pnl")
        hit = _exact(rid, *ratios.profit_pct_of_max_profit(pnl, _finite(state.max_profit, "max_profit")),
                     S12_PCT_OF_MAX_PROFIT, "ge")
    except _Missing as e:
        return DayAnswer(rid, SITUATION_ACTION, reason=e.code, slots=e.slots)
    return DayAnswer(rid, SITUATION_ACTION, hit, approaches=named if hit.fired else ())


def situation_answers(body: Mapping, state: StrategyState, why: str | None = None) -> tuple[DayAnswer, ...]:
    """S-02 and S-12 answered on ``state`` (the one function the screen and the worker reach through ``evaluate``)."""
    return tuple(a for a in (_trending_day(body, state, why), _big_win_early(body, state, why)) if a is not None)


def _add_situation_rules(body: Mapping, state: StrategyState, why: str | None, stage_name: str | None,
                         out: tuple[list[Result], list[str], list[RuleValue]]) -> None:
    """S-02 / S-12 into ``evaluate``'s results / clear / values, a yes/no value each (as the day rules)."""
    results, clear, values = out
    for d in situation_answers(body, state, why):
        if d.hit is None:
            results.append(NotChecked(d.rule_id, d.rule_id, d.reason or MISSING_LEG_DELTA, d.slots))
            continue
        hit = d.hit
        if hit.fired:
            results.append(Flag(d.rule_id, d.rule_id, stage_name, hit.value, hit.threshold, hit.cmp, (hit,)))
        else:
            clear.append(d.rule_id)
        values.append(RuleValue(d.rule_id, d.rule_id, hit.value, hit.threshold, hit.cmp, hit.fired,
                                yes_no=True, approaches=d.approaches))
