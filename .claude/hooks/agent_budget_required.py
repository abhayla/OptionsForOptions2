#!/usr/bin/env python3
"""agent_budget_required.py — PreToolUse hook, matcher: Agent.

Generalized from a project-specific import (see capability.json `provenance`).
No behavior change — only the docstring's project-specific artifact names
(a mechanism registry file, a project-specific "global CLAUDE.md" rule
number, a sibling hook's internal repo-relative path) were replaced with
generic descriptions. Every test case behaves identically.

Mechanism for a real recurring class: Agent briefs carried no wall-clock or
tool-call budget, so a worker polled a silent command a dozen times or
re-ran a whole dry pass instead of diagnosing and stopping. The owning
project's policy requires a `Budget: N min, M tool calls` line in every
Agent brief, sized by review tier. This hook is the deterministic backstop
— modelled line-for-line on the companion `agent-model-required` hook,
which does the same job for the `model` field.

Tier table (echoed in the deny reason so the caller sees it inline, never has to look it up):
  Tier C — 15 min / 30 tool calls
  Tier B — 30 min / 60 tool calls
  Tier A — 60 min / 120 tool calls
  A fix round or re-check = HALF its tier's budget.
  Reviewer = 20 min / 40 tool calls.
  Raise the budget only with a one-line reason in the same brief.

Detection: the `prompt` field is scanned as plain text for a line matching a Budget
declaration — a "Budget:" label followed, anywhere on the same line, by a number of
minutes and a number of calls (in either order, any punctuation/wording between them:
"Budget: 30 min / 60 calls", "Budget: 30 min wall-clock, 60 tool calls", "Budget: 15
minutes, 30 tool calls"). A Budget line inside a fenced code block still counts — the
prompt is matched as raw text, never parsed as markdown, so fences are invisible to the
regex. Mentioning "budget" in prose with no minute/call figures does NOT satisfy the rule.

Exemption: `subagent_type: "fork"` may omit the Budget line — a fork inherits the parent's
running budget by definition (Agent tool contract), so there is nothing separate to size.
The exemption list is configurable via `AGENT_BUDGET_REQUIRED_ALLOW` (comma-separated
subagent_type PREFIXES; default: "fork") — any subagent_type starting with one of these
prefixes is exempt.

Off-switch: `AGENT_BUDGET_REQUIRED=0` disables this hook entirely (allow everything, no
output) — mirrors the companion `agent-model-required` hook's own off-switch, an
emergency escape hatch.

Fail-open ONLY on a genuine parse failure: malformed/non-JSON stdin, or any unexpected
exception while reading it — those exit 0 (allow), because a broken guard must never block
a legitimate dispatch. An Agent tool_use with `tool_input` missing or null is a DIFFERENT
case — a real Agent call always carries tool_input, so a missing one is a malformed
dispatch, not a parse error, and correctly DENIES (mirrors the companion hook's own rule
for a missing `model`).

Block mechanism: exit 2 with the reason on stderr, plain text, no JSON. A JSON
`permissionDecision: "deny"` with exit 0 is overridable by ANY other matching hook's
"allow" (measured; finding json-deny-overridden-by-another-hooks-allow) — only exit 2 is
documented as non-overridable.
"""
import json
import os
import re
import sys


TIER_TABLE = (
    "Add a `Budget: N min, M tool calls` line to this Agent() prompt: "
    "Tier C = 15 min / 30 tool calls; Tier B = 30 min / 60 tool calls; "
    "Tier A = 60 min / 120 tool calls; a fix round or re-check = half its tier's budget; "
    "reviewer = 20 min / 40 tool calls. Raise the budget only with a one-line reason in "
    "the same brief. Exception: subagent_type: \"fork\" does not need a Budget line "
    "(forks inherit the parent's running budget)."
)

# Matches e.g. "Budget: 30 min / 60 calls", "Budget: 30 min wall-clock, 60 tool calls",
# "Budget: 15 minutes, 30 tool calls" — a "Budget:" label, then a number of minutes, then
# (anywhere later on the same line) a number of calls. Plain-text scan: works the same
# whether or not the line sits inside a fenced code block. The calls number is captured
# so it can be checked against the target agent's own maxTurns.
BUDGET_RE = re.compile(
    r"budget\s*:\s*\d+\s*min.*?(\d+)\s*(?:tool\s+)?calls",
    re.IGNORECASE,
)

# `maxTurns: 100` in an agent .md frontmatter block.
MAX_TURNS_RE = re.compile(r"^\s*maxTurns\s*:\s*(\d+)\s*$", re.IGNORECASE | re.MULTILINE)

OVER_BUDGET_FRACTION = 0.8


def deny(reason):
    print(reason, file=sys.stderr)
    sys.exit(2)


def _allowed_prefixes():
    raw = os.environ.get("AGENT_BUDGET_REQUIRED_ALLOW", "fork")
    return [p.strip() for p in raw.split(",") if p.strip()]


def _has_budget_line(prompt):
    if not isinstance(prompt, str) or not prompt.strip():
        return False
    for line in prompt.splitlines():
        if BUDGET_RE.search(line):
            return True
    return False


def _budget_calls(prompt):
    """Return the tool-call number from the FIRST Budget line found, or None."""
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    for line in prompt.splitlines():
        m = BUDGET_RE.search(line)
        if m:
            try:
                return int(m.group(1))
            except (TypeError, ValueError):
                return None
    return None


def _project_root(data):
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    if root and os.path.isdir(root):
        return root
    cwd = data.get("cwd") if isinstance(data, dict) else None
    if cwd and os.path.isdir(cwd):
        return cwd
    return os.getcwd()


def _agent_max_turns(project_root, subagent_type):
    """Read `maxTurns` from `.claude/agents/<subagent_type>.md` frontmatter.

    Returns None (skip the turn-limit check) when the agent file does not
    exist, has no `maxTurns` in its frontmatter, or anything goes wrong
    reading it — an unknown agent or a missing field is not this guard's
    business to invent a number for.
    """
    if not subagent_type or not project_root:
        return None
    path = os.path.join(project_root, ".claude", "agents", "%s.md" % subagent_type)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    m = MAX_TURNS_RE.search(text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


def main():
    if os.environ.get("AGENT_BUDGET_REQUIRED") == "0":
        return  # off-switch: allow everything, log nothing

    data = json.load(sys.stdin)
    if data.get("tool_name") not in ("Agent", "Task"):
        return
    tool_input = data.get("tool_input")
    if tool_input is None:
        tool_input = {}
    if not isinstance(tool_input, dict):
        return

    subagent_type = tool_input.get("subagent_type") or ""

    if any(subagent_type.startswith(prefix) for prefix in _allowed_prefixes()):
        return  # exempt subagent_type (default: fork — inherits the parent's budget)

    prompt = tool_input.get("prompt")
    if not _has_budget_line(prompt):
        deny(TIER_TABLE)

    # Second check (finding agent-budget-exceeds-turn-limit): a Budget line
    # that exists but asks for more tool calls than the target agent can ever
    # make before its own maxTurns cuts it off mid-work. Unknown agent or no
    # maxTurns on file -> nothing to check against, so skip (never invent a
    # limit).
    calls = _budget_calls(prompt)
    if calls is not None:
        max_turns = _agent_max_turns(_project_root(data), subagent_type)
        if max_turns is not None:
            limit = OVER_BUDGET_FRACTION * max_turns
            if calls > limit:
                deny(
                    "Budget asks for %d tool calls, but subagent_type %r has "
                    "maxTurns: %d — a budget above %.0f%% of that (%d calls) "
                    "runs the agent past its own hard stop mid-work "
                    "(finding agent-budget-exceeds-turn-limit). Lower the "
                    "Budget line or split the brief into smaller items."
                    % (calls, subagent_type, max_turns, OVER_BUDGET_FRACTION * 100, int(limit))
                )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
