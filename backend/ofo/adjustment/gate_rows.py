"""The plain data shapes of the alert gate: the stored-record rows it restores from (ADR-237 (5)) and the Preset.
Imports nothing from the gate, so the storage and settings layers can use them without pulling the gate in (the
risk-exit modules must not reach the gate: REQ-170 AC-5)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class GateRow:
    """The last stored record of one rule (ADR-237 (5)): when it opened, its threshold, and its outcome."""

    rule_id: str
    at: datetime
    threshold: Decimal | None
    dismissed: bool
    open: bool


@dataclass(frozen=True)
class GateRows:
    """What `restore` needs: the last record per rule and the count of records opened on `today` (IST)."""

    last: tuple[GateRow, ...]
    opened_today: int


@dataclass(frozen=True)
class Preset:
    candle: timedelta
    cooldown: timedelta
    rearm_fraction: Decimal
    daily_cap: int
    quiet_until: time
