"""tracker_check.py <repo-root> [--offline FIXTURE.json]

Checks docs/process/build-ahead-tracker.md (ADR-112 (2), goal-chain chain rules 8-9):
  - the table parses and every Status is on the closed list (an allow-list);
  - no Id present in the tracker at origin/main is missing now (a row leaves only as closed/parked/deferred);
  - held #N -> PR N open; merged #N -> PR N merged; parked/deferred #N -> issue N exists;
  - an issue-id row (#N): closed -> issue closed, any open status -> issue open;
  - every OPEN issue has a row; every open row has a contract.
Output: one line per failure, or OK. Exit 0 OK, 1 failures, 2 the check could not run (gh/git missing or failing).
--offline replaces both gh calls and the git base with a JSON file: {"base": "<tracker text>",
"issues": [{"number": N, "state": "OPEN|CLOSED"}], "prs": [{"number": N, "state": "OPEN|MERGED|CLOSED"}]}.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TRACKER = "docs/process/build-ahead-tracker.md"
BASE_REF = "origin/main"
GH_LIMIT = 2000
USAGE = "usage: tracker_check.py <repo-root> [--offline FIXTURE.json]"
COLUMNS = ["Id", "Item", "P", "Contract", "Tier", "Status", "Evidence"]
STATUS_PLAIN = {"todo", "building", "verified", "closed", "blocked-owner", "blocked-live"}
STATUS_WITH_NUMBER = {"held", "merged", "parked", "deferred"}
CLOSED_WORDS = {"closed", "parked", "deferred"}
MIN_TABLE_LINES = 3  # header, separator, at least one row
WITH_NUMBER_PARTS = 2  # "held" and "#N"
CONTRACT_RE =re.compile(r"GC-\w+|owner|stage-5")


class CheckError(Exception):
    """The check could not run (exit 2), as opposed to a tracker failure (exit 1)."""


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_tracker(text, failures):
    rows = []
    lines = [ln for ln in text.splitlines() if ln.lstrip().startswith("|")]
    if len(lines) < MIN_TABLE_LINES or split_row(lines[0]) != COLUMNS:
        failures.append(f"table: header is not exactly {' | '.join(COLUMNS)} (or the table is missing)")
        return rows
    for ln in lines[2:]:
        cells = split_row(ln)
        if len(cells) != len(COLUMNS):
            failures.append(
                f"table: row has {len(cells)} columns, expected {len(COLUMNS)} "
                f"(a literal | inside a cell must be escaped as \\|): {ln[:60]}")
            continue
        rows.append(dict(zip(COLUMNS, cells, strict=True)))
    return rows


def parse_status(status):
    """-> (word, number or None) or None when the status is not on the closed list."""
    parts = status.split(" ")
    if len(parts) == 1 and parts[0] in STATUS_PLAIN:
        return parts[0], None
    if len(parts) == WITH_NUMBER_PARTS and parts[0] in STATUS_WITH_NUMBER and re.fullmatch(r"#\d+", parts[1]):
        return parts[0], int(parts[1][1:])
    return None


def check_rows(rows, issues, prs, failures):
    seen = set()
    for row in rows:
        rid = row["Id"]
        if rid in seen:
            failures.append(f"{rid}: duplicate row")
        seen.add(rid)
        parsed = parse_status(row["Status"])
        if parsed is None:
            failures.append(f"{rid}: status '{row['Status']}' is not on the closed list")
            continue
        check_contract_and_prs(row, *parsed, (issues, prs), failures)
        check_issue_row(row, parsed[0], issues, failures)


def check_contract_and_prs(row, word, num, gh, failures):
    issues, prs = gh
    rid = row["Id"]
    if word not in CLOSED_WORDS and not CONTRACT_RE.fullmatch(row["Contract"]):
        failures.append(f"{rid}: open row (status {word}) has no contract (found '{row['Contract']}')")
    if word == "held" and prs.get(num) != "OPEN":
        failures.append(f"{rid}: held #{num} but PR {num} is {prs.get(num, 'not found')}, not OPEN")
    if word == "merged" and prs.get(num) != "MERGED":
        failures.append(f"{rid}: merged #{num} but PR {num} is {prs.get(num, 'not found')}, not MERGED")
    if word in ("parked", "deferred") and num not in issues:
        failures.append(f"{rid}: {word} #{num} but issue {num} does not exist")


def check_issue_row(row, word, issues, failures):
    rid = row["Id"]
    m = re.fullmatch(r"#(\d+)", rid)
    if not m:
        return
    state = issues.get(int(m.group(1)))
    if state is None:
        failures.append(f"{rid}: issue {m.group(1)} not found on GitHub")
    elif word == "closed" and state != "CLOSED":
        failures.append(f"{rid}: status closed but issue is {state}")
    elif word != "closed" and state == "CLOSED":
        failures.append(f"{rid}: status {row['Status']} but issue is CLOSED")


def check_open_issues_have_rows(rows, issues, failures):
    covered = set()
    for row in rows:
        m = re.fullmatch(r"#(\d+)", row["Id"])
        if m:
            covered.add(int(m.group(1)))
    for num, state in sorted(issues.items()):
        if state == "OPEN" and num not in covered:
            failures.append(f"#{num}: open issue has no row in the tracker")


def check_no_row_deleted(rows, base_text, failures):
    base_failures = []
    base_ids = {r["Id"] for r in parse_tracker(base_text, base_failures)}
    if base_failures:
        raise CheckError(f"the tracker at {BASE_REF} does not parse: {base_failures[0]}")
    now = {r["Id"] for r in rows}
    for rid in sorted(base_ids - now):
        failures.append(f"{rid}: row deleted (present at {BASE_REF}); a row leaves only as closed, parked or deferred")


def run(cmd, root):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=root, encoding="utf-8",  # noqa: S603
                           check=False)
    except OSError as e:
        raise CheckError(f"{cmd[0]} failed to start: {e}") from e
    if r.returncode != 0:
        raise CheckError(f"{' '.join(cmd[:3])} exited {r.returncode}: {(r.stderr or '').strip()[:200]}")
    return r.stdout


def gh_states(root, kind):
    if not shutil.which("gh"):
        raise CheckError("gh binary not found")
    out = run(["gh", kind, "list", "--state", "all", "--json", "number,state", "--limit", str(GH_LIMIT)], root)
    try:
        items = json.loads(out)
    except ValueError as e:
        raise CheckError(f"gh {kind} list returned invalid JSON: {e}") from e
    if not items:
        raise CheckError(f"gh {kind} list returned an empty list (cannot compare against GitHub)")
    if len(items) >= GH_LIMIT:
        raise CheckError(f"gh {kind} list returned {len(items)} items, equal to the limit: may be truncated")
    return {int(i["number"]): i["state"] for i in items}


def load_offline(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        base = data["base"]
        issues = {int(i["number"]): i["state"] for i in data["issues"]}
        prs = {int(i["number"]): i["state"] for i in data["prs"]}
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise CheckError(f"offline fixture unreadable: {type(e).__name__}: {e}") from e
    return base, issues, prs


def check(root, offline=None):
    try:
        text = (Path(root) / TRACKER).read_text(encoding="utf-8")
    except OSError as e:
        raise CheckError(f"cannot read {TRACKER}: {e}") from e
    if offline:
        base, issues, prs = load_offline(offline)
    else:
        base = run(["git", "show", f"{BASE_REF}:{TRACKER}"], root)
        issues, prs = gh_states(root, "issue"), gh_states(root, "pr")
    failures = []
    rows = parse_tracker(text, failures)
    if not rows and not failures:
        failures.append("table: no rows")
    check_rows(rows, issues, prs, failures)
    check_open_issues_have_rows(rows, issues, failures)
    check_no_row_deleted(rows, base, failures)
    return failures


def main(argv):
    args = argv[1:]
    offline = None
    if "--offline" in args:
        i = args.index("--offline")
        if i + 1 >= len(args):
            print(USAGE)
            return 2
        offline = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1:
        print(USAGE)
        return 2
    try:
        failures = check(args[0], offline)
    except CheckError as e:
        print(f"CANNOT CHECK: {e}")
        return 2
    for f in failures:
        print(f)
    if not failures:
        print("OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
