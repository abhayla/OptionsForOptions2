"""REQ-071: the adjustment metric registry holds the 30 reference-video values exactly as the spec table
lists them, and refuses a calculator for any value whose feasibility is not ``pass``.

The expected rows are PARSED from ``spec/technical-design/adjustment-data-contract.md`` (never retyped), so the
registry and the spec cannot drift apart silently.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ofo.adjustment.registry import (
    DATA_FILE,
    FeasibilityError,
    MetricRegistry,
    RegistryError,
    load_rows,
)

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "spec" / "technical-design" / "adjustment-data-contract.md"
VALID = {"pass", "fail", "unknown", "unclear"}


def _spec_rows() -> list[dict]:
    rows = []
    for line in SPEC.read_text(encoding="utf-8").splitlines():
        if not re.match(r"\| \d+ \|", line):
            continue
        c = [x.strip() for x in line.strip().strip("|").split(" | ")]
        assert len(c) == 8, line[:40]
        rows.append({"id": int(c[0]), "name": c[1], "source": c[4], "frequency": c[5],
                     "calculation": c[6], "feasibility_note": c[7]})
    return rows


def _fake(_inputs):  # a stand-in calculator; real ones are a later work item
    return None


def test_ac1_all_30_rows_match_the_spec_table():
    """AC-1: every registry row equals the spec row (id, value, source, frequency, calculation, feasibility)."""
    spec = _spec_rows()
    reg = MetricRegistry().rows
    assert [r["id"] for r in spec] == list(range(1, 31))
    assert [r.id for r in reg] == list(range(1, 31))
    for s, r in zip(spec, reg):
        assert r.name == s["name"], s["id"]
        assert r.source == s["source"], s["id"]
        assert r.frequency == s["frequency"], s["id"]
        assert r.calculation == s["calculation"], s["id"]
        assert r.feasibility_note == s["feasibility_note"], s["id"]
        assert r.feasibility in VALID
        # normalised value = the first word of the spec's feasibility cell
        assert r.feasibility == s["feasibility_note"].split()[0].rstrip(";,"), s["id"]


def test_ac1_known_feasibility_and_owner_readings():
    """AC-1: hand-read spec verdicts, Q246 readings on rows 10/26/28, rows 24-25 out of V1."""
    reg = MetricRegistry()
    expected = {23: "fail", 20: "unknown", 19: "unknown", 12: "unclear", 13: "unclear",
                3: "pass", 4: "pass", 8: "pass", 10: "pass", 28: "pass", 26: "pass", 24: "unknown", 25: "unknown"}
    for i, f in expected.items():
        assert reg.get(i).feasibility == f, i
    for i in (10, 26, 28):
        assert "Q246" in reg.get(i).owner_reading
    for i in (4, 26):
        assert "Q248" in reg.get(i).owner_reading
    for i in (24, 25):
        assert reg.get(i).out_of_v1 and reg.get(i).feasibility != "pass"
    assert [r.id for r in reg.rows if r.out_of_v1] == [24, 25]
    assert reg.get(1).owner_reading == ""


def test_ac2_pass_row_accepts_a_calculator():
    """AC-2: a calculator registers for a feasible (pass) value and is retrievable."""
    reg = MetricRegistry()
    reg.register_calculator(3, _fake)
    assert reg.calculator(3) is _fake
    assert reg.registered_ids() == [3]


@pytest.mark.parametrize("metric_id,feas", [(23, "fail"), (20, "unknown"), (12, "unclear"), (24, "unknown")])
def test_ac2_non_pass_rows_are_refused(metric_id, feas):
    """AC-2: row 23 (fail), 20 (unknown), 12 (unclear), 24 (out of V1) raise and register nothing."""
    reg = MetricRegistry()
    assert reg.get(metric_id).feasibility == feas
    with pytest.raises(FeasibilityError):
        reg.register_calculator(metric_id, _fake)
    assert reg.registered_ids() == []
    with pytest.raises(RegistryError):
        reg.calculator(metric_id)


def test_ac2_every_non_pass_row_is_refused_and_every_pass_row_accepted():
    """AC-2: across all 30 rows, exactly the spec's ``pass`` rows accept a calculator."""
    reg = MetricRegistry()
    for r in reg.rows:
        if r.feasibility == "pass":
            reg.register_calculator(r.id, _fake)
        else:
            with pytest.raises(FeasibilityError):
                reg.register_calculator(r.id, _fake)
    assert reg.registered_ids() == [r.id for r in reg.rows if r.feasibility == "pass"]


def test_ac2_bad_registrations_fail_closed():
    """AC-2: unknown id, duplicate registration and a non-callable are rejected."""
    reg = MetricRegistry()
    with pytest.raises(RegistryError):
        reg.register_calculator(31, _fake)
    with pytest.raises(RegistryError):
        reg.register_calculator(True, _fake)  # bool is not an id
    with pytest.raises(RegistryError):
        reg.register_calculator(3, "not callable")
    reg.register_calculator(3, _fake)
    with pytest.raises(RegistryError):
        reg.register_calculator(3, _fake)


def test_ac2_feasibility_cannot_be_forged_by_the_caller():
    """AC-2: mutating a returned row or the rows list does not make a refused value registrable."""
    reg = MetricRegistry()
    with pytest.raises(Exception):
        reg.get(23).feasibility = "pass"  # frozen dataclass
    assert isinstance(reg.rows, tuple)
    with pytest.raises(FeasibilityError):
        reg.register_calculator(23, _fake)


def test_ac1_data_file_rejects_drift(tmp_path):
    """AC-1: a data file with a wrong feasibility word, unknown key, missing row or duplicate id is refused."""
    good = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    def write(rows):
        p = tmp_path / "r.json"
        p.write_text(json.dumps(rows), encoding="utf-8")
        return p

    bad_word = [dict(r) for r in good]
    bad_word[0]["feasibility"] = "passed"
    with pytest.raises(RegistryError):
        load_rows(write(bad_word))
    extra = [dict(r) for r in good]
    extra[0]["feasability"] = "pass"
    with pytest.raises(RegistryError):
        load_rows(write(extra))
    with pytest.raises(RegistryError):
        load_rows(write(good[:-1]))
    dup = [dict(r) for r in good]
    dup[1]["id"] = 1
    with pytest.raises(RegistryError):
        load_rows(write(dup))
    oov = [dict(r) for r in good]
    oov[23]["feasibility"] = "pass"  # row 24 is out of V1 (Q246) and can never be pass
    with pytest.raises(RegistryError):
        load_rows(write(oov))
    assert len(load_rows(write(good))) == 30


def test_ac2_rows_4_26_28_accept_a_calculator():
    """AC-2: owner decisions Q248 (rows 4, 26) and Q246 (row 28) made these feasible; each accepts a calculator."""
    reg = MetricRegistry()
    for i in (4, 26, 28):
        assert reg.get(i).feasibility == "pass", i
        reg.register_calculator(i, _fake)
        assert reg.calculator(i) is _fake
    assert reg.registered_ids() == [4, 26, 28]


def test_ac1_data_file_refuses_a_boolean_id(tmp_path):
    """AC-1: True == 1 in Python, so a row id of true must be refused, not accepted as row 1."""
    rows = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    rows[0]["id"] = True
    p = tmp_path / "r.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(RegistryError):
        load_rows(p)
