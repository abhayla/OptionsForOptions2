"""The outcome as plain JSON-ready data (W-063 step 3): every money/points/IV value is the Decimal's own string, never a
float (ADR-008); times are ISO-8601 with their offset; enums are their values. Standard library only."""
from __future__ import annotations

import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from ofo.outcome.service import Outcome, OutcomeLeg
from ofo.table import Cell, ColumnSpec, Table


def _s(value: Decimal | int | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise TypeError(f"a number field must be a Decimal or an int, got {type(value).__name__}")
    return f"{value:f}" if isinstance(value, Decimal) else str(value)


def _t(value: datetime.datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _col_id(cid: object) -> str:
    if isinstance(cid, Enum):
        return str(cid.value)
    return _s(cid)  # a scenario column's id is its level


def _cell(cell: Cell) -> dict[str, Any]:
    v = cell.value
    value = v if isinstance(v, str) or v is None else _s(v)
    return {"value": value, "display": cell.display, "kind": cell.kind.value, "reason": cell.reason,
            "side": cell.side, "per_unit": _s(cell.per_unit), "vendor": _s(cell.vendor)}


def _column(col: ColumnSpec, visible: set[str]) -> dict[str, Any]:
    cid = _col_id(col.id)
    return {"id": cid, "label": col.label, "kind": col.kind.value, "is_scenario_level": col.is_scenario_level,
            "markers": list(col.markers), "visible": cid in visible}


def _table(table: Table, visible_cols) -> dict[str, Any]:
    visible = {_col_id(c.id) for c in visible_cols}
    return {"underlying": table.underlying, "spot_level": _s(table.spot_level), "spot_at": _t(table.spot_at),
            "output_label": table.output_label, "columns": [_column(c, visible) for c in table.columns],
            "rows": [{"row_id": r.row_id, "cells": {_col_id(k): _cell(c) for k, c in r.cells.items()}}
                     for r in table.rows]}


def _leg(leg: OutcomeLeg) -> dict[str, Any]:
    return {"instrument_id": leg.instrument_id, "symbol": leg.symbol, "action": leg.action.value,
            "instrument": None if leg.instrument is None else leg.instrument.value, "strike": _s(leg.strike),
            "expiry": None if leg.expiry is None else leg.expiry.isoformat(), "lots": leg.lots,
            "lot_size": leg.lot_size, "quantity": leg.quantity, "planned_entry": _s(leg.planned_entry),
            "captured_at": _t(leg.captured_at), "ltp": _s(leg.ltp), "iv": _s(leg.iv),
            "health": None if leg.health is None else leg.health.value, "label": leg.label}


def outcome_to_dict(out: Outcome) -> dict[str, Any]:
    scenario = payoff = summary = table = None
    if out.scenario is not None and out.level_set is not None:
        v, ls = out.scenario, out.level_set
        scenario = {
            "view": v.view.value, "label": v.label, "kind": v.kind, "available": v.available,
            "unavailable_reason": v.unavailable_reason, "output_label": v.output_label,
            "levels": [{"level": _s(c.level), "current": c.is_current, "zero_pnl": c.is_zero_pnl}
                       for c in ls.columns],
            "totals": None if v.totals is None else [_s(x) for x in v.totals],
            "step": _s(ls.step), "start": _s(ls.start), "end": _s(ls.end),
        }
        payoff = {"view": v.view.value, "points": [{"level": _s(lvl), "pnl": _s(p)} for lvl, p in out.payoff_points]}
    if out.summary is not None:
        s = out.summary
        summary = {
            "what_can_i_lose": s.what_can_i_lose, "what_can_i_make": s.what_can_i_make,
            "where_do_i_start_losing": s.where_do_i_start_losing, "max_profit": _s(s.max_profit),
            "max_loss": _s(s.max_loss), "max_profit_unlimited": s.max_profit_unlimited,
            "max_loss_unlimited": s.max_loss_unlimited, "breakevens": [_s(b) for b in s.breakevens],
            "lower_be": _s(s.lower_be), "upper_be": _s(s.upper_be),
            "risk_boundaries": [_s(b) for b in s.risk_boundaries],
        }
    if out.table is not None:
        table = _table(out.table, out.visible_columns)
    return {
        "state": out.state.value, "underlying": out.underlying, "ux_level": out.ux_level.value,
        "status_label": out.status_label, "reason": out.reason, "output_label": out.output_label,
        "valuation": _t(out.valuation), "spot_level": _s(out.spot_level), "spot_at": _t(out.spot_at),
        "legs": [_leg(leg) for leg in out.legs], "margin": {"state": out.margin.state, "reason": out.margin.reason},
        "table": table, "scenario": scenario, "payoff": payoff, "summary": summary,
    }
