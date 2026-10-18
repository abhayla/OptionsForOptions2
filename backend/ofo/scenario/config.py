"""Scenario level configuration per index (REQ-034 AC-4; ADR-042; scenario-calculations.md §4).

Step, anchor and the default-range rules are Admin configuration, never constants in the level code. The defaults
below are the Admin defaults (ADR-042: NIFTY 100 points, SENSEX 300 points); Admin replaces them with
:meth:`ScenarioConfig.from_mapping`. Every value is index POINTS, never rupees.

Validation fails closed: a step or anchor that is not a positive multiple of the index's strike gap (read from the
instrument catalogue, never hard-coded) is refused, as are unknown keys, absurd sizes and duplicate indices.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Final, Iterable, Mapping

from ofo.instruments.catalogue import Catalogue

MAX_STEP_POINTS: Final = Decimal("10000")
MAX_HALF_WIDTH_POINTS: Final = Decimal("50000")
MAX_MARGIN_STEPS: Final = 50
MAX_COLUMNS_CAP: Final = 1000


def _points(value: object, name: str, cap: Decimal, *, allow_zero: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite decimal.Decimal of index points, got {value!r}")
    if value != value.to_integral_value():
        raise ValueError(f"{name} must be a whole number of index points, got {value}")
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{name} must be {'>= 0' if allow_zero else '> 0'} points, got {value}")
    if value > cap:
        raise ValueError(f"{name} {value} exceeds the cap of {cap} points")
    return value


def _count(value: object, name: str, cap: int, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer, got {value!r}")
    if not minimum <= value <= cap:
        raise ValueError(f"{name} must be within [{minimum}, {cap}], got {value}")
    return value


@dataclass(frozen=True)
class ScenarioConfig:
    """How one index's scenario levels are chosen.

    - ``step_points``: distance between grid columns (NIFTY 100, SENSEX 300).
    - ``anchor_points``: grid columns sit on multiples of this rounded level (Q33C: rounded 100-point levels for
      NIFTY); the step must be a multiple of it, so every column is an anchor multiple.
    - ``min_half_width_points``: the default range reaches at least this far each side of spot rounded to the
      anchor (owner's first sketch, T1 #83: NIFTY 23,000 -> 22,000 ... 24,000).
    - ``margin_steps``: steps added beyond the outermost strike, breakeven, risk boundary or expected move.
    - ``max_columns``: refuses a range with more grid columns than this (absurd size guard).
    """

    index: str
    step_points: Decimal
    anchor_points: Decimal
    min_half_width_points: Decimal
    margin_steps: int
    max_columns: int

    def __post_init__(self) -> None:
        if not isinstance(self.index, str) or not self.index.strip() or self.index != self.index.strip().upper():
            raise ValueError(f"index must be an upper-case index name, got {self.index!r}")
        _points(self.step_points, "step_points", MAX_STEP_POINTS)
        _points(self.anchor_points, "anchor_points", MAX_STEP_POINTS)
        _points(self.min_half_width_points, "min_half_width_points", MAX_HALF_WIDTH_POINTS, allow_zero=True)
        _count(self.margin_steps, "margin_steps", MAX_MARGIN_STEPS, minimum=0)
        _count(self.max_columns, "max_columns", MAX_COLUMNS_CAP, minimum=2)
        if self.step_points % self.anchor_points != 0:
            raise ValueError(
                f"step_points {self.step_points} must be a multiple of anchor_points {self.anchor_points}"
            )

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> ScenarioConfig:
        """Build from an Admin settings record. Every key is required; an unknown (e.g. misspelled) key is refused.

        Point values are given as strings or Decimals ("300"), never floats.
        """
        if not isinstance(data, Mapping):
            raise ValueError(f"scenario config must be a mapping, got {type(data).__name__}")
        names = [f.name for f in fields(cls)]
        unknown = sorted(set(data) - set(names))
        if unknown:
            raise ValueError(f"unknown scenario config keys: {unknown}")
        missing = sorted(set(names) - set(data))
        if missing:
            raise ValueError(f"missing scenario config keys: {missing}")
        values = dict(data)
        for key in ("step_points", "anchor_points", "min_half_width_points"):
            raw = values[key]
            if isinstance(raw, float):
                raise ValueError(f"{key} must not be a float, got {raw!r}")
            if isinstance(raw, str):
                try:
                    values[key] = Decimal(raw)
                except ArithmeticError as exc:
                    raise ValueError(f"{key} is not a number: {raw!r}") from exc
        return cls(**values)  # type: ignore[arg-type]

    def check_against_catalogue(self, catalogue: Catalogue, expiry: datetime.date) -> Decimal:
        """Refuse a step or anchor that is not a multiple of the strike gap listed for this index and expiry.

        ADR-042: every column sits on a real strike level. Returns the measured strike gap.
        """
        gap = catalogue.strike_gap(self.index, expiry)
        for name, value in (("step_points", self.step_points), ("anchor_points", self.anchor_points)):
            if value % gap != 0:
                raise ValueError(
                    f"{self.index} {name} {value} is not a multiple of the listed strike gap {gap} "
                    f"(expiry {expiry}); columns would not sit on real strike levels"
                )
        return gap


# Admin defaults (ADR-042). SENSEX is ~3x NIFTY's level, so its widths scale by 3 like its step.
DEFAULT_CONFIGS: Final = (
    ScenarioConfig("NIFTY", Decimal("100"), Decimal("100"), Decimal("1000"), 2, 200),
    ScenarioConfig("SENSEX", Decimal("300"), Decimal("300"), Decimal("3000"), 2, 200),
)


class ScenarioSettings:
    """The Admin set of per-index configs. One config per index; a duplicate index is refused."""

    def __init__(self, configs: Iterable[ScenarioConfig] = DEFAULT_CONFIGS) -> None:
        self._by_index: dict[str, ScenarioConfig] = {}
        for config in configs:
            if not isinstance(config, ScenarioConfig):
                raise ValueError(f"every entry must be a ScenarioConfig, got {config!r}")
            if config.index in self._by_index:
                raise ValueError(f"duplicate scenario config for {config.index}")
            self._by_index[config.index] = config
        if not self._by_index:
            raise ValueError("scenario settings need at least one index config")

    def for_index(self, index: str) -> ScenarioConfig:
        try:
            return self._by_index[index]
        except KeyError:
            raise ValueError(f"no scenario config for index {index!r}") from None
