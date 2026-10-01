#!/usr/bin/env python3
"""verifier-write-guard: a read-only agent (the verifier) cannot leave files in the repo.

Wired in the project settings (never only in an agent's frontmatter, which does not run in a
headless session) on PreToolUse, PostToolUse and PostToolUseFailure for the shell tools (Bash,
PowerShell). It acts ONLY when the hook input's `agent_type` names a read-only agent: `verifier` by
default, the env var VERIFIER_WRITE_GUARD_AGENTS adds more (comma-separated), and a namespaced name
counts by its last ':' part (`plugin:verifier`). Every other agent and the main session (no
`agent_type`) pass through untouched, exit 0.

It judges one foreground call at a time, by what changed on disk (never by the command text), in
evidence/, work/ and spec/ of every judged root: the git top level of the hook input's cwd and of
CLAUDE_PROJECT_DIR, and every worktree `git worktree list` names for them.

  PreToolUse   a call asked to run in the background is refused before it runs. Otherwise:
               snapshot path -> sha256 of every entry under the three folders, plus git's untracked
               set, into <system temp>/verifier-write-guard/snap/<16 hex>.json. A snapshot that
               cannot be written refuses the call.
  PostToolUse  compare with the snapshot. An entry is MOVED to
  (+Failure)   <system temp>/verifier-quarantine/<stamp>/<relative path> only if it was ABSENT at Pre
               AND git reports it UNTRACKED now (an honest verifier's new file; a merge or checkout
               brings tracked files). Every other change (a changed file, a new tracked file) is
               COPIED there and reported, never moved or reverted, because the guard cannot tell
               whose edit it is; a deletion is reported. MANIFEST.json in the quarantine folder
               lists each entry (checkout root, path, sha256, action). Any change: exit 2 with
               "REFUSED: the verifier must not write files; ..." naming each path with its checkout
               and the quarantine folder. Nothing changed: exit 0.

Links and junctions are never walked or followed: each is one opaque entry; a moved one is removed
as a link (its target is recorded and never touched).

Fail safe (REQ-015 AC-3): no snapshot, or an unreadable one -> refuse and LIST what git sees as
untracked or modified under the three folders, moving and restoring nothing. A malformed input that
names a read-only agent is refused; one that names none exits 0 with a note. A crash while judging a
read-only agent's call is a refusal. A missing script is a no-op (the settings command checks the file
exists first). A file that cannot be read during the snapshot is skipped with a note.

Threat model: this stops an honest verifier's writes. It does not stop a deliberate forger running
as the same user, who can edit the snapshot or this script.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

PROTECTED = ("evidence", "work", "spec")
DEFAULT_READ_ONLY_AGENTS = ("verifier",)
ENV_AGENTS = "VERIFIER_WRITE_GUARD_AGENTS"
PRE = "PreToolUse"
POST_EVENTS = ("PostToolUse", "PostToolUseFailure")
SNAP_TTL_SECONDS = 24 * 3600
GUARD_DIR_NAME = "verifier-write-guard"
QUARANTINE_DIR_NAME = "verifier-quarantine"
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



def new_quarantine_dir() -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S") + "-%d" % time.time_ns()
    q = os.path.join(tempfile.gettempdir(), QUARANTINE_DIR_NAME, stamp)
    os.makedirs(q, exist_ok=False)
    return q


def _q_target(q: str, root_index: int, rel: str) -> str:
    parts = rel.split("/")
    if root_index:
        parts = ["root-%d" % root_index] + parts
    return os.path.join(q, *parts)


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


def take_out(full: str, dst: str) -> None:
    """Move one created entry out of the repo. A link or junction is removed as a link (its target
    is recorded and never touched); a file is copied then unlinked (works across drives)."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if is_link(full):
        with open(dst + ".link.txt", "w", encoding="utf-8") as fh:
            fh.write("link removed from the repo; target (untouched): %s\n" % _link_target(full))
        if os.path.isdir(full) and not os.path.islink(full):
            os.rmdir(full)  # a junction: removes the link only, never the target's contents
        else:
            try:
                os.unlink(full)
            except IsADirectoryError:
                os.rmdir(full)
        return
    shutil.copy2(full, dst)
    os.remove(full)


# ------------------------------------------------------------------------------------ judging


def _porcelain(root: str) -> list[str] | None:
    r = _git(["-C", root, "status", "--porcelain=v1", "--untracked-files=all", "--", *PROTECTED], timeout=30)
    if r is None or r.returncode != 0:
        return None
    return [l for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()]


def untracked_set(root: str) -> set[str] | None:
    """Paths git reports as untracked (`??`) under the three folders, or None if git cannot say."""
    lines = _porcelain(root)
    if lines is None:
        return None
    out = set()
    for l in lines:
        if l.startswith("?? "):
            p = l[3:].strip()
            if p.startswith('"') and p.endswith('"'):
                p = p[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape").encode("latin-1").decode("utf-8", "replace")
            out.add(p.rstrip("/"))
    return out


def _is_untracked(rel: str, untracked: set[str] | None) -> bool:
    """True only when git itself names `rel` (or, for a link or folder git lists by its contents,
    something under it) as untracked. No git answer = not untracked (never moved)."""
    if not untracked:
        return False
    return rel in untracked or any(u.startswith(rel + "/") for u in untracked)


def _file_sha(path: str) -> str:
    try:
        return _entry_hash(path)
    except OSError:
        return UNREADABLE


def new_report() -> dict:
    return {"moved": [], "copied": [], "deleted": [], "quarantine": None, "manifest": []}


def judge(roots_before: list[dict], report: dict) -> None:
    """Compare each root's snapshot with disk now. MOVE an entry only if it was absent at Pre and
    git sees it as untracked now; COPY (never move, never revert) every other change; note
    deletions. Writes MANIFEST.json into the quarantine folder."""
    q = None

    def qdir() -> str:
        nonlocal q
        if q is None:
            q = new_quarantine_dir()
            report["quarantine"] = q
        return q

    for idx, entry in enumerate(roots_before):
        root = entry["root"]
        before = entry.get("files", {})
        before_dirs = set(entry.get("dirs", []))
        now, now_dirs = scan(root)
        created = sorted(set(now) - set(before))
        changed = sorted(r for r in set(now) & set(before)
                         if now[r] != before[r] and UNREADABLE not in (now[r], before[r]))
        deleted = sorted(set(before) - set(now))
        if not (created or changed or deleted):
            continue
        untracked = untracked_set(root) if created else set()
        moved_any = False
        for rel in created:
            full = os.path.join(root, *rel.split("/"))
            dst = _q_target(qdir(), idx, rel)
            sha = _file_sha(full)
            if _is_untracked(rel, untracked):
                take_out(full, dst)
                report["moved"].append((root, rel))
                report["manifest"].append({"root": root, "path": rel, "sha256": sha, "action": "moved"})
                moved_any = True
            else:
                _copy_out(full, dst)
                report["copied"].append((root, rel, "new, tracked"))
                report["manifest"].append({"root": root, "path": rel, "sha256": sha, "action": "copied"})
        if moved_any:
            # folders the call created and left empty after the move (deepest first)
            for rel_dir in sorted(now_dirs - before_dirs, key=lambda p: p.count("/"), reverse=True):
                try:
                    os.rmdir(os.path.join(root, *rel_dir.split("/")))
                except OSError:
                    pass
        for rel in changed:
            full = os.path.join(root, *rel.split("/"))
            _copy_out(full, _q_target(qdir(), idx, rel))
            report["copied"].append((root, rel, "changed"))
            report["manifest"].append({"root": root, "path": rel, "sha256": _file_sha(full), "action": "copied"})
        for rel in deleted:
            report["deleted"].append((root, rel))
            report["manifest"].append({"root": root, "path": rel, "sha256": before[rel], "action": "deleted"})
    if q is not None:
        with open(os.path.join(q, "MANIFEST.json"), "w", encoding="utf-8") as fh:
            json.dump(report["manifest"], fh, indent=1)


def _copy_out(full: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if is_link(full):
        with open(dst + ".link.txt", "w", encoding="utf-8") as fh:
            fh.write("link (left in place, not followed); target: %s\n" % _link_target(full))
    else:
        shutil.copyfile(full, dst)


def _where(root: str, rel: str) -> str:
    return "%s (in %s)" % (rel, root)


def refusal_text(report: dict) -> str:
    bits = []
    if report["moved"]:
        bits.append("created, untracked (moved out of the repo): "
                    + ", ".join(_where(r, p) for r, p in report["moved"]))
    if report["copied"]:
        bits.append("changed or tracked (NOT moved, NOT reverted; a copy is in quarantine; the orchestrator "
                    "must check each): " + ", ".join("%s [%s]" % (_where(r, p), k) for r, p, k in report["copied"]))
    if report["deleted"]:
        bits.append("deleted (not restored; the orchestrator must check each): "
                    + ", ".join(_where(r, p) for r, p in report["deleted"]))
    return ("REFUSED: the verifier must not write files; under evidence/, work/ or spec/ this call left: "
            "%s. Quarantine folder (with MANIFEST.json): %s. Return your evidence blocks in your reply; "
            "the orchestrator records them. Quote this refusal in your final reply."
            % ("; ".join(bits), report.get("quarantine")))


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
        manifest = {"roots": []}
        for root in roots:
            files, dirs = scan(root, notes)
            u = untracked_set(root)
            manifest["roots"].append({"root": root, "files": files, "dirs": sorted(dirs),
                                      "untracked_at_pre": sorted(u) if u is not None else None})
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
                   "list what changed under evidence/, work/ or spec/; nothing was moved. The "
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
    if report["moved"] or report["copied"] or report["deleted"]:
        refuse(refusal_text(report))
    sys.exit(0)


# ------------------------------------------------------------------------------------ main


_AGENT_IN_RAW_RE = re.compile(r'"agent_type"\s*:\s*"([^"]*)"')
NOT_JUDGED_EVENTS = ("SubagentStop", "Stop")  # never wired; exit 0 so a stale wiring cannot trap a stop


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    agents = read_only_agents()

    if not isinstance(data, dict):
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
