"""Shared by the orchestrator route hooks: hook-input parsing and a quote-aware split of a shell command into steps.

Reuses gate_before_commit's scanner (quoted text and heredoc bodies are data; `bash -c "..."` is judged recursively).
Every caller must fail open: if this module or the scanner cannot be imported, the hook allows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate_before_commit as g

MAX_LEN = 100_000
MAX_DEPTH = 3


def read_input() -> dict:
    data = json.loads(sys.stdin.read() or "{}")
    return data if isinstance(data, dict) else {}


def core_steps(command: str, ps: bool = False, depth: int = 0) -> list[list[str]]:
    """Each step's words with wrappers (env, time, uv run, ...) stripped, including steps inside `bash -c`."""
    steps, unterm = g._scan(command, ps)
    if unterm and not ps:
        steps, _ = g._scan(command, True)
    out: list[list[str]] = []
    for words, _ in steps:
        core = g._core(words)
        if core:
            out.append(core)
        if depth < MAX_DEPTH:
            inner = g._shell_inner(words)
            if inner is not None:
                out.extend(core_steps(inner[0], inner[1], depth + 1))
    return out


def head(words: list[str]) -> str:
    return g._base(words[0])


def run_hook(decide_fn) -> int:
    """decide_fn(tool_name, tool_input) -> refusal text or None. Exit 2 + stderr to refuse, 0 otherwise (fail open)."""
    try:
        data = read_input()
        reason = decide_fn(str(data.get("tool_name", "")), data.get("tool_input") or {})
    except Exception:  # noqa: BLE001 - a hook must never block on its own bug
        return 0
    if not reason:
        return 0
    sys.stderr.write(reason + "\n")
    return 2
