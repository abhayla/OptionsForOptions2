"""ofo.alerts: the kind table (ADR-330 (3), (3b), (4)) and its tie to the catalogue and migration 0054."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from ofo import alerts
from ofo.adjustment import level_watch
from ofo.adjustment import stop_lines as sl
from ofo.errors.explanations import EXPLANATIONS, LABEL_TABLES

_MIGRATION = Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions" \
    / "0054_actionable_alert_answers.py"


def test_actionable_and_informational_kinds_are_exactly_the_decided_ones() -> None:
    assert {k for k, v in alerts.KINDS.items() if v.actionable} == {
        "plan_loss_stop", "plan_profit_target", "plan_rupee_loss", "plan_rupee_profit", "plan_time_exit",
        "adjustment_rule", "side_closed"}
    assert {k for k, v in alerts.KINDS.items() if not v.actionable} == {
        "level_watch", "stop_fired", "settled", "orders_placed", "stop_saved"}
    # ADR-242 (3): a watched level is not actionable and not a History note: its own one-record-per-episode lifecycle
    assert {k for k in alerts.KINDS if alerts.is_informational(k)} == {
        "stop_fired", "settled", "orders_placed", "stop_saved"}
    assert alerts.kind_of(level_watch.RULE_PREFIX + level_watch.ABOVE) == alerts.LEVEL_WATCH
    assert alerts.allowed_answers(alerts.LEVEL_WATCH) == ()


def test_answers_per_kind() -> None:
    assert alerts.allowed_answers("plan_loss_stop") == ("exit", "continue")
    assert alerts.allowed_answers("side_closed") == ("add_legs", "confirm_new_shape")
    assert alerts.allowed_answers("stop_fired") == ()
    assert alerts.allowed_answers("nonsense") == ()
    assert alerts.is_actionable("adjustment_rule") and not alerts.is_actionable("settled")
    assert not alerts.is_actionable("nonsense")


@pytest.mark.parametrize(("trigger", "kind"), [
    ("T-06", "plan_loss_stop"), ("T-16", "plan_loss_stop"), ("stop.credit_x", "plan_loss_stop"),
    ("T-07", "plan_profit_target"), (sl.TRIGGER_TIME_EXIT, "plan_time_exit"),
    ("T-01", "adjustment_rule"), ("T-19", "adjustment_rule"),
    ("", "adjustment_rule"), (None, "adjustment_rule")])
def test_kind_of_trigger_ids(trigger: str | None, kind: str) -> None:
    assert alerts.kind_of(trigger) == kind


def test_every_answer_has_its_label_and_the_wording_lines_exist() -> None:
    labels = LABEL_TABLES["alert_answer"]
    assert set(labels) == set(alerts.ANSWERS)
    assert labels["exit"] == "Exit the position" and labels["continue"] == "Continue with the position"
    for kind in alerts.KINDS.values():
        assert kind.wording_id in EXPLANATIONS
    assert EXPLANATIONS["alert_fired_at"].text == "Fired at {time}"
    assert EXPLANATIONS["alert_no_longer_true_since"].text == "no longer true since {time}"


def _literals(path: Path, *names: str) -> dict[str, object]:
    """Read module-level literal assignments from a file by parsing it, so the check never imports the module
    (the file does ``from alembic import op``; domain-tests has no alembic, and a skip hides the guard)."""
    found: dict[str, object] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in names:
            found[node.targets[0].id] = ast.literal_eval(node.value)
    assert set(found) == set(names), f"{path.name} lacks a literal for {sorted(set(names) - set(found))}"
    return found


def test_the_migration_copies_the_table() -> None:
    copy = _literals(_MIGRATION, "KINDS", "ANSWERS")
    assert tuple(alerts.KINDS) == copy["KINDS"]
    assert copy["ANSWERS"] == alerts.ANSWERS
