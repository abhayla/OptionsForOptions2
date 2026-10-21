#!/usr/bin/env python3
"""status_page_due.py - Stop hook and SessionStart note (REQ-052 AC-7, OD-76).

Stop (no argument): when a project stage changed since the status page was last published, build the page (no model
tokens) and block the stop ONCE per fingerprint per session with a short request for one Artifact publish.
SessionStart (`--session-start`): print ONE line when the project has no link yet; otherwise silent.

Silent (exit 0, no output) when any of these holds:
  - STATUS_PAGE_DUE=0 (off-switch);
  - the session is not an attended one: CLAUDE_CODE_SESSION_ATTENDED != "1" (headless `claude -p` sets "0");
  - the hook input carries an agent_id (a subagent; ATTENDED is "1" there, so only this check silences it; the kit
    settings also never wire this hook to SubagentStop);
  - the project is a linked git worktree (git-dir != git-common-dir; if that cannot be told, assume linked) or its
    branch is not the default branch (origin/HEAD, else main or master);
  - Stop: views/status-page.json is missing or has no url; the fingerprint equals the published one; this session was
    already asked for this fingerprint; the page could not be built;
  - Stop with stop_hook_active true: it never blocks (no loop) but still RECORDS a publish seen in the transcript;
  - any error at all (the whole main is wrapped; a broken hook never traps a stop).

Fingerprint (local only, no network): sorted requirement, work item, plan step and owner-question statuses, the
number of plan change entries per plan, release ids, and the merge-commit count on HEAD. Hashed with sha256. Record
files are read as utf-8-sig and the plan `steps` / `changes` lists are read in both YAML flow ({...}) and block style.
(The repo's own parser needs PyYAML; this hook ships to projects as a stdlib-only script, so it reads the two lists
itself.)

State: views/status-page.state.json (gitignored), written atomically (temp file + os.replace):
  {"published_fingerprint": fp, "published_by": session_id,
   "sessions": {session_id: {"prompted_fp", "published_fp", "failed_fp", "mark_line", "ts"}}}
A publish seen in a session is credited ONLY when it answers a prompt, and then to THAT SESSION'S prompted
fingerprint (the page that was built and asked for), never to the fingerprint of the moment. A publish nobody asked
for credits nothing (it may predate a change made later in the same turn). `mark_line` is the transcript length when
a publish was last seen, so a publish line is counted once. `failed_fp` is the fingerprint whose page build failed
in this session; later stops do not rebuild for it. Sessions idle for 7 days are pruned; before every write the state
file is re-read and only this session's entry is merged into it.

Transcript shape (real lines, trimmed, in tests/fixtures/status_page_due/real_artifact_lines.jsonl):
  assistant record: content [{"type": "tool_use", "id", "name": "Artifact", "input": {"file_path": ".../views/status-page.html",
  "url": "https://claude.ai/artifact/...", "label"?}}]; user record: content [{"type": "tool_result", "tool_use_id",
  "content": "Published <path> at <url> (Version N ...)"}]. A refusal is a tool_result starting "Publish refused" or
  "You hadn't viewed" (the real ones carry is_error true; checked by text as well). Success = no is_error and text
  starting "Published".

Python 3.9+ stdlib only. The only subprocesses besides git are the page build (`--fetch`, 40 s timeout; on failure
one rebuild without `--fetch`, 40 s). The hook's own wiring timeout is 90 s.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

STATE_REL = "views/status-page.state.json"
LINK_REL = "views/status-page.json"
PAGE_REL = "views/status-page.html"
BUILD_REL = "tools/build_status_page.py"
BUILD_TIMEOUT = 40
SESSION_TTL = 7 * 24 * 3600
NO_LINK_NOTE = ("This project has no status page link yet: publish views/status-page.html once and save the link "
                "in views/status-page.json.")

STATUS_RE = re.compile(r"^status:\s*[\"']?([^\s\"'#]+)", re.M)
ITEM_STATUS_RE = re.compile(r"\bstatus:\s*[\"']?([A-Za-z_-]+)")


def _git(root, *args):
    r = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=30)
    return r.stdout.strip() if r.returncode == 0 else None


def _front(path):
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return ""
    m = re.match(r"---\r?\n(.*?)\r?\n---", text, re.S)
    return m.group(1) if m else ""


def _section_items(front, key):
    """The list items under a top-level `key:` in a frontmatter block, each as its own text; flow style
    (`- {a: 1}`) and block style (`- a: 1` plus indented lines) both work; `key: []` is empty."""
    lines = front.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^%s:\s*(?:#.*)?$" % re.escape(key), ln):
            start = i + 1
            break
    if start is None:
        return []
    body = []
    for ln in lines[start:]:
        if ln.strip() and not ln.startswith((" ", "\t", "-")) and not ln.lstrip().startswith("#"):
            break  # next top-level key
        body.append(ln)
    marks = [(len(ln) - len(ln.lstrip()), i) for i, ln in enumerate(body) if re.match(r"^\s*-(\s|$)", ln)]
    if not marks:
        return []
    indent = min(m[0] for m in marks)
    starts = [i for ind, i in marks if ind == indent]
    items = []
    for n, s in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(body)
        items.append("\n".join(body[s:end]))
    return items


def _listdir(root, rel, prefix):
    d = os.path.join(root, rel)
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    return [os.path.join(d, n) for n in names if n.startswith(prefix) and n.endswith(".md")]


def compute_fingerprint(root):
    parts = []
    for rel, prefix in (("spec/requirements", "REQ-"), ("work", "W-"), ("owner-questions", "OQ-")):
        for p in _listdir(root, rel, prefix):
            m = STATUS_RE.search(_front(p))
            parts.append("%s/%s=%s" % (rel, os.path.basename(p), m.group(1) if m else "?"))
    for p in _listdir(root, "plans", "PL-"):
        fm = _front(p)
        m = STATUS_RE.search(fm)
        steps = []
        for item in _section_items(fm, "steps"):
            sm = ITEM_STATUS_RE.search(item)
            steps.append(sm.group(1) if sm else "?")
        parts.append("plans/%s=%s|steps=%s|changes=%d" % (os.path.basename(p), m.group(1) if m else "?",
                                                          ",".join(steps), len(_section_items(fm, "changes"))))
    for p in _listdir(root, "releases", "R-"):
        parts.append("releases/%s" % os.path.basename(p))
    merges = _git(root, "rev-list", "--merges", "--count", "HEAD")
    parts.append("merges=%s" % merges)
    return hashlib.sha256("\n".join(sorted(parts)).encode("utf-8")).hexdigest()


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


READ_TRIES = 3
READ_PAUSE = 0.05


def _read_state(path):
    """Read the shared state file. Returns {} when the file is missing (empty state is right) or genuinely
    corrupt (still unparseable after the retries: the next write replaces it); returns None when the file
    EXISTS but could not be read (e.g. a sharing violation while another session replaces it): the caller
    must not write, or it would publish {} over the shared fingerprint and other sessions' entries."""
    unreadable = False
    for i in range(READ_TRIES):
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                d = json.load(fh)
            return d if isinstance(d, dict) else {}
        except OSError:
            unreadable = True
        except ValueError:
            unreadable = False
        if i < READ_TRIES - 1:
            time.sleep(READ_PAUSE)
    return None if unreadable else {}


def write_state(path, state):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".status-page-state.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _same_path(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def is_linked_worktree(root):
    gd = _git(root, "rev-parse", "--git-dir")
    cd = _git(root, "rev-parse", "--git-common-dir")
    if gd is None or cd is None:
        return True  # cannot tell: stay silent
    return not _same_path(os.path.join(root, gd), os.path.join(root, cd))


def on_default_branch(root):
    cur = _git(root, "branch", "--show-current")
    if not cur:
        return False
    head = _git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        return cur == head.split("/", 1)[-1]
    return cur in ("main", "master")


def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return ""


def publish_seen(transcript, url, start_line):
    """True when, at/after line `start_line`, an Artifact tool_use for views/status-page.html and `url` got a
    tool_result that is not an error and starts with "Published"."""
    if not isinstance(transcript, str) or not os.path.isfile(transcript):
        return False
    uses = set()
    with open(transcript, "r", encoding="utf-8", errors="replace") as fh:
        for i, raw in enumerate(fh):
            if i < start_line:
                continue
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            content = (rec.get("message") or {}).get("content") if isinstance(rec, dict) else None
            if not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use" and b.get("name") == "Artifact":
                    inp = b.get("input") or {}
                    fp = str(inp.get("file_path", "")).replace("\\", "/")
                    if fp.endswith(PAGE_REL) and inp.get("url") == url:
                        uses.add(b.get("id"))
                elif b.get("type") == "tool_result" and b.get("tool_use_id") in uses:
                    text = _text_of(b.get("content")).lstrip()
                    if not b.get("is_error") and text.startswith("Published"):
                        return True
    return False


def line_count(transcript):
    if not isinstance(transcript, str):
        return 0
    try:
        with open(transcript, "r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def _run_build(root, args):
    try:
        r = subprocess.run([sys.executable, os.path.join(root, BUILD_REL), "."] + args + ["--out", PAGE_REL],
                           cwd=root, capture_output=True, timeout=BUILD_TIMEOUT)
        return r.returncode == 0
    except Exception:
        return False


def build_page(root):
    """True when a build exited 0: first with --fetch, else once more without it (the page then says the GitHub
    data is unmeasured). False when there is no build script or both fail."""
    if not os.path.isfile(os.path.join(root, BUILD_REL)):
        return False
    if _run_build(root, ["--fetch"]):
        return os.path.isfile(os.path.join(root, PAGE_REL))
    if _run_build(root, []):
        return os.path.isfile(os.path.join(root, PAGE_REL))
    return False


def _project_root(payload):
    start = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    root = _git(start, "rev-parse", "--show-toplevel")
    return os.path.normpath(root) if root else None


def _eligible(payload):
    """The root of an attended, main-checkout, default-branch project; else None."""
    if os.environ.get("STATUS_PAGE_DUE") == "0":
        return None
    if os.environ.get("CLAUDE_CODE_SESSION_ATTENDED") != "1":
        return None
    root = _project_root(payload)
    if not root:
        return None
    if is_linked_worktree(root) or not on_default_branch(root):
        return None
    return root


def session_start_note(payload):
    root = _eligible(payload)
    if not root:
        return None
    url = _read_json(os.path.join(root, LINK_REL)).get("url")
    if isinstance(url, str) and url:
        return None
    return NO_LINK_NOTE


def _prune(sessions, now):
    for k in [k for k, v in sessions.items() if not isinstance(v, dict) or now - float(v.get("ts") or 0) > SESSION_TTL]:
        del sessions[k]


def decide(payload):
    """Return the block reason, or None to allow."""
    root = _eligible(payload)
    if not root:
        return None
    url = _read_json(os.path.join(root, LINK_REL)).get("url")
    if not isinstance(url, str) or not url:
        return None
    active = bool(payload.get("stop_hook_active"))
    fp = compute_fingerprint(root)
    state_path = os.path.join(root, STATE_REL)
    state = _read_state(state_path)
    if state is None:
        return None  # exists but unreadable: record nothing, block nothing (fail open)
    sessions = state.get("sessions")
    if not isinstance(sessions, dict):
        sessions = {}
        state["sessions"] = sessions
    now = time.time()
    _prune(sessions, now)
    sid = str(payload.get("session_id") or "")
    s = sessions.get(sid)
    if not isinstance(s, dict):
        s = {}
    sessions[sid] = s
    s["ts"] = now
    transcript = payload.get("transcript_path")
    pending = s.get("prompted_fp") and s.get("published_fp") != s.get("prompted_fp")
    start = int(s.get("mark_line") or 0)  # publish lines before this were already scanned (counted or not)
    credited = None
    if publish_seen(transcript, url, start):
        s["mark_line"] = line_count(transcript)
        if pending:  # only a publish that answers a prompt credits, and only the prompted fingerprint
            credited = s["prompted_fp"]
            s["published_fp"] = credited
    published = credited or state.get("published_fingerprint")
    if active or published == fp or s.get("prompted_fp") == fp or s.get("failed_fp") == fp:
        _save(state_path, sid, s, credited)  # record only; never block here
        return None
    if not build_page(root):
        s["failed_fp"] = fp  # do not pay for the same failing build at every later stop
        _save(state_path, sid, s, credited)
        return None
    s["prompted_fp"] = fp
    _save(state_path, sid, s, credited)
    return ("Stage changed: publish %s to %s once (Artifact publish, file_path + url); "
            "if refused as not viewed or identical, publish again." % (PAGE_REL, url))


def _save(state_path, sid, s, credited):
    """Re-read the state file and merge only THIS session's entry (and its credit) into it: another session may
    have written while this one was building (up to 80 s), and a blind write would drop its entry."""
    fresh = _read_state(state_path)
    if fresh is None:
        return  # exists but unreadable: skip the write rather than replace it with {}
    sessions = fresh.get("sessions")
    if not isinstance(sessions, dict):
        sessions = {}
        fresh["sessions"] = sessions
    sessions[sid] = s
    _prune(sessions, time.time())
    if credited:
        fresh["published_fingerprint"] = credited
        fresh["published_by"] = sid
    write_state(state_path, fresh)


def main():
    try:
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except ValueError:
            return
        if not isinstance(payload, dict):
            return
        if payload.get("agent_id"):
            return  # a subagent's hook input carries agent_id: silent by code, not only by wiring
        if "--session-start" in sys.argv[1:]:
            note = session_start_note(payload)
            if note:
                print(note)
            return
        reason = decide(payload)
        if reason:
            print(json.dumps({"decision": "block", "reason": reason}))
    except Exception:
        pass  # fail open: a broken hook must never trap a stop


if __name__ == "__main__":
    main()
    sys.exit(0)
