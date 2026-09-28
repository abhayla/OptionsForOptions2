#!/usr/bin/env python3
"""kithash.py — the one place `sha256_of` lives (shipped into every project's `tools/`).

sha256 of LF-normalized content: CRLF is collapsed to LF before hashing, so a Windows checkout and
an LF checkout (Linux/CI) of the same text always hash equal (PR #15). Both the Factory's
provenance generator and the kit's own drift/selftest tools import this one function rather than
each keeping their own copy, so a Windows/Linux mismatch can never creep back in through a second
implementation.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
