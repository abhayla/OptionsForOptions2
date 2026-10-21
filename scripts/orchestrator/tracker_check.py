"""tracker_check.py <repo-root> [--offline FIXTURE.json]

Checks docs/process/build-ahead-tracker.md (ADR-112 (2), goal-chain chain rules 8-9):
  - the table parses and every Status is on the closed list (an allow-list);
  - no Id present in the tracker at origin/main is missing now (a row leaves only as closed/parked/deferred);
  - held #N -> PR N open; merged #N -> PR N merged; parked/deferred #N -> issue N exists;
  - an issue-id row (#N): closed -> issue closed, any open status -> issue open;
  - every OPEN issue has a row; every open row has a contract;
  - GC-6 rows (nothing silent, contract section 0): todo/building needs `verify:` in its notes, blocked-* needs
    `owner-accepted YYYY-MM-DD`, and every row id section 4 of the GC-6 contract names has a tracker row;
  - a todo/building row whose Item or Evidence names a PR that GitHub reports MERGED is stale (one PR list).
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
STATUS_ISSUE_WORDS = {"parked", "deferred"}  # their #N is an issue (held/merged name a PR)
MIN_TABLE_LINES = 3  # header, separator, at least one row
WITH_NUMBER_PARTS = 2  # "held" and "#N"
CONTRACT_RE = re.compile(r"GC-\w+|owner|stage-5")
GC6 = "GC-6"
GC6_CONTRACT_GLOB = "docs/process/goal-contract-GC-6-*.md"
VERIFY_RE = re.compile(r"verify:\s*\S")
ACCEPTED_RE = re.compile(r"owner-accepted \d{4}-\d{2}-\d{2}")
VERIFY_STATUSES = {"todo", "building"}
SECTION_START = re.compile(r"^## 4\.", re.M)
SECTION_END = re.compile(r"^## \d+\.", re.M)  # numbered: a heading wrapped onto a second '## ' line is not an end
AC_SUFFIX_RE = re.compile(r"\s+AC-(\d+)\b")
PR_REF_RE = re.compile(r"\bPR\s+#(\d+)\b(?!-)", re.I)  # only an explicit own-PR reference, never a bare "#N"
OUT_OF_SCOPE_LINE = re.compile(r"^Out of this contract.*$", re.M)
# A plan id is an issue number (#352, #352-2) or an UPPER-CASE hyphenated name (CI-SPLIT, W-118-sel, REQ-041).
PLAN_ID_RE = re.compile(r"#\d+(?:-\d+)?|\b[A-Z][A-Z0-9]*(?:-[A-Za-z0-9]+)+\b")
NAMED_ISSUE_RE = re.compile(r"(\b[A-Z][A-Z0-9]*(?:-[A-Za-z0-9]+)+\b)\s*\(\s*(#\d+)\s*\)")  # NAME (#N)
NOT_ROW_PREFIXES = ("ADR-", "GC-", "AC-")  # decision, contract and criterion references, not rows


class CheckError(Exception):
    """The check could not run (exit 2), as opposed to a tracker failure (exit 1)."""


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_tracker(text, failures):
    rows = []
    numbered = [(n, ln) for n, ln in enumerate(text.splitlines(), 1) if ln.lstrip().startswith("|")]
    if len(numbered) < MIN_TABLE_LINES or split_row(numbered[0][1]) != COLUMNS:
        failures.append(f"table: header is not exactly {' | '.join(COLUMNS)} (or the table is missing)")
        return rows
    for number, ln in numbered[2:]:
        cells = split_row(ln)
        if len(cells) != len(COLUMNS):
            failures.append(
                f"table: row has {len(cells)} columns, expected {len(COLUMNS)} "
                f"(a literal | inside a cell must be escaped as \\|) at line {number}: {ln[:60]}")
            continue
        rows.append({**dict(zip(COLUMNS, cells, strict=True)), "line": number})
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
        parsed = parse_status(row["Status"])  # "deferred #482" on any row covers issue 482
        if parsed and parsed[0] in STATUS_ISSUE_WORDS:
            covered.add(parsed[1])
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


def check_gc6_rows(rows, failures):
    """Rules 1 and 2: a GC-6 row cannot stall or close silently (contract section 0)."""
    for row in rows:
        if row["Contract"] != GC6:
            continue
        word = row["Status"].split(" ")[0]
        where = f"line {row['line']}: {row['Id']}"
        if word in VERIFY_STATUSES and not VERIFY_RE.search(row["Evidence"]):
            failures.append(f"{where}: {word} row has no 'verify:' command in its notes")
        if word.startswith("blocked") and not ACCEPTED_RE.search(row["Evidence"]):
            failures.append(f"{where}: {row['Status']} row has no 'owner-accepted YYYY-MM-DD' in its notes")


def check_merged_pr_in_open_row(rows, prs, failures):
    """A todo/building row whose own cells name a PR that GitHub says is MERGED is stale (measured 2026-10-21:
    HOME-NEW said building after PR #464 merged). One PR list serves every row (the call gh_states already made)."""
    for row in rows:
        word = row["Status"].split(" ")[0]
        if word not in VERIFY_STATUSES:
            continue
        named = {int(n) for n in PR_REF_RE.findall(" ".join(row[c] for c in COLUMNS))}
        for num in sorted(n for n in named if prs.get(n) == "MERGED"):
            failures.append(f"line {row['line']}: {row['Id']}: status {word} but its notes name PR #{num}, "
                            f"which is MERGED on GitHub (update the row: merged/verified/closed, or say what is left)")


def contract_plan_ids(contract_text, pr_numbers):
    """Row ids named in section 4 of the contract; None when the section is missing."""
    start = SECTION_START.search(contract_text)
    if not start:
        return None
    body = contract_text[start.end():]
    end = SECTION_END.search(body)
    body = OUT_OF_SCOPE_LINE.sub("", body[:end.start()] if end else body)
    ids = set()
    for m in PLAN_ID_RE.finditer(body):
        tok = m.group(0)
        if tok.startswith(NOT_ROW_PREFIXES):
            continue
        if tok.startswith("#") and tok[1:].isdigit() and int(tok[1:]) in pr_numbers:
            continue  # a held PR, not an issue row
        ac = AC_SUFFIX_RE.match(body, m.end())
        ids.add(f"{tok}-AC{ac.group(1)}" if ac else tok)  # "W-083 AC-2" names the row W-083-AC2
    return ids


def check_contract_ids(rows, contract, issues, prs, failures):
    """Rule 3: every id the contract's order of work names is a tracker row. contract = (path, text)."""
    contract_name, contract_text = contract
    ids = contract_plan_ids(contract_text, {n for n in prs if n not in issues})
    if not ids:
        failures.append(f"{contract_name}: section 4 is missing or names no row ids (cannot compare)")
        return
    have = {r["Id"] for r in rows}
    for name, num in NAMED_ISSUE_RE.findall(contract_text[SECTION_START.search(contract_text).end():]):
        if name in have or num in have:  # "NAME (#N)" is met by a row Id NAME or Id #N
            ids -= {name, num}
    for rid in sorted(ids - have):
        failures.append(f"{contract_name}: {rid}: named in section 4 but has no tracker row")


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


def read_contract(root):
    """The one GC-6 contract file; 0 or 2+ matches is an error (fail closed)."""
    found = sorted(p for p in Path(root).glob(GC6_CONTRACT_GLOB) if p.is_file())
    if len(found) != 1:
        raise CheckError(f"{GC6_CONTRACT_GLOB}: expected exactly one contract file, found {len(found)}")
    try:
        return found[0].relative_to(root).as_posix(), found[0].read_text(encoding="utf-8")
    except OSError as e:
        raise CheckError(f"cannot read {found[0]}: {e}") from e


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
    contract = read_contract(root)
    failures = []
    rows = parse_tracker(text, failures)
    if not rows and not failures:
        failures.append("table: no rows")
    check_rows(rows, issues, prs, failures)
    check_open_issues_have_rows(rows, issues, failures)
    check_no_row_deleted(rows, base, failures)
    check_gc6_rows(rows, failures)
    check_merged_pr_in_open_row(rows, prs, failures)
    check_contract_ids(rows, contract, issues, prs, failures)
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
    if failures:
        print(f"{len(failures)} violation(s)")
    else:
        print("OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
