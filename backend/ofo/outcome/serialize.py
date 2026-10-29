# ruff: noqa: E501, PLR2004
"""The outcome as plain JSON-ready data (W-063 step 3): every money/points/IV value is the Decimal's own string, never a
float (ADR-008); times are ISO-8601 with their offset; enums are their values. Standard library only."""
from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any

from ofo.engine.black_scholes import GREEK_STEP
from ofo.engine.display import breakeven_percent_exact
from ofo.errors.explanations import render_explanation
from ofo.outcome import money
from ofo.outcome.price_text import price_text
from ofo.outcome.service import Outcome, OutcomeLeg
from ofo.table import Cell, ColumnSpec, Table
from ofo.table.model import scenario_caption_parts
from ofo.timeutil import days_to_expiry


def _s(value: Decimal | int | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise TypeError(f"a number field must be a Decimal or an int, got {type(value).__name__}")
    return f"{value:f}" if isinstance(value, Decimal) else str(value)


def _level(value: Decimal | None) -> str | None:
    """The index level as the browser prints it: two decimals ("22713.00", "22709.50"), never a Decimal that lost its
    trailing zeros ("22713", "22709.5") (REQ-152 AC-2 style; the index row of GET /indices is already quantized)."""
    return price_text(value)


def _t(value: datetime.datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _whole(value: Decimal | None, *, signed: bool) -> Any:
    """REQ-152: the whole-rupee text of a summary figure, made on the server from the catalogue (ADR-008, ADR-003);
    None stays None (the reason or the unlimited flag is beside it)."""
    if value is None:
        return None
    return render_explanation("summary_whole_rupees_signed" if signed else "summary_whole_rupees", amount=value)


def _breakeven(level: Decimal, spot: Decimal | None) -> Any:
    """REQ-153 AC-1: the level in whole points with its signed percent from spot; no usable spot: the level alone."""
    percent = breakeven_percent_exact(level, spot)
    if percent is None:
        return render_explanation("summary_breakeven_level", level=level)
    return render_explanation("summary_breakeven_percent", level=level, percent=percent)


def _margin(out: Outcome) -> dict[str, Any]:
    m = out.margin
    return {"state": m.state, "reason": m.reason, "needed": _s(m.needed), "broker_needed": _s(m.broker_needed),
            "available": _s(m.available), "needed_display": _whole(m.needed, signed=False),
            "broker_needed_display": _whole(m.broker_needed, signed=False),
            "available_display": _whole(m.available, signed=False),
            "checked_at": _t(m.checked_at), "shortfall": m.shortfall,
            "shortfall_reason": m.shortfall_reason}


def _breakdown(b: Any) -> dict[str, Any] | None:
    """ADR-167 (2): the round-trip charges by component as Decimal strings, shown once (Sensibull screen 022);
    ``rates_read_on`` is the date of the rates; ``label`` the catalogue word "estimate". Hunk from
    origin/build/W-127-b2-payoff @194cc405 (backend/ofo/outcome/serialize.py), plus the label and the rates date."""
    if b is None:
        return None
    return {"brokerage": _s(b.brokerage), "stt": _s(b.stt), "exchange_transaction": _s(b.exchange_transaction),
            "gst": _s(b.gst), "stamp": _s(b.stamp), "sebi": _s(b.sebi), "total": _s(b.total),
            "rates_read_on": b.read_on.isoformat(), "label": render_explanation("money_charges_label"),
            "exercise_stt_rate": _s(b.exercise_stt_rate),
            "exercise_stt_note": None if b.exercise_stt_rate is None else render_explanation(
                "money_charges_exercise_stt", pct=(b.exercise_stt_rate * 100).normalize())}


def _net_premium(p: money.NetPremium | None) -> dict[str, Any] | None:
    if p is None:
        return None
    return {"amount": _s(p.amount), "amount_display": _whole(p.amount, signed=False), "side": p.side,
            "per_unit": _s(p.per_unit), "per_unit_display": price_text(p.per_unit), "text": p.text, "reason": p.reason}


def _funds_share(f: money.FundsShare | None) -> dict[str, Any] | None:
    if f is None:
        return None
    return {"margin_needed": _s(f.margin_needed), "read_at": _t(f.read_at), "max_profit_percent": _s(f.max_profit_percent),
            "max_loss_percent": _s(f.max_loss_percent), "max_profit_text": f.max_profit_text,
            "max_loss_text": f.max_loss_text}


def _col_id(cid: object) -> str:
    if isinstance(cid, Enum):
        return str(cid.value)
    return _s(cid)  # a scenario column's id is its level


def _per_unit_4dp(value: Decimal | None) -> Decimal | None:
    """A per-unit Greek at the boundary: Decimal to 4 dp (scenario-calculations section 4), never through a float."""
    return None if value is None else value.quantize(GREEK_STEP, rounding=ROUND_HALF_UP)


def _cell(cell: Cell) -> dict[str, Any]:
    v = cell.value
    value = v if isinstance(v, str) or v is None else _s(v)
    return {"value": value, "display": cell.display, "kind": cell.kind.value, "reason": cell.reason,
            "side": cell.side, "per_unit": _s(_per_unit_4dp(cell.per_unit)),
            "per_unit_display": cell.per_unit_display, "vendor": _s(cell.vendor)}


def _column(col: ColumnSpec, visible: set[str]) -> dict[str, Any]:
    cid = _col_id(col.id)
    return {"id": cid, "label": col.label, "kind": col.kind.value, "is_scenario_level": col.is_scenario_level,
            "markers": list(col.markers), "visible": cid in visible}


def _table(table: Table, visible_cols) -> dict[str, Any]:
    visible = {_col_id(c.id) for c in visible_cols}
    return {"underlying": table.underlying, "spot_level": _level(table.spot_level), "spot_at": _t(table.spot_at),
            "output_label": table.output_label, "scenario_heading": list(scenario_caption_parts(table)),
            "columns": [_column(c, visible) for c in table.columns],
            "rows": [{"row_id": r.row_id, "cells": {_col_id(k): _cell(c) for k, c in r.cells.items()}}
                     for r in table.rows]}


def _leg(leg: OutcomeLeg, today: datetime.date | None) -> dict[str, Any]:
    return {"instrument_id": leg.instrument_id, "symbol": leg.symbol, "action": leg.action.value,
            "instrument": None if leg.instrument is None else leg.instrument.value, "strike": _s(leg.strike),
            "expiry": None if leg.expiry is None else leg.expiry.isoformat(),
            "days_to_expiry": None if today is None else days_to_expiry(leg.expiry, today), "lots": leg.lots,
            "lot_size": leg.lot_size, "quantity": leg.quantity, "planned_entry": _s(leg.planned_entry),
            "planned_entry_display": price_text(leg.planned_entry),
            "captured_at": _t(leg.captured_at), "ltp": _s(leg.ltp), "ltp_display": price_text(leg.ltp), "iv": _s(leg.iv),
            "health": None if leg.health is None else leg.health.value, "label": leg.label}


def _points(levels, totals) -> list[dict[str, Any]]:
    """Payoff points with their server display text (the table cells' rupee format, GC-BM F-8): the browser never
    formats or computes a money value (ADR-008)."""
    return [{"level": _s(lvl), "pnl": _s(p), "display": render_explanation("cell_rupees", amount=p)}
            for lvl, p in zip(levels, totals, strict=True)]


def _curve(v: Any) -> dict[str, Any]:
    """REQ-083 AC-1/AC-3: one view's curve; unavailable -> no points and the engine's reason."""
    return {"view": v.view.value, "label": v.label, "kind": v.kind, "available": v.available,
            "unavailable_reason": v.unavailable_reason, "output_label": v.output_label,
            "points": _points(v.levels, v.totals) if v.available and v.totals is not None else []}


def _greeks_out(g: Any) -> dict[str, Any] | None:
    return None if g is None else {"delta": _s(g.delta), "gamma": _s(g.gamma), "theta": _s(g.theta), "vega": _s(g.vega)}


def _target(t: Any) -> dict[str, Any]:
    """REQ-084 AC-1/AC-2/AC-4: the what-if target's limits, the clamped inputs and every engine figure there."""
    pnl = None if t.pnl is None else {"value": _s(t.pnl), "display": render_explanation("cell_rupees", amount=t.pnl)}
    greeks = None if t.greeks is None else {"legs": [_greeks_out(g) for g in t.greeks.legs],
                                            "total": _greeks_out(t.greeks.total), "unavailable": t.greeks.unavailable,
                                            "unavailable_text": t.greeks.unavailable_text}
    return {"limits": {"min": _s(t.limits.min), "max": _s(t.limits.max), "step": _s(t.limits.step)},
            "level": _s(t.level), "level_clamped": t.level_clamped, "level_clamp_text": t.level_clamp_text,
            "at": t.at, "at_clamped": t.at_clamped, "clamp": t.clamp, "at_clamp_text": t.at_clamp_text, "at_refused_reason": t.at_refused_reason, "kind": t.kind, "model": t.model,
            "output_label": t.output_label, "pnl": pnl,
            "breakevens": None if t.breakevens is None else [_s(b) for b in t.breakevens],
            "breakevens_reason": t.breakevens_reason,
            "curve": None if t.curve is None else _curve(t.curve), "greeks": greeks}


def _view_head(v: Any) -> dict[str, Any]:
    return {"view": v.view.value, "label": v.label, "kind": v.kind, "available": v.available,
            "unavailable_reason": v.unavailable_reason}


def _payoff_table(t: Any) -> dict[str, Any]:
    """REQ-137 AC-1: one row per level, each view's P&L with its display text (None where the view is unavailable)."""
    cols = {v.view: (v.totals if v.available else None) for v in t.views}

    def cell(view, i):
        totals = cols.get(view)
        if totals is None:
            return None
        return {"pnl": _s(totals[i]), "display": render_explanation("cell_rupees", amount=totals[i])}

    from ofo.scenario.levels import move_from_spot  # noqa: PLC0415 - late like View below (D-B26, REQ-137 AC-2)
    from ofo.scenario.views import View  # late: the module's imports stay the outcome's own

    def row(i, lvl):
        pct, pct_display = move_from_spot(lvl, t.spot)
        return {"level": _s(lvl), "level_display": render_explanation("cell_points", value=lvl),
                "nearest_spot": lvl == t.nearest_spot, "move_pct": _s(pct), "move_pct_display": pct_display,
                "estimated_now": cell(View.ESTIMATED_NOW, i), "at_expiry": cell(View.AT_EXPIRY, i)}
    return {"step": _s(t.step), "available": t.unavailable_reason is None,
            "unavailable_reason": t.unavailable_reason, "columns": [_view_head(v) for v in t.views],
            "rows": [row(i, lvl) for i, lvl in enumerate(t.levels)]}


def _sd(sd: Any) -> dict[str, Any]:
    """REQ-083 AC-4 / REQ-137 AC-3: the SD table rows and the four band levels, both from the same rows."""
    rows = [{"sd": r.sd, "label": render_explanation("sd_label", n=r.sd), "move": _s(r.move),
             "percent": _s(r.percent), "lower": _s(r.lower), "upper": _s(r.upper),
             "move_display": render_explanation("sd_move", points=r.move, percent=r.percent),
             "lower_display": render_explanation("cell_number", value=r.lower),
             "upper_display": render_explanation("cell_number", value=r.upper)} for r in sd.rows]
    bands = []
    if len(sd.rows) == 2:
        one, two = sd.rows
        for n, level in ((-2, two.lower), (-1, one.lower), (1, one.upper), (2, two.upper)):
            bands.append({"sd": n, "label": render_explanation("sd_label", n=n), "level": _s(level),
                          "display": render_explanation("cell_number", value=level)})
    return {"available": sd.available, "reason": sd.reason, "horizon_days": sd.horizon_days, "iv": _s(sd.iv),
            "spot": _s(sd.spot), "rows": rows, "bands": bands}


def outcome_to_dict(out: Outcome, today: datetime.date | None = None) -> dict[str, Any]:
    """``today``: the IST date of the answer's own clock (REQ-135 AC-2); the legs' days to expiry count from it."""
    scenario = payoff = summary = table = None
    if out.scenario is not None and out.level_set is not None:
        v, ls = out.scenario, out.level_set
        scenario = {
            "view": v.view.value, "label": v.label, "kind": v.kind, "available": v.available,
            "unavailable_reason": v.unavailable_reason, "output_label": v.output_label,
            "levels": [{"level": _s(c.level), "current": c.is_current, "zero_pnl": c.is_zero_pnl}
                       for c in ls.columns],
            "totals": None if v.totals is None else [_s(x) for x in v.totals],
            "step": _s(ls.step), "start": _s(ls.start), "end": _s(ls.end), "customised": ls.customised,
        }
        # GC-BM F-8: a graph point can be a strike that is no table column, so each point carries its own display
        # text (the table cells' rupee format), and the browser never formats or computes a money value (ADR-008)
        payoff = {"view": v.view.value, "points": _points(*zip(*out.payoff_points, strict=True))
                  if out.payoff_points else []}
        if out.other_view is not None:  # both views asked for: the other view's totals on the table's levels
            o = out.other_view
            scenario["other"] = {"view": o.view.value, "label": o.label, "kind": o.kind, "available": o.available,
                                 "unavailable_reason": o.unavailable_reason, "output_label": o.output_label,
                                 "totals": None if o.totals is None else [_s(x) for x in o.totals]}
    if out.summary is not None:
        s = out.summary
        summary = {
            "what_can_i_lose": s.what_can_i_lose, "what_can_i_make": s.what_can_i_make,
            "where_do_i_start_losing": s.where_do_i_start_losing, "max_profit": _s(s.max_profit),
            "max_profit_display": _whole(s.max_profit, signed=True),
            "max_loss": _s(s.max_loss),
            "max_loss_display": None if s.max_loss is None else _whole(-s.max_loss, signed=True),
            "breakevens_display": [_breakeven(b, out.spot_level) for b in s.breakevens],
            "max_profit_unlimited": s.max_profit_unlimited,
            "max_loss_unlimited": s.max_loss_unlimited, "breakevens": [_s(b) for b in s.breakevens],
            "lower_be": _s(s.lower_be), "upper_be": _s(s.upper_be),
            "risk_boundaries": [_s(b) for b in s.risk_boundaries],
            "charges": _s(s.charges), "charges_unavailable": s.charges_unavailable,
            "reward_risk": _s(s.reward_risk), "reward_risk_reason": s.reward_risk_reason,
            "time_value": _s(s.time_value), "time_value_display": _whole(s.time_value, signed=True),
            "intrinsic_value": _s(s.intrinsic_value),
            "intrinsic_value_display": _whole(s.intrinsic_value, signed=True),
            "risk_reward": _s(s.risk_reward), "value_label": s.value_label, "value_reason": s.value_reason,
            "net_premium": _net_premium(s.net_premium), "funds_share": _funds_share(s.funds_share),
        }
    if out.table is not None:
        table = _table(out.table, out.visible_columns)
    body = {
        "state": out.state.value, "underlying": out.underlying,
        "status_label": out.status_label, "reason": out.reason, "output_label": out.output_label,
        "valuation": _t(out.valuation), "spot_level": _level(out.spot_level), "spot_at": _t(out.spot_at),
        "legs": [_leg(leg, today) for leg in out.legs], "margin": _margin(out),
        "table": table, "scenario": scenario, "payoff": payoff, "summary": summary,
        "charges_breakdown": _breakdown(out.charges_breakdown),
    }
    if out.curves:  # both views asked for (REQ-083 AC-1): absent otherwise, so today's replies keep their keys
        body["curves"] = {c.view.value: _curve(c) for c in out.curves}
    if out.payoff_table is not None:  # REQ-137 AC-1: a step or both views asked for
        body["payoff_table"] = _payoff_table(out.payoff_table)
    if out.standard_deviation is not None:  # REQ-083 AC-4 / REQ-137 AC-3: sd_bands asked for
        body["standard_deviation"] = _sd(out.standard_deviation)
    if out.centre_label is not None:  # FROM_ENTRIES only: every other answer keeps its exact keys
        body["centre_label"] = out.centre_label
    if out.target is not None:  # REQ-084 AC-4: only when a target level or time was sent
        body["target"] = _target(out.target)
    return body
