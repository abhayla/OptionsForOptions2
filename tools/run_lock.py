#!/usr/bin/env python3
"""run_lock.py - a cooperative run lock held as a GitHub ref (REQ-055 AC-4).

Usage:
    python tools/run_lock.py acquire <run-id> [--cap-hours N] [--session ID]
    python tools/run_lock.py release <run-id> [--session ID]
    python tools/run_lock.py status

The lock is the ref `refs/locks/<run-id>`, created with one atomic `POST git/refs`. GitHub refuses a second create of
the same ref (HTTP 422), so two sessions racing for the same run cannot both win. The ref points at a small commit
made through the API (the remote must hold the object; a local commit-tree object would not exist there) whose
message records the holder: session id, host, start time (UTC) and cap in hours.

Exit codes: 0 done; 1 refused (held by someone else, or release by a non-holder, or no such lock); 2 error
(no GitHub access, bad input).

The lock is COOPERATIVE: a session that force-deletes the ref overrides it, and nothing stops it. A STALE lock
(older than its cap) is reported by `status` and never removed by this tool; the person who owns the decision
deletes it. Release re-reads the ref right before deleting; the small window left after that is accepted because the
lock is cooperative. Refs under refs/locks are not branches, so no CI runs on them. The session id is CLAUDE_SESSION_ID,
else RUN_LOCK_SESSION, else --session, else a generated nonce that `acquire` prints (keep it for `release`).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import socket
import subprocess
import sys
import uuid

DEFAULT_CAP_HOURS = 6.0   # a project can change it per call with --cap-hours
GH_TIMEOUT = 60
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
FIELDS = ("session", "host", "started", "cap_hours")


def _run(args: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """The one subprocess seam (tests replace it). Returns (exit code, stdout, stderr); never raises."""
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=GH_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, "", f"{type(e).__name__}: {e}"
    return r.returncode, r.stdout, r.stderr


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def _host() -> str:
    return socket.gethostname()


def repo_slug() -> str | None:
    rc, out, _ = _run(["git", "remote", "get-url", "origin"])
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?\s*$", out.strip()) if rc == 0 else None
    return f"{m.group(1)}/{m.group(2)}" if m else None


def gh_api(*args: str) -> tuple[int, str, str]:
    return _run(["gh", "api", *args])


def parse_message(msg: str) -> dict:
    d = {}
    for line in msg.splitlines():
        k, sep, v = line.partition(": ")
        if sep and k in FIELDS:
            d[k] = v.strip()
    return d


def build_message(run_id: str, session: str, started: datetime.datetime, cap: float) -> str:
    return (f"run lock {run_id}\n\nsession: {session}\nhost: {_host()}\n"
            f"started: {started.isoformat()}\ncap_hours: {cap:g}\n")


def _is_404(out: str, err: str) -> bool:
    """True only for an HTTP 404 status (gh prints `(HTTP 404)`; the JSON body has "status": "404"), never for a stray 404."""
    if re.search(r"HTTP 404\b", out + err):
        return True
    try:
        return str(json.loads(out).get("status")) == "404"
    except (ValueError, AttributeError):
        return False


def read_lock(slug: str, run_id: str) -> tuple[str, dict] | str:
    """(commit sha, holder fields) or an error string starting 'absent' / 'error'."""
    rc, out, err = gh_api(f"repos/{slug}/git/ref/locks/{run_id}")
    if rc != 0:
        return "absent" if _is_404(out, err) else f"error: reading the lock failed: {(err or out).strip()[:200]}"
    try:
        sha = json.loads(out)["object"]["sha"]
    except (ValueError, KeyError, TypeError):
        return "error: the lock ref answer was not understood"
    rc, out, err = gh_api(f"repos/{slug}/git/commits/{sha}")
    if rc != 0:
        return f"error: reading the lock commit failed: {(err or out).strip()[:200]}"
    try:
        return sha, parse_message(json.loads(out)["message"])
    except (ValueError, KeyError, TypeError):
        return "error: the lock commit answer was not understood"


def age_hours(holder: dict, now: datetime.datetime) -> float | None:
    try:
        return (now - datetime.datetime.fromisoformat(holder["started"])).total_seconds() / 3600
    except (KeyError, ValueError):
        return None


def describe(run_id: str, holder: dict, now: datetime.datetime) -> str:
    age = age_hours(holder, now)
    cap = holder.get("cap_hours")
    stale = ""
    try:
        if age is not None and cap is not None and age > float(cap):
            stale = "  STALE"
    except ValueError:
        pass
    return (f"{run_id}: session {holder.get('session', '?')} on {holder.get('host', '?')}, started "
            f"{holder.get('started', '?')}, " + (f"age {age:.1f}h" if age is not None else "age unknown")
            + f", cap {cap or '?'}h{stale}")


def session_id(arg: str | None, generated_ok: bool) -> tuple[str, bool]:
    s = arg or os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("RUN_LOCK_SESSION")
    if s:
        return s, False
    return (f"nonce-{uuid.uuid4().hex[:12]}", True) if generated_ok else ("", False)


def acquire(run_id: str, cap: float, session_arg: str | None) -> int:
    slug = repo_slug()
    if not slug:
        print("cannot find owner/repo from `git remote get-url origin`", file=sys.stderr)
        return 2
    session, generated = session_id(session_arg, True)
    rc, out, err = gh_api(f"repos/{slug}/commits/HEAD", "--jq", ".commit.tree.sha")
    tree = out.strip()
    if rc != 0 or not re.fullmatch(r"[0-9a-f]{40}", tree):
        print(f"cannot read the default branch tree: {(err or out).strip()[:200]}", file=sys.stderr)
        return 2
    msg = build_message(run_id, session, _now(), cap)
    rc, out, err = gh_api("-X", "POST", f"repos/{slug}/git/commits", "-f", f"message={msg}", "-f", f"tree={tree}")
    try:
        sha = json.loads(out)["sha"] if rc == 0 else ""
    except (ValueError, KeyError, TypeError):
        sha = ""
    if not sha:
        print(f"cannot create the lock commit: {(err or out).strip()[:200]}", file=sys.stderr)
        return 2
    rc, out, err = gh_api("-X", "POST", f"repos/{slug}/git/refs", "-f", f"ref=refs/locks/{run_id}", "-f", f"sha={sha}")
    if rc == 0:
        print(f"acquired {run_id} as session {session}" + (" (generated; keep it for release: --session)" if generated else ""))
        return 0
    if "422" in out + err and "Reference already exists" in out + err:
        held = read_lock(slug, run_id)
        if isinstance(held, tuple):
            print(f"held by someone else: {describe(run_id, held[1], _now())}")
        else:
            print(f"held by someone else (holder not readable: {held})")
        return 1
    print(f"cannot create the lock ref: {(err or out).strip()[:200]}", file=sys.stderr)
    return 2


def release(run_id: str, session_arg: str | None) -> int:
    slug = repo_slug()
    if not slug:
        print("cannot find owner/repo from `git remote get-url origin`", file=sys.stderr)
        return 2
    session, _ = session_id(session_arg, False)
    if not session:
        print("no session id: set CLAUDE_SESSION_ID or RUN_LOCK_SESSION or pass --session", file=sys.stderr)
        return 2
    held = read_lock(slug, run_id)
    if held == "absent":
        print(f"no lock named {run_id}")
        return 1
    if isinstance(held, str):
        print(held, file=sys.stderr)
        return 2
    if held[1].get("session") != session:
        print(f"refused: {run_id} is held by session {held[1].get('session', '?')}, not {session}")
        return 1
    again = read_lock(slug, run_id)   # re-read right before DELETE: refuse if the lock changed hands since the check
    if not isinstance(again, tuple) or again[0] != held[0]:
        print(f"refused: {run_id} changed since the holder check; nothing deleted")
        return 1
    rc, out, err = gh_api("-X", "DELETE", f"repos/{slug}/git/refs/locks/{run_id}")
    if rc != 0:
        print(f"cannot delete the lock ref: {(err or out).strip()[:200]}", file=sys.stderr)
        return 2
    print(f"released {run_id}")
    return 0


def status() -> int:
    slug = repo_slug()
    if not slug:
        print("cannot find owner/repo from `git remote get-url origin`", file=sys.stderr)
        return 2
    rc, out, err = gh_api(f"repos/{slug}/git/matching-refs/locks/", "--paginate", "--jq", ".[].ref")
    if rc != 0:
        print(f"cannot list locks: {(err or out).strip()[:200]}", file=sys.stderr)
        return 2
    refs = out.split()
    if not refs:
        print("no locks held")
        return 0
    now = _now()
    for ref in sorted(refs):
        run_id = ref.removeprefix("refs/locks/")
        held = read_lock(slug, run_id)
        print(describe(run_id, held[1], now) if isinstance(held, tuple) else f"{run_id}: holder not readable ({held})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cooperative run lock held as a GitHub ref.")
    ap.add_argument("action", choices=("acquire", "release", "status"))
    ap.add_argument("run_id", nargs="?")
    ap.add_argument("--cap-hours", type=float, default=DEFAULT_CAP_HOURS)
    ap.add_argument("--session")
    a = ap.parse_args(argv)
    if a.action != "status" and not (a.run_id and RUN_ID.match(a.run_id) and ".." not in a.run_id and not a.run_id.endswith((".lock", "."))):
        print("run-id must be letters, digits, dot, dash or underscore (no '..', max 100)", file=sys.stderr)
        return 2
    if a.cap_hours <= 0:
        print("--cap-hours must be above 0", file=sys.stderr)
        return 2
    if a.action == "acquire":
        return acquire(a.run_id, a.cap_hours, a.session)
    if a.action == "release":
        return release(a.run_id, a.session)
    return status()


if __name__ == "__main__":
    sys.exit(main())
