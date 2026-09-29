"""Adjustment metric registry (REQ-071): the reference-video values and the feasibility guard.

The 30 values are DATA (``metric_registry.json``, taken from the table in
``spec/technical-design/adjustment-data-contract.md``); a test parses that table and compares, so the two cannot
drift. A calculator may be registered only for a value whose feasibility is ``pass`` (Data Feasibility Test,
REQ-071 AC-2): the check reads the registry's own row, never a caller-supplied verdict.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

DATA_FILE = Path(__file__).with_name("metric_registry.json")
FEASIBILITY_VALUES = frozenset({"pass", "fail", "unknown", "unclear"})
_KEYS = frozenset({"id", "name", "source", "frequency", "calculation", "feasibility", "feasibility_note",
                   "owner_reading", "out_of_v1"})
EXPECTED_IDS = tuple(range(1, 31))


class RegistryError(ValueError):
    """The registry data or a registration request is invalid."""


class FeasibilityError(RegistryError):
    """A calculator was requested for a value whose feasibility is not ``pass``."""


@dataclass(frozen=True)
class MetricRow:
    id: int
    name: str
    source: str
    frequency: str
    calculation: str
    feasibility: str
    feasibility_note: str
    owner_reading: str
    out_of_v1: bool


def load_rows(path: Path = DATA_FILE) -> tuple[MetricRow, ...]:
    """Load and validate the data file; any drift raises ``RegistryError``."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise RegistryError("registry data must be a list of rows")
    rows = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != _KEYS:
            raise RegistryError(f"row has missing or unknown keys: {sorted(item) if isinstance(item, dict) else item}")
        if item["feasibility"] not in FEASIBILITY_VALUES:
            raise RegistryError(f"row {item['id']}: feasibility {item['feasibility']!r} not in {sorted(FEASIBILITY_VALUES)}")
        if not isinstance(item["out_of_v1"], bool):
            raise RegistryError(f"row {item['id']}: out_of_v1 must be a bool")
        rows.append(MetricRow(**item))
    if tuple(r.id for r in rows) != EXPECTED_IDS:
        raise RegistryError("registry must hold exactly rows 1..30 in order")
    for r in rows:
        if r.out_of_v1 and r.feasibility == "pass":
            raise RegistryError(f"row {r.id}: an out-of-V1 value cannot be pass")
    return tuple(rows)


class MetricRegistry:
    """The metric table plus the calculators registered against feasible rows."""

    def __init__(self, path: Path = DATA_FILE) -> None:
        self.rows: tuple[MetricRow, ...] = load_rows(path)
        self._by_id = {r.id: r for r in self.rows}
        self._calculators: dict[int, Callable] = {}

    def get(self, metric_id: int) -> MetricRow:
        row = self._by_id.get(metric_id) if type(metric_id) is int else None
        if row is None:
            raise RegistryError(f"unknown metric id {metric_id!r}")
        return row

    def register_calculator(self, metric_id: int, calculator: Callable) -> None:
        row = self.get(metric_id)
        if not callable(calculator):
            raise RegistryError("calculator must be callable")
        if row.feasibility != "pass":
            raise FeasibilityError(
                f"metric {row.id} ({row.name[:40]}) has feasibility {row.feasibility!r}; "
                "only 'pass' values may be built (REQ-071 AC-2)")
        if row.id in self._calculators:
            raise RegistryError(f"metric {row.id} already has a calculator")
        self._calculators[row.id] = calculator

    def calculator(self, metric_id: int) -> Callable:
        row = self.get(metric_id)
        if row.id not in self._calculators:
            raise RegistryError(f"no calculator registered for metric {row.id}")
        return self._calculators[row.id]

    def registered_ids(self) -> list[int]:
        return sorted(self._calculators)
