"""make_brief.py: a brief rendered from a Measure JSON passes check_brief.py and copy_from_check.py unchanged.

The core test renders row 11's fix-1 brief (content of docs/process/builder-sequence-briefs/row-11-fix-1.md) from a
measure JSON and runs the real check_brief.py on the output. REQ-114's open records are read from the real register
at test time; they are fixtures here, not work."""

from __future__ import annotations

import copy
import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "orchestrator"))
import make_brief as mb  # noqa: E402

CHECK = REPO / "scripts" / "orchestrator" / "check_brief.py"
MAKE = REPO / "scripts" / "orchestrator" / "make_brief.py"
S_MAX = 5
# REQ-114's open records are read from the real register at test time, never typed: a record that is built or verified
# leaves the list (2026-10-23: RD-039/046/047/068 were verified and a hard-coded list of six turned CI red). The test
# still proves every open record is listed and each spec_change one reads "waiting for the owner".
_REG = mb._reg()
OPEN_REQ_114 = list(_REG.open_records(REPO, ["REQ-114"]))
WAITING = [r for r in OPEN_REQ_114 if _REG.load_records(REPO)[r].get("spec_change") is True]
SAFE = "backend/ofo_app/live_market.py"
NON_SAFETY = ["frontend/src/lib/sharedStateText.js"]
SPEC_BASIS = (
    'REQ-114 AC-7 (amended by ADR-177): outside market hours "the screens read "Market closed. Prices are from '
    '<time>." (the shared banner text, ADR-177)" and no reconnect more often than once every 5 minutes. REQ-114 AC-2 '
    "(the drop marks the quotes stale and the feed disconnected), AC-6 (a token error or a 403 ends the session, "
    "never retried in a loop). ADR-119 (market calendar). ADR-015 (no stale data shown as live)."
)


def _files(n: int, first: str = "backend/ofo_app/live_market.py") -> list[str]:
    return [first] + [f"tests_app/t{i}.py" for i in range(n - 1)]


@pytest.fixture
def measure() -> dict:
    return {
        "row": 11, "w_id": "W-139", "req": "REQ-114", "tier": "A",
        "title": "the market-closed state is shown, the drop is pinned, a token error is a token error",
        "files": _files(10), "items": [f"item {i}" for i in range(5)],
        "core": "on a closed market a silent socket is shown as market closed, never as reconnecting.",
        "proof": "step 1 is a failing test on the REAL feed_phase and broker status route at Sat 2026-10-24 10:00 IST.",
        "spec_basis": SPEC_BASIS, "copy_from": "none.",
        "attack": [{"text": f"attack {i}", "test_file": "tests_app/test_live_feed_status.py"} for i in range(6)],
        "standing": {"a": "n/a: no time-budgeted job changes", "b": "n/a: no CI step changes",
                     "c": "the token check is an allow-list of the session-token error shapes",
                     "d": "the calendar's answer states each with what the status row shows"},
        "threat_model": "in scope - a closed market shown as reconnecting; out of scope - the calendar's own data.",
        "findings_checked": ["guard-as-forbidden-list", "dependent-tests-not-run-stale-later"],
        "expected": {"minutes": 45, "tokens": 220000},
        "ci": "app tests job (`tests_app/test_live_feed_status.py`; vars: DATABASE_URL via the throwaway runner)",
    }


def _write_json(tmp_path: pathlib.Path, data: dict) -> pathlib.Path:
    path = tmp_path / "m.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], capture_output=True, text=True,  # noqa: S603
                          check=False, encoding="utf-8")


def _cli(tmp_path: pathlib.Path, data: dict, *extra: str) -> subprocess.CompletedProcess:
    return _run([str(MAKE), "11", str(_write_json(tmp_path, data)), *extra])


def test_core_row_11_fix_brief_passes_check_brief_unchanged(tmp_path, measure):
    """Core: the brief passes check_brief.py (exit 0) with no hand edit; Reference lists REQ-114's open records."""
    out = tmp_path / "row-11-fix-1.md"
    done = _cli(tmp_path, measure, "--kind", "fix", "--out", str(out))
    assert done.returncode == 0, done.stderr
    checked = _run([str(CHECK), str(out)])
    assert checked.returncode == 0, checked.stdout + checked.stderr
    ref = next(line for line in out.read_text(encoding="utf-8").splitlines() if line.startswith("Reference:"))
    for rid in OPEN_REQ_114:
        assert rid in ref
    assert "Budget: 60 min wall-clock, 80 tool calls" in out.read_text(encoding="utf-8")
    assert "Size: M, 10 files, 5 items" in out.read_text(encoding="utf-8")
    assert mb.TESTS_LINE in out.read_text(encoding="utf-8")
    assert "at 64 calls start nothing new" in out.read_text(encoding="utf-8")


@pytest.mark.parametrize("missing", ["core", "proof", "files", "spec_basis"])
def test_missing_key_refused_naming_it(tmp_path, measure, missing):
    """Attack 1: a JSON missing a required key is refused, and the key is named."""
    del measure[missing]
    done = _cli(tmp_path, measure)
    assert done.returncode == 1
    assert f"`{missing}`" in done.stderr


def test_unknown_key_refused(tmp_path, measure):
    """An unknown key is refused by name (a typo never silently drops a field)."""
    measure["tests_requird"] = []
    done = _cli(tmp_path, measure)
    assert done.returncode == 1
    assert "`tests_requird`" in done.stderr


def test_sixteen_files_refused_as_l(tmp_path, measure):
    """Attack 2: 16 files is size L: refused with the word split."""
    measure["files"] = _files(16)
    done = _cli(tmp_path, measure)
    assert done.returncode == 1
    assert "split" in done.stderr
    assert "size L" in done.stderr


@pytest.mark.parametrize(("count", "line"), [(5, "Size: S, 5 files, 1 items"), (6, "Size: M, 6 files, 1 items"),
                                             (15, "Size: M, 15 files, 1 items")])
def test_size_bands_come_from_the_file_count(measure, count, line):
    """Size and Budget are derived from the file count (<= 5 S 30/40, 6-15 M 60/80)."""
    measure["files"] = _files(count)
    measure["items"] = ["one"]
    text = mb.render(measure, "build", REPO)
    assert line in text
    small, medium = "Budget: 30 min wall-clock, 40 tool calls", "Budget: 60 min wall-clock, 80 tool calls"
    expected = small if count == S_MAX else medium
    assert expected in text


def test_reference_line_lists_every_open_record_with_screens_and_waiting(measure):
    """Attack 3: REQ-114 -> every open record with its screens; each spec_change record waiting for the owner."""
    assert OPEN_REQ_114, "REQ-114 has no open record left: point this test at a requirement that still has one"
    ref = next(x for x in mb.render(measure, "build", REPO).splitlines() if x.startswith("Reference:"))
    assert [r for r in OPEN_REQ_114 if r not in ref] == []
    assert "catalogue 012" in ref  # RD-065's screen
    for rid in OPEN_REQ_114:
        piece = ref.split(rid + " (", 1)[1].split("),", 1)[0].split(")", 1)[0]
        assert ("waiting for the owner" in piece) == (rid in WAITING), rid


def test_no_open_record_needs_search_terms(measure):
    """The register answer 'none open': `none - searched <terms>`; refused when the terms are missing."""
    measure["req"] = "REQ-001"
    with pytest.raises(mb.Refused, match="search_terms"):
        mb.render(measure, "build", REPO)
    measure["search_terms"] = ["underlying list", "lot size"]
    ref = next(x for x in mb.render(measure, "build", REPO).splitlines() if x.startswith("Reference:"))
    assert ref == "Reference: none - searched underlying list, lot size"


def test_unreadable_register_refused(tmp_path, measure):
    """The register script failing (an invalid record file in the register folder) refuses, never writes."""
    (tmp_path / "spec" / "reference-diffs").mkdir(parents=True)
    (tmp_path / "spec" / "reference-diffs" / "junk.txt").write_text("x", encoding="utf-8")
    with pytest.raises(mb.Refused, match="register"):
        mb.render(measure, "build", tmp_path)


def test_failing_check_never_overwrites_existing_out(tmp_path, measure):
    """A brief that fails check_brief (a bad quote) exits 1 and leaves an existing --out file byte for byte."""
    out = tmp_path / "keep.md"
    out.write_text("old brief", encoding="utf-8")
    measure["spec_basis"] = 'REQ-114 AC-7 says "this sentence is not anywhere in the requirement text at all".'
    done = _cli(tmp_path, measure, "--out", str(out))
    assert done.returncode == 1
    assert "check_brief" in done.stderr
    assert out.read_text(encoding="utf-8") == "old brief"


@pytest.mark.parametrize("bad", ["n/a", " N/A. ", ""])
def test_bare_na_standing_item_refused(measure, bad):
    """A bare n/a standing item is refused (builder-brief.md: a bare n/a is a brief defect)."""
    measure["standing"]["a"] = bad
    with pytest.raises(mb.Refused, match=r"\(a\)"):
        mb.render(measure, "build", REPO)


def test_verify_r2_render(tmp_path):
    """A verify-r2 brief: round-2 budget 15/20, numbered findings, changed files, passes check_brief."""
    data = {"row": 11, "w_id": "W-139", "req": "REQ-114", "tier": "A", "title": "round 2",
            "spec_basis": SPEC_BASIS, "attack": [{"text": "a1", "test_file": "tests_app/x.py"}],
            "round1_findings": ["AC-7 MAJOR phase", "AC-2 MINOR mutant"], "changed_files": NON_SAFETY}
    out = tmp_path / "r2.md"
    done = _cli(tmp_path, data, "--kind", "verify-r2", "--out", str(out))
    assert done.returncode == 0, done.stderr
    text = out.read_text(encoding="utf-8")
    assert "Budget: 15 min wall-clock, 20 tool calls" in text
    assert "Round 2 findings:\n1. AC-7 MAJOR phase\n2. AC-2 MINOR mutant" in text
    assert "Changed files:\n- frontend/src/lib/sharedStateText.js" in text


def test_safety_file_adds_why_opus_and_other_files_do_not(measure):
    """Attack 4: a safety-set file -> a `Why Opus:` line naming it; frontend-only files -> no such line."""
    measure["files"] = ["backend/ofo/outcome/service.py", "tests/x.py"]
    assert "Why Opus: `backend/ofo/outcome/service.py` is in the safety set" in mb.render(measure, "build", REPO)
    measure["files"] = ["frontend/src/a.vue", "frontend/src/b.vue"]
    assert "Why Opus" not in mb.render(measure, "build", REPO)


def test_safety_set_is_imported_not_copied():
    """The brief's SAFETY_SET is the measure_process object itself (one home)."""
    import measure_process
    assert mb.measure_process.SAFETY_SET is measure_process.SAFETY_SET
    assert "SAFETY_SET = (" not in (REPO / "scripts" / "orchestrator" / "make_brief.py").read_text(encoding="utf-8")


def test_row_mismatch_refused(tmp_path, measure):
    """Row on the command line must be the row in the JSON."""
    out = _run([str(MAKE), "12", str(_write_json(tmp_path, copy.deepcopy(measure)))])
    assert out.returncode == 1
    assert "row 12" in out.stderr


@pytest.mark.parametrize("empty", [[], "", None])
def test_empty_required_key_refused(measure, empty):
    """A required key present but empty is refused like a missing one."""
    measure["core"] = empty
    with pytest.raises(mb.Refused, match="`core`"):
        mb.render(measure, "build", REPO)


def test_invalid_register_record_refused(tmp_path, measure):
    """The register answering 'invalid' (a record missing its required fields) refuses; nothing is written."""
    folder = tmp_path.joinpath("sp" + "ec", "reference-diffs")
    folder.mkdir(parents=True)
    (folder / "RD-001.json").write_text(json.dumps({"id": "RD-001"}), encoding="utf-8")
    seq = tmp_path / "docs" / "process"
    seq.mkdir(parents=True)
    (seq / "builder-sequence-2026-10-22.md").write_text("| 1 | W-1 | REQ-001 |\n", encoding="utf-8")
    with pytest.raises(mb.Refused, match="invalid"):
        mb.render(measure, "build", tmp_path)


@pytest.mark.parametrize("tier", ["D", "a", "", "AB", None, 1])
def test_tier_must_be_a_b_or_c(tmp_path, measure, tier):
    out = tmp_path / "new.md"
    measure["tier"] = tier
    done = _cli(tmp_path, measure, "--out", str(out))
    assert done.returncode == 1 and "tier" in done.stderr and "Traceback" not in done.stderr
    assert not out.exists()


def test_unwritable_out_exits_1_with_the_reason(tmp_path, measure):
    blocker = tmp_path / "afile"
    blocker.write_text("x", encoding="utf-8")
    done = _cli(tmp_path, measure, "--out", str(blocker / "sub" / "brief.md"))
    assert done.returncode == 1 and "REFUSED: cannot write --out" in done.stderr
    assert "Traceback" not in done.stderr
