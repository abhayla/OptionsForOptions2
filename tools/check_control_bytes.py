#!/usr/bin/env python3
"""Fail on control bytes in tracked text files (REQ-063 AC-3, harvest issue 174).

A byte below 0x20 other than tab, LF and CR inside a tracked text file is almost always an escape that went
through shell quoting (a backslash-b written as 0x08, a backslash-x01 written as 0x01) and silently changes
what the file means. This tool lists every one as path:line:column and the byte in hex.

Usage: check_control_bytes.py [repo-root]     (default ".")

Exit 0: none. Exit 1: control bytes found, or a bad allow-list entry. Exit 2: git unavailable or the file
list cannot be read (fail closed).

A file git treats as binary (a NUL in its first 8000 bytes, git's own heuristic) is skipped.
Exemptions: .claude/project/control-bytes-allow.txt, one `path # reason` per line; blank lines and lines
that start with # are ignored; an entry with no reason after # is itself an error.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ALLOW_REL = ".claude/project/control-bytes-allow.txt"
OK_BYTES = {0x09, 0x0A, 0x0D}
BINARY_PROBE = 8000


def _stdio_replace() -> None:
    """Keep the stream's encoding but replace what it cannot hold, so a cp1252 console (Windows) never
    raises UnicodeEncodeError on a file name (issue 159)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


def tracked_files(root: Path) -> list[str]:
    """Tracked paths from `git ls-files -z`; raises RuntimeError when git cannot answer."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=False
        )
    except OSError as exc:
        raise RuntimeError(f"git is unavailable: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return [p.decode("utf-8", "replace") for p in proc.stdout.split(b"\0") if p]


def read_allow(root: Path) -> tuple[set[str], list[str]]:
    """Return (exempt paths, error lines)."""
    path = root / ALLOW_REL
    allowed: set[str] = set()
    errors: list[str] = []
    if not path.is_file():
        return allowed, errors
    for n, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entry, sep, reason = line.partition("#")
        entry = entry.strip()
        if not sep or not reason.strip():
            errors.append(f"{ALLOW_REL}:{n}: exemption for '{entry}' has no reason after #")
            continue
        allowed.add(entry)
    return allowed, errors


def scan(data: bytes) -> list[tuple[int, int, int]]:
    """(line, column, byte) of every control byte; empty for binary data."""
    if b"\0" in data[:BINARY_PROBE]:
        return []
    found = []
    line, col = 1, 1
    for b in data:
        if b < 0x20 and b not in OK_BYTES:
            found.append((line, col, b))
        if b == 0x0A:
            line, col = line + 1, 1
        else:
            col += 1
    return found


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0] if args else ".")
    try:
        files = tracked_files(root)
    except RuntimeError as exc:
        print(f"check_control_bytes: {exc}", file=sys.stderr)
        return 2
    allowed, errors = read_allow(root)
    hits = 0
    bad_files = 0
    for rel in files:
        if rel in allowed:
            continue
        p = root / rel
        try:
            data = p.read_bytes()
        except OSError:
            if p.is_symlink() or not p.exists() or p.is_dir():
                continue  # deleted in the work tree, a dangling link, or a submodule folder: nothing to read
            print(f"check_control_bytes: cannot read {rel}", file=sys.stderr)
            return 2
        found = scan(data)
        if found:
            bad_files += 1
        for line, col, b in found:
            print(f"{rel}:{line}:{col} 0x{b:02X}")
            hits += 1
    for e in errors:
        print(e)
    if hits or errors:
        print(f"check_control_bytes: {hits} control byte(s) in {bad_files} file(s), {len(errors)} allow-list error(s)")
        return 1
    print(f"check_control_bytes: ok ({len(files)} tracked files)")
    return 0


if __name__ == "__main__":
    _stdio_replace()
    sys.exit(main())
