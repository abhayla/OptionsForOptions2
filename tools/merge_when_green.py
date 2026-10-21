"""Merge a pull request only when CI has really run and every check passed.

    python tools/merge_when_green.py <pr-number> --reviewed-sha <full sha of the reviewed commit> [--timeout-min 20] [--max-updates 0..3, default 3]

Why: `gh pr checks --watch && gh pr merge` merged PR #11 while CI had not started, because "no checks reported"
exited 0 (finding check-validates-nothing-reports-pass, third occurrence). Here zero checks means WAIT, never pass.

W-042 (OD-85 D5): a PR branch that is BEHIND its base gets ONE merge commit from the base (`gh pr update-branch`,
never --rebase, so reviewed commits are not rewritten), only when every check is green and every run finished,
at most --max-updates times, and the merge is pinned to the head commit that was checked. Without branch
protection GitHub reports a stale PR as CLEAN (finding merge-state-clean-hides-stale-branch) and the first read
after a push as UNKNOWN, so staleness is decided by the compare API (behind_by > 0), with BEHIND and a merge
refusal "not up to date" as additional signals, never by mergeStateStatus alone.

Coverage rule (always on): --reviewed-sha R, the full 40-character sha of the commit that was reviewed, is ALWAYS
required; without it nothing is read, updated or merged. Whatever head H is about to merge (after any update) must
be covered by that review. R must be an ancestor of H (compare R...H behind_by == 0). C = files changed R..H
(a rename counts under its old and new name). If C meets the PR diff at H, the PR diff at R or a Tier A path T,
the tool refuses with "RE-REVIEW NEEDED: <files>". T = kit default paths plus the entries of the project Tier A
file (path below, `entries: [{path, category}]`, absent file = no entries) read at the base, at R and at H. A list
of 300 or more changed files may be truncated and is refused. A file that is in C but in neither PR diff came from
the base, not from a push to the PR, and needs no review of this PR unless it is a T path.

Post-review bookkeeping carve-out (OD-86). Trust is decided by exact SHAPE, never by folder: pytest, CI and
trace_check pick files up by NAME (a conftest.py or test_*.py anywhere), so a folder carve-out would be a code
execution carve-out. A PR-pushed file in C is bookkeeping only when the T check passed first and it is one of:
evidence/W-<id>/AC-<n>.md, reviews/W-<id>-r<n>.md (ids of 3 or more digits, .md only, and only for the PR's OWN
work items, the W-ids whose work/W-<id>.md is in the PR diff at R); views/trace.md, views/build-order.md,
views/spec-digest.md (the only views CI regenerates and compares); work/W-<own id>.md where only status,
verification_status, review_status and next_action differ between R and H (every other field, tests_required
included, and the body must be equal; a work item added after review is not bookkeeping). Anything else pushed after
review is RE-REVIEW NEEDED. When bookkeeping is present, trace_check must pass at H, run on a `git archive` of H in
a temp dir (fetch, extract, this interpreter, timeout, remove); a non-zero exit, a timeout or a missing tool
refuses (fail closed). Honesty line: the gate guarantees the bookkeeping is inert (no code runs because of it and
it changes nothing a reviewer judged); whether the evidence is honest stays the orchestrator's duty, not this
tool's.

Known gap (no fix without branch protection): the base can move between the staleness check and the merge. GitHub
then merges the PR into a base that CI never saw, an untested combination; only branch protection ("require branches
to be up to date") closes it, and that setting is out of this tool's scope.

Every answer the tool decides on, and what it does:

    gh pr update-branch "updated"            -> wait for headRefOid to change (until --timeout-min), then re-check on the new sha
    gh pr update-branch "already up-to-date" -> head unchanged; counts as an update; loop (bounded by --max-updates)
    gh pr update-branch exit 1 "conflicts"   -> REFUSED (conflict); head unchanged
    gh pr update-branch other non-zero       -> REFUSED with gh's output
    head does not change before timeout      -> REFUSED (timeout)
    mergeStateStatus UNKNOWN                 -> ignored; the compare API decides
    mergeStateStatus CLEAN, behind_by 0      -> not stale; merge
    mergeStateStatus CLEAN, behind_by > 0    -> stale (the hidden-stale case); update
    mergeStateStatus BEHIND                  -> stale even if the compare read says 0
    mergeStateStatus DIRTY / CONFLICTING     -> REFUSED at start (check_pr_state)
    merge refused "not up to date"           -> stale; update
    compare API error on the staleness read  -> wait, retry until timeout, then REFUSED
    compare / contents API error on coverage -> REFUSED (fail closed)
    checks red, pending, none, runs unfinished -> never update, never merge
    updates used == --max-updates and stale  -> REFUSED (updates exhausted)
"""
import argparse
import fnmatch
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

PASSING = {"pass", "skipping"}
FAILING = {"fail", "cancel"}

CONFLICT_MESSAGE = "CONFLICTING: GitHub runs no CI on this PR; merge the base branch in first"


def check_pr_state(pr_state):
    """Return ('already_merged', None), ('refuse', message) or ('poll', None) for gh pr view's
    {"state", "mergeable", "mergeStateStatus"} JSON.

    A CONFLICTING/DIRTY PR gets zero CI runs from GitHub, so waiting on checks would wait forever
    (the same "no checks reported" trap decide() already guards against, one layer up). mergeable
    is UNKNOWN right after a push, since GitHub computes it lazily — that case keeps polling.
    """
    if pr_state.get("state") == "MERGED":
        return ("already_merged", None)
    if pr_state.get("mergeable") == "CONFLICTING" or pr_state.get("mergeStateStatus") == "DIRTY":
        return ("refuse", CONFLICT_MESSAGE)
    return ("poll", None)


def read_pr_state(pr):
    out = subprocess.run(["gh", "pr", "view", str(pr), "--json", "state,mergeable,mergeStateStatus"],
                         capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        return {}
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return {}


def decide(checks):
    """Return 'merge', 'wait' or 'refuse' for a list of {"name", "bucket"} dicts from gh."""
    if not checks:
        return "wait"
    buckets = [c.get("bucket", "") for c in checks]
    if any(b in FAILING for b in buckets):
        return "refuse"
    if all(b in PASSING for b in buckets):
        return "merge"
    return "wait"


PASS_CONCLUSIONS = {"SUCCESS", "SKIPPED", "NEUTRAL"}
FAIL_CONCLUSIONS = {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}
_SEVERITY = {"pass": 0, "pending": 1, "fail": 2}
_NEWEST = "9999-12-31T23:59:59Z"


def entry_bucket(entry):
    """Map one statusCheckRollup entry (CheckRun or StatusContext) to pass / fail / pending.

    Anything not recognised is pending: the gate waits rather than guess.
    """
    if "context" in entry or ("state" in entry and "conclusion" not in entry):
        state = (entry.get("state") or "").upper()
        if state == "SUCCESS":
            return "pass"
        if state in ("FAILURE", "ERROR"):
            return "fail"
        return "pending"
    if (entry.get("status") or "").upper() != "COMPLETED":
        return "pending"
    conclusion = (entry.get("conclusion") or "").upper()
    if conclusion in PASS_CONCLUSIONS:
        return "pass"
    if conclusion in FAIL_CONCLUSIONS:
        return "fail"
    return "pending"


def _sort_key(entry, bucket):
    started = entry.get("startedAt") or entry.get("createdAt") or ""
    if not started or started.startswith("0001-"):
        # No usable start time: a pending or failing entry counts as the newest (fail safe), a
        # passing one as the oldest, so it can never outvote a dated result.
        started = "" if bucket == "pass" else _NEWEST
    return (started, _SEVERITY[bucket])  # equal times: the worse bucket sorts last, so it wins


def newest_checks(rollup):
    """Reduce a statusCheckRollup list to [{"name", "bucket"}], one per distinct check, newest run wins.

    finding merge-gate-reads-superseded-run: the rollup lists a check once per CI run, so a failed or
    cancelled run that a newer run replaced must not decide. A distinct check is (type, workflow, name)
    for a CheckRun and (type, context) for a StatusContext: two workflows can each have a job with the
    same name, and a green one must never hide the other's failure.
    """
    newest = {}
    for entry in rollup or []:
        name = entry.get("name") or entry.get("context") or ""
        if "context" in entry and "name" not in entry:
            ident = ("StatusContext", entry.get("context") or "")
        else:
            ident = (entry.get("__typename") or "CheckRun", entry.get("workflowName") or "", name)
        bucket = entry_bucket(entry)
        key = _sort_key(entry, bucket)
        if ident not in newest or key > newest[ident][0]:
            newest[ident] = (key, bucket, name, ident[0])
    return [{"name": n, "bucket": b, "kind": k} for _, b, n, k in newest.values()]


def read_pr_snapshot(pr):
    """Read head sha, base branch, merge state and checks in ONE gh call (the merge is pinned to that sha)."""
    empty = {"sha": "", "base": "", "merge_state": "", "checks": []}
    out = subprocess.run(["gh", "pr", "view", str(pr), "--json",
                          "headRefOid,baseRefName,mergeStateStatus,statusCheckRollup"],
                         capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        return empty
    try:
        data = json.loads(out.stdout)
        return {"sha": data.get("headRefOid") or "", "base": data.get("baseRefName") or "",
                "merge_state": data.get("mergeStateStatus") or "",
                "checks": newest_checks(data.get("statusCheckRollup"))}
    except (json.JSONDecodeError, AttributeError):
        return empty


def read_pr_checks(pr):
    """Return (head_sha, checks) read in one gh call, so the merge can be pinned to that commit."""
    snap = read_pr_snapshot(pr)
    return (snap["sha"], snap["checks"])


def read_checks(pr):
    return read_pr_checks(pr)[1]


def unfinished_runs(sha, has_check_runs=True):
    """Return what is still unfinished on this commit: [] only when every listed run is completed.

    A label-triggered run may exist before its jobs reach the rollup, so this is asked before any
    final verdict, merge or refuse. Safe side everywhere: a failed or unreadable run list, or an empty
    one while CheckRun entries exist (their run is not listed yet), is not finished. An empty list
    next to only StatusContext entries (no Actions run involved) is finished.
    """
    out = subprocess.run(["gh", "run", "list", "--commit", sha, "--limit", "100",
                          "--json", "status,conclusion,databaseId"], capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        return ["run list unreadable"]
    try:
        runs = json.loads(out.stdout)
    except json.JSONDecodeError:
        return ["run list unreadable"]
    if not isinstance(runs, list):
        return ["run list unreadable"]
    if not runs:
        return ["no run listed yet for the head commit"] if has_check_runs else []
    return ["run %s (%s)" % (r.get("databaseId") if isinstance(r, dict) else "?",
                             (r.get("status") or "unknown") if isinstance(r, dict) else "unreadable")
            for r in runs if not (isinstance(r, dict) and (r.get("status") or "").lower() == "completed")]


def runs_finished(sha, has_check_runs=True):
    """True when every run on this commit is completed (see unfinished_runs for the safe-side cases)."""
    return not unfinished_runs(sha, has_check_runs)


# ---- W-042: base update of a stale branch, with a coverage rule ----

class ApiError(Exception):
    """A GitHub read failed or returned something unusable. Callers fail closed (or wait and retry)."""


_FILES_LIMIT = 300  # the compare API lists at most 300 files; a full list may be truncated, so it is not trusted
_CLAUDE_DIR = "." + "claude"
_FACTORY_DIR = "." + "factory"
_LOCK_NAME = "factory" + ".lock"
TIER_A_FILE = _CLAUDE_DIR + "/project/tier-a.yaml"
# Kit-default Tier A paths (T is never empty): hooks, settings, workflows, tools, the lock file, the Tier A file.
KIT_TIER_A = [
    _CLAUDE_DIR + "/hooks/",
    _CLAUDE_DIR + "/settings*",
    _CLAUDE_DIR + "/kit/",
    TIER_A_FILE,
    ".github/workflows/",
    "tools/",
    _FACTORY_DIR + "/",
    "*" + _LOCK_NAME,
]


def _gh_api(endpoint, raw=False):
    cmd = ["gh", "api"] + (["-H", "Accept: application/vnd.github.raw"] if raw else []) + [endpoint]
    return subprocess.run(cmd, capture_output=True, text=True)


def compare(a, b):
    """compare/{a}...{b}: behind_by (commits in a that b lacks) and the changed file names. Raises ApiError."""
    out = _gh_api("repos/{owner}/{repo}/compare/%s...%s" % (a, b))
    if out.returncode != 0 or not (out.stdout or "").strip():
        raise ApiError("compare %s...%s failed: %s" % (a, b, (out.stderr or out.stdout or "").strip()[:200]))
    try:
        data = json.loads(out.stdout)
        behind = int(data["behind_by"])
        files = data.get("files") or []
        names = set()
        for f in files:
            names.add(f["filename"])
            if f.get("previous_filename"):
                names.add(f["previous_filename"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError):
        raise ApiError("compare %s...%s returned an unreadable answer" % (a, b))
    if len(files) >= _FILES_LIMIT:
        raise ApiError("compare %s...%s lists %d files, which may be truncated" % (a, b, len(files)))
    return {"behind_by": behind, "files": names}


def is_stale(base, sha, merge_state=""):
    """True when the base has commits the head lacks. BEHIND counts; CLEAN and UNKNOWN never decide. Raises ApiError."""
    if not base or not sha:
        raise ApiError("base branch or head commit unknown")
    behind = compare(base, sha)["behind_by"] > 0
    return behind or merge_state == "BEHIND"


_GH_NOT_FOUND = re.compile(r"(?m)^gh: Not Found \(HTTP 404\)\s*$")


def fetch_file(path, ref):
    """Text of `path` at `ref`, or None when it does not exist there (404). Raises ApiError on any other failure."""
    out = _gh_api("repos/{owner}/{repo}/contents/%s?ref=%s" % (path, ref), raw=True)
    if out.returncode != 0:
        text = (out.stderr or "") + (out.stdout or "")
        if _GH_NOT_FOUND.search(out.stderr or ""):
            return None  # only gh's own "Not Found (HTTP 404)" line means absent; any other failure refuses
        raise ApiError("%s at %s unreadable: %s" % (path, ref, text.strip()[:200]))
    return out.stdout


def tier_a_entries(ref):
    """Paths named by the project Tier A file at `ref` (absent file = no entries). Raises ApiError (fail closed)."""
    text = fetch_file(TIER_A_FILE, ref)
    if text is None:
        return []
    try:
        import yaml  # imported here: only a project Tier A file needs it, and a missing yaml must fail closed
        data = yaml.safe_load(text)
        if data is None:
            return []
        paths = [e["path"] for e in data["entries"]]
        if not all(isinstance(x, str) and x for x in paths):
            raise ValueError("entry path")
        return paths
    except Exception as exc:  # noqa: BLE001 - every failure to read the Tier A file refuses
        raise ApiError("tier-a file at %s is not usable: %s" % (ref, exc))


def path_matches(path, pattern):
    """Case-insensitive: a trailing / is a folder prefix, * ? [ are globs, anything else is a file or folder name."""
    p = path.replace("\\", "/").lower()
    pat = pattern.replace("\\", "/").lower()
    if pat.endswith("/"):
        return p.startswith(pat)
    if any(ch in pat for ch in "*?["):
        return fnmatch.fnmatchcase(p, pat)
    return p == pat or p.startswith(pat + "/")


def review_record_gate(pr, sha):
    """Seam for the review-record gate (a later item adds its check here). Returns (ok, message)."""
    return (True, "")


_HEX40 = re.compile(r"[0-9a-fA-F]{40}")
_WORK_ITEM = re.compile(r"work/W-([0-9]{3,})\.md")
_EVIDENCE = re.compile(r"evidence/W-([0-9]{3,})/AC-[0-9]+\.md")
_REVIEW_RECORD = re.compile(r"reviews/W-([0-9]{3,})-r[0-9]+\.md")
_CI_VIEWS = {"views/trace.md", "views/build-order.md", "views/spec-digest.md"}  # CI regenerates and compares these
_WORK_STATUS_FIELDS = {"status", "verification_status", "review_status", "next_action"}


def _own(match, own_ids):
    """True when the work-item id in this file name is one of the PR's own (its work file is in the PR diff)."""
    return match.group(1) in own_ids


def bookkeeping_shape(path, own_ids):
    """True when `path` has one of the exact bookkeeping shapes (and, for ids, belongs to this PR's own items)."""
    match = _EVIDENCE.fullmatch(path) or _REVIEW_RECORD.fullmatch(path) or _WORK_ITEM.fullmatch(path)
    if match:
        return _own(match, own_ids)
    return path in _CI_VIEWS


def reviewed_sha_problem(value):
    """Return a refusal message when --reviewed-sha is missing or not a full 40-hex sha, else ''."""
    if not value:
        return "REFUSED: --reviewed-sha is required (the full 40-character sha of the reviewed commit)"
    if not _HEX40.fullmatch(value):
        return "REFUSED: --reviewed-sha must be the full 40-character sha of the reviewed commit, not %r" % value
    return ""


def _split_frontmatter(text):
    """(frontmatter dict, body) of a work item; ValueError when it has no readable frontmatter."""
    import yaml
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ValueError("no frontmatter")
    end = text.find("\n---\n", 3)
    if end < 0:
        raise ValueError("unterminated frontmatter")
    data = yaml.safe_load(text[4:end + 1])
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a mapping")
    return data, text[end + 5:]


def work_item_status_only(path, reviewed, head):
    """True when the work item differs between R and H only in the status fields (body and every other field equal).
    A file missing at either commit, or unreadable frontmatter, is not bookkeeping. Raises ApiError on a failed read."""
    before, after = fetch_file(path, reviewed), fetch_file(path, head)
    if before is None or after is None:
        return False
    try:
        fm_before, body_before = _split_frontmatter(before)
        fm_after, body_after = _split_frontmatter(after)
    except Exception:  # noqa: BLE001 - anything unreadable is a change that needs a review
        return False
    keep = lambda fm: {k: v for k, v in fm.items() if k not in _WORK_STATUS_FIELDS}  # noqa: E731
    return body_before == body_after and keep(fm_before) == keep(fm_after)


def run_trace_check(sha, timeout_s=300):
    """Run the project's trace_check on a `git archive` of `sha` (no worktree). Returns (ok, message); fails closed."""
    tmp = None
    try:
        fetched = subprocess.run(["git", "fetch", "origin", sha], capture_output=True)
        if fetched.returncode != 0:
            return (False, "REFUSED: trace_check not run, git fetch of %s failed" % sha[:12])
        archive = subprocess.run(["git", "archive", "--format=tar", sha], capture_output=True)
        if archive.returncode != 0:
            return (False, "REFUSED: trace_check not run, git archive of %s failed" % sha[:12])
        tmp = tempfile.mkdtemp(prefix="mwg-trace-")
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tf:
            for member in tf.getmembers():
                if os.path.isabs(member.name) or ".." in member.name.replace("\\", "/").split("/"):
                    return (False, "REFUSED: trace_check not run, unsafe path in the archive: %s" % member.name)
            if hasattr(tarfile, "data_filter"):
                tf.extractall(tmp, filter="data")
            else:
                tf.extractall(tmp)
        script = os.path.join(tmp, "tools", "trace_check.py")
        if not os.path.isfile(script):
            return (False, "REFUSED: trace_check not run, tools/trace_check.py is missing at %s" % sha[:12])
        done = subprocess.run([sys.executable, script, tmp], cwd=tmp, capture_output=True, text=True,
                              timeout=timeout_s)
        if done.returncode != 0:
            tail = ((done.stdout or "") + (done.stderr or "")).strip()[-400:]
            return (False, "REFUSED: trace_check failed at %s: %s" % (sha[:12], tail))
        return (True, "")
    except subprocess.TimeoutExpired:
        return (False, "REFUSED: trace_check timed out after %s s at %s" % (timeout_s, sha[:12]))
    except (OSError, tarfile.TarError, ValueError) as exc:
        return (False, "REFUSED: trace_check not run: %s" % exc)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def check_coverage(base, reviewed, head, incoming=False):
    """Return (True, "") or (False, message): is the change from the reviewed commit to `head` covered by that review?

    incoming=True also counts the files a pending base update would bring (compare head...base), so an update
    that could not be covered is refused before anything is pushed; trace_check then waits for the real new head.
    Fail closed: any unreadable answer refuses.
    """
    problem = reviewed_sha_problem(reviewed)
    if problem:
        return (False, problem)
    try:
        span = compare(reviewed, head)
        if span["behind_by"] != 0:
            return (False, "REFUSED: reviewed sha %s is not an ancestor of head %s" % (reviewed[:12], head[:12]))
        changed = set(span["files"]) | (compare(head, base)["files"] if incoming else set())
        if not changed:
            return (True, "")
        patterns = list(KIT_TIER_A)
        for ref in (base, reviewed, head):
            patterns += tier_a_entries(ref)
        tier_a = lambda f: any(path_matches(f, pat) for pat in patterns)  # noqa: E731
        diff_head = compare(base, head)["files"]
        diff_reviewed = compare(base, reviewed)["files"]
        protected = diff_head | diff_reviewed
        own_ids = {m.group(1) for m in (_WORK_ITEM.fullmatch(f) for f in diff_reviewed) if m}
        hit, bookkeeping = set(), set()
        for f in sorted(changed):
            if tier_a(f):
                hit.add(f)                  # the Tier A check comes first, for every file
            elif f not in protected:
                continue                    # came from the base, not from a push to this PR
            elif not bookkeeping_shape(f, own_ids):
                hit.add(f)
            elif _WORK_ITEM.fullmatch(f) and not work_item_status_only(f, reviewed, head):
                hit.add(f)
            else:
                bookkeeping.add(f)
    except ApiError as exc:
        return (False, "REFUSED: coverage could not be checked: %s" % exc)
    if hit:
        return (False, "RE-REVIEW NEEDED: %s" % ", ".join(sorted(hit)))
    if bookkeeping and not incoming:
        return run_trace_check(head)
    return (True, "")


def run_update_branch(pr):
    """Run `gh pr update-branch` (a merge commit, never --rebase). Returns (kind, text); kind is
    updated, up_to_date, conflict or error."""
    out = subprocess.run(["gh", "pr", "update-branch", str(pr)], capture_output=True, text=True)
    text = ((out.stdout or "") + (out.stderr or "")).strip()
    low = text.lower()
    if out.returncode == 0:
        return ("up_to_date" if "already up-to-date" in low or "already up to date" in low else "updated", text)
    if "conflict" in low:
        return ("conflict", text)
    return ("error", text)


def wait_for_new_head(pr, old_sha, deadline, interval_s):
    """Poll until headRefOid differs from old_sha. Returns the new sha, or '' on timeout."""
    while True:
        out = subprocess.run(["gh", "pr", "view", str(pr), "--json", "headRefOid"], capture_output=True, text=True)
        sha = ""
        if out.returncode == 0 and (out.stdout or "").strip():
            try:
                sha = json.loads(out.stdout).get("headRefOid") or ""
            except (json.JSONDecodeError, AttributeError):
                sha = ""
        if sha and sha != old_sha:
            return sha
        if time.time() > deadline:
            return ""
        time.sleep(interval_s)


_STALE_MERGE_REFUSAL = ("not up to date", "head branch is behind", "branch is behind")


MAX_UPDATES_LIMIT = 3  # REQ-055 AC-2: "retries at most three times"; the flag may lower it, never raise it


def _max_updates(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("--max-updates must be a whole number from 0 to %d, not %r" % (MAX_UPDATES_LIMIT, text))
    if not 0 <= value <= MAX_UPDATES_LIMIT:
        raise argparse.ArgumentTypeError("--max-updates must be from 0 to %d, not %d" % (MAX_UPDATES_LIMIT, value))
    return value


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pr")
    ap.add_argument("--timeout-min", type=float, default=20)
    ap.add_argument("--interval-s", type=float, default=20)
    ap.add_argument("--reviewed-sha", default="", help="REQUIRED: full 40-character sha of the reviewed commit")
    ap.add_argument("--max-updates", type=_max_updates, default=3, help="base updates allowed, 0 to 3")
    a = ap.parse_args(argv)
    problem = reviewed_sha_problem(a.reviewed_sha)
    if problem:
        print(problem)
        return 1
    verdict, message = check_pr_state(read_pr_state(a.pr))
    if verdict == "already_merged":
        print("already merged")
        return 0
    if verdict == "refuse":
        print(message)
        return 1
    deadline = time.time() + a.timeout_min * 60
    updates = 0
    merge_said_stale = False
    while True:
        snap = read_pr_snapshot(a.pr)
        sha, checks = snap["sha"], snap["checks"]
        verdict = decide(checks)
        unfinished = []
        if verdict in ("merge", "refuse"):
            # finding merge-gate-reads-superseded-run: a run still going on the head commit can replace
            # the checks listed now, so neither a merge nor a refusal is final until all runs are done.
            unfinished = (unfinished_runs(sha, any(c.get("kind") != "StatusContext" for c in checks))
                          if sha else ["head commit unknown"])
            if unfinished:
                verdict = "wait"
        names = ", ".join(f"{c.get('name')}={c.get('bucket')}" for c in checks) or "no checks reported yet"
        if verdict == "refuse":
            print(f"REFUSED: PR {a.pr} has a failing check: {names}")
            return 1
        if verdict == "merge":
            # Green and every run finished. Only now may the branch be updated or merged.
            try:
                stale = merge_said_stale or is_stale(snap["base"], sha, snap["merge_state"])
            except ApiError as exc:
                unfinished = ["staleness unreadable: %s" % exc]
                verdict = "wait"
            else:
                if stale:
                    if updates >= a.max_updates:
                        print(f"REFUSED: PR {a.pr} is still behind its base after {updates} updates (updates exhausted)")
                        return 1
                    ok, why = check_coverage(snap["base"], a.reviewed_sha, sha, incoming=True)
                    if not ok:
                        print(why)
                        return 1
                    kind, text = run_update_branch(a.pr)
                    updates += 1
                    merge_said_stale = False
                    deadline = time.time() + a.timeout_min * 60  # a new head gets a new CI window
                    if kind == "conflict":
                        print(f"REFUSED: PR {a.pr} cannot be updated, the base conflicts: {text}")
                        return 1
                    if kind == "error":
                        print(f"REFUSED: PR {a.pr} base update failed: {text}")
                        return 1
                    if kind == "updated":
                        new_sha = wait_for_new_head(a.pr, sha, deadline, a.interval_s)
                        if not new_sha:
                            print(f"REFUSED: PR {a.pr} head did not change after the base update "
                                  f"within {a.timeout_min} min")
                            return 1
                    if kind == "up_to_date":
                        time.sleep(a.interval_s)  # head unchanged: do not spin on the same answer
                    continue
        if verdict == "merge":
            ok, why = check_coverage(snap["base"], a.reviewed_sha, sha)
            if not ok:
                print(why)
                return 1
            ok, why = review_record_gate(a.pr, sha)
            if not ok:
                print(why)
                return 1
            print(f"all {len(checks)} checks passed: {names}")
            merge_result = subprocess.run(
                ["gh", "pr", "merge", str(a.pr), "--merge", "--delete-branch", "--match-head-commit", sha],
                capture_output=True, text=True,
            )
            # gh-merge-delete-branch-fails-in-worktree: --delete-branch tries to switch the
            # worktree to the base branch, which the main checkout already holds, so gh can exit
            # non-zero after the merge itself succeeded on GitHub. Re-read the PR's real state
            # instead of trusting gh's local exit code.
            post_state = read_pr_state(a.pr)
            if post_state.get("state") == "MERGED":
                print("merged")
                if merge_result.returncode != 0:
                    note = (merge_result.stderr or merge_result.stdout).strip()
                    print(f"note: local branch cleanup failed: {note}")
                return 0
            refusal = (merge_result.stderr or merge_result.stdout or "")
            if merge_result.returncode != 0 and any(m in refusal.lower() for m in _STALE_MERGE_REFUSAL):
                merge_said_stale = True  # the merge itself says the branch is behind: take the update path
                continue
            sys.stderr.write(refusal)
            return merge_result.returncode or 1
        if time.time() > deadline:
            waiting = f"; unfinished: {', '.join(unfinished)}" if unfinished else ""
            print(f"REFUSED: PR {a.pr} not green within {a.timeout_min} min ({names}{waiting})")
            return 1
        time.sleep(a.interval_s)


if __name__ == "__main__":
    sys.exit(main())
