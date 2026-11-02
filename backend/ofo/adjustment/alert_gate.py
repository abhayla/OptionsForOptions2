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

from ofo.timeutil import IST
from ofo.timeutil import SESSION_OPEN as MARKET_OPEN

WORSE_THAN_LAST = "Worse than the last one"
WORSE_THAN_DISMISSED = "Worse than the one you dismissed"
HELD_DAILY_LIMIT = "daily_limit"
HELD_QUIET_TIME = "quiet_time"
#: The catalogue is the one home of the shown words (ofo.errors.explanations); the two record texts above are tested
#: equal to their catalogue entries (tests/adjustment/test_alert_texts.py), the held reasons render through these ids.
TEXT_IDS: Mapping[str, str] = {
    WORSE_THAN_LAST: "alert_record_worse_than_last",
    WORSE_THAN_DISMISSED: "alert_record_worse_than_dismissed",
    HELD_DAILY_LIMIT: "alert_held_daily_limit",
    HELD_QUIET_TIME: "alert_held_quiet_time",
}

Cmp = Literal["ge", "le", "bool"]
Value = Union[Decimal, bool]  # noqa: UP007


@dataclass(frozen=True)
class Preset:
    candle: timedelta
    cooldown: timedelta
    rearm_fraction: Decimal
    daily_cap: int
    quiet_until: time


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


Event = Union[Opened, Held]  # noqa: UP007


@dataclass(frozen=True)
class _Record:
    level: int
    threshold: Decimal | None
    at: datetime
    dismissed: bool = False


@dataclass(frozen=True)
class _Hold:
    reason: str
    level: int
    threshold: Decimal | None


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


def _refresh(rule: _Rule, pend: _Pending, level: int, preset: Preset) -> _Rule:
    """Apply a close to the clear mark and the held episode before deciding."""
    rec, hold = rule.record, rule.hold
    if rec is not None and not rule.cleared and _safe_by_band(pend.spec, pend.value, rec.threshold, preset):
        rule = replace(rule, cleared=True)
    if hold is not None and (
        _safe_by_band(pend.spec, pend.value, hold.threshold, preset)
        or level > hold.level
        or (hold.reason == HELD_QUIET_TIME and pend.end.time() > preset.quiet_until)
    ):
        rule = replace(rule, hold=None)
    return rule


def _close(state: GateState, rule_id: str, pend: _Pending, preset: Preset) -> tuple[GateState, list[Event]]:
    t, value, spec = pend.end, pend.value, pend.spec
    if state.day != t.date():
        state = replace(state, day=t.date(), opened_today=0)
    level = _level(spec, value)
    rule = _refresh(replace(state.rule(rule_id), pending=None), pend, level, preset)
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
        rule = replace(rule, hold=_Hold(reason, level, threshold))
        return state.with_rule(rule_id, rule), [Held(rule_id, t, reason, value, level)]
    rule = replace(rule, record=_Record(level, threshold, t), cleared=False, hold=None)
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
    for rule_id in sorted(readings):
        spec, value = readings[rule_id]
        if value is None:
            continue
        rule = state.rule(rule_id)
        state = state.with_rule(rule_id, replace(rule, pending=_Pending(end, value, spec)))
    return state, events


def dismiss(state: GateState, rule_id: str) -> GateState:
    """ADR-236: mark the rule's last record dismissed; same-level re-opening still needs cleared + cool-down."""
    rule = state.rule(rule_id)
    if rule.record is None:
        return state
    return state.with_rule(rule_id, replace(rule, record=replace(rule.record, dismissed=True)))
