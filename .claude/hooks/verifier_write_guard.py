#!/usr/bin/env python3
"""verifier-write-guard: a read-only agent (the verifier) cannot leave files in the repo.

Wired in the project settings (never only in an agent's frontmatter, which does not run in a
headless session) on PreToolUse, PostToolUse and PostToolUseFailure for the shell tools (Bash,
PowerShell), and on SubagentStop (cleanup only, see below). It acts ONLY when the hook input's `agent_type` names a read-only agent: `verifier` and `reviewer` by
default, the env var VERIFIER_WRITE_GUARD_AGENTS adds more (comma-separated), and a namespaced name
counts by its last ':' part (`plugin:verifier`). Every other agent and the main session (no
`agent_type`) pass through untouched, exit 0.

It judges one foreground call at a time, by what changed on disk (never by the command text), in
evidence/, work/ and spec/ of every judged root: the git top level of the hook input's cwd and of
CLAUDE_PROJECT_DIR, and every linked worktree of each.

  PreToolUse   a call asked to run in the background is refused before it runs. Otherwise:
               snapshot path -> sha256 of every entry under the three folders into
               <system temp>/verifier-write-guard/snap/<16 hex>.json. A snapshot that cannot be
               written refuses the call.
  PostToolUse  compare with the snapshot. Any created, changed or deleted entry: exit 2 with
  (+Failure)   "REFUSED: the verifier must not write files; ..." listing each path with its checkout.
               The guard NEVER moves, copies, restores or deletes a repo file (OD-120): the
               orchestrator checks the listed paths. Nothing changed: exit 0.

  SubagentStop a read-only agent finished: delete the snapshots THIS agent left behind (a call another
               PreToolUse hook blocked never gets a Post event). Only a snapshot whose recorded
               agent_id equals the stop input's AND its session_id equals the stop input's, or was
               recorded as None/missing (an empty string is a recorded value), is deleted (parallel
               verifiers run at once; a snapshot with a different non-empty session_id is kept). It
               never touches a repo file, and ALWAYS exits 0 (exit 2 would stop the subagent from
               finishing). A missing agent_id deletes nothing; an unreadable or non-object snapshot, or
               one without an agent_id, is left for the 24 h prune. The main session's Stop is not judged.

Links and junctions are never walked or followed: each is one opaque entry.

Fail safe (REQ-015 AC-3): no snapshot, or an unreadable one -> refuse and LIST what git sees as
untracked or modified under the three folders, touching nothing. A malformed input that
names a read-only agent is refused; one that names none exits 0 with a note. A crash while judging a
read-only agent's call is a refusal. A missing script is a no-op (the settings command checks the file
exists first). A file that cannot be read during the snapshot is skipped with a note.

Threat model (OD-120): an accident guard. It reports an honest verifier's write and refuses the call;
it does not stop a deliberate forger running as the same user, who can edit the snapshot or this script,
and a write undone inside the same call is not seen.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time

PROTECTED = ("evidence", "work", "spec")
DEFAULT_READ_ONLY_AGENTS = ("verifier", "reviewer")
ENV_AGENTS = "VERIFIER_WRITE_GUARD_AGENTS"
PRE = "PreToolUse"
POST_EVENTS = ("PostToolUse", "PostToolUseFailure")
SNAP_TTL_SECONDS = 24 * 3600
GUARD_DIR_NAME = "verifier-write-guard"
UNREADABLE = "unreadable"


# ------------------------------------------------------------------------------------ helpers


def read_only_agents() -> set[str]:
    names = {a.lower() for a in DEFAULT_READ_ONLY_AGENTS}
    extra = os.environ.get(ENV_AGENTS, "")
    names.update(p.strip().lower() for p in extra.split(",") if p.strip())
    return names


def is_read_only(agent, agents: set[str]) -> bool:
    return isinstance(agent, str) and agent.strip().split(":")[-1].strip().lower() in agents


def refuse(msg: str) -> None:
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(2)


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _git(args: list[str], timeout: int = 15):
    try:
        return subprocess.run(["git", *args], capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def _git_toplevel(path: str) -> str | None:
    r = _git(["-C", path, "rev-parse", "--show-toplevel"])
    if r is None or r.returncode != 0 or not r.stdout.strip():
        return None
    return os.path.abspath(r.stdout.decode("utf-8", "replace").strip())


def _worktrees(root: str) -> list[str]:
    r = _git(["-C", root, "worktree", "list", "--porcelain"])
    if r is None or r.returncode != 0:
        return []
    out = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("worktree "):
            p = line[len("worktree "):].strip()
            if os.path.isdir(p):
                out.append(os.path.abspath(p))
    return out


def judged_roots(data: dict) -> list[str]:
    """Top level of cwd and of CLAUDE_PROJECT_DIR, plus every worktree of each. Order kept."""
    roots: list[str] = []
    seen: set[str] = set()

    def add(p: str) -> None:
        if _norm(p) not in seen:
            seen.add(_norm(p))
            roots.append(p)

    for cand in (data.get("cwd"), os.environ.get("CLAUDE_PROJECT_DIR")):
        if not isinstance(cand, str) or not cand.strip() or not os.path.isdir(cand):
            continue
        top = _git_toplevel(cand)
        add(top or os.path.abspath(cand))
        if top:
            for wt in _worktrees(top):
                add(wt)
    return roots


def is_link(path: str) -> bool:
    """A symlink or a junction / other reparse point: never walked, never followed."""
    try:
        if os.path.islink(path):
            return True
        if hasattr(os.path, "isjunction") and os.path.isjunction(path):
            return True
        attrs = getattr(os.lstat(path), "st_file_attributes", 0)
        return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError:
        return False


def _link_target(path: str) -> str:
    try:
        return os.readlink(path)
    except (OSError, ValueError):
        return "?"


def _entry_hash(path: str) -> str:
    if is_link(path):
        return "link:" + hashlib.sha256(_link_target(path).encode("utf-8", "replace")).hexdigest()
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan(root: str, notes: list[str] | None = None) -> tuple[dict[str, str], set[str]]:
    """{relative posix path: hash} of every file or link under the protected folders, and the set
    of relative real directories there. Links are leaves; nothing behind a link is read."""
    files: dict[str, str] = {}
    dirs: set[str] = set()
    for top in PROTECTED:
        base = os.path.join(root, top)
        if is_link(base):
            files[top] = _entry_hash(base)
            continue
        if not os.path.isdir(base):
            continue
        stack = [base]
        while stack:
            d = stack.pop()
            dirs.add(os.path.relpath(d, root).replace("\\", "/"))
            try:
                names = sorted(os.listdir(d))
            except OSError:
                continue
            for name in names:
                full = os.path.join(d, name)
                rel = os.path.relpath(full, root).replace("\\", "/")
                if is_link(full):
                    files[rel] = _entry_hash(full)
                elif os.path.isdir(full):
                    stack.append(full)
                else:
                    try:
                        files[rel] = _entry_hash(full)
                    except OSError as exc:
                        files[rel] = UNREADABLE
                        if notes is not None:
                            notes.append("%s (%s)" % (rel, exc.__class__.__name__))
    return files, dirs


def state_base() -> str:
    return os.path.join(tempfile.gettempdir(), GUARD_DIR_NAME)


def _key(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:16]


def snap_path(data: dict) -> str | None:
    tid = data.get("tool_use_id")
    if not isinstance(tid, str) or not tid.strip():
        return None
    sid = data.get("session_id") if isinstance(data.get("session_id"), str) else ""
    return os.path.join(state_base(), "snap", _key(sid, tid) + ".json")



def _write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    os.replace(tmp, path)


def _prune_old_state() -> None:
    now = time.time()
    for sub in ("snap",):
        base = os.path.join(state_base(), sub)
        try:
            names = os.listdir(base)
        except OSError:
            continue
        for name in names:
            p = os.path.join(base, name)
            try:
                if now - os.path.getmtime(p) > SNAP_TTL_SECONDS:
                    os.remove(p)
            except OSError:
                pass

# ------------------------------------------------------------------------------------ judging


def _porcelain(root: str) -> list[str] | None:
    r = _git(["-C", root, "status", "--porcelain=v1", "--untracked-files=all", "--", *PROTECTED], timeout=30)
    if r is None or r.returncode != 0:
        return None
    return [l for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()]


def _file_sha(path: str) -> str:
    try:
        return _entry_hash(path)
    except OSError:
        return UNREADABLE


def new_report() -> dict:
    return {"created": [], "changed": [], "deleted": []}


def judge(roots_before: list[dict], report: dict) -> None:
    """Compare each root's snapshot with disk now and list every created, changed or deleted entry.
    Nothing on disk is touched."""
    for entry in roots_before:
        root = entry["root"]
        before = entry.get("files", {})
        now, _dirs = scan(root)
        report["created"] += [(root, r) for r in sorted(set(now) - set(before))]
        report["changed"] += [(root, r) for r in sorted(set(now) & set(before))
                              if now[r] != before[r] and UNREADABLE not in (now[r], before[r])]
        report["deleted"] += [(root, r) for r in sorted(set(before) - set(now))]


def _where(root: str, rel: str) -> str:
    return "%s (in %s)" % (rel, root)


def refusal_text(report: dict) -> str:
    bits = ["%s: %s" % (k, ", ".join(_where(r, p) for r, p in report[k]))
            for k in ("created", "changed", "deleted") if report[k]]
    return ("REFUSED: the verifier must not write files; under evidence/, work/ or spec/ this call left: "
            "%s. Nothing was moved, copied or restored (the orchestrator must check each path). Return "
            "your evidence blocks in your reply; the orchestrator records them. Quote this refusal in "
            "your final reply." % "; ".join(bits))


def list_from_git(roots: list[str]) -> tuple[list[str], bool]:
    """The no-snapshot listing: git's untracked/modified entries under the three folders. Touches
    nothing. Returns (lines, git_ok)."""
    lines, ok = [], True
    for root in roots:
        entries = _porcelain(root)
        if entries is None:
            ok = False
            continue
        lines += ["%s (in %s)" % (e, root) for e in entries]
    return lines, ok


# ------------------------------------------------------------------------------------ events


def on_pre(data: dict, agent: str, roots: list[str]) -> None:
    tin = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    if str(tin.get("run_in_background")).strip().lower() == "true":
        refuse("REFUSED: a %s shell call may not run in the background (its writes would land after "
               "this guard's check). Run it in the foreground." % agent)
    sp = snap_path(data)
    if sp is None:
        refuse("REFUSED: verifier-write-guard got a %s call with no tool_use_id, so it cannot match "
               "the call to its result; the call is refused." % agent)
    notes: list[str] = []
    try:
        _prune_old_state()
        manifest = {"roots": [],
                    "agent_id": data.get("agent_id") if isinstance(data.get("agent_id"), str) else None,
                    "session_id": data.get("session_id") if isinstance(data.get("session_id"), str) else None}
        for root in roots:
            files, _dirs = scan(root, notes)
            manifest["roots"].append({"root": root, "files": files})
        _write_json(sp, manifest)
    except OSError as exc:
        refuse("REFUSED: verifier-write-guard could not write its snapshot for this %s call (%s), "
               "so it could not check the call afterwards; the call is refused." % (agent, exc))
    if notes:
        sys.stderr.write("verifier-write-guard: could not read (skipped, not judged): %s\n" % ", ".join(notes))
    sys.exit(0)


def _load(path: str | None) -> dict | None:
    if path is None:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            m = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(m, dict) or not isinstance(m.get("roots"), list):
        return None
    return m


def on_post(data: dict, agent: str, roots: list[str]) -> None:
    sp = snap_path(data)
    manifest = _load(sp)
    if manifest is None:
        lines, git_ok = list_from_git(roots)
        why = ("no tool_use_id in the hook input (malformed)" if sp is None
               else "no snapshot from before this call (missing or unreadable)")
        if not git_ok:
            refuse("REFUSED: verifier-write-guard had %s (%s call) and git status failed, so it cannot "
                   "list what changed under evidence/, work/ or spec/; nothing was changed. The "
                   "orchestrator must check those folders. Quote this refusal in your final reply."
                   % (why, agent))
        refuse("REFUSED: verifier-write-guard had %s (%s call); nothing was moved or restored. Untracked "
               "or modified under evidence/, work/, spec/ (the orchestrator must check each): %s. Quote "
               "this refusal in your final reply." % (why, agent, "; ".join(lines) if lines else "none"))
    report = new_report()
    judge(manifest["roots"], report)
    try:
        os.remove(sp)
    except OSError:
        pass
    if report["created"] or report["changed"] or report["deleted"]:
        refuse(refusal_text(report))
    sys.exit(0)


# ------------------------------------------------------------------------------------ main


def on_subagent_stop(data: dict) -> None:
    """Delete only the snapshots THIS agent left (recorded agent_id equals the stop input's, and the
    recorded session_id equals it or was recorded as None/missing). Never touches the repo, never judges; always exits 0 (exit 2 on
    SubagentStop would stop the subagent from finishing). Anything unreadable, not a dict, or without
    an agent_id is skipped and left for the 24 h prune."""
    try:
        agent_id, session_id = data.get("agent_id"), data.get("session_id")
        if not isinstance(agent_id, str) or not agent_id.strip():
            sys.exit(0)
        if not isinstance(session_id, str):
            session_id = None  # matches only a snapshot recorded without a session id
        base = os.path.join(state_base(), "snap")
        try:
            names = os.listdir(base)
        except OSError:
            sys.exit(0)
        for name in names:
            if not name.endswith(".json"):
                continue
            path = os.path.join(base, name)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    m = json.load(fh)
                if not isinstance(m, dict):
                    continue
                if m.get("agent_id") == agent_id and (m.get("session_id") == session_id
                                                      or m.get("session_id") is None):
                    os.remove(path)
            except Exception:  # one bad snapshot file must not stop the others being cleaned
                continue
    except SystemExit:
        raise
    except Exception as exc:  # never block a stop
        sys.stderr.write("verifier-write-guard: snapshot cleanup on SubagentStop failed (%s: %s); "
                         "leftover snapshots are pruned after 24 h.\n" % (type(exc).__name__, exc))
    sys.exit(0)


_AGENT_IN_RAW_RE = re.compile(r'"agent_type"\s*:\s*"([^"]*)"')
_STOP_EVENT_IN_RAW_RE = re.compile(r'"hook_event_name"\s*:\s*"(?:SubagentStop|Stop)"')
NOT_JUDGED_EVENTS =("Stop",)  # the main session's stop is not judged; exit 0


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    agents = read_only_agents()

    if not isinstance(data, dict):
        if _STOP_EVENT_IN_RAW_RE.search(raw or ""):
            sys.stderr.write("verifier-write-guard: stop-event input is not a JSON object; nothing to "
                             "clean, and a stop is never blocked.\n")
            sys.exit(0)
        m = _AGENT_IN_RAW_RE.search(raw or "")
        if m and is_read_only(m.group(1), agents):
            refuse("REFUSED: verifier-write-guard could not read its hook input (not a JSON object) "
                   "for a %s call, so it cannot check what the call changed; the call is refused."
                   % m.group(1))
        sys.stderr.write("verifier-write-guard: hook input is not a JSON object; cannot tell which "
                         "agent made the call, so it is not judged.\n")
        sys.exit(0)

    agent = data.get("agent_type")
    if not is_read_only(agent, agents):
        sys.exit(0)  # main session or any other agent: untouched

    try:
        event = data.get("hook_event_name")
        if event in NOT_JUDGED_EVENTS:
            sys.exit(0)
        if event == "SubagentStop":
            on_subagent_stop(data)
        roots = judged_roots(data)
        if not roots:
            refuse("REFUSED: verifier-write-guard got no usable cwd (and no CLAUDE_PROJECT_DIR) for a "
                   "%s call, so it cannot check what the call changed; the call is refused." % agent)
        if event == PRE:
            on_pre(data, agent, roots)
        if event in POST_EVENTS:
            on_post(data, agent, roots)
        refuse("REFUSED: verifier-write-guard got a %s call with hook_event_name %r, which it does "
               "not handle; the call is refused." % (agent, event))
    except SystemExit:
        raise
    except Exception as exc:  # a crash must never let a verifier write pass unreported
        refuse("REFUSED: verifier-write-guard failed while checking this %s call (%s: %s); the "
               "orchestrator must check evidence/, work/ and spec/ by hand. Quote this refusal in "
               "your final reply." % (agent, type(exc).__name__, exc))


if __name__ == "__main__":
    main()
