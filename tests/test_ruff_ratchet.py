"""The ruff ratchet's comparison logic, without running ruff."""
import importlib.util
import pathlib

_PATH = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "ruff_ratchet.py"
_spec = importlib.util.spec_from_file_location("ruff_ratchet", _PATH)
ratchet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ratchet)

BASE = {"E501": 10, "F401": 3}


def test_counts_are_per_rule_and_a_parse_failure_is_counted():
    rows = [{"code": "E501"}, {"code": "E501"}, {"code": "F401"}, {"code": None}]
    assert ratchet.count_by_rule(rows) == {"E501": 2, "F401": 1, "syntax-error": 1}


def test_a_count_that_rises_fails_and_names_the_rule():
    code, lines, write = ratchet.decide(BASE, {"E501": 11, "F401": 3}, update=False)
    assert code == 1 and not write
    assert "ruff ratchet: E501 rose 10 -> 11" in lines


def test_a_new_rule_is_a_rise_from_zero():
    code, lines, _ = ratchet.decide(BASE, {**BASE, "S101": 1}, update=False)
    assert code == 1 and "ruff ratchet: S101 rose 0 -> 1" in lines


def test_equal_or_falling_counts_pass():
    assert ratchet.decide(BASE, dict(BASE), update=False)[0] == 0
    code, lines, write = ratchet.decide(BASE, {"E501": 9}, update=False)
    assert code == 0 and not write and "ruff ratchet: F401 fell 3 -> 0" in lines


def test_update_refuses_when_a_count_rose_even_if_another_fell():
    code, lines, write = ratchet.decide(BASE, {"E501": 1, "F401": 4}, update=True)
    assert code == 1 and write is False and any("--update refused" in line for line in lines)


def test_it_fails_closed_when_ruff_cannot_be_counted_or_there_is_no_baseline(monkeypatch, tmp_path):
    def broken():
        raise RuntimeError("ruff exited 2")

    monkeypatch.setattr(ratchet, "run_ruff", broken)
    assert ratchet.main([]) == 2
    monkeypatch.setattr(ratchet, "BASELINE", tmp_path / "missing.json")
    assert ratchet.main([]) == 2


def test_update_writes_when_nothing_rose():
    code, _, write = ratchet.decide(BASE, {"E501": 9, "F401": 3}, update=True)
    assert (code, write) == (0, True)


def test_a_failing_ratchet_ends_on_a_fail_line_even_when_other_rules_fell():
    """Finding gate-output-read-by-eye: the LAST line is the verdict; "fell" lines never end a failing run."""
    code, lines, _ = ratchet.decide({"E501": 5, "I001": 9}, {"E501": 6, "I001": 2}, update=False)
    assert code == 1
    assert lines[-1] == "ruff ratchet: FAIL, 1 rule(s) rose: E501"
