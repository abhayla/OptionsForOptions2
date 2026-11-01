# ruff: noqa: E501
"""Readers that turn the settings in force into the values a calculation takes as explicit parameters (REQ-167 AC-4).

Spec basis: ADR-222 (1) "No rupee amount, rate, percentage or threshold that changes a figure a user sees is typed in
code"; REQ-167 AC-4 "Each wired calculation reads the value in force when it runs (no restart)".

Every function takes the mapping the app layer built with ``settings_in_force`` (required: there is no fallback to the
registry defaults; a pure test passes ``ofo.settings.defaults()`` explicitly); the number itself is written only in ``registry.json``. Each read goes
through :func:`ofo.settings.value_of`, so a key missing from the mapping is an error, never a silent default.
Standard library only.
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping
from decimal import Decimal

from ofo.marketdata.forward import ForwardQuality
from ofo.settings import time_of, value_of

SD_HORIZON_DAYS = "scenarios.sd_horizon_days"
TARGET_SPAN = "scenarios.target_span"
PAYOFF_STEP_COUNT = 4
PAYOFF_STEP_KEY = "scenarios.payoff_step_{}"
PAYOFF_DEFAULT_STEP_KEY = "scenarios.payoff_default_step_{}"
QUICK_PICK_COUNT = 4
QUICK_PICK_KEY = "scenarios.strangle_quick_pick_{}_{}"
SCENARIO_FIELDS = ("step_points", "anchor_points", "half_width_points", "margin_steps", "max_columns")
INDEXES = ("NIFTY", "SENSEX")
FORWARD_QUALITY_WIDTH = "pricing.forward_quality_width"
FORWARD_STRIKES_NEAR = "pricing.forward_strikes_near"
FORWARD_MIN_STRIKES = "pricing.forward_min_strikes"


def sd_horizon_days(values: Mapping[str, Decimal]) -> int:
    return int(value_of(values, SD_HORIZON_DAYS))


def target_span(values: Mapping[str, Decimal]) -> Decimal:
    return value_of(values, TARGET_SPAN)


def payoff_steps(values: Mapping[str, Decimal]) -> tuple[Decimal, ...]:
    v = values
    return tuple(value_of(v, PAYOFF_STEP_KEY.format(i)) for i in range(1, PAYOFF_STEP_COUNT + 1))


def payoff_default_step(values: Mapping[str, Decimal], index: str) -> Decimal:
    """The payoff table's interval for ``index`` when none is picked; an index with no setting is refused (REQ-137 AC-1),
    never given another index's step."""
    if index not in INDEXES:
        raise ValueError(f"no payoff table strike step is stated for {index!r} (REQ-137 AC-1)")
    return value_of(values, PAYOFF_DEFAULT_STEP_KEY.format(index.lower()))


def quick_pick_distances(values: Mapping[str, Decimal]) -> dict[str, tuple[int, ...]]:
    v = values
    return {i: tuple(int(value_of(v, QUICK_PICK_KEY.format(i.lower(), n))) for n in range(1, QUICK_PICK_COUNT + 1))
            for i in INDEXES}


def scenario_fields(values: Mapping[str, Decimal], index: str) -> dict[str, Decimal]:
    """The five scenario-column values of ``index`` by ScenarioConfig field name (half width = min_half_width)."""
    if index not in INDEXES:
        raise ValueError(f"no scenario settings are stated for {index!r}")
    v = values
    return {f: value_of(v, f"scenarios.{index.lower()}_{f}") for f in SCENARIO_FIELDS}


def forward_quality(values: Mapping[str, Decimal]) -> ForwardQuality:
    """The three forward settings in force as the one parameter object ``parity_forward`` requires (REQ-167 AC-5)."""
    return ForwardQuality(width=value_of(values, FORWARD_QUALITY_WIDTH),
                          strikes_near=int(value_of(values, FORWARD_STRIKES_NEAR)),
                          min_strikes=int(value_of(values, FORWARD_MIN_STRIKES)))


# ---- speeds, detection, billing, data (GC-SET batch 2) ---------------------------------------------------------
OPEN_STRATEGY_SECONDS = "speeds.open_strategy_seconds"
TRIAL_DAYS = "billing.trial_days"
REFERRAL_DAYS = "billing.referral_days"
FREEZE_STALE_DAYS = "data.freeze_file_stale_days"


def open_strategy_seconds(values: Mapping[str, Decimal]) -> float:
    """Seconds between two live pushes of one open strategy (a time gate, not money: a float is exact enough)."""
    return float(value_of(values, OPEN_STRATEGY_SECONDS))


def trial_days(values: Mapping[str, Decimal]) -> int:
    return int(value_of(values, TRIAL_DAYS))


def referral_days(values: Mapping[str, Decimal]) -> int:
    return int(value_of(values, REFERRAL_DAYS))


def freeze_stale_days(values: Mapping[str, Decimal]) -> int:
    return int(value_of(values, FREEZE_STALE_DAYS))


MAX_DELIST_PERCENT = "data.max_delist_percent"


def max_delist_percent(values: Mapping[str, Decimal]) -> Decimal:
    return value_of(values, MAX_DELIST_PERCENT)


CHAIN_STRIKES_EACH_SIDE = "limits.chain_strikes_each_side"


def chain_strikes_each_side(values: Mapping[str, Decimal]) -> int:
    """The most strikes either side of ATM the option chain shows and accepts (REQ-167 AC-5)."""
    return int(value_of(values, CHAIN_STRIKES_EACH_SIDE))


HISTORY_MAX_DAYS = "limits.history_max_days"


def history_max_days(values: Mapping[str, Decimal]) -> int:
    """The most trading days of strategy price history one read returns (REQ-167 AC-5)."""
    return int(value_of(values, HISTORY_MAX_DAYS))


# ---- exchange and broker facts (GC-SET step 5a): IST wall-clock times stored HHMM --------------------------------
PAPER_SETTLE_FROM = "facts.paper_settle_from"
PAPER_RETRY_UNTIL = "facts.paper_retry_until"


def paper_settle_from(values: Mapping[str, Decimal]) -> datetime.time:
    """From this IST time on expiry day the paper settlement reads the index close (REQ-167 AC-5)."""
    return time_of(value_of(values, PAPER_SETTLE_FROM))


def paper_retry_until(values: Mapping[str, Decimal]) -> datetime.time:
    """While a group had no close, the settlement job retries until this IST time (REQ-167 AC-5)."""
    return time_of(value_of(values, PAPER_RETRY_UNTIL))
