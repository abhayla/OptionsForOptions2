"""Normalized market data and data health (REQ-049)."""
from __future__ import annotations

from ofo.marketdata.availability import MonitoringStatus, strategy_monitoring_status
from ofo.marketdata.disconnect import DisconnectStatus, disconnect_message, disconnect_status_for_strategy
from ofo.marketdata.health import (
    ORCHESTRATOR_DEFAULT_THRESHOLDS,
    HealthResult,
    HealthThresholds,
    build_quote,
    evaluate_health,
)
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.marketdata.rule_adapter import build_snapshot, input_health_from_quotes, worst_health
from ofo.rules.inputs import DataHealth

__all__ = [
    "DataHealth",
    "DisconnectStatus",
    "HealthResult",
    "HealthThresholds",
    "ORCHESTRATOR_DEFAULT_THRESHOLDS",
    "MonitoringStatus",
    "NormalizedQuote",
    "SourceMetadata",
    "build_quote",
    "build_snapshot",
    "disconnect_message",
    "disconnect_status_for_strategy",
    "evaluate_health",
    "input_health_from_quotes",
    "strategy_monitoring_status",
    "worst_health",
]
