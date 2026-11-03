"""The adjustment alert gate (REQ-170 AC-1..AC-4, ADR-236): one suggestion per crossing episode.

A pure state machine, one state per strategy. Each `step` is one check: it takes the rule values read at `now`
(the caller passes `now`; the gate never reads a clock and does no I/O), builds candles of the preset's length aligned
to 09:15 IST, and judges each rule only on a candle close (the last value seen in the candle). Edge, not level: a rule
opens one record when a close is beyond its line; it re-arms only after a close clears the line by the re-arm band
AND the cool-down from the record has passed; one ladder level worse opens at once (escalation). A daily cap and a
quiet time after the open turn a would-be record into a `Held` event, never a silent drop.

Risk exits (stop-loss, conditional exits, REQ-041 / paper triggers) never pass through this gate (AC-5): it applies to
adjustment suggestions only. The screen check and the background check share this one gate.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal, Union

from ofo.adjustment.gate_rows import GateRow, GateRows, Preset  # noqa: F401 - re-exported for callers
from ofo.adjustment.held_reasons import HELD_DAILY_LIMIT, HELD_QUIET_TIME, HELD_TEXT_IDS  # noqa: F401 - re-exported
from ofo.timeutil import IST
from ofo.timeutil import SESSION_OPEN as MARKET_OPEN

#: Catalogue ids (ofo.errors.explanations is the one home of the shown words); the gate holds no English.
WORSE_THAN_LAST = "alert_record_worse_than_last"
WORSE_THAN_DISMISSED = "alert_record_worse_than_dismissed"
# The held reasons and their catalogue ids live in `held_reasons`, a neutral module the opportunities route reads
# without reaching this gate; re-exported here for the gate's callers.

Cmp = Literal["ge", "le", "bool"]
Value = Union[Decimal, bool]  # noqa: UP007


INTRADAY = Preset(timedelta(minutes=1), timedelta(minutes=5), Decimal("0.10"), 6, time(9, 20))
WEEKLY = Preset(timedelta(minutes=5), timedelta(minutes=30), Decimal("0.20"), 4, time(9, 30))
MONTHLY = Preset(timedelta(minutes=15), timedelta(hours=2), Decimal("0.25"), 2, time(9, 45))


@dataclass(frozen=True)
class RuleSpec:
    """ladder[0] = the current stage's threshold, then strictly more severe later-stage thresholds; () for bool."""

    rule_id: str
    cmp: Cmp
    ladder: tuple[Decimal, ...]


def _more_severe(cmp: Cmp, a: Decimal, b: Decimal) -> bool:
    """True when `a` is strictly more severe than `b`."""
    return a > b if cmp == "ge" else a < b


def ladder_for(cmp: Cmp, current: Decimal | None, later: tuple[Decimal, ...] | list[Decimal]) -> tuple[Decimal, ...]:
    """The escalation ladder: current, then each later threshold strictly more severe than the last kept one."""
    if cmp == "bool":
        return ()
    if cmp not in ("ge", "le"):
        raise ValueError(f"the alert gate does not know the cmp {cmp!r}")
    if current is None:
        raise ValueError("a ge/le rule needs a current threshold")
    kept = [current]
    for value in later:
        if _more_severe(cmp, value, kept[-1]):
            kept.append(value)
    return tuple(kept)


@dataclass(frozen=True)
class Opened:
    rule_id: str
    at: datetime
    level: int
    threshold: Decimal | None
    value: Value
    worse: Literal["last", "dismissed"] | None = None


@dataclass(frozen=True)
class Held:
    rule_id: str
    at: datetime
    reason: str
    value: Value
    level: int


@dataclass(frozen=True)
class Lapsed:
    """ADR-237 (4): an open record's episode ended (a close cleared its line by the re-arm band). Once per record."""

    rule_id: str
    at: datetime
    value: Value


Event = Union[Opened, Held, Lapsed]  # noqa: UP007


@dataclass(frozen=True)
class _Record:
    level: int
    threshold: Decimal | None
    at: datetime
    dismissed: bool = False
    final: bool = False  # lapsed / acted on / dismissed: no Lapsed event any more
    unleveled: bool = False  # restored with a stored threshold but no real ladder yet: levelled at the first real close
    record_id: int | None = None  # the stored record's id (restored, or set after the open is written; #639 item 2)
    #: the (cmp, ladder) its level was taken against; a close with another ladder re-levels it (ADR-237 (8))
    ladder: tuple | None = None


@dataclass(frozen=True)
class _Hold:
    reason: str
    level: int
    threshold: Decimal | None
    unleveled: bool = False  # as _Record.unleveled
    ladder: tuple | None = None  # as _Record.ladder


@dataclass(frozen=True)
class _Pending:
    end: datetime
    value: Value
    spec: RuleSpec


@dataclass(frozen=True)
class _Rule:
    pending: _Pending | None = None
    record: _Record | None = None
    cleared: bool = False
    hold: _Hold | None = None


@dataclass(frozen=True)
class GateState:
    rules: tuple[tuple[str, _Rule], ...] = ()
    day: date | None = None
    opened_today: int = 0
    paused_at: datetime | None = None  # the latest pause seen: no candle containing it has a close (pause())

    def rule(self, rule_id: str) -> _Rule:
        return dict(self.rules).get(rule_id, _Rule())

    def with_rule(self, rule_id: str, rule: _Rule) -> GateState:
        rules = dict(self.rules)
        rules[rule_id] = rule
        return replace(self, rules=tuple(sorted(rules.items())))


def initial_state() -> GateState:
    return GateState()


def _ist(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(IST)


def _candle_end(now: datetime, candle: timedelta) -> datetime:
    anchor = datetime.combine(now.date(), MARKET_OPEN, tzinfo=IST)
    index = (now - anchor) // candle
    return anchor + candle * (index + 1)


def level_of(spec: RuleSpec, value: Value) -> int:
    """The ladder level `value` reaches (-1 = not beyond the current line)."""
    return _level(spec, value)


def _level(spec: RuleSpec, value: Value) -> int:
    if spec.cmp == "bool":
        return 0 if value is True else -1
    level = -1
    for i, thr in enumerate(spec.ladder):
        if (value >= thr) if spec.cmp == "ge" else (value <= thr):
            level = i
    return level


def _safe_by_band(spec: RuleSpec, value: Value, threshold: Decimal | None, preset: Preset) -> bool:
    """The close is on the safe side of `threshold` by the re-arm band (rearm_fraction x |threshold|)."""
    if spec.cmp == "bool" or threshold is None:
        return value is False
    if isinstance(value, bool):
        return False
    band = preset.rearm_fraction * abs(threshold)
    return value <= threshold - band if spec.cmp == "ge" else value >= threshold + band


def _refresh(rule_id: str, rule: _Rule, pend: _Pending, level: int, preset: Preset) -> tuple[_Rule, list[Event]]:
    """Apply a close to the clear mark, the record's lapse and the held episode before deciding."""
    rec, hold = rule.record, rule.hold
    events: list[Event] = []
    if rec is not None and not rule.cleared and _safe_by_band(pend.spec, pend.value, rec.threshold, preset):
        rule = replace(rule, cleared=True)
        if not (rec.dismissed or rec.final):
            rule = replace(rule, record=replace(rec, final=True))
            events.append(Lapsed(rule_id, pend.end, pend.value))
    if hold is not None and (
        _safe_by_band(pend.spec, pend.value, hold.threshold, preset)
        or level > hold.level
        or (hold.reason == HELD_QUIET_TIME and pend.end.time() > preset.quiet_until)
    ):
        rule = replace(rule, hold=None)
    return rule, events


def _unleveled(spec: RuleSpec | None, threshold: Decimal | None) -> bool:
    """A stored threshold with no real ladder to level it against (no spec, or the yes/no placeholder of a rule not
    checked at the restoring check): its level is not known yet (review #2 of 0036)."""
    return threshold is not None and (spec is None or spec.cmp == "bool")


def _ladder_key(spec: RuleSpec | None) -> tuple | None:
    """What a level is relative to: the comparison and the ladder (None: no real ladder, a yes/no placeholder)."""
    return None if spec is None or spec.cmp == "bool" else (spec.cmp, spec.ladder)


def _stale(kept: _Record | _Hold, key: tuple) -> bool:
    return kept.unleveled or (kept.ladder is not None and kept.ladder != key)


def _leveled(rule: _Rule, spec: RuleSpec) -> _Rule:
    """Level a record / hold against the ladder this close carries, by the restore rule (``_restored_level``): a
    restored one at the first real (ge / le) ladder, and ANY one whose ladder changed since it was levelled - a
    playbook change or a STAGE change (days left, expiry kind) alike (ADR-237 (8)). The stored THRESHOLD is kept,
    never replaced by the placeholder's. A yes/no close leaves it as it is (it cannot escalate a number)."""
    key = _ladder_key(spec)
    if key is None:
        return rule
    rec, hold = rule.record, rule.hold
    if rec is not None and _stale(rec, key):
        rule = replace(rule, record=replace(rec, level=_restored_level(spec, rec.threshold), unleveled=False,
                                            ladder=key))
    if hold is not None and _stale(hold, key):
        rule = replace(rule, hold=replace(hold, level=max(_restored_level(spec, hold.threshold), 0), unleveled=False,
                                          ladder=key))
    return rule


def _close(state: GateState, rule_id: str, pend: _Pending, preset: Preset) -> tuple[GateState, list[Event]]:
    t, value, spec = pend.end, pend.value, pend.spec
    if state.day != t.date():
        state = replace(state, day=t.date(), opened_today=0)
    level = _level(spec, value)
    rule, lapsed = _refresh(rule_id, _leveled(replace(state.rule(rule_id), pending=None), spec), pend, level, preset)
    state = state.with_rule(rule_id, rule)
    state, events = _decide(state, rule_id, rule, pend, level, preset)
    return state, lapsed + events


def _decide(  # noqa: PLR0913 - one close's inputs
    state: GateState, rule_id: str, rule: _Rule, pend: _Pending, level: int, preset: Preset,
) -> tuple[GateState, list[Event]]:
    t, value, spec = pend.end, pend.value, pend.spec
    rec, hold = rule.record, rule.hold
    if level < 0:
        return state.with_rule(rule_id, rule), []
    armed = rec is None or (rule.cleared and t >= rec.at + preset.cooldown)
    if armed:
        worse = None
    elif level > rec.level:
        worse = "dismissed" if rec.dismissed else "last"
    else:
        return state.with_rule(rule_id, rule), []
    threshold = spec.ladder[level] if spec.ladder else None
    reason = None
    if t.time() <= preset.quiet_until:
        reason = HELD_QUIET_TIME
    elif state.opened_today >= preset.daily_cap:
        reason = HELD_DAILY_LIMIT
    if reason is not None:
        if hold is not None and hold.reason == reason and level <= hold.level:
            return state.with_rule(rule_id, rule), []
        rule = replace(rule, hold=_Hold(reason, level, threshold, ladder=_ladder_key(spec)))
        return state.with_rule(rule_id, rule), [Held(rule_id, t, reason, value, level)]
    rule = replace(rule, record=_Record(level, threshold, t, ladder=_ladder_key(spec)), cleared=False, hold=None)
    state = replace(state.with_rule(rule_id, rule), opened_today=state.opened_today + 1)
    return state, [Opened(rule_id, t, level, threshold, value, worse)]


def step(
    state: GateState,
    *,
    now: datetime,
    preset: Preset,
    readings: Mapping[str, tuple[RuleSpec, Value | None]],
) -> tuple[GateState, list[Event]]:
    """One check at `now`: process every candle close that is due, then record this check's samples.

    A rule missing from `readings` gives no sample; a value of None (not readable) gives no sample either, so a
    candle with only None has no close. An empty `readings` still processes due closes.
    """
    now = _ist(now)
    events: list[Event] = []
    due = sorted(
        (rule.pending.end, rule_id)
        for rule_id, rule in state.rules
        if rule.pending is not None and now >= rule.pending.end
    )
    for _, rule_id in due:
        state, evs = _close(state, rule_id, state.rule(rule_id).pending, preset)
        events.extend(evs)
    end = _candle_end(now, preset.candle)
    if state.paused_at is not None and state.paused_at >= end - preset.candle:
        return state, events  # this candle saw a pause: no sample, so it has no close (pause())
    for rule_id in sorted(readings):
        spec, value = readings[rule_id]
        if value is None:
            continue
        rule = state.rule(rule_id)
        state = state.with_rule(rule_id, replace(rule, pending=_Pending(end, value, spec)))
    return state, events


def pause(state: GateState, at: datetime) -> GateState:
    """GC-ALERT1 step 5 review round 2, finding 2: the strategy was paused (stale feed, missing leg, a failed read)
    at `at`. A candle that saw a pause was not fully watched, so it has no close, as a candle with no readable value
    has none (ADR-237 (2)): every pending candle still running at `at` is dropped (it neither opens, holds nor lapses),
    and `step` takes no sample in a candle that contains the latest pause. A pending candle that ended at or before
    `at` was fully watched and keeps its close. Pure; the caller passes `at`."""
    at = _ist(at)
    rules = tuple((rid, replace(rule, pending=None) if rule.pending is not None and rule.pending.end > at else rule)
                  for rid, rule in state.rules)
    latest = at if state.paused_at is None else max(state.paused_at, at)
    return replace(state, rules=rules, paused_at=latest)


def dismiss(state: GateState, rule_id: str, record_id: int | None = None) -> GateState:
    """ADR-236: mark the rule's last record dismissed; same-level re-opening still needs cleared + cool-down.
    ``record_id`` (#639 item 2): only when the gate's record IS that stored record; a record opened after the dismissed
    one was read (the rebuild's read window) is a different record and is left as it is. None = the rule's last record
    (a caller with no stored ids)."""
    rule = state.rule(rule_id)
    if rule.record is None or (record_id is not None and rule.record.record_id != record_id):
        return state
    return state.with_rule(rule_id, replace(rule, record=replace(rule.record, dismissed=True)))


def _restored_level(spec: RuleSpec | None, threshold: Decimal | None) -> int:
    """The current ladder's level of a stored threshold: the most severe rung the stored one reaches; -1 when it is
    less severe than the current line (the stage moved on: a close beyond the current line is then worse)."""
    if spec is None or spec.cmp == "bool" or threshold is None:
        return 0
    level = -1
    for i, thr in enumerate(spec.ladder):
        if thr == threshold or _more_severe(spec.cmp, threshold, thr):
            level = i
    return level


def restore(rows: GateRows, today: date, specs: Mapping[str, RuleSpec]) -> GateState:
    """ADR-237 (5): the gate state on worker start. Cleared is not stored, so every rule counts as not cleared (quiet
    at the same level; an escalation still opens, worded by the dismissed flag); the day's count keeps the cap.
    `specs` = each rule's current RuleSpec (from the first readings); a rule without one restores at level 0."""
    if rows.opened_today < 0:
        raise ValueError("opened_today cannot be negative")
    state = replace(GateState(), day=today, opened_today=rows.opened_today)
    for row in rows.last:
        spec = specs.get(row.rule_id)
        rec = _Record(_restored_level(spec, row.threshold), row.threshold, _ist(row.at),
                      dismissed=row.dismissed, final=not row.open, unleveled=_unleveled(spec, row.threshold),
                      record_id=row.id, ladder=_ladder_key(spec))
        state = state.with_rule(row.rule_id, _Rule(record=rec))
    return state


def restore_held(state: GateState, rule_id: str, reason: str, threshold: Decimal | None,
                 spec: RuleSpec | None) -> GateState:
    """GC-ALERT1 wire-b item 5: a crossing held today (a stored held row newer than the rule's last record) is
    restored as the rule's held episode, so a restarted worker writes no second Held row for the same episode. The
    episode ends as any hold does (cleared by the band, one level worse, the quiet time over)."""
    if reason not in (HELD_DAILY_LIMIT, HELD_QUIET_TIME):
        raise ValueError(f"unknown held reason {reason!r}")
    level = max(_restored_level(spec, threshold), 0)
    hold = _Hold(reason, level, threshold, unleveled=_unleveled(spec, threshold), ladder=_ladder_key(spec))
    return state.with_rule(rule_id, replace(state.rule(rule_id), hold=hold))


def with_record_id(state: GateState, rule_id: str, record_id: int) -> GateState:
    """The stored id of the rule's record the gate just opened (the store answers it after the write); pure."""
    rule = state.rule(rule_id)
    if rule.record is None:
        return state
    return state.with_rule(rule_id, replace(rule, record=replace(rule.record, record_id=record_id)))


def is_dismissed(state: GateState, rule_id: str) -> bool | None:
    """Whether the rule's last record in the gate is dismissed; None when the gate holds no record for it."""
    rec = state.rule(rule_id).record
    return None if rec is None else rec.dismissed
