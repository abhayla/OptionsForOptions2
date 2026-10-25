#!/usr/bin/env python3
"""tools/measure_tokens.py - read-only token report over Claude Code session JSONL files (REQ-060 AC-6).

Per project folder, per kind (main session or agent) and per model it prints the calls, context tokens read
(input + cache_read_input_tokens + cache_creation_input_tokens), output tokens and the 6 most-used tool names.
An assistant message counts once: its lines (one per streamed content block) merge by message id, taking the
largest usage seen and every tool call in any of its lines. Unreadable or partial lines are skipped.
Writes nothing.

Budget mode (REQ-062 AC-2): --budgets prints, per agent transcript, the Budget line of its first prompt beside the
actual tool calls and the minutes from the first to the last timestamp (wall-clock including waits).

Usage:
    python tools/measure_tokens.py [--root DIR] [--since YYYY-MM-DD] [--budgets]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
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


HOOK_FILES = (("capabilities", "hooks", "agent-budget-required", "agent_budget_required.py"),
              (".claude", "hooks", "agent_budget_required.py"))
# The hook's BUDGET_RE captures the calls number only; the minutes are read from the matched line with this minimal
# pattern, anchored right after the "Budget:" label. The line itself is still selected by the hook's pattern.
MINUTES_RE = re.compile(r"budget\s*:\s*(\d+)\s*min", re.IGNORECASE)


def _bases() -> list:
    return [Path(__file__).resolve().parent.parent, Path.cwd()]


def load_budget_re(bases=None):
    """Return BUDGET_RE from the kit budget hook file (one home for the pattern), or None if the file is absent."""
    for base in (bases if bases is not None else _bases()):
        for parts in HOOK_FILES:
            path = Path(base).joinpath(*parts)
            if not path.is_file():
                continue
            try:
                spec = importlib.util.spec_from_file_location("_budget_hook", path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod.BUDGET_RE
            except Exception:
                continue
    return None


def _prompt_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b["text"] if isinstance(b, dict) and isinstance(b.get("text"), str) else
                         (b if isinstance(b, str) else "") for b in content)
    return ""


def _parse_ts(ts):
    if not isinstance(ts, str):
        return None
    try:
        when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def read_budget(prompt: str, budget_re):
    """(minutes, calls) from the first line of the prompt the hook's pattern matches, else None."""
    for line in prompt.splitlines():
        m = budget_re.search(line)
        if m:
            mins = MINUTES_RE.search(line)
            return (int(mins.group(1)) if mins else None, int(m.group(1)))
    return None


def agent_row(path: Path, budget_re, since=None) -> dict | None:
    prompt, first, last, tools = None, None, None, set()
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            when = _parse_ts(obj.get("timestamp"))
            msg = obj.get("message")
            # The budget comes from the first prompt even when it predates --since; only the counts are cut.
            if prompt is None and obj.get("type") == "user" and isinstance(msg, dict):
                prompt = _prompt_text(msg.get("content"))
            if since is not None and when is not None and when < since:
                continue
            if when is not None:
                first = when if first is None or when < first else first
                last = when if last is None or when > last else last
            if isinstance(msg, dict) and isinstance(msg.get("content"), list) and (
                    obj.get("type") in (None, "assistant") or msg.get("role") == "assistant"):
                mid = msg.get("id") if msg.get("id") is not None else ("line", n)
                for i, block in enumerate(msg["content"]):
                    if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name"):
                        tools.add((mid, str(block.get("id") or i)))
    if since is not None and first is None and not tools:
        return None  # nothing on or after --since: the transcript is out of the window, not a NO-BUDGET row
    budget = read_budget(prompt or "", budget_re)
    minutes = round((last - first).total_seconds() / 60, 1) if first and last else 0.0
    calls = len(tools)
    if budget is None:
        status = "NO-BUDGET"
    elif calls > budget[1] or (budget[0] is not None and minutes > budget[0]):
        status = "OVER"
    else:
        status = "OK"
    agent_type = "-"
    meta = path.with_suffix(".meta.json")
    try:
        data = json.loads(meta.read_text(encoding="utf-8", errors="replace"))
        if isinstance(data, dict) and data.get("agentType"):
            agent_type = str(data["agentType"])
    except (OSError, ValueError):
        pass
    return {"id": path.stem.removeprefix("agent-"), "type": agent_type, "budget": budget, "calls": calls,
            "minutes": minutes, "status": status}


def budget_report(root: Path, budget_re, since=None) -> str:
    lines, counts, folders = [], Counter(), {}
    for path in sorted(root.rglob("*.jsonl")):
        rel = path.relative_to(root)
        if kind_of(rel) != "agent":
            continue
        folder = rel.parts[0] if len(rel.parts) > 1 else "."
        try:
            row = agent_row(path, budget_re, since)
        except OSError:
            continue
        if row is None:
            continue
        folders[folder] = folders.get(folder, 0) + 1
        counts[row["status"]] += 1
        b = row["budget"]
        bmin = "?" if b is None or b[0] is None else b[0]
        lines.append(f"{folder} | agent {row['id']} | {row['type']} | "
                     f"budget {'-' if b is None else bmin} min, {'-' if b is None else b[1]} calls | "
                     f"actual {row['calls']} calls, {row['minutes']} min (wall-clock incl. waits) | {row['status']}")
    for folder, n in sorted(folders.items()):
        lines.append(f"folder {folder}: {n} transcripts")
    lines.append(f"total: OVER {counts['OVER']} / OK {counts['OK']} / NO-BUDGET {counts['NO-BUDGET']}")
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
    ap.add_argument("--budgets", action="store_true", help="per agent transcript: Budget line vs actual")
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
    if args.budgets:
        budget_re = load_budget_re()
        if budget_re is None:
            print("budget hook file not found (agent_budget_required.py)", file=sys.stderr)
            return 2
        print(budget_report(root, budget_re, since))
        return 0
    out = render(collect(root, since))
    print(out if out else "no sessions found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
