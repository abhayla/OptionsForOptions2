"""Tests for scripts/orchestrator/tracker_check.py, run with --offline fixtures (no gh, no git).

Each test plants one failure in an otherwise clean tracker and asserts exit 1 naming the row.
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "orchestrator" / "tracker_check.py"
HEADER = "| Id | Item | P | Contract | Tier | Status | Evidence |\n|---|---|---|---|---|---|---|\n"
CLEAN_ROWS = {
    "#10": ("GC-2h", "todo"),
    "#11": ("GC-3F", "held #50"),
    "#12": ("GC-3F", "merged #51"),
    "#13": ("GC-2h", "closed"),
    "#14": ("GC-3G", "parked #14"),
    "#15": ("GC-3G", "deferred #15"),
    "OQ-1": ("owner", "blocked-owner"),
    "S5-1": ("stage-5", "todo"),
}
GH_ISSUES = [{"number": 10, "state": "OPEN"}, {"number": 11, "state": "OPEN"}, {"number": 12, "state": "OPEN"},
             {"number": 13, "state": "CLOSED"}, {"number": 14, "state": "OPEN"}, {"number": 15, "state": "OPEN"}]
EXIT_CANNOT_CHECK = 2
CLOSED_ROW = 13
TODO_ROW = 10
GH_PRS = [{"number": 50, "state": "OPEN"}, {"number": 51, "state": "MERGED"}]


def table(rows):
    body = "".join(f"| {rid} | item | P1 | {c} | A | {s} | |\n" for rid, (c, s) in rows.items())
    return "# Tracker\n\n" + HEADER + body


def exec_script(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],  # noqa: S603
                          capture_output=True, text=True, encoding="utf-8", check=False)


def run(tmp_path, rows=None, base_rows=None, raw=None, **gh):
    """rows/raw set the tracker; base_rows the origin/main copy; gh: issues=/prs= the GitHub answer."""
    issues, prs = gh.get("issues"), gh.get("prs")
    tracker = tmp_path / "docs" / "process" / "build-ahead-tracker.md"
    tracker.parent.mkdir(parents=True, exist_ok=True)
    tracker.write_text(raw if raw is not None else table(rows if rows is not None else CLEAN_ROWS),
                       encoding="utf-8", newline="\n")
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps({"base": table(base_rows if base_rows is not None else CLEAN_ROWS),
                                   "issues": GH_ISSUES if issues is None else issues,
                                   "prs": GH_PRS if prs is None else prs}), encoding="utf-8")
    r = exec_script(tmp_path, "--offline", fixture)
    return r.returncode, r.stdout


def with_row(rid, contract, status):
    rows = dict(CLEAN_ROWS)
    rows[rid] = (contract, status)
    return rows


def test_clean_fixture_exits_0(tmp_path):
    assert run(tmp_path) == (0, "OK\n")


def test_deleted_row_names_the_id(tmp_path):
    rows = {k: v for k, v in CLEAN_ROWS.items() if k != "OQ-1"}
    code, out = run(tmp_path, rows=rows)
    assert code == 1
    assert out.startswith("OQ-1: row deleted")


def test_status_off_the_closed_list_fails(tmp_path):
    for bad in ("done", "Todo", "held", "held #x", "merged  #51", "parked", "todo #3", ""):
        code, out = run(tmp_path, rows=with_row("OQ-1", "owner", bad), base_rows=CLEAN_ROWS)
        assert code == 1, bad
        assert "OQ-1: status" in out, bad


def test_held_needs_open_pr(tmp_path):
    code, out = run(tmp_path, prs=[{"number": 50, "state": "MERGED"}, {"number": 51, "state": "MERGED"}])
    assert code == 1
    assert "#11: held #50 but PR 50 is MERGED" in out


def test_held_pr_not_found_fails(tmp_path):
    code, out = run(tmp_path, prs=[{"number": 51, "state": "MERGED"}])
    assert code == 1
    assert "#11: held #50 but PR 50 is not found" in out


def test_merged_needs_merged_pr(tmp_path):
    code, out = run(tmp_path, prs=[{"number": 50, "state": "OPEN"}, {"number": 51, "state": "OPEN"}])
    assert code == 1
    assert "#12: merged #51 but PR 51 is OPEN" in out


def test_closed_row_with_open_issue_fails(tmp_path):
    issues = [dict(i, state="OPEN") if i["number"] == CLOSED_ROW else i for i in GH_ISSUES]
    code, out = run(tmp_path, issues=issues)
    assert code == 1
    assert "#13: status closed but issue is OPEN" in out


def test_open_row_with_closed_issue_fails(tmp_path):
    issues = [dict(i, state="CLOSED") if i["number"] == TODO_ROW else i for i in GH_ISSUES]
    code, out = run(tmp_path, issues=issues)
    assert code == 1
    assert "#10: status todo but issue is CLOSED" in out


def test_open_issue_without_row_fails(tmp_path):
    code, out = run(tmp_path, issues=[*GH_ISSUES, {"number": 99, "state": "OPEN"}])
    assert code == 1
    assert out == "#99: open issue has no row in the tracker\n"


def test_closed_issue_without_row_is_fine(tmp_path):
    assert run(tmp_path, issues=[*GH_ISSUES, {"number": 99, "state": "CLOSED"}])[0] == 0


def test_open_row_without_contract_fails(tmp_path):
    for bad in ("", "-", "GC", "soon"):
        code, out = run(tmp_path, rows=with_row("OQ-1", bad, "todo"), base_rows=CLEAN_ROWS)
        assert code == 1, bad
        assert "OQ-1: open row (status todo) has no contract" in out, bad


def test_closed_row_needs_no_contract(tmp_path):
    assert run(tmp_path, rows=with_row("OQ-1", "-", "closed"), base_rows=CLEAN_ROWS)[0] == 0


def test_parked_to_missing_issue_fails(tmp_path):
    code, out = run(tmp_path, rows=with_row("OQ-1", "owner", "parked #777"), base_rows=CLEAN_ROWS)
    assert code == 1
    assert "OQ-1: parked #777 but issue 777 does not exist" in out


def test_duplicate_id_fails(tmp_path):
    raw = table(CLEAN_ROWS) + "| OQ-1 | again | P1 | owner | A | todo | |\n"
    code, out = run(tmp_path, raw=raw)
    assert code == 1
    assert "OQ-1: duplicate row" in out


def test_wrong_column_count_fails_closed(tmp_path):
    code, out = run(tmp_path, raw=table(CLEAN_ROWS) + "| X-1 | only | three |\n")
    assert code == 1
    assert out.startswith("table: row has 3 columns")


def test_missing_table_fails_closed(tmp_path):
    code, out = run(tmp_path, raw="# Tracker\n\nno table here\n")
    assert code == 1
    assert out.startswith("table: header")


def test_wrong_header_fails_closed(tmp_path):
    raw = table(CLEAN_ROWS).replace("| Status |", "| State |")
    code, out = run(tmp_path, raw=raw)
    assert code == 1
    assert out.startswith("table: header")


def test_unreadable_fixture_is_exit_2(tmp_path):
    (tmp_path / "docs" / "process").mkdir(parents=True)
    (tmp_path / "docs" / "process" / "build-ahead-tracker.md").write_text(table(CLEAN_ROWS), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    r = exec_script(tmp_path, "--offline", bad)
    assert r.returncode == EXIT_CANNOT_CHECK
    assert r.stdout.startswith("CANNOT CHECK")


def test_missing_tracker_is_exit_2(tmp_path):
    r = exec_script(tmp_path, "--offline", tmp_path / "x.json")
    assert r.returncode == EXIT_CANNOT_CHECK
