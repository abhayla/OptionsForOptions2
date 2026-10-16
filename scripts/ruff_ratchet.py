"""Ruff ratchet: lint counts per rule may fall, never rise.

Runs `ruff check --output-format=json` with the repo's `ruff.toml`, counts violations per rule code and compares them
with the committed `scripts/ruff_baseline.json`.

    python scripts/ruff_ratchet.py            exit 1 when any rule's count is above the baseline (prints which)
    python scripts/ruff_ratchet.py --update   rewrite the baseline, refused (exit 1) when any count rose

Fails closed (exit 2): ruff missing or crashing, output that is not the JSON list ruff prints, or no baseline file.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Mapping

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "ruff_baseline.json"
SYNTAX = "syntax-error"  # ruff reports a file it cannot parse with code null


def count_by_rule(violations: Iterable[Mapping[str, object]]) -> dict[str, int]:
    counts = Counter(str(v.get("code") or SYNTAX) for v in violations)
    return dict(sorted(counts.items()))


def rises(baseline: Mapping[str, int], current: Mapping[str, int]) -> list[tuple[str, int, int]]:
    """Every (rule, baseline count, current count) where the count went up; a rule absent from the baseline is 0."""
    return [(code, baseline.get(code, 0), n) for code, n in sorted(current.items()) if n > baseline.get(code, 0)]


def falls(baseline: Mapping[str, int], current: Mapping[str, int]) -> list[tuple[str, int, int]]:
    return [(code, n, current.get(code, 0)) for code, n in sorted(baseline.items()) if current.get(code, 0) < n]


def decide(baseline: Mapping[str, int], current: Mapping[str, int], update: bool) -> tuple[int, list[str], bool]:
    """(exit code, lines to print, whether to write the baseline). Pure: no ruff, no files."""
    up = rises(baseline, current)
    lines = [f"ruff ratchet: {code} rose {old} -> {new}" for code, old, new in up]
    lines += [f"ruff ratchet: {code} fell {old} -> {new}" for code, old, new in falls(baseline, current)]
    if up:
        if update:
            lines.append("ruff ratchet: --update refused, a count rose; fix the new violations first")
        # Always end on a verdict line (finding gate-output-read-by-eye: with "fell" lines last and no summary, two
        # builders read a failing ratchet as passing on 2026-10-16).
        lines.append(f"ruff ratchet: FAIL, {len(up)} rule(s) rose: {', '.join(code for code, _, _ in up)}")
        return 1, lines, False
    lines.append(f"ruff ratchet: OK, no rule rose ({sum(current.values())} violations, {len(current)} rules)")
    return 0, lines, update


def run_ruff() -> list[dict[str, object]]:
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format=json", "--exit-zero", "--no-cache", "."],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ruff exited {proc.returncode}: {proc.stderr.strip()[:2000]}")
    data = json.loads(proc.stdout)
    if not isinstance(data, list):
        raise RuntimeError("ruff output is not a JSON list")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="rewrite the baseline when no count rose")
    args = parser.parse_args(argv)
    if not BASELINE.is_file() and not args.update:
        print(f"ruff ratchet: no baseline at {BASELINE}; create it with --update", file=sys.stderr)
        return 2
    try:
        current = count_by_rule(run_ruff())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ruff ratchet: cannot count violations, failing closed: {exc}", file=sys.stderr)
        return 2
    if BASELINE.is_file():
        code, lines, write = decide(json.loads(BASELINE.read_text(encoding="utf-8")), current, args.update)
    else:  # first run: --update creates the baseline from today's counts
        total = sum(current.values())
        code, lines, write = 0, [f"ruff ratchet: no baseline yet, creating it ({total} violations)"], True
    print("\n".join(lines))
    if write:
        BASELINE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"ruff ratchet: baseline written to {BASELINE.relative_to(ROOT).as_posix()}")
    return code


if __name__ == "__main__":
    sys.exit(main())
