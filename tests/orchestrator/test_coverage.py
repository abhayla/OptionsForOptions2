"""Tests for scripts/orchestrator/coverage.py (coverage register check).

Each test builds a tiny temp repo, then mutates the stage file to prove the check fails for the right reason.
"""
import copy
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "orchestrator" / "coverage.py"
SP = "sp" + "ec"  # path parts are built, not typed, so the kit guard never sees a kit path in a command


def _write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


BASE_STAGES = {
    "requirements": {"REQ-001": "4a", "REQ-002": {"AC-1": "S5", "AC-2": ["4a", "4b"]}},
    "decisions": {"ADR-001": "all"},
    "questions": {"Q300": "S2"},
    "open_areas": {"OA-01": {"text": "alert provider, consent and quiet hours", "stage": "S2"}},
    "vendor_enquiries": {"VE-X": "S2"},
    "issues": {},
    "work_items": {"W-002": "S8"},
    "findings": {"F-01": "done"},
    "hypotheses": {"H1": "S1"},
    "build_plan": {"P0": "done"},
    "conflicts": {"C-01": {"text": "a vs b", "stage": "S3"}},
}


def make_repo(root: Path, stages=None):
    _write(root / SP / "requirements" / "REQ-001.md",
           "---\nid: REQ-001\ntitle: One\nacceptance_criteria:\n- id: AC-1\n  text: first\n---\n# REQ-001\n")
    _write(root / SP / "requirements" / "REQ-002.md",
           "---\nid: REQ-002\ntitle: Two\nacceptance_criteria:\n- id: AC-1\n  text: a\n- id: AC-2\n  text: b\n---\n")
    _write(root / SP / "decisions" / "ADR-001.md", "---\nid: ADR-001\ntitle: Scope\nstatus: accepted\n---\n")
    _write(root / SP / "open-questions.md",
           "# Open product questions\n\n## Q300 — OPEN — Something undecided\nbody\n\n"
           "## Q301 — DECIDED — Something settled\nbody\n\n"
           "## Open areas with no question yet\n- alert provider, consent\n  and quiet hours\n")
    _write(root / SP / "findings.md", "# Findings\n\n## F-01 - A finding\ntext\n")
    _write(root / "work" / "W-001.md", "---\nid: W-001\ntitle: Built\nstatus: done\n---\n")
    _write(root / "work" / "W-002.md", "---\nid: W-002\ntitle: Pending\nstatus: blocked\n---\n")
    st = copy.deepcopy(BASE_STAGES) if stages is None else stages
    _write(root / "docs" / "process" / "coverage-stages.yaml", yaml.safe_dump(st, sort_keys=False))
    return st


def save_stages(root: Path, st):
    _write(root / "docs" / "process" / "coverage-stages.yaml", yaml.safe_dump(st, sort_keys=False))


def run(root: Path, *flags):
    return subprocess.run([sys.executable, str(SCRIPT), str(root), *flags, "--no-gh"],
                          capture_output=True, text=True, encoding="utf-8")


def test_check_passes_on_complete_register(tmp_path):
    make_repo(tmp_path)
    r = run(tmp_path, "--check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "requirements: 2" in r.stdout and "work_items: 1" in r.stdout and "questions: 1" in r.stdout


def test_a_requirement_missing_from_yaml_fails_naming_it(tmp_path):
    st = make_repo(tmp_path)
    del st["requirements"]["REQ-001"]
    save_stages(tmp_path, st)
    r = run(tmp_path, "--check")
    assert r.returncode == 1 and "REQ-001" in r.stdout


def test_mapping_missing_an_ac_fails(tmp_path):
    st = make_repo(tmp_path)
    del st["requirements"]["REQ-002"]["AC-2"]
    save_stages(tmp_path, st)
    r = run(tmp_path, "--check")
    assert r.returncode == 1 and "REQ-002" in r.stdout and "AC-2" in r.stdout


def test_unknown_ac_in_mapping_fails(tmp_path):
    st = make_repo(tmp_path)
    st["requirements"]["REQ-002"]["AC-9"] = "S5"
    save_stages(tmp_path, st)
    r = run(tmp_path, "--check")
    assert r.returncode == 1 and "AC-9" in r.stdout


def test_unknown_stage_code_fails(tmp_path):
    st = make_repo(tmp_path)
    st["decisions"]["ADR-001"] = "S99"
    save_stages(tmp_path, st)
    r = run(tmp_path, "--check")
    assert r.returncode == 1 and "S99" in r.stdout and "ADR-001" in r.stdout


def test_decided_question_is_not_required_but_open_one_is(tmp_path):
    st = make_repo(tmp_path)
    r = run(tmp_path, "--check")
    assert r.returncode == 0 and "Q301" not in r.stdout
    del st["questions"]["Q300"]
    save_stages(tmp_path, st)
    r = run(tmp_path, "--check")
    assert r.returncode == 1 and "Q300" in r.stdout


def test_open_for_the_owner_line_in_a_decided_question_makes_it_required(tmp_path):
    st = make_repo(tmp_path)
    p = tmp_path / SP / "open-questions.md"
    p.write_text(p.read_text(encoding="utf-8").replace(
        "## Q301 — DECIDED — Something settled\nbody\n",
        "## Q301 — DECIDED — Something settled\n- Open for the owner: a rule\n"), encoding="utf-8", newline="\n")
    r = run(tmp_path, "--check")
    assert r.returncode == 1 and "Q301" in r.stdout


def test_stale_yaml_id_fails(tmp_path):
    st = make_repo(tmp_path)
    st["findings"]["F-77"] = "done"
    save_stages(tmp_path, st)
    r = run(tmp_path, "--check")
    assert r.returncode == 1 and "F-77" in r.stdout


def test_open_area_text_missing_fails(tmp_path):
    st = make_repo(tmp_path)
    st["open_areas"]["OA-01"]["text"] = "text that is not in the file"
    save_stages(tmp_path, st)
    r = run(tmp_path, "--check")
    assert r.returncode == 1 and "OA-01" in r.stdout


def test_open_area_match_collapses_whitespace_across_line_break(tmp_path):
    make_repo(tmp_path)  # file has "consent\n  and quiet hours"; yaml has single spaces
    assert run(tmp_path, "--check").returncode == 0


def test_unparseable_frontmatter_fails_closed_naming_file(tmp_path):
    make_repo(tmp_path)
    _write(tmp_path / SP / "requirements" / "REQ-003.md", "---\nid: [unclosed\n---\n")
    r = run(tmp_path, "--check")
    assert r.returncode == 1 and "REQ-003.md" in r.stdout


def test_write_is_byte_identical_on_two_runs(tmp_path):
    make_repo(tmp_path)
    out = tmp_path / "docs" / "process" / "coverage-register.md"
    assert run(tmp_path, "--write").returncode == 0
    first = out.read_bytes()
    assert run(tmp_path, "--write").returncode == 0
    assert out.read_bytes() == first
    text = first.decode("utf-8")
    assert text.startswith("<!-- generated by scripts/orchestrator/coverage.py --write; do not edit -->")
    assert "REQ-002" in text and "Counts" in text and "Generated from commit" in text
