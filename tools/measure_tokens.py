#!/usr/bin/env python3
"""tools/measure_tokens.py - read-only token report over Claude Code session JSONL files (REQ-060 AC-6).

Per project folder, per kind (main session or agent) and per model it prints the calls, context tokens read
(input + cache_read_input_tokens + cache_creation_input_tokens), output tokens and the 6 most-used tool names.
An assistant message counts once: its lines (one per streamed content block) merge by message id, taking the
largest usage seen and every tool call in any of its lines. Unreadable or partial lines are skipped.
Writes nothing.

Usage:
    python tools/measure_tokens.py [--root DIR] [--since YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

TOP_TOOLS = 6


def kind_of(path: Path) -> str:
    if "subagents" in path.parts or path.name.startswith("agent-"):
        return "agent"
    return "main"


def _num(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _before(ts, since) -> bool:
    if since is None or not isinstance(ts, str):
        return False
    try:
        when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when < since


def collect(root: Path, since: datetime | None = None) -> dict:
    """Return {(project, kind, model): {calls, context, output, tools: Counter}}."""
    stats: dict = {}
    for path in sorted(root.rglob("*.jsonl")):
        try:
            rel = path.relative_to(root)
            project = rel.parts[0] if len(rel.parts) > 1 else "."
            kind = kind_of(rel)
            merged: dict = {}  # message id -> one record; a streamed message is written once per content block
            with open(path, encoding="utf-8", errors="replace") as fh:
                for n, line in enumerate(fh):
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    msg = obj.get("message") if isinstance(obj, dict) else None
                    if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
                        continue
                    if obj.get("type") not in (None, "assistant") and msg.get("role") != "assistant":
                        continue
                    if _before(obj.get("timestamp"), since):
                        continue
                    usage = msg["usage"]
                    mid = msg.get("id") if msg.get("id") is not None else ("line", n)
                    rec = merged.setdefault(mid, {"model": str(msg.get("model") or "unknown"), "context": 0,
                                                  "output": 0, "tools": Counter()})
                    context = (_num(usage.get("input_tokens")) + _num(usage.get("cache_read_input_tokens"))
                               + _num(usage.get("cache_creation_input_tokens")))
                    rec["context"] = max(rec["context"], context)
                    rec["output"] = max(rec["output"], _num(usage.get("output_tokens")))
                    content = msg.get("content")
                    if isinstance(content, list):
                        for i, block in enumerate(content):
                            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name"):
                                rec["tools"][(str(block["name"]), str(block.get("id") or i))] = 1
            for rec in merged.values():
                row = stats.setdefault((project, kind, rec["model"]),
                                       {"calls": 0, "context": 0, "output": 0, "tools": Counter()})
                row["calls"] += 1
                row["context"] += rec["context"]
                row["output"] += rec["output"]
                for (name, _id) in rec["tools"]:
                    row["tools"][name] += 1
        except OSError:
            continue
    return stats


def render(stats: dict) -> str:
    lines = []
    for (project, kind, model), row in sorted(stats.items()):
        tools = ", ".join(f"{n}={c}" for n, c in sorted(row["tools"].items(), key=lambda t: (-t[1], t[0]))[:TOP_TOOLS])
        lines.append(
            f"{project} | {kind} | {model} | calls={row['calls']} | context={row['context']} | "
            f"output={row['output']} | tools: {tools or '-'}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass
    ap = argparse.ArgumentParser(description="Token report over Claude Code session files (read-only).")
    ap.add_argument("--root", default=str(Path.home() / ".claude" / "projects"))
    ap.add_argument("--since", help="YYYY-MM-DD; skip messages before this date (UTC)")
    args = ap.parse_args(argv)
    since = None
    if args.since:
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            print("--since must be YYYY-MM-DD", file=sys.stderr)
            return 2
    root = Path(args.root)
    if not root.is_dir():
        print(f"no such folder: {root}", file=sys.stderr)
        return 2
    out = render(collect(root, since))
    print(out if out else "no sessions found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
