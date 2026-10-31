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

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Context, Decimal, DivisionByZero, Inexact, InvalidOperation, Overflow, localcontext
from typing import Final, Literal

from ofo.engine import adjust_ratios as ratios
from ofo.errors import render

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
_GAP_UNTIL: Final = "09:30"
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
    adjustment_cost: Decimal | None = None
    atm_iv: Decimal | None = None
    entry_atm_iv: Decimal | None = None
    day_open: Decimal | None = None
    prev_close: Decimal | None = None
    adjustments_used: int | None = None
    expiry_pnl_at_spot: Decimal | None = None  # T-02: whole-trade P&L at expiry if spot stays here
    tighten_percent: Decimal | None = None  # the due day rule's X ("Tighten every trigger by X%")
    prices_fresh: bool | None = None  # T-21: True only when the prices are fresh; None = unknown


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
class Evaluation:
    stage_name: str | None
    stage_index: int | None
    results: tuple[Result, ...]
    memory: dict[str, dict[str, bool]]
    clear: tuple[str, ...] = ()  # rule ids evaluated false at this check
    withheld: str | None = None  # T-21: why no suggestion is made
    notes: tuple[str, ...] = field(default=())


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


_STAGE_NAME_MAX = 80  # the PlaybookName slot's bound
_STAGE_FALLBACK = "current"


def _stage_words(name: object) -> str:
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
        raise _Missing(f"{P}no_stage_value", stage=_stage_words(c.stage_name))
    if tid == "T-10b":
        return raw
    lim = Decimal(raw)
    pct = c.state.tighten_percent
    if pct is not None and tid in c.body.get("tightened", ()):
        with localcontext(_EXACT):
            lim = lim * (1 + pct / _HUNDRED) if t["cmp"] == "le" else lim * (1 - pct / _HUNDRED)
    return lim


def _compare(c: _Ctx, tid: str, num: Decimal, den: Decimal = Decimal(1)) -> Hit:
    """value = num / den (den > 0) against this stage's limit, exact and inclusive."""
    lim = _limit(c, tid)
    cmp = c.body["triggers"][tid]["cmp"]
    with localcontext(_EXACT):
        scaled = lim * den
        fired = num <= scaled if cmp == "le" else num >= scaled
    with localcontext(_SHOW):
        value = num / den
    return Hit(tid, value, lim, cmp, fired)


def _shorts(s: StrategyState) -> tuple[ShortLeg, ...]:
    if not s.shorts:
        raise _Missing(f"{P}no_short_leg")
    return s.shorts


def _t01(c: _Ctx) -> Hit:
    spot = _need(c.state.spot, "spot")
    near = min(abs(x.strike - spot) for x in _shorts(c.state))  # ambiguous (two shorts): the nearest one
    return _compare(c, "T-01", near * _HUNDRED, spot)


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


def _t09(c: _Ctx) -> Hit:
    prices = [x.ltp for x in _shorts(c.state)]
    if any(p is None for p in prices):
        raise _Missing(f"{P}missing_short_price")
    return _compare(c, "T-09", min(prices))


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
    if hhmm > _GAP_UNTIL:
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
    cost = _need(c.state.adjustment_cost, "adjustment_cost")
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


def _outcomes(body: Mapping, state: StrategyState) -> tuple[_Ctx, str | None, list[_Outcome]]:
    c = _context(body, state)
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
             entry_state: StrategyState | None = None) -> Evaluation:
    """Evaluate every rule of ``body`` on ``state``; pure (takes the F-71 memory, returns the new one)."""
    validate_body(body)
    c, why, outcomes = _outcomes(body, state)
    entry = None
    new = {k: dict(v) for k, v in (memory or {}).items()}
    results: list[Result] = []
    clear = []
    for o in outcomes:
        if o.rule_id not in new:
            if entry is None:
                entry = {} if entry_state is None else {x.rule_id: x.fired for x in _outcomes(body, entry_state)[2]}
            new[o.rule_id] = {"held_at_entry": bool(entry.get(o.rule_id, False)), "seen_clear": False}
        mem = new[o.rule_id]
        if o.reason is not None:
            results.append(NotChecked(o.rule_id, o.lead, o.reason, o.slots))
        elif not o.fired:
            mem["seen_clear"] = True
            clear.append(o.rule_id)
        else:
            lead = next((h for h in o.hits if h.trigger_id == o.lead), o.hits[0])
            if mem["held_at_entry"] and not mem["seen_clear"]:
                results.append(AlreadyTrue(o.rule_id, lead.trigger_id, lead.value, lead.threshold, cmp=lead.cmp))
            else:
                results.append(Flag(o.rule_id, lead.trigger_id, c.stage_name, lead.value, lead.threshold, lead.cmp,
                                    o.hits))
    return Evaluation(c.stage_name, c.stage, tuple(results), new, tuple(clear), why)
