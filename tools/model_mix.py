#!/usr/bin/env python3
"""model_mix.py - which models actually ran, and did an alias move to a model the routing table was not reviewed for?

Reads a Claude Code transcripts folder READ-ONLY (no network call):
  <dir>/*.jsonl                         the main sessions (role "main")
  <dir>/*/subagents/*.jsonl             one file per subagent run; its sibling <name>.meta.json holds the
                                        subagent type (role) and the model the dispatch asked for

Every assistant message is counted once by its message id (a streamed message repeats its id in several
transcript lines; the line with the most output tokens wins). The synthetic model id is skipped.

Prints, per role (and requested model) and model: messages, output tokens, cache-read tokens, and the share of
all output + cache-read tokens. Then the alarms, read against the routing table's `reviewed_for` map:

  NO TRANSCRIPTS: <path>   (every mode) the transcripts folder does not exist; never read as "no alarms"
  NEW MODEL: <alias> latest id <id> differs from reviewed <id> - re-check the effort table
      for each family in the table: the model id of the LATEST message of that family differs from the id
      the table was reviewed for. Older ids in the history never alarm.
  UNROUTED MODEL: <id>
      a model id of a family the table does not name.

Usage:
    python tools/model_mix.py [transcripts_dir] [--days N] [--alarms] [--table PATH]

transcripts_dir  default: ~/.claude/projects/<cwd with every character outside A-Z a-z 0-9 replaced by '-'>
--days N         only messages stamped within the last N days (default 14)
--alarms         print only the alarm lines (nothing when there are none)
--table PATH     routing table; default .claude/kit/model-routing.yaml when present, else
                 capabilities/routing/model-routing.yaml

A report tool: it always exits 0. Standard library plus PyYAML (already a dependency of the kit's tools).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SYNTHETIC = "<synthetic>"
# The families are the keys of the table's `reviewed_for` map (substring match on the model id), so a family the
# table does not name is UNROUTED, and no family name is typed into this tool.


def encode_cwd(cwd: str) -> str:
    """Claude Code's project folder name for a working directory: every character that is not A-Z a-z 0-9 becomes
    '-' (measured: Temp\\kit-live-proof-_3agin2e\\project -> kit-live-proof--3agin2e-project)."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def default_transcripts_dir(cwd: str | None = None) -> Path:
    return Path.home() / ".claude" / "projects" / encode_cwd(cwd or str(Path.cwd()))


def default_table(cwd: Path | None = None) -> Path:
    base = cwd or Path.cwd()
    kit = base / ".claude" / "kit" / "model-routing.yaml"
    return kit if kit.is_file() else base / "capabilities" / "routing" / "model-routing.yaml"


def family_of(model_id: str, families) -> str | None:
    low = model_id.lower()
    for fam in families:
        if fam.lower() in low:
            return fam
    return None


def parse_ts(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _read_meta(jsonl: Path) -> dict:
    meta = jsonl.with_name(jsonl.stem + ".meta.json")
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _jsonl_files(root: Path):
    """(path, role, requested model) for the main sessions first, then every subagent run."""
    for p in sorted(root.glob("*.jsonl")):
        yield p, "main", "-"
    for p in sorted(root.glob("*/subagents/*.jsonl")):
        meta = _read_meta(p)
        yield p, str(meta.get("agentType") or "unknown"), str(meta.get("model") or "-")


def collect(root: Path, days: int, now: datetime | None = None) -> list[dict]:
    """One record per message id: role, requested, model, ts, out, cache_read. Read-only."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    best: dict[str, dict] = {}
    for path, role, requested in _jsonl_files(root):
        try:
            fh = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict) or rec.get("type") != "assistant":
                    continue
                msg = rec.get("message")
                if not isinstance(msg, dict):
                    continue
                mid, model, usage = msg.get("id"), msg.get("model"), msg.get("usage")
                if not (isinstance(mid, str) and isinstance(model, str) and isinstance(usage, dict)):
                    continue
                if model == SYNTHETIC:
                    continue
                ts = parse_ts(rec.get("timestamp"))
                if ts is not None and ts < cutoff:
                    continue
                out = usage.get("output_tokens")
                cache = usage.get("cache_read_input_tokens")
                out = out if isinstance(out, int) else 0
                cache = cache if isinstance(cache, int) else 0
                prev = best.get(mid)
                if prev is None or out > prev["out"]:
                    keep_ts = ts or (prev["ts"] if prev else None)
                    first = prev or {"role": role, "requested": requested}
                    best[mid] = {"role": first["role"], "requested": first["requested"], "model": model,
                                 "ts": keep_ts, "out": out, "cache": cache}
    return list(best.values())


def aggregate(records: list[dict]) -> list[dict]:
    rows: dict[tuple, dict] = {}
    for r in records:
        row = rows.setdefault((r["role"], r["requested"], r["model"]),
                              {"role": r["role"], "requested": r["requested"], "model": r["model"],
                               "msgs": 0, "out": 0, "cache": 0})
        row["msgs"] += 1
        row["out"] += r["out"]
        row["cache"] += r["cache"]
    total = sum(x["out"] + x["cache"] for x in rows.values())
    out = sorted(rows.values(), key=lambda x: -(x["out"] + x["cache"]))
    for x in out:
        x["share"] = (x["out"] + x["cache"]) / total if total else 0.0
    return out


def load_reviewed_for(table: Path) -> dict | None:
    try:
        import yaml  # PyYAML: the kit's tools already depend on it
        data = yaml.safe_load(table.read_text(encoding="utf-8"))
    except Exception:
        return None
    reviewed = data.get("reviewed_for") if isinstance(data, dict) else None
    if not isinstance(reviewed, dict):
        return None
    return {str(k): str(v) for k, v in reviewed.items()}


def alarms(records: list[dict], reviewed_for: dict) -> list[str]:
    lines: list[str] = []
    # NEW MODEL: per family, the model id of the latest message; older ids never alarm.
    latest: dict[str, tuple] = {}
    for r in records:
        fam = family_of(r["model"], reviewed_for)
        if fam is None:
            continue
        stamp = r["ts"] or datetime.min.replace(tzinfo=timezone.utc)
        if fam not in latest or stamp >= latest[fam][0]:
            latest[fam] = (stamp, r["model"])
    for fam in reviewed_for:
        if fam in latest and latest[fam][1] != reviewed_for[fam]:
            lines.append(f"NEW MODEL: {fam} latest id {latest[fam][1]} differs from reviewed "
                         f"{reviewed_for[fam]} - re-check the effort table")
    # UNROUTED MODEL: a model id of a family the table does not name.
    seen: set[str] = set()
    for r in records:
        if family_of(r["model"], reviewed_for) is None and r["model"] not in seen:
            seen.add(r["model"])
            lines.append(f"UNROUTED MODEL: {r['model']}")
    return lines


def render(root: Path, days: int, records: list[dict], rows: list[dict]) -> list[str]:
    total_out = sum(r["out"] for r in records)
    total_cache = sum(r["cache"] for r in records)
    lines = [f"Model mix: {root}", f"Last {days} days: {len(records)} messages (each message id counted once), "
             f"{total_out:,} output tokens, {total_cache:,} cache-read tokens", ""]
    header = f"{'role':<22} {'asked':<10} {'model':<28} {'msgs':>7} {'output':>13} {'cache-read':>16} {'share':>7}"
    lines += [header, "-" * len(header)]
    for x in rows:
        lines.append(f"{x['role'][:22]:<22} {x['requested'][:10]:<10} {x['model'][:28]:<28} {x['msgs']:>7,} "
                     f"{x['out']:>13,} {x['cache']:>16,} {x['share'] * 100:>6.1f}%")
    lines.append("")
    lines.append("share = (output + cache-read tokens) of this row / the same sum over all rows")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Token spend per model and role from Claude Code transcripts.")
    ap.add_argument("transcripts_dir", nargs="?", default=None)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--alarms", action="store_true", help="print only the alarm lines")
    ap.add_argument("--table", default=None)
    args = ap.parse_args(argv)

    root = Path(args.transcripts_dir) if args.transcripts_dir else default_transcripts_dir()
    table = Path(args.table) if args.table else default_table()
    if not root.is_dir():
        print(f"NO TRANSCRIPTS: {root}")  # in every mode: a missing folder must never read as "no alarms"
        return 0
    records = collect(root, args.days)
    reviewed = load_reviewed_for(table)
    if args.alarms:
        if reviewed is None:
            print(f"model_mix: cannot read reviewed_for from {table}")
        else:
            for line in alarms(records, reviewed):
                print(line)
        return 0
    for line in render(root, args.days, records, aggregate(records)):
        print(line)
    if reviewed is None:
        print(f"ALARMS: not checked, cannot read reviewed_for from {table}")
    else:
        found = alarms(records, reviewed)
        print("ALARMS:" if found else "ALARMS: none")
        for line in found:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
