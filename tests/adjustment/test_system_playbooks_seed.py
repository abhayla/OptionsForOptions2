"""GC-ADJ2 step 1A leftover: the checked-in system playbook seed is exactly what build_system_playbooks.py writes."""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_build_system_playbooks_check_exits_zero():
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_system_playbooks.py"), "--check"],  # noqa: S603
                         cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
    assert run.returncode == 0, run.stdout + run.stderr


SEED = ROOT / "backend" / "ofo" / "adjustment" / "system_playbooks.json"
FIXTURE = ROOT / "tests" / "fixtures" / "adjust_scenarios" / "_playbooks.json"


def _seed_bodies() -> dict:
    return {row["strategy_type"]: row["body"] for row in json.loads(SEED.read_text(encoding="utf-8"))["playbooks"]}


def test_ic_seed_carries_every_adr_216_guard():
    """ADR-216: stop = 50% of max loss or 4% of margin, whichever first; expiry day: close a spread whose short is
    within 0.3% of spot by 14:30; the plan sheet's time exit is 14:30. The mockup's 13:00 tighten rule is OFF."""
    body = _seed_bodies()["ic"]
    g = body["guards"]
    assert (g["profit_target_pct_of_max_profit"], g["stop_line_pct_of_max_loss"], g["stop_line_pct_of_margin"],
            g["stop_line_rule"], g["max_adjustments"], g["time_exit"]) == (
        "50", "50", "4", "whichever comes first", 2, "14:30")
    expiry = [r for r in body["day_rules"] if r["when"] == "expiry"]
    assert [r for r in expiry if r["on"]] == [{"on": True, "when": "expiry", "at": "14:30", "action": 5,
                                               "close_if_short_within_pct": "0.3"}]
    assert [r for r in expiry if not r["on"]] == [{"on": False, "when": "expiry", "at": "13:00", "action": 4,
                                                   "percent": "20"}]


def test_every_other_family_keeps_the_fixture_guards_and_day_rules():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for key, body in _seed_bodies().items():
        if key == "ic":
            continue
        assert body["guards"] == fixture["guards"], key
        assert body["day_rules"] == fixture["day_rules"], key
        assert "stop_line_pct_of_margin" not in body["guards"] and "time_exit" not in body["guards"], key
        assert [r for r in body["day_rules"] if r["when"] == "expiry"] == [
            {"on": True, "when": "expiry", "at": "13:00", "action": 4, "percent": "20"}], key


def test_body_validation_accepts_the_ic_seed_with_its_new_keys():
    """The evaluator's validator (the store's second layer) takes the new guard and day-rule keys unchanged."""
    sys.path.insert(0, str(ROOT / "backend"))
    from ofo.adjustment.playbook_eval import validate_body  # noqa: PLC0415 - needs the backend on the path

    validate_body(_seed_bodies()["ic"])
