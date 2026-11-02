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
  - NO origin default ref exists (see below) and the project is a linked git worktree (git-dir != git-common-dir; if
    that cannot be told, assume linked) or its branch is not the default branch (origin/HEAD, else main or master);
  - Stop: views/status-page.json is missing or has no url; the fingerprint equals the published one; this session was
    already asked for this fingerprint; the page could not be built;
  - Stop with stop_hook_active true: it never blocks (no loop) but still RECORDS a publish seen in the transcript;
  - any error at all (the whole main is wrapped; a broken hook never traps a stop).

Origin's default branch (OD-130, REQ-064 AC-4): the hook resolves the commit of origin/HEAD, else origin/main, else
origin/master (the local remote-tracking ref; no network, no fetch). When it exists the hook works on ANY branch and in
a linked worktree: the fingerprint is computed from that commit, never from the working tree or HEAD (records are read
with one `git cat-file --batch`, merges are counted on that commit), and the page is built from that commit's tree:
`git archive <sha>` is extracted to a temp dir, and the CHECKOUT's tools/build_status_page.py runs against that dir
with `--code-root <checkout>` (records come from the archive; code state, gh/pull request data and the project name
come from the checkout), `--sha <short sha>` and `--out views/status-page.html` in the checkout (the history reads
of the records, e.g. file ages, find no history in the temp dir and read unmeasured; the checkout's tool is used so a stale tree cannot build with an older tool; if the
checkout has none, the archive's copy is used). The link (views/status-page.json, read from the checkout only: no
link there is silence) and the state file stay in the checkout. With no such ref (no origin, never fetched) today's reading stays: HEAD and the working tree, on the default
branch outside a linked worktree only. A ref that exists but whose archive cannot be made or built is a failed build:
silent, remembered per fingerprint. A ref that is old (fetch never run) is used as it is; a merge the session has not
fetched is not seen.

Fingerprint (local only, no network): sorted requirement, work item, plan step and owner-question statuses, the
number of plan change entries per plan, release ids, and the merge-commit count on the commit above (HEAD when there
is no origin ref). Hashed with sha256. Record
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
one rebuild without `--fetch`, 40 s; the archive step 15 s; all of it shares an 80 s budget). The hook's own wiring
timeout is 90 s.
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


def _front_text(text):
    m = re.match(r"---\r?\n(.*?)\r?\n---", text, re.S)
    return m.group(1) if m else ""


def _front(path):
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return ""
    return _front_text(text)


class _Commit:
    """The records of one commit, read with git only (never the working tree): `names` lists the files of a folder,
    `fronts` holds each file's frontmatter. One `cat-file --batch` process serves every file."""

    def __init__(self, root, sha):
        self.root, self.sha = root, sha
        out = _git(root, "ls-tree", "-r", "--name-only", sha, "--", "spec/requirements", "work", "owner-questions",
                   "plans", "releases")
        self.files = [ln for ln in (out or "").splitlines() if ln]
        self.fronts = {}
        paths = [f for f in self.files if f.endswith(".md")]
        if not paths:
            return
        r = subprocess.run(["git", "-C", root, "cat-file", "--batch"], capture_output=True, timeout=30,
                           input="".join("%s:%s\n" % (sha, f) for f in paths).encode("utf-8"))
        data, pos = r.stdout, 0
        for f in paths:
            nl = data.find(b"\n", pos)
            head = data[pos:nl].split() if nl >= 0 else []
            if len(head) != 3 or head[1] != b"blob":
                pos = nl + 1 if nl >= 0 else len(data)
                continue
            size = int(head[2])
            self.fronts[f] = _front_text(data[nl + 1:nl + 1 + size].decode("utf-8-sig", errors="replace"))
            pos = nl + 1 + size + 1

    def names(self, rel, prefix):
        return sorted(f for f in self.files if f.startswith(rel + "/") and "/" not in f[len(rel) + 1:]
                      and os.path.basename(f).startswith(prefix) and f.endswith(".md"))


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


def compute_fingerprint(root, sha=None):
    """From the working tree and HEAD, or (sha given) from that commit only."""
    parts = []
    com = _Commit(root, sha) if sha else None

    def files(rel, prefix):
        if com:
            return [(f, com.fronts.get(f, "")) for f in com.names(rel, prefix)]
        return [(p, None) for p in _listdir(root, rel, prefix)]

    def front(item):
        return item[1] if com else _front(item[0])

    for rel, prefix in (("spec/requirements", "REQ-"), ("work", "W-"), ("owner-questions", "OQ-")):
        for it in files(rel, prefix):
            m = STATUS_RE.search(front(it))
            parts.append("%s/%s=%s" % (rel, os.path.basename(it[0]), m.group(1) if m else "?"))
    for it in files("plans", "PL-"):
        p = it[0]
        fm = front(it)
        m = STATUS_RE.search(fm)
        steps = []
        for item in _section_items(fm, "steps"):
            sm = ITEM_STATUS_RE.search(item)
            steps.append(sm.group(1) if sm else "?")
        parts.append("plans/%s=%s|steps=%s|changes=%d" % (os.path.basename(p), m.group(1) if m else "?",
                                                          ",".join(steps), len(_section_items(fm, "changes"))))
    for it in files("releases", "R-"):
        parts.append("releases/%s" % os.path.basename(it[0]))
    merges = _git(root, "rev-list", "--merges", "--count", sha or "HEAD")
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


BUDGET = 80
ARCHIVE_TIMEOUT = 15


def _run_build(root, args, src=None, timeout=BUILD_TIMEOUT, script=None):
    try:
        code = ["--code-root", root] if src else []
        r = subprocess.run([sys.executable, script or os.path.join(root, BUILD_REL), src or "."] + args + code
                           + ["--out", PAGE_REL], cwd=root, capture_output=True, timeout=timeout)
        return r.returncode == 0
    except Exception:
        return False


def build_page(root, src=None, sha=None, started=None):
    """True when a build exited 0: first with --fetch, else once more without it (the page then says the GitHub
    data is unmeasured). False when there is no build script or both fail. With `src` (a directory holding a
    commit's tree) the checkout's script renders that directory and the page lands in the checkout; `sha` is the
    commit's short id for the page. `started` is when the whole hook step began (the 80 s budget)."""
    script = os.path.join(root, BUILD_REL)
    if src and not os.path.isfile(script):
        script = os.path.join(src, BUILD_REL)  # the checkout has no tool: use the commit's own
    if not os.path.isfile(script):
        return False
    t0 = started if started is not None else time.time()
    extra = ["--sha", sha] if sha else []
    for args in (["--fetch"], []):
        left = min(BUILD_TIMEOUT, BUDGET - (time.time() - t0))
        if left < 1:
            return False
        if _run_build(root, args + extra, src, left, script):
            return os.path.isfile(os.path.join(root, PAGE_REL))
    return False


def _extract_archive(root, sha, dest):
    """Write the tree of `sha` into `dest` (regular files only, names confined to dest). True on success."""
    import tarfile
    r = subprocess.run(["git", "-C", root, "archive", "--format=tar", sha], capture_output=True,
                       timeout=ARCHIVE_TIMEOUT)
    if r.returncode != 0:
        return False
    import io
    base = os.path.realpath(dest)
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
        for m in tf:
            if not m.isreg():
                continue
            target = os.path.realpath(os.path.join(base, m.name))
            if not target.startswith(base + os.sep):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as out:
                out.write(tf.extractfile(m).read())
    return True


def build_page_from_commit(root, sha):
    """Build the page from the tree of `sha` (archive into a temp dir), writing it into the checkout. False when
    the archive or the build fails."""
    t0 = time.time()
    try:
        with tempfile.TemporaryDirectory(prefix="status-page-src.") as tmp:
            if not _extract_archive(root, sha, tmp):
                return False
            short = _git(root, "rev-parse", "--short", sha)
            return build_page(root, src=tmp, sha=short, started=t0)
    except Exception:
        return False


def origin_default_sha(root):
    """The commit of origin's default branch as this clone last saw it: origin/HEAD, else origin/main, else
    origin/master; None when none of them resolves."""
    for ref in ("refs/remotes/origin/HEAD", "refs/remotes/origin/main", "refs/remotes/origin/master"):
        sha = _git(root, "rev-parse", "--verify", "-q", ref + "^{commit}")
        if sha:
            return sha
    return None


def _project_root(payload):
    start = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    root = _git(start, "rev-parse", "--show-toplevel")
    return os.path.normpath(root) if root else None


def _eligible(payload):
    """(root, sha) of an attended project; sha is origin's default-branch commit (any branch, any worktree) or None,
    and then the project must be a main checkout on its default branch. (None, None) when not eligible."""
    if os.environ.get("STATUS_PAGE_DUE") == "0":
        return None, None
    if os.environ.get("CLAUDE_CODE_SESSION_ATTENDED") != "1":
        return None, None
    root = _project_root(payload)
    if not root:
        return None, None
    sha = origin_default_sha(root)
    if sha:
        return root, sha
    if is_linked_worktree(root) or not on_default_branch(root):
        return None, None
    return root, None


def _link_url(root, sha):
    """The stored link: the checkout's file only (no link there means no link: silent)."""
    return _read_json(os.path.join(root, LINK_REL)).get("url")


def session_start_note(payload):
    root, sha = _eligible(payload)
    if not root:
        return None
    url = _link_url(root, sha)
    if isinstance(url, str) and url:
        return None
    return NO_LINK_NOTE


def _prune(sessions, now):
    for k in [k for k, v in sessions.items() if not isinstance(v, dict) or now - float(v.get("ts") or 0) > SESSION_TTL]:
        del sessions[k]


def decide(payload):
    """Return the block reason, or None to allow."""
    root, sha = _eligible(payload)
    if not root:
        return None
    url = _link_url(root, sha)
    if not isinstance(url, str) or not url:
        return None
    active = bool(payload.get("stop_hook_active"))
    fp = compute_fingerprint(root, sha)
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
    if not (build_page_from_commit(root, sha) if sha else build_page(root)):
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
            payload = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace") or "{}")
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
