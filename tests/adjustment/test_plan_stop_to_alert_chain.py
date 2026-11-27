"""Plan stop to alert, END TO END, for every guard kind (live test day 27 Nov 2026; Lane Q2 gap 4).

The chain under test is the one the worker runs on every check: the plan body's guards -> ``playbook_eval.evaluate``
(the real evaluator, rule memory carried) -> ``gate_readings.readings`` (the one readings function) ->
``alert_gate.step``
(the real gate) -> one ``Opened`` event = one stored alert row. A worker restart is ``alert_gate.restore`` from the rows
the first life stored. No clock is read; every ``now`` is passed in.

Real cases: 27 Nov paper trade A-D #200 (the rupee stop crossed from 11:00 and no alert opened: the daily cap of 4 was
used by four automatic records) and A-E #202 (Rs 50 stop typed after entry; no alert row for 25 minutes). The same
class: a plan stop that crosses while the gate holds it, forgets it or never sees it.

Guard kinds: percent loss stop (T-06), rupee loss stop, 2x credit line, time exit, rupee profit target.
Situations: (saved) the plan is saved while the level is already crossed; (quiet) crossed inside the quiet period;
(cap) crossed after 4 other alerts that day; (restart before / after the alert) a worker restart between the crossing
and the alert, or after it. Every cell must give EXACTLY ONE alert row.

Spec basis: REQ-170 AC-5 (risk exits are not delayed), ADR-267 and its amendment 2 (the plan's own stops are never
held by the daily cap), ADR-330 (5), ADR-237 (5) (restart restores the gate), ADR-236 (quiet time holds, never drops).
Cells that fail on origin/integration/nb-1126 at 206a9f0 are strict xfails naming the branch that fixes them; when that
branch is merged the strict xfail turns into a failure and the mark is deleted (that is the signal).
"""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from ofo.adjustment import alert_gate as ag
from ofo.adjustment import gate_readings
from ofo.adjustment import stop_lines as sl
from ofo.adjustment.alert_gate import GateRow, GateRows
from ofo.adjustment.cap_scope import cap_exempt
from test_playbook_eval import body_of, evaluate, load, state_of

D = Decimal
DAY = date(2026, 11, 27)
PRESET = ag.WEEKLY  # 5-minute candles, quiet until 09:30, daily cap 4
CANDLE_MINUTES = 5
HAS_SECONDS = 2
OTHERS = ("T-03", "T-14", "T-01", "T-02")  # four automatic alerts: the weekly cap of 4 is used


def at(hhmm: str) -> datetime:
    clock = hhmm if hhmm.count(":") == HAS_SECONDS else hhmm + ":00"
    return datetime.combine(DAY, time.fromisoformat(clock), tzinfo=ag.IST)


def _credit_line(state):
    line = sl.StopInForce(sl.STOP_CREDIT, True, D("2"), D("300"), "strategy", None)
    return replace(state, stops=sl.StopsInForce((*state.stops.lines, line), None, None))


class Kind:
    """One guard kind: how to put it in the plan body and how a check reads when it is / is not crossed."""

    def __init__(self, name: str, rule_id: str):
        self.name, self.rule_id = name, rule_id

    def body(self, start: datetime) -> dict:
        body = copy.deepcopy(body_of(load("ADJ-01")))
        body["status"] = "approved"
        guards = body.setdefault("guards", {})
        if self.name == "rupee_loss":
            guards[sl.RUPEE_LOSS_KEY] = "100"
        elif self.name == "rupee_profit":
            guards[sl.RUPEE_PROFIT_KEY] = "100"
        elif self.name == "time_exit":
            guards["time_exit"] = {"at": start.strftime("%H:%M"), "on": DAY.isoformat()}
            if not any(r["id"] == "T-10b" for r in body["rules"]):
                body["rules"].append({"id": "T-10b", "any_of": ["T-10b"]})
        return body

    def state(self, now: datetime, crossed: bool):
        state = replace(state_of(load("ADJ-01")), today=DAY, hhmm=now.strftime("%H:%M"))
        if self.name == "percent_loss":
            amount = state.stops.lines[0].amount
            return replace(state, pnl=-(amount + 1) if crossed else D("-1"))
        if self.name == "rupee_loss":
            return replace(state, pnl=D("-101") if crossed else D("-1"))
        if self.name == "credit_2x":
            return replace(_credit_line(state), pnl=D("-301") if crossed else D("-1"))
        if self.name == "rupee_profit":
            return replace(state, pnl=D("101") if crossed else D("1"))
        return state  # time_exit: the clock decides (the guard's own time is the crossing start)


KINDS = [Kind("percent_loss", sl.TRIGGER_MAX_LOSS), Kind("rupee_loss", sl.RUPEE_LOSS_RULE),
         Kind("credit_2x", sl.CREDIT_RULE), Kind("time_exit", sl.TRIGGER_TIME_EXIT),
         Kind("rupee_profit", sl.RUPEE_PROFIT_RULE)]


class Worker:
    """The worker's loop for one plan: evaluator memory + gate state + the stored rows (survive a restart)."""

    def __init__(self, kind: Kind, start: datetime, others_from: datetime | None = None, dip: bool = False):
        self.kind, self.start, self.others_from, self.dip = kind, start, others_from, dip
        self.body, self.memory, self.gate = kind.body(start), {}, ag.initial_state()
        self.rows: list[GateRow] = []  # the stored alert rows (an Opened event writes one)
        self.events: list = []
        self.specs: dict = {}

    def check(self, now: datetime) -> None:
        dipped = self.dip and now.minute % CANDLE_MINUTES == CANDLE_MINUTES - 1  # inside again on the last minute
        crossed = now >= self.start and not dipped
        ev = evaluate(self.body, self.kind.state(now, crossed), self.memory, None)
        self.memory = ev.memory
        readings = {k: v for k, v in gate_readings.readings(ev).items() if k == self.kind.rule_id}
        if self.others_from is not None:  # four automatic rules that are true from ``others_from`` on
            on = now >= self.others_from
            for r in OTHERS:
                readings[r] = (ag.RuleSpec(r, "bool", ()), on)
        self.specs.update({k: s for k, (s, _v) in readings.items()})
        self.gate, out = ag.step(self.gate, now=now, preset=PRESET, readings=readings)
        for e in out:
            if isinstance(e, ag.Opened):
                self.rows.append(GateRow(e.rule_id, e.at, e.threshold, False, True, id=len(self.rows) + 1))
        self.events += out

    def restart(self, now: datetime) -> None:
        """A new worker life: the gate is rebuilt from the stored rows (ADR-237 (5)); the rule memory is stored too."""
        last = {r.rule_id: r for r in self.rows}
        capped = sum(1 for r in self.rows if not cap_exempt(r.rule_id))
        self.gate = ag.restore(GateRows(tuple(last.values()), capped), now.date(), self.specs)

    def run(self, first: str, last: str, *, restart_at: str | None = None) -> None:
        t, end = at(first + ":44"), at(last + ":44")
        restarted = False
        while t <= end:
            if restart_at is not None and not restarted and t >= at(restart_at + ":00"):
                self.restart(t)
                restarted = True
            self.check(t)
            t += timedelta(minutes=1)

    def alert_rows(self) -> list[GateRow]:
        return [r for r in self.rows if r.rule_id == self.kind.rule_id]


#: situation -> (crossing start, first check, last check, others from, restart at)
SITUATIONS = {
    "saved_already_crossed": ("09:45:00", "10:00", "10:20", None, None),
    "crossed_in_quiet_period": ("09:20:00", "09:16", "09:50", None, None),
    "crossed_after_4_other_alerts": ("11:00:00", "10:50", "11:30", "10:40:00", None),
    "restart_before_the_alert": ("11:00:30", "10:50", "11:30", None, "11:02"),
    "restart_after_the_alert": ("11:00:30", "10:50", "11:30", None, "11:20"),
    # #202: past the line for 4 of every 5 minutes, back inside on the last one: a candle-close wait never sees it
    "crosses_and_dips_before_candle_close": ("12:13:44", "12:01", "12:30", None, None),
}
#: the dip situation applies to the loss stops only (a target or the time exit is judged at the candle close)
LOSS_KINDS = ("percent_loss", "rupee_loss", "credit_2x")
#: today's failures on 206a9f0, proved by running this file there (see RESULTS-lane-q2.md). Reason names the fix branch.
_CAP = "held by the daily cap (#200); fixed on origin/hotfix/loss-stop-1127 (c040e73e, ADR-267 amendment 2)"
_DIP = "rupee stop waits for the candle close (#202); fixed on origin/hotfix/loss-stop-1127 (468561e4)"
XFAIL: dict[tuple[str, str], str] = {
    **{(k.name, "crossed_after_4_other_alerts"): _CAP for k in KINDS},
    ("rupee_loss", "crosses_and_dips_before_candle_close"): _DIP,
}


def _cells():
    for kind in KINDS:
        for situation in SITUATIONS:
            if situation.startswith("crosses_and_dips") and kind.name not in LOSS_KINDS:
                continue
            marks = []
            if (kind.name, situation) in XFAIL:
                marks.append(pytest.mark.xfail(strict=True, reason=XFAIL[(kind.name, situation)]))
            yield pytest.param(kind, situation, id=f"{kind.name}-{situation}", marks=marks)


@pytest.mark.parametrize(("kind", "situation"), list(_cells()))
def test_plan_guard_gives_exactly_one_alert_row(kind, situation):
    start, first, last, others, restart_at = SITUATIONS[situation]
    worker = Worker(kind, at(start), at(others) if others else None, dip=situation.startswith('crosses_and_dips'))
    worker.run(first, last, restart_at=restart_at)
    rows = worker.alert_rows()
    assert len(rows) == 1, (kind.name, situation, [(type(e).__name__, e.rule_id, e.at.time()) for e in worker.events
                                                    if e.rule_id == kind.rule_id])
    if situation == "crossed_in_quiet_period":  # held until the quiet time ends, never dropped (ADR-236)
        assert rows[0].at.time() > PRESET.quiet_until
