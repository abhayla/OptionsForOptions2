#!/usr/bin/env python3
"""answer_writeback_guard.py — Stop hook (REQ-049 AC-3, OD-69).

Every owner answer goes back into the spec before the turn ends (spec-first R4). This hook reads the session
transcript and blocks the stop ONCE when the owner answered a question-tool call in this session and no write to
the decision log happened after the latest such answer, unless the session said `No spec change: <reason>` after
that answer.

Transcript shapes (read from a real interactive transcript, 2026-10-02; a trimmed copy is the test fixture
tests/fixtures/answer_writeback/real_lines.jsonl):
  - the question: an `assistant` record whose message.content holds {"type": "tool_use", "name": "AskUserQuestion",
    "id": <id>, "input": {"questions": [...]}};
  - the answer: a `user` record whose message.content holds {"type": "tool_result", "tool_use_id": <that id>,
    "content": "Your questions have been answered: ..."} (content may also be a list of text blocks). A rejected or
    interrupted question has a different text or `is_error: true` and is not an answer. The same words inside some
    other tool's input or output are not an answer either: the tool_use_id must be a question's id;
  - a write, counted only when its tool_result is not an error:
      * an Edit, Write, MultiEdit or NotebookEdit whose `file_path` (or `notebook_path`; either slash) ends in
        docs/spec/decisions.md or names a decision RECORD under spec/decisions/ (`<PREFIX>-<number>....md`, e.g.
        ADR-004.md; README.md and other files there do not count);
      * a Bash or PowerShell call whose command text names the log by path (docs/spec/decisions.md,
        or a decision record under spec/decisions/, not a README) AND writes: a redirect whose target is that path
        (> or >>, not 2>&1), tee, sed -i, Set-Content, Add-Content, Out-File, a python open( with mode a/w/x, or
        .write( (OD-69 itself was appended by a python heredoc with open(p, 'a') on docs/spec/decisions.md). A read
        (grep, cat, git diff) does not count.
The decision is made from transcript tool calls only; file times are never read (a checkout or pull touching the
file is not a write-back).

Decision:
  - stop_hook_active true -> allow (the block happens once; never a loop);
  - transcript missing or unreadable, or the payload unreadable -> allow (fail open);
  - no answered question -> allow;
  - a decision-log write after the latest answer -> allow;
  - any assistant text after the latest answer, or `last_assistant_message`, has a line starting `No spec change:` followed by
    a reason -> allow (so a later turn of the same session is not blocked again);
  - otherwise print {"decision": "block", "reason": ...} on stdout (exit 0), which makes Claude continue the turn.

Off-switch: ANSWER_WRITEBACK_GUARD=0. Any unexpected error allows the stop. Python 3.9+ stdlib only.
"""
import json
import os
import re
import sys

QUESTION_TOOL = "AskUserQuestion"
ANSWER_PREFIX = "Your questions have been answered"
FILE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")
NO_CHANGE_RE = re.compile(r"(?m)^\s*No spec change:\s*\S")
OD_LOG_TAIL = "docs/spec/decisions.md"
# a decision record under spec/decisions/: <PREFIX>-<number>[anything].md
ADR_RECORD_RE = re.compile(r"(?:^|[/\s\"'=])spec/decisions/[A-Za-z]+-\d+[^/\s\"']*\.md(?![\w])")
# a shell command names the log by PATH (never just any file ending in decisions.md) ...
_LOG_PATH = r"(?:docs/spec/decisions\.md(?![\w])|spec/decisions/[A-Za-z]+-\d+[^/\s\"']*\.md(?![\w]))"
SHELL_LOG_RE = re.compile(r"(?<![\w.-])" + _LOG_PATH)
# ... and WRITES: a redirect whose target is that path (not 2>&1), tee, sed -i, Set/Add-Content, Out-File, a python
# open() with mode a/w/x, or .write(
SHELL_REDIRECT_RE = re.compile(r"(?<![\d&<])>>?\s*[\"']?[^\s\"'|;&<>]*(?<![\w.-])" + _LOG_PATH)
SHELL_WRITE_RES = (
    re.compile(r"\btee\b"),
    re.compile(r"\bsed\b[^\n|;&]*\s-[A-Za-z]*i"),
    re.compile(r"\b(?:Set-Content|Add-Content|Out-File)\b", re.I),
    re.compile(r"\bopen\(\s*[^,()]+,\s*(?:mode\s*=\s*)?['\"][awx][bt+]*['\"]"),
    re.compile(r"\bopen\([^()]*\bmode\s*=\s*['\"][awx][bt+]*['\"]"),
    re.compile(r"\.write\("),
)


def is_decision_log(path):
    if not isinstance(path, str) or not path:
        return False
    p = path.replace("\\", "/")
    return p == OD_LOG_TAIL or p.endswith("/" + OD_LOG_TAIL) or bool(ADR_RECORD_RE.search(p))


def shell_names_decision_log(command):
    if not isinstance(command, str) or not command:
        return False
    c = command.replace("\\", "/")
    if SHELL_REDIRECT_RE.search(c):
        return True
    return bool(SHELL_LOG_RE.search(c)) and any(r.search(c) for r in SHELL_WRITE_RES)


def result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text") or "" for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def scan(path):
    """One streaming pass. Returns (latest answer (index, text) or None, write indices, [(index, assistant text)])."""
    questions = set()
    answer = None
    writes = {}      # tool_use_id -> record index
    failed = set()   # tool_use_ids whose result is an error
    texts = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for idx, raw in enumerate(fh):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            content = (rec.get("message") or {}).get("content") if isinstance(rec.get("message"), dict) else None
            if not isinstance(content, list):
                continue
            if rec.get("type") == "assistant":
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text":
                        texts.append((idx, b.get("text") or ""))
                    elif b.get("type") == "tool_use":
                        name = b.get("name")
                        inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                        if name == QUESTION_TOOL:
                            questions.add(b.get("id"))
                        elif name in FILE_TOOLS and is_decision_log(inp.get("file_path") or inp.get("notebook_path")):
                            writes[b.get("id")] = idx
                        elif name in SHELL_TOOLS and shell_names_decision_log(inp.get("command")):
                            writes[b.get("id")] = idx
            elif rec.get("type") == "user":
                for b in content:
                    if not isinstance(b, dict) or b.get("type") != "tool_result":
                        continue
                    tid = b.get("tool_use_id")
                    if b.get("is_error"):
                        failed.add(tid)
                        continue
                    if tid in questions and result_text(b.get("content")).lstrip().startswith(ANSWER_PREFIX):
                        answer = (idx, result_text(b.get("content")))
    write_idx = [i for tid, i in writes.items() if tid not in failed]
    return answer, write_idx, texts


def main():
    if os.environ.get("ANSWER_WRITEBACK_GUARD") == "0":
        return
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        return
    if not isinstance(data, dict) or data.get("stop_hook_active"):
        return
    path = data.get("transcript_path")
    if not isinstance(path, str) or not os.path.isfile(path):
        return
    try:
        answer, write_idx, texts = scan(path)
    except OSError:
        return
    if answer is None:
        return
    a_idx, a_text = answer
    if any(i > a_idx for i in write_idx):
        return
    later = [t for i, t in texts if i > a_idx]
    final = data.get("last_assistant_message")
    if isinstance(final, str):
        later.append(final)
    if any(NO_CHANGE_RE.search(t or "") for t in later):
        return
    shown = " ".join(a_text.split())[:160]
    reason = ("The owner answered a question this session (%s) and no decision row was written after it "
              "(answer-writeback guard, REQ-049). Write the answer into the decision log now (an OD row in "
              "docs/spec/decisions.md, or a record in spec/decisions/), or, if the answer changes nothing in the "
              "spec, end your message with `No spec change: <reason>`." % shown)
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail open: a broken guard must never trap a stop
    sys.exit(0)
