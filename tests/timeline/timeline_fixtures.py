"""Shared inputs for the W-020 timeline tests: the golden Iron Condor (scenario-calculations.md §6) and a real
executed StrategyRecord, so the active version comes from ofo.strategy.versions, not a typed-in number.

Stressed LTPs (hand-chosen for a loss; entries are the §6 golden entries). Hand computation, (LTP - entry) x 75 for a
BUY and (entry - LTP) x 75 for a SELL:
  BUY 22800 PE  42.50 -> 120.00:  +77.50 x 75 = +5812.50
  SELL 23000 PE 86.00 -> 250.00: -164.00 x 75 = -12300.00
  SELL 23400 CE 91.50 ->  10.00:  +81.50 x 75 = +6112.50
  BUY 23600 CE  44.00 ->   3.00:  -41.00 x 75 = -3075.00
  strategy live P&L = -3450.00 (the golden §6 LTPs give +1365.00, which no max-loss rule can trigger on).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from pathlib import Path

import yaml

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.rules import DataHealth, Evaluation, RuleAction, evaluate, exit_max_loss, snapshot_from_strategy
from ofo.strategy.definition import StrategyDefinition
from ofo.strategy.versions import ExecutionResult, Position, ResultStatus, StrategyRecord

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
EXPIRY = datetime.date(2026, 10, 27)
QTY = 75
T0 = datetime.datetime(2026, 10, 1, 9, 20, tzinfo=IST)
CHECKED_AT = datetime.datetime(2026, 10, 20, 10, 0, tzinfo=IST)
SOURCE = "zerodha-kite-quote"
EXPECTED_LOSS_PNL = D("-3450.00")  # hand computation above
EXPECTED_THRESHOLD = D("-3000")  # exit_max_loss(3000) compares live P&L <= -3000 (templates.py docstring)


def golden_legs(ltps: tuple[str, str, str, str]) -> tuple[Leg, ...]:
    return (
        Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, QTY, D("42.50"), D(ltps[0])),
        Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, QTY, D("86.00"), D(ltps[1])),
        Leg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, QTY, D("91.50"), D(ltps[2])),
        Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, QTY, D("44.00"), D(ltps[3])),
    )


GOLDEN = Strategy(golden_legs(("38.20", "72.50", "78.00", "39.50")))
STRESSED = Strategy(golden_legs(("120.00", "250.00", "10.00", "3.00")))
MAX_LOSS_RULE = exit_max_loss("ml-3000", D("3000"), action=RuleAction.ALERT_AND_PREPARE_ORDERS)


def clock() -> datetime.datetime:
    return datetime.datetime(2026, 10, 20, 15, 30, tzinfo=IST)


def executed_record() -> StrategyRecord:
    """The golden condor proposed, confirmed and filled (1 lot per leg) -> version 1 active."""
    definition = StrategyDefinition.from_engine("NIFTY", GOLDEN, risk_limits={"max_loss": D("8175")})
    rec = StrategyRecord(definition, at=T0, clock=clock)
    v1 = rec.propose_execution(at=T0 + datetime.timedelta(minutes=1))
    rec.confirm(v1.number, at=T0 + datetime.timedelta(minutes=2))

    def c(instrument: Instrument, strike: str) -> tuple:
        return ("NIFTY", instrument, D(strike), EXPIRY)

    filled = Position(((c(Instrument.PE, "22800"), 75), (c(Instrument.PE, "23000"), -75),
                       (c(Instrument.CE, "23400"), -75), (c(Instrument.CE, "23600"), 75)))
    rec.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, filled, T0 + datetime.timedelta(minutes=3), "exec-1", attempt=rec.live_attempt))
    assert rec.active_version is not None and rec.active_version.number == 1
    return rec


def snapshot(strategy: Strategy, *, health: DataHealth = DataHealth.AVAILABLE,
             at: datetime.datetime = CHECKED_AT, source: str = SOURCE):
    return snapshot_from_strategy(strategy, underlying_level=D("22950"), as_of=at, data_health=health, source=source)


def loss_evaluation(**kwargs) -> Evaluation:
    return evaluate(MAX_LOSS_RULE, snapshot(STRESSED, **kwargs))


REQ_040 = Path(__file__).resolve().parents[2] / "spec" / "requirements" / "REQ-040.md"


def ac_text(ac_id: str) -> str:
    """One REQ-040 acceptance-criterion text, read from the spec file on disk (never copied into a test)."""
    raw = REQ_040.read_text(encoding="utf-8")
    _, frontmatter, _ = raw.split("---\n", 2)
    return {ac["id"]: ac["text"] for ac in yaml.safe_load(frontmatter)["acceptance_criteria"]}[ac_id]
