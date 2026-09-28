#!/usr/bin/env python3
"""evidence_claim_guard.py — Stop hook.

Generalized from a project-specific import (see capability.json `provenance`).
Behavior is unchanged from the source hook except: the default log path is now
project-relative (`.factory/logs/evidence-claim-misses.log`, resolved against
the hook's own `cwd` payload field, falling back to the current working
directory) instead of a fixed path under one user's home directory, and the
docstring's project-specific incident references were replaced with a generic
description of the mechanism. Behavior for every test case is identical.

Mechanism for the Defect-fix / honesty class: any assistant turn that CLAIMS
done/pass/green/verified/merged/deployed etc. must back that claim with an
evidence table naming a real tool call made THIS turn — not a restated
intention, not "trust me".

Reads Stop-hook stdin JSON (`transcript_path`, `session_id`, `stop_hook_active`,
`cwd`). If `stop_hook_active` is true -> exit 0 silently (prevents hook-loop
recursion). Off-switch `EVIDENCE_CLAIM_GUARD=0` -> no-op, no log, no output.

TURN SLICING: the transcript is JSONL, one record per line, each record has
`type` in {user, assistant, ...} and `message.content` = a string or a list
of content blocks (`type` in {text, tool_use, tool_result}). The FINAL turn
is everything after the LAST "real" user prompt — a `user` record whose
content is a plain string, OR a list containing NO `tool_result` block (a
`tool_result`-carrying user record is a tool reply, not a turn boundary, and
must never reset the turn). A two-pass streaming read: pass 1 finds the LINE
NUMBER of the last real user prompt without buffering the file; pass 2
re-streams and keeps only records after that line — bounded memory
regardless of transcript size.

From the final turn: `text` = the assistant text blocks joined in order;
`tools` = every tool_use block's (name, input) from this turn.

STEP 1 — is this a CLAIM turn? Regex (case-insensitive, word-boundary) on
`text`: done|complete[d]?|passe[sd]|passing|all green|green|verified|merged|
deployed|landed|shipped|fixed|works|working now|success(ful|fully)?.
Exempt (never a claim turn, no log line at all):
  - text shorter than 200 chars
  - text's FIRST LINE matches ^\\*Enhanced: no change or ^\\*Sync-check:
  - the last real user prompt is a slash-command turn: its content (string,
    or joined text blocks if a list) starts with "<command-name>" or a
    literal "/" (covers /end-session, /start-session, /continue and any
    other command)

STEP 2 — evidence table: find a markdown table in `text` whose header row
contains both "claim" and "evidence" (case-insensitive). Missing -> miss
class `no-evidence-table`.

STEP 3 — per data row, extract the Evidence cell's content: text inside the
first backtick span, else the text after the first colon, else the whole
cell; normalise whitespace. A row MATCHES if that normalised string (only
when >= 20 chars — the floor) is a case-insensitive substring of ONE
individual match value for this turn's tool_use calls, OR the cell contains
"unverified" (explicit honesty allowed), OR the cell contains "not run" or
"failed" (a reported failure allowed). The match values per tool call are:
its whole-input JSON dump (`json.dumps(input, ensure_ascii=False,
default=str)` — never `ensure_ascii=True`, which escapes non-ASCII like
em-dashes to `\\uXXXX` and breaks a literal-character citation), every
individual string value found recursively inside the input (dicts/lists
walked, each string leaf kept as its own candidate), and each of those
values again prefixed `"<tool name>:"`. Candidates are NEVER concatenated
across tool calls or across dict keys into one blob — a cell must be a
substring of exactly ONE such value, so a fragment that only "matches" by
spanning two unrelated tool calls (or an unrelated sibling field) never
counts. Any row matching none of these -> miss class `evidence-not-run`
(detail = first 60 chars of that cell).

STEP 4 — outcome. Default MODE is log-only: append one TSV line
`<iso ts>\\t<session_id>\\t<cwd>\\t<miss-class>\\t<detail[:80]>` to the log
file (override `EVIDENCE_CLAIM_LOG`; rotates to `.1` at 512 KB, overwriting
any previous `.1`). Compliant claim turns ALSO get one line, class
`claim-ok`, detail = matched row count (so a weekly hit-rate ratio is
computable — misses are not logged alone). Exit 0 always; no stdout unless
blocking.

If `EVIDENCE_CLAIM_BLOCK=1` and the outcome is a miss (not claim-ok):
additionally print `{"decision":"block","reason":"<one line>"}` to stdout —
for a Stop hook this makes Claude continue the turn instead of stopping.

Never block or log when: this is not a claim turn (silent, no log line at
all); `stop_hook_active` is true; the guard is switched off; the transcript
path is missing/unreadable (silent early exit, no log — this is normal, not
an error). On any unexpected exception: log `error` class (fail-open) and
exit 0 — a broken guard must never block a stop.

Python 3.9+ stdlib only (no third-party imports). Safe to run under
`python -I -S` (isolated mode) since it makes no third-party imports.
"""
import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone


def _default_log_path():
    """Project-relative log location: <cwd>/.factory/logs/evidence-claim-misses.log.
    Resolved lazily (inside main(), using the hook payload's own `cwd` when
    present) so the default never hard-codes any machine-specific path."""
    return os.path.join(".factory", "logs", "evidence-claim-misses.log")


LOG_PATH_OVERRIDE = os.environ.get("EVIDENCE_CLAIM_LOG")

LOG_MAX_BYTES = 512 * 1024

_REDACT_RE = re.compile(r"(ghp_\S*|sk-\S*|password=\S*|token=\S*)", re.IGNORECASE)


def _redact(text):
    return _REDACT_RE.sub("***", text or "")


def _resolve_log_path(payload_cwd):
    # Fix round 2 (2026-09-27): a session working in a SUBFOLDER of the project (payload_cwd is
    # that subfolder, not the project root) must still write the log under the project ROOT's
    # ignored folder, never a stray copy inside the subfolder. CLAUDE_PROJECT_DIR is the project
    # root Claude Code itself sets for every hook call, so it wins over payload_cwd; only when it
    # is unset do we fall back to payload_cwd, then the process cwd.
    if LOG_PATH_OVERRIDE:
        return LOG_PATH_OVERRIDE
    root_dir = "." + "factory"
    base = os.environ.get("CLAUDE_PROJECT_DIR") or payload_cwd or os.getcwd()
    return os.path.join(base, root_dir, "logs", "evidence-claim-misses.log")


def _rotate_log_if_needed(log_path):
    try:
        if os.path.exists(log_path) and os.path.getsize(log_path) >= LOG_MAX_BYTES:
            os.replace(log_path, log_path + ".1")
    except Exception:
        pass


def _log(miss_class, detail, session_id="", cwd="", log_path=None):
    try:
        resolved = log_path or _resolve_log_path(cwd)
        _rotate_log_if_needed(resolved)
        ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        line = "%s\t%s\t%s\t%s\t%s\n" % (
            ts,
            session_id or "",
            cwd or "",
            miss_class,
            _redact(detail or "")[:80],
        )
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        with open(resolved, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


CLAIM_RE = re.compile(
    r"\b(done|complete[d]?|passe[sd]|passing|all green|green|verified|merged|"
    r"deployed|landed|shipped|fixed|works|working now|success(ful|fully)?)\b",
    re.IGNORECASE,
)

EXEMPT_FIRST_LINE_RE = re.compile(r"^\*(Enhanced: no change|Sync-check:)", re.IGNORECASE)


def _is_user_turn_boundary(record):
    if record.get("type") != "user":
        return False
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                return False
        return True
    return False


def _prompt_text(record):
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
        return "\n".join(parts)
    return ""


def _is_slash_prompt(text):
    stripped = (text or "").lstrip()
    return stripped.startswith("<command-name>") or stripped.startswith("/")


def _find_last_boundary_line_number(path):
    boundary = -1
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for i, raw_line in enumerate(fh):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if _is_user_turn_boundary(record):
                boundary = i
    return boundary


def _collect_final_turn(path, boundary_line):
    text_parts = []
    tool_calls = []
    boundary_prompt_text = ""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for i, raw_line in enumerate(fh):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if i == boundary_line:
                boundary_prompt_text = _prompt_text(record)
            if i < boundary_line:
                continue
            if record.get("type") != "assistant":
                continue
            content = (record.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text_parts.append(block.get("text") or "")
                elif block.get("type") == "tool_use":
                    tool_calls.append((block.get("name") or "", block.get("input")))
    return "\n".join(text_parts), tool_calls, boundary_prompt_text


def _is_claim_turn(text):
    if len(text) < 200:
        return False
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if EXEMPT_FIRST_LINE_RE.match(first_line.strip()):
        return False
    return bool(CLAIM_RE.search(text))


_SEPARATOR_ROW_RE = re.compile(r"^[\s|:\-]+$")


def _find_evidence_rows(text):
    lines = text.splitlines()
    header_idx = None
    claim_idx = None
    evidence_idx = None
    for i, line in enumerate(lines):
        if "|" not in line:
            continue
        low = line.lower()
        if "claim" in low and "evidence" in low:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            c_idx = next((j for j, c in enumerate(cells) if "claim" in c.lower()), None)
            e_idx = next((j for j, c in enumerate(cells) if "evidence" in c.lower()), None)
            if c_idx is not None and e_idx is not None:
                header_idx = i
                claim_idx = c_idx
                evidence_idx = e_idx
                break
    if header_idx is None:
        return None

    rows = []
    j = header_idx + 1
    if j < len(lines) and lines[j].strip() and _SEPARATOR_ROW_RE.match(lines[j]):
        j += 1
    while j < len(lines):
        line = lines[j]
        stripped = line.strip()
        # The table ends at the first line that is not itself a table row —
        # a line must start with "|" (after optional leading whitespace) to
        # be consumed. Prose containing an unrelated "|" later in the line
        # (e.g. "roughly 3|4 of yesterday's run") must never be mistaken for
        # a continuation row.
        if not stripped.startswith("|"):
            break
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if evidence_idx < len(cells):
            rows.append(cells[evidence_idx])
        j += 1
    return rows


def _extract_evidence_text(cell):
    m = re.search(r"`([^`]+)`", cell)
    if m:
        return m.group(1)
    if ":" in cell:
        return cell.split(":", 1)[1]
    return cell


def _normalize(text):
    return re.sub(r"\s+", " ", text or "").strip()


EVIDENCE_FLOOR_CHARS = 20


def _row_matches(cell, match_values_lower):
    low_cell = cell.lower()
    if "unverified" in low_cell:
        return True
    if "not run" in low_cell or "failed" in low_cell:
        return True
    evidence_text = _normalize(_extract_evidence_text(cell))
    if len(evidence_text) < EVIDENCE_FLOOR_CHARS:
        return False
    needle = evidence_text.lower()
    for value in match_values_lower:
        if needle in value:
            return True
    return False


def _extract_string_values(obj, out):
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _extract_string_values(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _extract_string_values(v, out)


def _collect_match_values(tool_calls):
    """Per-tool-call match-value candidates — never concatenated across
    tool calls. Each tool call contributes its own whole-input JSON dump
    plus every string leaf found recursively inside it (and that leaf again
    prefixed "<name>:"), so a cell can only match a substring that genuinely
    belongs to ONE real value from ONE real tool call."""
    values = []
    for name, tool_input in tool_calls:
        try:
            dumped = json.dumps(tool_input, ensure_ascii=False, default=str)
        except Exception:
            dumped = str(tool_input)
        values.append(name + " " + dumped)

        leaves = []
        _extract_string_values(tool_input, leaves)
        for leaf in leaves:
            values.append(leaf)
            values.append(name + ":" + leaf)
    return values


def _block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))


def main():
    if os.environ.get("EVIDENCE_CLAIM_GUARD") == "0":
        return

    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(data, dict):
        return

    if data.get("stop_hook_active"):
        return

    session_id = data.get("session_id") or ""
    cwd = data.get("cwd") or ""
    transcript_path = data.get("transcript_path")
    if not transcript_path or not isinstance(transcript_path, str):
        return
    if not os.path.isfile(transcript_path):
        return

    boundary_line = _find_last_boundary_line_number(transcript_path)
    text, tool_calls, boundary_prompt_text = _collect_final_turn(transcript_path, boundary_line)

    if _is_slash_prompt(boundary_prompt_text):
        return

    if not _is_claim_turn(text):
        return

    rows = _find_evidence_rows(text)
    if not rows:
        _log("no-evidence-table", "", session_id, cwd)
        if os.environ.get("EVIDENCE_CLAIM_BLOCK") == "1":
            _block(
                "no-evidence-table: this claim turn needs a markdown table with "
                "Claim | Evidence columns naming a tool call made this turn"
            )
        return

    match_values_lower = [v.lower() for v in _collect_match_values(tool_calls)]
    failing_cell = None
    matched_count = 0
    for cell in rows:
        if _row_matches(cell, match_values_lower):
            matched_count += 1
        elif failing_cell is None:
            failing_cell = cell

    if failing_cell is not None:
        _log("evidence-not-run", failing_cell[:60], session_id, cwd)
        if os.environ.get("EVIDENCE_CLAIM_BLOCK") == "1":
            _block(
                "evidence-not-run: an Evidence cell doesn't reference a tool call made "
                "this turn — add the real command/result or mark it unverified/failed"
            )
        return

    _log("claim-ok", str(len(rows)), session_id, cwd)


def run_guarded():
    try:
        main()
    except Exception:
        _log("error", "internal-exception: " + traceback.format_exc().replace("\n", " | "))


if __name__ == "__main__":
    run_guarded()
    sys.exit(0)
