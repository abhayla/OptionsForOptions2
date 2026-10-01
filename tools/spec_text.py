#!/usr/bin/env python3
"""spec_text.py — the ONE tokenizer and spec-item reader shared by spec_similar.py and spec_dupes.py (REQ-009).

Both tools must score text the same way, or the lookup a writer runs before writing (spec_similar) would disagree
with the check CI runs after (spec_dupes). The tokenizer reproduces the M4.1 core-proof spike exactly, because the
0.40 blocking threshold (OD-38) was measured with it:

- lowercase; words = regex ``[a-z][a-z\\-]{2,}``;
- drop the STOP words below;
- stem by stripping the first matching suffix of SUFFIXES when at least 4 letters remain;
- score = |A & B| / |A | B| over the two word SETS (Jaccard);
- an item with fewer than MIN_WORDS content words is never compared.

Spec items (what is compared; same kind only, OD-32):
- requirement items: each requirement's ``statement`` and each acceptance-criterion ``text``;
- decision items: sentences of each ``spec/decisions/*.md`` body (after the frontmatter), split on sentence ends and
  list bullets, keeping sentences of >= 5 content words and skipping Markdown heading lines (OD-38); for a repo that keeps an
  owner-decision log at ``docs/spec/decisions.md`` (the Factory), each ``| OD-n |`` row's decision cell split on
  ``.`` / ``;``.

A Source abstracts where files come from: the working tree, or (for tooling and tests) a git ref.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

WORD_RE = re.compile(r"[a-z][a-z\-]{2,}")
STOP = frozenset(
    "a an the and or of to in on for is are be by with as at from that this it its not no any every each can may "
    "must should will their they them into than then when which who whose all only also new has have per via v1 so "
    "if user users".split()
)
SUFFIXES = ("ations", "ation", "ings", "ing", "ies", "ied", "ed", "es", "s", "ly")
MIN_STEM = 4
MIN_WORDS = 4
MIN_SENTENCE_WORDS = 5
THRESHOLD = 0.40  # OD-38: block at >= 0.40 word overlap

ADR_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n\s*[-*]\s+")
OD_SPLIT_RE = re.compile(r"(?<=[.;])\s+")
OD_ROW_RE = re.compile(r"^\|\s*(OD-\d+)\s*\|")
# "(distinct from OD-12: <the difference>)" inside a Factory OD row's decision cell
# "(distinct from OD-12 #<fp>: <the difference>)" inside a Factory OD row's decision cell; the difference may hold
# one level of nested brackets; a note without "#<fp>" still parses (so it can be reported as lacking one).
OD_NOTE_RE = re.compile(r"\(distinct from ([A-Za-z]+-\d+)(?:\s+#([0-9a-f]{12}))?\s*:\s*((?:[^()]|\([^()]*\))*)\)")
_DELIM_RE = re.compile(r"(?m)^---[ \t]*\r?$")

REQ_DIR = "spec/requirements"
ADR_DIR = "spec/decisions"
OD_LOG = "docs/spec/decisions.md"
OD_CELLS = 5  # id, date, decision, owner's words, changes


def stem(word: str) -> str:
    for suf in SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= MIN_STEM:
            return word[: -len(suf)]
    return word


def normalize(text: str) -> str:
    """NFKC (full-width, ligatures, no-break space -> plain) and drop invisible format characters (Unicode category
    Cf, e.g. a zero-width space), so neither can split a word and hide a restatement. No homoglyph mapping."""
    text = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def canon(text: str) -> str:
    """Canonical text for identity (never for scoring): normalized, casefolded, whitespace collapsed. Keeps digits
    and punctuation, which the tokenizer drops."""
    return " ".join(normalize(text).casefold().split())


def fingerprint(*texts: str) -> str:
    """First 12 hex of sha256 over the canonical texts, sorted (order-free for a pair)."""
    return hashlib.sha256("\x1f".join(sorted(canon(t) for t in texts)).encode("utf-8")).hexdigest()[:12]


def words(text: str) -> frozenset[str]:
    text = normalize(text)
    return frozenset(stem(w) for w in WORD_RE.findall(text.lower()) if w not in STOP)


def score(a: frozenset[str], b: frozenset[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


# A Markdown heading LINE: first non-space character '#', followed by a space or another '#'. "#1 ..." is not one.
HEADING_LINE_RE = re.compile(r"^[ \t]*#(?:#|[ \t]|$)")


def is_heading(text: str) -> bool:
    return bool(HEADING_LINE_RE.match(text))


def parse_frontmatter(text: str) -> tuple[dict | None, str, str | None]:
    """(frontmatter mapping or None, body, error or None). No leading '---' = no frontmatter, not an error; a
    frontmatter that is unclosed, not YAML or not a mapping is an error (never skipped silently)."""
    if not text.startswith("---"):
        return None, text, None
    delims = list(_DELIM_RE.finditer(text))
    if len(delims) < 2:
        return None, text, "frontmatter is not closed by a '---' line"
    body = text[delims[1].end():]
    try:
        data = yaml.safe_load(text[delims[0].end():delims[1].start()])
    except yaml.YAMLError as exc:
        return None, body, "invalid YAML: " + " ".join(str(exc).split())
    if not isinstance(data, dict):
        return None, body, "frontmatter is not a mapping"
    return data, body, None


def split_frontmatter(text: str) -> tuple[dict | None, str]:
    """(frontmatter mapping or None, body). Delimiter = a line that is exactly '---'."""
    data, body, _err = parse_frontmatter(text)
    return data, body


@dataclass(frozen=True)
class Item:
    kind: str          # "requirement" | "decision"
    owner: str         # record id: REQ-009, ADR-021, OD-12
    label: str         # item id shown in output: "REQ-009 AC-7", "ADR-021 s4", "OD-12 s2"
    text: str
    words: frozenset = field(compare=False)


@dataclass
class Record:
    kind: str
    id: str
    path: str
    raw: str                      # the whole record text (file, or OD row) to detect a changed decision
    data: dict                    # frontmatter (requirements, ADRs); {"decision": cell} for an OD row
    items: list
    pin_text: str = ""            # decisions: the text a pin fingerprints (exemption notes removed)


class Source:
    """Reads spec files from the working tree (ref=None) or from a git ref. Records that cannot be read are collected
    in `problems` as (path, reason), so a check can block on them instead of skipping them."""

    def __init__(self, root: Path, ref: str | None = None):
        self.root = Path(root)
        self.ref = ref
        self._listing: list[str] | None = None
        self.problems: list[tuple[str, str]] = []

    def _git(self, *args: str) -> str:
        out = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if out.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
        return out.stdout

    def list(self, folder: str, pattern: str) -> list[str]:
        if self.ref is None:
            base = self.root / folder
            return sorted(p.relative_to(self.root).as_posix() for p in base.glob(pattern)) if base.is_dir() else []
        if self._listing is None:
            self._listing = self._git("ls-tree", "-r", "--name-only", self.ref).splitlines()
        rx = re.compile(re.escape(folder + "/") + pattern.replace(".", r"\.").replace("*", r"[^/]*") + "$")
        return sorted(p for p in self._listing if rx.match(p))

    def commit_date(self) -> str | None:
        """YYYY-MM-DD committer date of the ref (None for the working tree)."""
        return self._git("show", "-s", "--format=%cs", self.ref).strip() if self.ref else None

    def read(self, rel: str) -> str | None:
        if self.ref is None:
            p = self.root / rel
            return p.read_text(encoding="utf-8") if p.is_file() else None
        try:
            return self._git("show", f"{self.ref}:{rel}")
        except RuntimeError:
            return None


def _make(kind: str, owner: str, label: str, text: str) -> Item:
    text = " ".join(str(text).split())
    return Item(kind, owner, label, text, words(text))


def requirement_records(src: Source) -> list[Record]:
    out = []
    for rel in src.list(REQ_DIR, "REQ-*.md"):
        raw = src.read(rel) or ""
        data, _body, err = parse_frontmatter(raw)
        if err or data is None:
            src.problems.append((rel, err or "no YAML frontmatter"))
            continue
        rid = str(data.get("id") or Path(rel).stem)
        items = []
        if data.get("statement"):
            items.append(_make("requirement", rid, f"{rid} statement", data["statement"]))
        for pos, ac in enumerate(data.get("acceptance_criteria") or [], 1):
            if isinstance(ac, dict) and ac.get("text"):
                # a criterion without an id gets a unique positional label, never a shared "AC-?"
                label = str(ac["id"]) if ac.get("id") else f"criterion#{pos}"
                items.append(_make("requirement", rid, f"{rid} {label}", ac["text"]))
        out.append(Record("requirement", rid, rel, raw, data, items))
    return out


def decision_sentences(body: str) -> list[str]:
    """Sentences of a decision body with at least MIN_SENTENCE_WORDS content words (tokenizer words, as the spike
    counted them). Heading LINES are removed first and act as a break, so the sentence right after a heading is kept
    as its own item (OD-38 excludes headings, never the prose under them)."""
    blocks, cur = [], []
    fence = None
    for line in body.splitlines():
        m = re.match(r"^[ \t]*(```+|~~~+)", line)
        if m:  # a '#' line inside a fenced code block is content, not a heading
            fence = None if fence and m.group(1)[0] == fence else (fence or m.group(1)[0])
        if fence is None and not m and is_heading(line):
            blocks.append("\n".join(cur))
            cur = []
        else:
            cur.append(line)
    blocks.append("\n".join(cur))
    out = []
    for block in blocks:
        out += [x.strip() for x in ADR_SPLIT_RE.split(block) if len(words(x)) >= MIN_SENTENCE_WORDS]
    return out


def adr_records(src: Source) -> list[Record]:
    out = []
    for rel in src.list(ADR_DIR, "*.md"):
        raw = src.read(rel) or ""
        data, body, err = parse_frontmatter(raw)
        if err:
            src.problems.append((rel, err))
            continue
        if data is None:
            if re.match(r"(?i)(ADR|OD)-\d+", Path(rel).name):
                src.problems.append((rel, "no YAML frontmatter"))
            continue  # README and other non-record files carry no frontmatter
        rid = str(data.get("id") or Path(rel).stem)
        items = [_make("decision", rid, f"{rid} s{i}", s) for i, s in enumerate(decision_sentences(body), 1)]
        # pin text: every frontmatter field except the exemption notes, plus the body
        # (`changes`, the record's relations, is excluded like the OD log's Changes cell: editing relations never
        # stales a pin; the amends rule in spec_dupes covers what a relation means for citing requirements)
        kept = {k: v for k, v in data.items() if k not in ("distinct_from", "changes")}
        pin = yaml.safe_dump(kept, sort_keys=True, allow_unicode=True, default_flow_style=False) + "\n" + body
        out.append(Record("decision", rid, rel, raw, data, items, pin))
    return out


def od_cells(line: str) -> list[str]:
    """Split a Markdown table row on unescaped pipes."""
    cells = re.split(r"(?<!\\)\|", line.strip())
    return [c.strip() for c in cells[1:-1]]


def od_records(src: Source) -> list[Record]:
    raw_log = src.read(OD_LOG)
    if raw_log is None:
        return []
    out = []
    for lineno, line in enumerate(raw_log.splitlines(), 1):
        m = OD_ROW_RE.match(line)
        if not m:
            continue
        cells = od_cells(line)
        decision = cells[2] if len(cells) > 2 else ""
        rid = m.group(1)
        # A "(distinct from OD-n: ...)" note is the writer's answer to this check, not decision text to compare.
        text = OD_NOTE_RE.sub(" ", decision)
        items = [_make("decision", rid, f"{rid} s{i}", s)
                 for i, s in enumerate((x for x in OD_SPLIT_RE.split(text) if len(words(x)) >= MIN_SENTENCE_WORDS), 1)]
        changes = cells[4] if len(cells) > 4 else ""
        out.append(Record("decision", rid, OD_LOG, line,
                          {"decision": decision, "line": lineno, "cells": len(cells), "changes": changes}, items, text))
    return out


def load_records(src: Source) -> list[Record]:
    return requirement_records(src) + adr_records(src) + od_records(src)


def utf8_stdout() -> None:
    """Spec text carries non-ASCII (₹, —); a Windows console codepage must not crash the report."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def comparable(item: Item) -> bool:
    """Items that take part in a comparison: at least MIN_WORDS content words (heading lines never become items)."""
    return len(item.words) >= MIN_WORDS
