"""Gate equivalence harness (lane G): parse the gate's output, compare old vs new per step, run seeds serially.

No wall-clock asserts: seconds are copied through, never compared. `run` takes an injected runner, so no real gate runs.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "orchestrator"))
import gate_equivalence as ge

SHA = "a" * 40

# the exact print formats of scripts/orchestrator/prepush.py
RED_PREFLIGHT = """\
ci_checks: pytest steps removed from the workflow copy: none
FAIL preflight 12.5s /tmp/prepush-x/preflight.log
STOP: preflight failed; the long steps were not run (fix it, commit, run again)
TOTAL FAIL 12.5s marker not written (failed: preflight)
"""
GREEN = """\
PASS preflight 1.2s /tmp/p/preflight.log
PASS ci_checks 2.0s /tmp/p/ci_checks.log
PASS domain_tests 3.1s /tmp/p/domain_tests.log
TOTAL PASS 6.3s marker /repo/.git/ofo-prepush/aaaa.json
"""
MIXED = """\
PASS preflight 1.0s /l/preflight.log
FAIL domain_tests 3.0s /l/domain_tests.log
PASS ruff_ratchet 0.5s /l/ruff_ratchet.log
TOTAL FAIL 4.5s marker not written (failed: domain_tests)
"""


def rec(steps, total, marker, expect_red=(), skips=None, stops=()):  # noqa: PLR0913
    return {"steps": dict(steps), "total": total, "marker": marker, "seconds": 1.0, "raw_path": "x",
            "expect_red": list(expect_red), "skip_reasons": skips or {}, "stops": list(stops)}


def compare_one(old, new, allow=()):
    rows, problems = ge.compare_seed("s", old, new, allow)
    return rows, problems


def kinds(problems):
    return sorted(p[0] for p in problems)


# ---- parse ----

def test_parse_red_preflight_stop():
    got = ge.parse_gate_output(RED_PREFLIGHT)
    assert got["steps"] == {"preflight": "FAIL"}
    assert got["total"] == "FAIL"
    assert got["stops"] == ["STOP: preflight failed; the long steps were not run (fix it, commit, run again)"]


def test_parse_green_and_marker_note():
    got = ge.parse_gate_output(GREEN)
    assert got["steps"] == {"preflight": "PASS", "ci_checks": "PASS", "domain_tests": "PASS"}
    assert got["total"] == "PASS"
    assert got["total_note"].startswith("marker ")


def test_parse_mixed_keeps_run_order():
    got = ge.parse_gate_output(MIXED)
    assert list(got["steps"]) == ["preflight", "domain_tests", "ruff_ratchet"]
    assert got["steps"]["domain_tests"] == "FAIL"


def test_parse_future_skip_and_stop_forms():
    text = ("SKIP frontend_unit docs-only change\nPASS preflight 1.0s /l\nSTOP cheap checks red\n"
            "TOTAL PASS 1.0s marker m\n")
    got = ge.parse_gate_output(text)
    assert got["steps"] == {"frontend_unit": "SKIP", "preflight": "PASS"}
    assert got["skip_reasons"] == {"frontend_unit": "docs-only change"}
    assert got["stops"] == ["STOP cheap checks red"]


def test_parse_no_total_line_is_none():
    assert ge.parse_gate_output("PASS preflight 1.0s /l\n")["total"] is None


# ---- compare: every mismatch kind ----

def test_equal_runs_have_no_problems():
    old = rec({"preflight": "PASS", "domain_tests": "FAIL"}, "FAIL", False, ["domain_tests"])
    assert compare_one(old, dict(old))[1] == []


def test_kind_i_verdict_differs():
    old = rec({"domain_tests": "FAIL"}, "FAIL", False, ["domain_tests"])
    new = rec({"domain_tests": "PASS"}, "FAIL", False)
    assert "VERDICT" in kinds(compare_one(old, new)[1])


def test_kind_ii_total_differs():
    old = rec({"preflight": "PASS"}, "PASS", True)
    new = rec({"preflight": "PASS"}, "FAIL", True)
    assert kinds(compare_one(old, new)[1]) == ["TOTAL"]


def test_kind_iii_marker_differs_old_wrote_new_did_not():
    old = rec({"preflight": "PASS"}, "PASS", True)
    new = rec({"preflight": "PASS"}, "PASS", False)
    assert kinds(compare_one(old, new)[1]) == ["MARKER"]


def test_kind_iv_step_missing_in_new():
    old = rec({"preflight": "PASS", "app_tests": "PASS"}, "PASS", True)
    new = rec({"preflight": "PASS"}, "PASS", True)
    assert kinds(compare_one(old, new)[1]) == ["MISSING"]


def test_kind_iv_explicit_skip_needs_an_allowed_reason():
    old = rec({"preflight": "PASS", "frontend_unit": "PASS"}, "PASS", True)
    new = rec({"preflight": "PASS", "frontend_unit": "SKIP"}, "PASS", True, skips={"frontend_unit": "docs-only lane"})
    assert kinds(compare_one(old, new)[1]) == ["SKIP-NOT-ALLOWED"]
    rows, problems = compare_one(old, new, allow=[r"docs-only"])
    assert problems == []
    assert next(r for r in rows if r["step"] == "frontend_unit")["new"] == "SKIP"


def test_kind_v_new_writes_marker_old_did_not_is_fatal_and_loud():
    old = rec({"preflight": "FAIL"}, "FAIL", False)
    new = rec({"preflight": "FAIL"}, "FAIL", True)
    got = compare_one(old, new)[1]
    assert "MARKER-NEW" in kinds(got)
    assert any("FATAL" in p[1] for p in got if p[0] == "MARKER-NEW")


def test_new_only_step_is_not_a_mismatch():
    old = rec({"preflight": "FAIL"}, "FAIL", False, ["preflight"], stops=["STOP: x"])
    new = rec({"preflight": "FAIL", "domain_tests": "PASS"}, "FAIL", False)
    rows, problems = compare_one(old, new)
    assert problems == []
    assert next(r for r in rows if r["step"] == "domain_tests")["status"] == "new-only"


# ---- seed validity ----

def test_seed_invalid_when_expected_red_step_is_green_in_old():
    old = rec({"preflight": "PASS", "ruff_ratchet": "PASS"}, "PASS", True, ["ruff_ratchet"])
    assert "SEED-INVALID" in kinds(compare_one(old, dict(old))[1])


def test_seed_valid_when_preflight_red_hides_a_later_expected_step():
    old = rec({"preflight": "FAIL"}, "FAIL", False, ["preflight", "ruff_ratchet"])
    assert compare_one(old, dict(old))[1] == []


def test_seed_invalid_when_clean_seed_is_not_green_with_marker():
    old = rec({"preflight": "PASS"}, "FAIL", False, [])
    assert "SEED-INVALID" in kinds(compare_one(old, dict(old))[1])


def test_compare_files_exit_code_and_markdown(tmp_path, capsys):
    good = {"label": "old", "seeds": {"s": rec({"domain_tests": "FAIL"}, "FAIL", False, ["domain_tests"])}}
    bad = {"label": "new", "seeds": {"s": rec({"domain_tests": "PASS"}, "FAIL", False)}}
    (tmp_path / "o.json").write_text(json.dumps(good))
    (tmp_path / "n.json").write_text(json.dumps(bad))
    (tmp_path / "n2.json").write_text(json.dumps({"label": "new", "seeds": good["seeds"]}))
    assert ge.main(["compare", str(tmp_path / "o.json"), str(tmp_path / "n2.json")]) == 0
    assert ge.main(["compare", str(tmp_path / "o.json"), str(tmp_path / "n.json")]) == 1
    out = capsys.readouterr().out
    assert "| seed | step | old | new | status |" in out
    assert "MISMATCH" in out


def test_compare_missing_seed_in_new_is_a_mismatch(tmp_path):
    old = {"label": "old", "seeds": {"s": rec({"preflight": "PASS"}, "PASS", True)}}
    (tmp_path / "o.json").write_text(json.dumps(old))
    (tmp_path / "n.json").write_text(json.dumps({"label": "new", "seeds": {}}))
    assert ge.main(["compare", str(tmp_path / "o.json"), str(tmp_path / "n.json")]) == 1


# ---- run with an injected runner ----

class FakeRunner:
    """Answers every command; gate commands print scripted output and may write a marker file."""

    def __init__(self, common_dir, outputs):
        self.common_dir, self.outputs, self.calls, self.current = common_dir, outputs, [], None

    def __call__(self, cmd, cwd, timeout=None):
        self.calls.append((list(cmd), cwd))
        if cmd[:2] == ["git", "rev-parse"] and "--git-common-dir" in cmd:
            return 0, self.common_dir
        if cmd[:2] == ["git", "checkout"]:
            self.current = cmd[-1]
            return 0, ""
        if cmd[0] == "git":
            return 0, ""
        if cmd[0] == "gate.py" or (len(cmd) > 1 and cmd[1] == "gate.py"):
            text, marker = self.outputs[self.current]
            if marker:
                os.makedirs(os.path.join(self.common_dir, ge.MARKER_DIR), exist_ok=True)
                pathlib.Path(self.common_dir, ge.MARKER_DIR, f"{self.current}.json").write_text("{}")
            return 0 if marker else 1, text
        return 0, ""


def manifest_for(tmp_path, seeds):
    path = tmp_path / "m.json"
    path.write_text(json.dumps(seeds))
    return str(path)


def test_run_records_per_seed_results_and_clears_stale_marker(tmp_path):
    common = tmp_path / "common"
    (common / ge.MARKER_DIR).mkdir(parents=True)
    (common / ge.MARKER_DIR / f"{SHA}.json").write_text("{}")  # stale marker for the seed sha: must be deleted first
    sha2 = "b" * 40
    manifest = manifest_for(tmp_path, [
        {"name": "clean", "sha": SHA, "base": "0" * 40, "expect_red": [], "note": ""},
        {"name": "red", "sha": sha2, "base": "0" * 40, "expect_red": ["domain_tests"], "note": ""}])
    runner = FakeRunner(str(common), {SHA: (GREEN, False), sha2: (MIXED, False)})  # the gate writes no marker for clean
    out = tmp_path / "out" / "old.json"
    wt = tmp_path / "wt"
    (wt / "frontend" / "node_modules").mkdir(parents=True)
    rc = ge.main(["run", "--gate", "gate.py", "--manifest", manifest, "--label", "old", "--out", str(out),
                  "--worktree", str(wt), "--extra-args=--full"], runner=runner)
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["label"] == "old"
    assert data["seeds"]["clean"]["marker"] is False  # stale one was deleted before the run; the fake wrote none
    assert data["seeds"]["clean"]["steps"]["domain_tests"] == "PASS"
    assert data["seeds"]["red"]["steps"]["domain_tests"] == "FAIL"
    assert data["seeds"]["red"]["expect_red"] == ["domain_tests"]
    assert os.path.isfile(data["seeds"]["red"]["raw_path"])
    gate_calls = [c for c, _ in runner.calls if "gate.py" in c]
    assert len(gate_calls) == len(data["seeds"])
    assert gate_calls[0][gate_calls[0].index("--repo") + 1] == str(wt) and "--full" in gate_calls[0]
    assert not (common / ge.MARKER_DIR / f"{SHA}.json").exists()


def test_run_marker_present_after_gate_writes_it_and_only_filters(tmp_path):
    common = tmp_path / "common"
    manifest = manifest_for(tmp_path, [
        {"name": "a", "sha": SHA, "base": "0" * 40, "expect_red": [], "note": ""},
        {"name": "b", "sha": "b" * 40, "base": "0" * 40, "expect_red": [], "note": ""}])
    runner = FakeRunner(str(common), {SHA: (GREEN, True)})
    out = tmp_path / "new.json"
    wt = tmp_path / "wt"
    (wt / "frontend" / "node_modules").mkdir(parents=True)
    ge.main(["run", "--gate", "gate.py", "--manifest", manifest, "--label", "new", "--out", str(out),
             "--worktree", str(wt), "--only", "a"], runner=runner)
    data = json.loads(out.read_text())
    assert list(data["seeds"]) == ["a"]
    assert data["seeds"]["a"]["marker"] is True


# ---- seeds table ----

def test_seed_table_names_and_expectations():
    names = [s.name for s in ge.SEEDS]
    assert names == ["clean_code", "ruff", "coverage", "money_scan", "domain_fail", "app_fail", "vitest_fail",
                     "lint_fail", "alembic_heads", "docs_clean", "docs_spec_break"]
    by = {s.name: s for s in ge.SEEDS}
    assert by["clean_code"].expect_red == [] and by["docs_clean"].expect_red == []
    assert "ruff_ratchet" in by["ruff"].expect_red and "preflight" in by["ruff"].expect_red
    assert by["domain_fail"].expect_red == ["domain_tests"]
    assert by["vitest_fail"].expect_red == ["frontend_unit"]
    assert by["lint_fail"].expect_red == ["frontend_lint"]
    assert by["alembic_heads"].expect_red[-1] == "alembic_guard"
    assert by["app_fail"].expect_red == ["app_tests"]


def _seed_free_bytes(root, rel, marker):
    """Bytes to start a scratch copy of rel from. If the working file already carries this seed's marker (the tree
    holds a seed), use the committed blob instead; None when there is no seed-free base (file absent or new)."""
    path = root / rel
    if not path.exists():
        return None
    data = path.read_bytes()
    if marker.encode() not in data:
        return data
    out = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{rel}"],  # noqa: S603, S607 - fixed git argv
                         capture_output=True, check=False)
    return out.stdout if out.returncode == 0 else None


def _copy_seed_touches(root, scratch, seed):
    """Copy the seed's touched files from root into scratch, starting each from a seed-free base."""
    marker = ge.SEED_MARKERS[seed.name]
    for rel in seed.touches:
        data = _seed_free_bytes(root, rel, marker)
        if data is not None:
            (scratch / rel).parent.mkdir(parents=True, exist_ok=True)
            (scratch / rel).write_bytes(data)


def _state(scratch, seed):
    return {rel: (scratch / rel).read_bytes() if (scratch / rel).exists() else None for rel in seed.touches}


def test_mutations_edit_a_copy_of_the_tree(tmp_path):
    """Every mutate function must change at least one existing-tree-relative file under a scratch root that mirrors
    the real layout (here: the real repo files copied)."""
    root = pathlib.Path(__file__).resolve().parents[2]
    for seed in ge.SEEDS:
        scratch = tmp_path / seed.name
        _copy_seed_touches(root, scratch, seed)
        before = _state(scratch, seed)
        seed.mutate(scratch)
        assert before != _state(scratch, seed), seed.name


def test_mutation_is_visible_when_the_tree_already_carries_the_seed(tmp_path):
    """A working tree that already holds a seed (e.g. the lint_fail seed commit) must not make the copy-and-mutate
    check fail: the scratch copy starts seed-free, so the mutation still changes it."""
    seed = next(s for s in ge.SEEDS if s.name == "lint_fail")
    tree = tmp_path / "tree"
    seed.mutate(tree)  # the tree now carries the seed file
    scratch = tmp_path / "scratch"
    _copy_seed_touches(tree, scratch, seed)
    before = _state(scratch, seed)
    seed.mutate(scratch)
    assert before != _state(scratch, seed), seed.name
