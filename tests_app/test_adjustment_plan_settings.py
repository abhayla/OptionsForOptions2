"""Contract "Your adjustment settings" step 3 part 1 CORE proof, on a fresh migrated database: GET
/api/strategies/{id}/adjustment-plan answers ``settings`` (every covered key: value + source from the ONE read,
``ofo_app.settings_in_force.in_force``), ``triggers`` and ``stops``.

Spec basis: ADR-245 (strategy, else user, else admin default, named); ADR-247 (stop lines); contract step 3 proof
(user 3 + plan 1.5 -> 1.5 "strategy"; plan value removed -> 3 "user"; user value reset -> 2 "default").
Same harness as ``test_adjustment_plan.py`` (scenario ADJ-02 through the app's own stores).
"""
from __future__ import annotations

import pathlib
import sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_adjustment_plan import OK, _call, _plan_path, _seeded, _system_ic, app_db_url  # noqa: F401

CARRY = "other.carry_gap_percent"
PREF = "/api/adjustments/preferences"


def _setting(out: dict, key: str) -> tuple:
    row = next(x for x in out["settings"] if x["key"] == key)
    return row["value"], row["source"], row["reason"]


async def test_core_plan_settings_follow_strategy_then_user_then_default(app_db_url, monkeypatch):  # noqa: F811 - the imported fixture
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system = await _system_ic(app_db_url)
    status, out = await _call("POST", f"{PREF}/{CARRY}", json={"value": "3"})
    assert status == OK, out
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": system.id, "settings": {CARRY: "1.5"}})
    assert status == OK, out
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK, out
    assert _setting(out, CARRY) == ("1.5", "strategy", None)
    assert _setting(out, "orders.default_lots") == ("1", "default", None)  # gap 4: two layers, the admin default
    assert _setting(out, "adjustments.roll_basis") == ("1", "default", None)
    # gap 3: the plan copy's triggers, named "strategy"; gap 2: the ADR-247 stop lines, always the three kinds
    t01 = next(t for t in out["triggers"] if t["id"] == "T-01")
    assert (t01["source"], t01["weekly"], out["triggers_reason"]) == ("strategy", ["0.75", "0.5", "0.3"], None)
    assert [x["kind"] for x in out["stops"]["lines"]] == ["max_loss_pct", "credit_multiple", "margin_pct"]
    assert out["stops"]["lines"][2]["active"] is False  # % of margin OFF by default
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": system.id, "settings": {}})
    assert status == OK, out
    assert _setting(out, CARRY) == ("3", "user", None)  # the write's reply reads the same one function
    status, _ = await _call("POST", f"{PREF}/{CARRY}/reset", json={})
    assert status == OK
    status, out = await _call("GET", _plan_path(sid))
    assert _setting(out, CARRY) == ("2", "default", None)


async def test_stop_amounts_come_from_the_engine_and_name_which_fires_first(app_db_url, monkeypatch):  # noqa: F811 - the imported fixture
    """Each active stop has an amount or a named reason; ``first`` is the smallest amount, or None with
    ``stop_first_unknown`` when an active stop has no amount (never guessed)."""
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK, out
    stops = out["stops"]
    active = [x for x in stops["lines"] if x["active"]]
    assert all((x["amount"] is None) == (x["reason"] is not None) for x in active), stops
    if all(x["amount"] is not None for x in active):
        assert stops["first"] == min(active, key=lambda x: Decimal(x["amount"]))["kind"] and stops["reason"] is None
    else:
        assert (stops["first"], stops["reason"]) == (None, "stop_first_unknown")
