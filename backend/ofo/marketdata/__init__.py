"""Normalized market data and data health (REQ-049)."""
from __future__ import annotations

from ofo.marketdata.availability import MonitoringStatus, strategy_monitoring_status
from ofo.marketdata.disconnect import disconnect_message
from ofo.marketdata.health import HealthThresholds, ORCHESTRATOR_DEFAULT_THRESHOLDS, build_quote, evaluate_health
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.marketdata.rule_adapter import input_health_from_quotes
from ofo.rules.inputs import DataHealth

__all__ = [
    "DataHealth",
    "HealthThresholds",
    "ORCHESTRATOR_DEFAULT_THRESHOLDS",
    "MonitoringStatus",
    "NormalizedQuote",
    "SourceMetadata",
    "build_quote",
    "disconnect_message",
    "evaluate_health",
    "input_health_from_quotes",
    "strategy_monitoring_status",
]
