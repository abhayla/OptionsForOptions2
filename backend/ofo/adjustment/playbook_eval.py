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
from ofo.adjustment import stop_lines as sl
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
#: T-14 (goal contract ic-e2e-paper, design decision 8): the worst whole-position P&L change from repricing at spot
#: x 1.01 and x 0.99 (same IV, same clock) through the engine (``ofo.adjustment.gamma``), as a % of the margin blocked.
#: Evaluated ONLY in scenario mode (B2 review F1): the one choke point is ``adjustment_check.with_gamma``, which fills
#: ``StrategyState.gamma`` only when ``scenario_mode.current()`` is set. No figures (live mode, or no state builder)
#: -> T-14 answers ``T14_PENDING`` exactly as before; figures that could not be valued -> ``GAMMA_UNKNOWN``.
#: Reason codes: each is a catalogue template id (backend/ofo/errors/templates.py, ``adjust_trigger_*``). The
#: evaluator returns the code and its slots; ``reason_text`` renders it through render(), the one route to a user.
P: Final = "adjust_trigger_"
T14_PENDING: Final = f"{P}t14_pending"
ALREADY_TRUE: Final = f"{P}already_true"
GAMMA_UNKNOWN: Final = f"{P}gamma_unknown"  # T-14: the 1% repricing could not be done (no model, a leg without IV)
MARGIN_UNREADABLE: Final = f"{P}margin_unreadable"  # a margin that is not a finite number
GAMMA_MOVE_PCT: Final = Decimal(1)  # T-14: the spot move, % up and down
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
    kind: str | None = None  # "CE" / "PE" (ADR-268: T-01 breached side); None = unknown, no breach check


@dataclass(frozen=True)
class CarryFigures:
    """The carry check's content (GC-IC1 1b, S-06): the whole-trade P&L (booked plus open legs) if spot gaps
    the carry gap setting (``other.carry_gap_percent``) up / down at the next session's open, valued by the engine (``ofo.adjustment.carry.gap_pnl``),
    and the broker-stated overnight margin. A figure not known is None with its reason code, never a zero."""

    up: Decimal | None
    down: Decimal | None
    gap_reason: str | None = None  # why up / down are None (a catalogue reason code)
    margin: Decimal | None = None  # the broker-stated margin; None = not stated (``margin_reason``)
    margin_reason: str | None = None
    next_open: datetime.datetime | None = None  # the time the gap figures are valued at
    gap_pct: Decimal | None = None  # the gap size in force (``other.carry_gap_percent``); None = not read
    #: where ``gap_pct`` came from (ADR-245, ``ofo.settings.layers``): "this strategy" / "your setting" / "default";
    #: None when not read
    gap_source: str | None = None
    #: why the gap setting could not be read (a ``layers`` reason code naming the layer; fail closed), else None
    gap_setting_reason: str | None = None


@dataclass(frozen=True)
class GammaFigures:
    """T-14's content (design decision 8): the whole-position P&L change if spot were ``GAMMA_MOVE_PCT`` % up / down
    NOW (same IVs, the same valuation clock ``at`` for the base and both moves), valued by the engine
    (``ofo.adjustment.gamma.gamma_figures``). Booked P&L cancels out of a change. Not known -> None with ``reason``
    (a catalogue reason code), never a zero."""

    up: Decimal | None
    down: Decimal | None
    reason: str | None = None
    at: datetime.datetime | None = None  # the one clock the base and both moves are valued at
    levels: tuple[Decimal, Decimal] | None = None  # (up level, down level) repriced at


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
    #: B2: True when the margin reply could not be read (``margin_block`` state "failed", or a figure that is not a
    #: number); T-14 then says "could not be read" rather than "not available". Either way ``margin`` is None.
    margin_unreadable: bool = False
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
    #: T-14's 1% repricing; None = not computed (live mode: ``with_gamma`` fills it in scenario mode only), so T-14
    #: answers ``T14_PENDING`` as before the formula existed
    gamma: GammaFigures | None = None
    #: GC-IC1 6a (ADR-240 (3)): every open option leg with its engine Greeks (S-02); None = the legs were not read
    held: tuple[HeldLeg, ...] | None = None
    today: datetime.date | None = None  # the IST session date of this check (S-12); None = not known
    entry_day: datetime.date | None = None  # the IST date the strategy was entered (first order); None = not known
    #: GC-IC1 4c (A-37, ADR-242): the user's active level watches, read on the rebuild with the gate load (never per
    #: check); () = none set
    watches: tuple[level_watch.LevelWatch, ...] = ()
    #: REQ-167 AC-4: the situation settings in force (``other.situation_net_delta_per_lot`` for S-02,
    #: ``other.situation_big_win_percent`` for S-12); None = not read, so that situation answers not checked
    s02_delta_per_lot: Decimal | None = None
    s12_percent: Decimal | None = None
    #: contract step 3 (ADR-245/247/250/251): the stop lines in force, from ``settings_in_force.stops_of`` ONLY (the
    #: evaluator owns no stop value). REQUIRED, no default: a caller that forgets the stops cannot build a state; None
    #: = not supplied, so the stop answers "not checked" (``sl.STOPS_NOT_SUPPLIED``), never a pass
    stops: sl.StopsInForce | None = field(kw_only=True)


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
    return _tightened(c, tid, Decimal(raw), t["cmp"])


def _tightened(c: _Ctx, tid: str, lim: Decimal, cmp: str) -> Decimal:
    """``lim`` tightened by the due day rule's X % when ``tid`` is a tightened trigger (one rule for every trigger
    and for the stop lines in force)."""
    pct = c.state.tighten_percent
    if pct is not None and tid in c.body.get("tightened", ()):
        with localcontext(_EXACT):
            lim = lim * (1 + pct / _HUNDRED) if cmp == "le" else lim * (1 - pct / _HUNDRED)
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


def short_breached(spot: Decimal, shorts: tuple[ShortLeg, ...]) -> ShortLeg | None:
    """ADR-268 (2): the short spot is AT or BEYOND (in the money): a CE with spot >= strike, a PE with spot <= strike.
    The deepest one when several; None when none (or no short states its kind)."""
    hit = [x for x in shorts if (x.kind == "CE" and spot >= x.strike) or (x.kind == "PE" and spot <= x.strike)]
    return max(hit, key=lambda x: abs(spot - x.strike)) if hit else None


def _t01(c: _Ctx) -> Hit:
    spot = _need(c.state.spot, "spot")
    hit = _compare(c, "T-01", *short_gap_pct(spot, _shorts(c.state)))
    if not hit.fired and short_breached(spot, c.state.shorts) is not None:
        # ADR-268 (2): at or beyond the strike flags, whatever the % gap (no distance left: value 0)
        return Hit("T-01", Decimal(0), hit.threshold, hit.cmp, True)
    return hit


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
        raise _Missing(f"{P}gap_after_open", until=c.gap_until)
    prev = _need(c.state.prev_close, "prev_close")
    if prev <= 0:
        raise _Missing(f"{P}prev_close_not_positive")
    return _compare(c, "T-13", abs(_need(c.state.day_open, "day_open") - prev) * _HUNDRED, prev)


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


def t14_margin(margin: object, unreadable: bool = False) -> Decimal:
    """The margin blocked T-14 divides by; absent, unreadable or not positive -> not checked (never a pass, never a
    division error)."""
    if margin is None:
        raise _Missing(MARGIN_UNREADABLE if unreadable else f"{P}missing_margin")
    if not isinstance(margin, Decimal) or not margin.is_finite():
        raise _Missing(MARGIN_UNREADABLE)
    if margin <= 0:
        raise _Missing(f"{P}margin_not_positive")
    return margin


def _t14(c: _Ctx) -> Hit:
    """The worst of the up and down 1% P&L changes, as a loss % of the margin blocked, >= this stage's value."""
    g = c.state.gamma
    if g is None:  # not computed: live mode (scenario-only, review F1), so "not checked yet" exactly as before
        raise _Missing(T14_PENDING)
    if g.reason is not None or g.up is None or g.down is None:
        raise _Missing(g.reason or GAMMA_UNKNOWN)
    margin = t14_margin(c.state.margin, c.state.margin_unreadable)
    worst = min(g.up, g.down)
    with localcontext(_EXACT):
        num = -worst * _HUNDRED
    return _compare(c, "T-14", num, margin)


_EVALUATORS: Final[dict[str, Callable[[_Ctx], Hit]]] = {
    "T-01": _t01, "T-01b": _t01b, "T-02": _t02, "T-03": _t03, "T-07": _t07, "T-09": _t09,
    "T-10b": _t10b, "T-11": _t11, "T-13": _t13, "T-14": _t14, "T-18": _t18, "T-19": _t19,
}
_T21: Final = "T-21"


def _trigger(c: _Ctx, tid: str) -> Hit | _Missing:  # noqa: PLR0911 - one answer per reason a trigger is not checked
    """A Hit, or the reason it is not checked. A stop trigger (T-06 / T-16) in ANY rule, a mixed one included, is
    answered from its stop line in force, never from the body's values (ADR-252)."""
    if tid in sl.STOP_TRIGGERS:
        return _stop_answer(c, tid)
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
    if tid in sl.STOP_TRIGGERS:  # the line in force carries its later figures (a flat line: none)
        line = _line(c.state, tid)
        return () if line is None or line.figure is None else tuple(_tightened(c, tid, x, "ge") for x in line.later)
    if c.stage is None or sl.is_stop_rule(tid):  # the 2x-credit line is one amount, not a per-stage value
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
        if set(members) <= sl.STOP_TRIGGERS:  # a stop: answered from the stop lines in force, never the body
            out.append(_stop_rule(c, rule, why))
            continue
        if why is not None:
            out.append(_Outcome(rule["id"], members[0], reason=why))
        elif members == [_T21]:  # the T-21 guard: prices are fresh, so its condition is false
            out.append(_Outcome(rule["id"], _T21))
        else:
            out.append(_rule(c, rule))
    named = {m for rule in body.get("rules", []) for m in (rule.get("any_of") or rule["all_of"])}
    for tid in sorted(sl.STOP_TRIGGERS - named):  # an active line no body rule names is still checked (ADR-252)
        line = _line(state, tid)
        if line is not None and line.active:
            out.append(_stop_rule(c, {"id": tid, "any_of": [tid]}, why))
    out.extend(_credit_outcome(state, why))
    return c, why, out


def _line(state: StrategyState, tid: str) -> sl.StopInForce | None:
    kind = sl.LINE_OF_TRIGGER.get(tid)
    return next((x for x in (state.stops.lines if state.stops is not None else ()) if x.kind == kind), None)


def _stop_hit(c: _Ctx, tid: str, line: sl.StopInForce) -> Hit:
    """The max-loss / margin stop: the loss as % of max loss / of margin against the line's % in force (tightened by
    the due day rule exactly as before), exact and inclusive."""
    if tid == sl.TRIGGER_MARGIN:
        margin = _need(c.state.margin, "margin")
        pnl = _need(c.state.pnl, "pnl")
        try:
            num, den = ratios.loss_pct_of_margin(pnl, margin)
        except ValueError:
            raise _Missing(f"{P}margin_not_positive") from None
    else:
        pnl = _need(c.state.pnl, "pnl")
        num, den = ratios.loss_pct_of_max_loss(pnl, _finite(c.state.max_loss, "max_loss"))
    return _exact(tid, num, den, _tightened(c, tid, line.figure, "ge"), "ge")  # type: ignore[arg-type]


def _stop_answer(c: _Ctx, tid: str) -> Hit | _Missing:  # noqa: PLR0911 - one answer per reason a stop is not checked
    t = c.body.get("triggers", {}).get(tid) or {}
    if t.get("greyed"):
        return _Missing(f"{P}greyed")
    if t.get("data", "ok") != "ok":
        return _Missing(f"{P}data_unavailable")
    if c.state.stops is None:
        return _Missing(sl.STOPS_NOT_SUPPLIED)
    line = _line(c.state, tid)
    if line is None or not line.active:
        return _Missing(f"{P}switched_off")
    if line.figure is None:
        return _Missing(sl.not_checked_code(line.reason))
    try:
        return _stop_hit(c, tid, line)
    except _Missing as e:
        return e


def _stop_rule(c: _Ctx, rule: Mapping, why: str | None) -> _Outcome:
    """A body rule whose members are stop triggers (T-06 / T-16): answered from the stop lines in force, never from
    the body's values (contract step 3); same rule id, same lead, same memory."""
    rid = rule["id"]
    members = rule.get("any_of") or rule["all_of"]
    if why is not None:
        return _Outcome(rid, members[0], reason=why)
    answers = [(m, _stop_answer(c, m)) for m in members]
    missing = [(m, x) for m, x in answers if isinstance(x, _Missing)]
    hits = tuple(x for _, x in answers if isinstance(x, Hit))
    fired = [h for h in hits if h.fired]
    if "all_of" in rule:
        if missing:
            return _Outcome(rid, missing[0][0], hits, missing[0][1].code, missing[0][1].slots)
        return _Outcome(rid, members[0], hits, fired=all(h.fired for h in hits))
    if fired:
        return _Outcome(rid, fired[0].trigger_id, hits, fired=True)
    if missing:
        return _Outcome(rid, missing[0][0], hits, missing[0][1].code, missing[0][1].slots)
    return _Outcome(rid, members[0], hits)


def _credit_outcome(state: StrategyState, why: str | None) -> list[_Outcome]:
    """ADR-247/251: the 2x-credit line (new plans only, ADR-250): the loss (``max(-pnl, 0)``) against the line's rupee
    amount, exact and inclusive; no amount -> "not checked" with its reason (fail closed)."""
    line = next((x for x in (state.stops.lines if state.stops is not None else ()) if x.kind == sl.STOP_CREDIT),
                None)
    if line is None or not line.active:
        return []
    rid = sl.CREDIT_RULE
    if why is not None:
        return [_Outcome(rid, rid, reason=why)]
    if line.amount is None or line.amount <= 0:
        return [_Outcome(rid, rid, reason=sl.not_checked_code(line.reason))]
    if state.pnl is None:
        return [_Outcome(rid, rid, reason=f"{P}missing_pnl")]
    loss = max(-state.pnl, Decimal(0))
    fired = loss >= line.amount
    return [_Outcome(rid, rid, (Hit(rid, loss, line.amount, "ge", fired),), fired=fired)]


def evaluate(body: Mapping, state: StrategyState, memory: Mapping[str, Mapping[str, bool]] | None = None,  # noqa: PLR0913
             entry_state: StrategyState | None = None, *, gap_until: str,
             entry_fallback: StrategyState | None = None) -> Evaluation:
    """Evaluate every rule of ``body`` on ``state``; pure (takes the F-71 memory, returns the new one). ``gap_until``
    is the user's gap-at-open window end "HH:MM" (REQ-168 AC-1; required, never defaulted). ``entry_fallback``
    (issue 65): a rule that cannot be computed on ``entry_state`` (the entry stated only spot and strikes, no Greeks)
    takes its entry value from this state instead (the first check), never "not held" by default."""
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
                entry = _entry_held(body, entry_state, entry_fallback, gap_until)
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


def _entry_held(body: Mapping, entry_state: StrategyState | None, fallback: StrategyState | None,
                gap_until: str) -> dict[str, bool]:
    """rule id -> held at entry: on ``entry_state``; a rule not computable there, on ``fallback`` (when given)."""
    if entry_state is None:
        return {}
    held = {x.rule_id: x.fired for x in _outcomes(body, entry_state, gap_until)[2] if x.reason is None}
    if fallback is not None:
        for x in _outcomes(body, fallback, gap_until)[2]:
            held.setdefault(x.rule_id, x.fired)
    return held


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


#: the id of a day rule that cannot be named (a malformed ``at``, ``when`` or ``action``): inside the Identifier
#: pattern, matches no rule (``day_rule_action`` refuses it), so a stored bad body never reaches the check route.
DAY_RULE_UNNAMEABLE: Final = f"{DAY_RULE_PREFIX}invalid"
_ID_PART: Final = re.compile(r"[A-Za-z0-9_-]{1,20}")


def day_rule_id(rule: Mapping) -> str:
    """The stable id of a day rule: its kind, time and action (``day.expiry.1430.5``). Fail closed: a part that is not
    a plain token (``at`` not HH:MM, a missing kind or action) -> ``DAY_RULE_UNNAMEABLE``, never an id outside the
    Identifier pattern."""
    at, when, action = rule.get("at"), rule.get("when"), rule.get("action")
    if (not isinstance(at, str) or not _HHMM.fullmatch(at) or not isinstance(when, str)
            or not _ID_PART.fullmatch(when) or type(action) is not int or not 0 <= action <= 99):  # noqa: PLR2004
        return DAY_RULE_UNNAMEABLE
    return f"{DAY_RULE_PREFIX}{when}.{at.replace(':', '')}.{action}"


def is_day_rule_id(rule_id: object) -> bool:
    return isinstance(rule_id, str) and rule_id.startswith((DAY_RULE_PREFIX, LEGACY_DAY_RULE_PREFIX))


def day_rule_action(body: Mapping | None, rule_id: object) -> int | None:
    """The action index of the day rule ``rule_id`` names in ``body``; None when it names none."""
    if not is_day_rule_id(rule_id) or rule_id == DAY_RULE_UNNAMEABLE or not isinstance(body, Mapping):
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
    it for the screen and the worker alike). The expiry-day close rule (action 5) and the carry checks are
    answered here; the tighten rule (action 4) stays ``tighten_percent``; a switched-on rule whose pair is not in
    ``ACTING_DAY_PAIRS`` is answered NotChecked (``DAY_RULE_NOT_CHECKED``), never skipped."""
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
        elif not day_rule_acts(rule):  # switched on but never acted on: "not checked", never silent
            answer = DayAnswer(day_rule_id(rule), action if type(action) is int else -1, reason=DAY_RULE_NOT_CHECKED)
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
DAY_ACTION_TIGHTEN: Final = 4  # PLAYBOOK_DAY_RULE_ACTION_TEXT["4"], "Tighten every trigger by this %"
DAY_RULE_NOT_CHECKED: Final = f"{P}day_rule_not_checked"
#: THE table of day-rule (kind, action) pairs the worker acts on (GC-IC1 step 10 fix, REQ-159 AC-4; B8: one place).
#: ``day_answers`` and ``adjustment_check._tighten`` act only on a pair listed here; the labels route sends the same
#: list to the editor and the plan sheet, which show every other switched-on rule as "not checked". A new acting pair
#: is added here only.
ACTING_DAY_PAIRS: Final = frozenset({
    ("expiry", DAY_ACTION_PREPARE_EXIT), ("expiry", DAY_ACTION_TIGHTEN),
    (BEFORE_WEEKEND, DAY_ACTION_CARRY_CHECK), (BEFORE_HOLIDAY, DAY_ACTION_CARRY_CHECK)})


def day_rule_acts(rule: Mapping) -> bool:
    """True when the worker acts on this rule's (kind, action) pair; every other pair is stored and shown only."""
    when, action = rule.get("when"), rule.get("action")
    return isinstance(when, str) and type(action) is int and (when, action) in ACTING_DAY_PAIRS
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
#: ADR-240 (1): S-03, S-04, S-05 are GUIDANCE (shown as words, never a rule that fires); ADR-244 adds S-08 and S-09.
#: ONE server constant: the playbook reply derives each situation's ``kind`` from it; never a key stored in a body.
GUIDANCE_SITUATIONS: Final = ("S-03", "S-04", "S-05", "S-08", "S-09")


def situation_kind(situation_id: object) -> str:
    return "guidance" if situation_id in GUIDANCE_SITUATIONS else "rule"


#: ADR-240 (3) numbers are settings (REQ-167 AC-4): ``other.situation_net_delta_per_lot`` (S-02, default 0.15) and
#: ``other.situation_big_win_percent`` (S-12, default 40, entry session only), carried on ``StrategyState``
SETTING_UNAVAILABLE: Final = f"{P}situation_setting_unavailable"
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
    if state.s02_delta_per_lot is None:  # the setting was not read: never a typed stand-in
        return DayAnswer(rid, SITUATION_ACTION, reason=SETTING_UNAVAILABLE)
    if not state.held or any(x.greeks is None or x.greeks.delta is None for x in state.held):
        return DayAnswer(rid, SITUATION_ACTION, reason=MISSING_LEG_DELTA)  # never a missing delta read as 0
    try:
        num, den = ratios.net_delta_per_lot(tuple((x.greeks, Action(x.side), x.lots) for x in state.held))
    except ValueError:
        return DayAnswer(rid, SITUATION_ACTION, reason=MISSING_LEG_DELTA)
    hit = _exact(rid, num, den, state.s02_delta_per_lot, "ge")
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
    if state.s12_percent is None:  # the setting was not read: never a typed stand-in
        return DayAnswer(rid, SITUATION_ACTION, reason=SETTING_UNAVAILABLE)
    try:
        pnl = _need(state.pnl, "pnl")
        hit = _exact(rid, *ratios.profit_pct_of_max_profit(pnl, _finite(state.max_profit, "max_profit")),
                     state.s12_percent, "ge")
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
