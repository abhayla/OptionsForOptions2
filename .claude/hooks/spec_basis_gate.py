#!/usr/bin/env python3
"""spec_basis_gate.py — PreToolUse hook, matcher: AskUserQuestion (REQ-049 AC-2, OD-69).

Every question put to the owner must say which part of the spec it rests on, so a question the spec already
answers is never asked. The hook reads the question tool's call and refuses it (exit 2, reason on stderr) when ANY
question's text:

  (a) has no `Spec basis:` label;
  (b) has one that cites no existing requirement or decision id and is not `none ... (searched: <terms>)`;
  (c) cites an id that does not exist in the spec (named in the refusal).

A cited id is a token whose prefix is a known id family (REQ, OD, ADR, or the prefix of any requirement or
decision id the spec holds) followed by `-<digits>`; other tokens such as `AC-2` or `W-026` are not ids here.
Ids compare by prefix (any case) and number value: od-37, OD-037 and OD-37 are one id; REQ-40 is REQ-040.
Existing ids are the union over CLAUDE_PROJECT_DIR and the payload's cwd (a worktree may hold a row the project
root does not have yet), read through tools/spec_text.py (the one spec reader): spec/requirements/REQ-*.md, the Factory's
docs/spec/decisions.md rows and a project's spec/decisions/*.md records. The refusal names views/spec-digest.md and
lists up to 3 word-match hits (spec_text's tokenizer and score) for the question text.

A question that passes is allowed with no output.

Fail-open (exit 0, no output) on our own problems, because a broken guard must never stop the owner being asked:
unreadable or non-JSON stdin, a payload that is not the question tool, no `questions` list, the project root not
found, no spec (no requirement folder and no decision log), no views/spec-digest.md, tools/spec_text.py missing or
not importable (it needs PyYAML), or any unexpected error.

Off-switch: SPEC_BASIS_GATE=0 allows everything.

Block mechanism: exit 2 with plain text on stderr; a JSON deny with exit 0 can be overridden by another hook's
allow (finding json-deny-overridden-by-another-hooks-allow).
"""
import json
import os
import re
import sys

DIGEST_REL = os.path.join("views", "spec-digest.md")
BASIS_RE = re.compile(r"spec\s+basis\s*:", re.IGNORECASE)
ID_TOKEN_RE = re.compile(r"\b([A-Za-z]+)-(\d+)\b")
NONE_RE = re.compile(r"^[\s*_`\"'(\[]*none\b", re.IGNORECASE)
SEARCHED_RE = re.compile(r"\(\s*searched\s*:\s*[^)\s][^)]*\)", re.IGNORECASE)
BASE_FAMILIES = ("REQ", "OD", "ADR")
MAX_HITS = 3


class FailOpen(Exception):
    """Our own problem (missing spec, digest or helper): allow the question."""


def project_roots(data):
    """CLAUDE_PROJECT_DIR and the payload's cwd (a worktree may hold rows the project root does not yet)."""
    roots, seen = [], set()
    for cand in (os.environ.get("CLAUDE_PROJECT_DIR"), data.get("cwd")):
        if isinstance(cand, str) and cand and os.path.isdir(cand):
            key = os.path.normcase(os.path.abspath(cand))
            if key not in seen:
                seen.add(key)
                roots.append(cand)
    if not roots:
        raise FailOpen("no project root")
    return roots


def id_key(prefix, number):
    """Canonical id: prefix case-folded, number by value (od-37 == OD-37, REQ-40 == REQ-040, ADR-4 == ADR-004)."""
    return (prefix.upper(), int(number))


def record_key(rid):
    m = ID_TOKEN_RE.fullmatch(str(rid).strip())
    return id_key(m.group(1), m.group(2)) if m else None


def load_all(roots):
    """(spec_text, records): the first root with spec, digest and helper is the primary; the records of every other
    root that holds a spec are added (union). Raises FailOpen when no root is complete."""
    primary = None
    for root in roots:
        try:
            primary = (root,) + load_spec(root)
            break
        except FailOpen:
            continue
    if primary is None:
        raise FailOpen("no complete root")
    root0, spec_text, records = primary
    for root in roots:
        if root == root0:
            continue
        try:
            records = records + spec_text.load_records(spec_text.Source(root))
        except Exception:
            pass  # a second root we cannot read adds nothing; it never causes a refusal of its own
    return spec_text, records


def load_spec(root):
    """(spec_text module, records). Raises FailOpen when the spec, the digest or the helper is missing."""
    has_spec = (os.path.isdir(os.path.join(root, "spec", "requirements"))
                or os.path.isfile(os.path.join(root, "docs", "spec", "decisions.md"))
                or os.path.isdir(os.path.join(root, "spec", "decisions")))
    if not has_spec:
        raise FailOpen("no spec")
    if not os.path.isfile(os.path.join(root, DIGEST_REL)):
        raise FailOpen("no digest")
    helper = os.path.join(root, "tools", "spec_text.py")
    if not os.path.isfile(helper):
        raise FailOpen("no helper")
    sys.dont_write_bytecode = True  # never leave a __pycache__ folder in the project's tools/
    sys.path.insert(0, os.path.dirname(helper))
    try:
        import spec_text  # noqa: E402  (the one spec reader, REQ-009)
        records = spec_text.load_records(spec_text.Source(root))
    except Exception as exc:  # ImportError (no PyYAML), unreadable files: our problem, not the question's
        raise FailOpen("helper failed: %s" % exc)
    return spec_text, records


def basis_verdict(text, ids, families):
    """None when the question's basis is valid, else the reason it is not."""
    m = BASIS_RE.search(text)
    if not m:
        return "no `Spec basis:` line"
    basis = text[m.end():]
    cited = [(p, n) for p, n in ID_TOKEN_RE.findall(basis) if p.upper() in families]
    unknown = sorted(set("%s-%s" % (p, n) for p, n in cited if id_key(p, n) not in ids))
    if unknown:
        return "cites id(s) not in the spec: %s" % ", ".join(unknown)
    if cited:
        return None
    if NONE_RE.match(basis) and SEARCHED_RE.search(basis):
        return None
    if NONE_RE.match(basis):
        return "`Spec basis: none` without `(searched: <terms>)`"
    return "the `Spec basis:` line cites no requirement or decision id"


def word_hits(spec_text, records, text):
    query = spec_text.words(text)
    scored = []
    for rec in records:
        for item in rec.items:
            s = spec_text.score(query, item.words)
            if s > 0:
                scored.append((s, item.label, item.text))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[:MAX_HITS]


def main():
    if os.environ.get("SPEC_BASIS_GATE") == "0":
        return 0
    try:  # spec text carries non-ASCII; a Windows console codepage must not turn a refusal into a crash
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        data = json.loads(raw)
    except Exception:
        return 0
    if not isinstance(data, dict) or data.get("tool_name") != "AskUserQuestion":
        return 0
    tool_input = data.get("tool_input")
    questions = tool_input.get("questions") if isinstance(tool_input, dict) else None
    if not isinstance(questions, list) or not questions:
        return 0  # not a question-tool call we can read: the tool itself rejects a malformed one
    try:
        spec_text, records = load_all(project_roots(data))
    except FailOpen:
        return 0
    ids = set(k for k in (record_key(r.id) for r in records) if k)
    families = set(BASE_FAMILIES) | set(k[0] for k in ids)

    bad = []
    for pos, q in enumerate(questions, 1):
        text = q.get("question") if isinstance(q, dict) else None
        text = text if isinstance(text, str) else ""
        why = basis_verdict(text, ids, families)
        if why:
            bad.append((pos, text, why))
    if not bad:
        return 0

    lines = ["Question refused (spec-basis gate, REQ-049): every owner question needs a `Spec basis:` line citing "
             "real requirement or decision ids, or `Spec basis: none (searched: <terms>)`."]
    for pos, text, why in bad:
        lines.append("- question %d: %s" % (pos, why))
        m = BASIS_RE.search(text)
        hits = word_hits(spec_text, records, text[: m.start()] if m else text)
        if hits:
            lines.append("  word-match hits (a second check, not a substitute for reading the digest):")
            for s, label, item_text in hits:
                lines.append("  %.2f %s: %s" % (s, label, item_text[:160]))
    lines.append("Read views/spec-digest.md (one line per decision, requirement and spec section), cite what "
                 "applies, and ask only what the spec leaves open.")
    sys.stderr.write("\n".join(lines) + "\n")
    return 2


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        code = 0  # fail open: a crash must never block the owner being asked
    sys.exit(code)
