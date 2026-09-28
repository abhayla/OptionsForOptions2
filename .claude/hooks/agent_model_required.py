#!/usr/bin/env python3
"""agent_model_required.py — PreToolUse hook, matcher: Agent.

Generalized from a project-specific import (see capability.json `provenance`).
No behavior change — only the docstring's project-specific artifact names
(a routing-policy doc's repo-relative path, task ids) were replaced with
generic descriptions.

Model routing policy: EVERY Agent()/workflow dispatch must set `model`
explicitly — inheriting the driver's own model is a deliberate choice,
never a default. This hook is the deterministic backstop: a dispatched
Agent tool call with no `model` set gets DENIED (not just logged) so the
omission is caught before the subagent burns tokens on the wrong tier.

Tier table (echoed in the deny reason so the caller sees it inline, never has to look it up):
  Sonnet — clear brief + machine-checkable gate: eval runs, itemized fix workers, code edits
           per plan, research, docs. DEFAULT for execution.
  Opus   — fuzzy/multi-file/cross-cutting code, deep debugging, architecture analysis, or any
           REVIEWER role (maker != checker).
  Haiku  — rubric scoring, blind re-grades, classification, extraction, format checks.
  Top tier — frontier judgment (novel unrubriced design, subtle spec reasoning, the final
           ship-gate adversarial verification) — set `model` to the project's designated
           top-tier model EXPLICITLY; omission is never accepted (silently telling the
           reader to "omit model" here would just re-trigger this same deny forever).

Exemption: `subagent_type: "fork"` may omit `model` — a fork inherits the parent model/context
by definition (Agent tool contract), so there is nothing to route. The exemption list is
configurable via `AGENT_MODEL_REQUIRED_ALLOW` (comma-separated subagent_type PREFIXES;
default: "fork") — any subagent_type starting with one of these prefixes is exempt.

Off-switch: `AGENT_MODEL_REQUIRED=0` disables this hook entirely (allow everything, no
output) — an emergency escape hatch.

Fail-open ONLY on a genuine parse failure: malformed/non-JSON stdin, or any unexpected
exception while reading it — those exit 0 (allow), because a broken guard must never block
a legitimate dispatch. An Agent tool_use with `tool_input` missing or null is a DIFFERENT
case — a real Agent call always carries tool_input, so a missing one is a malformed
dispatch, not a parse error, and correctly DENIES: `model` is absent either way, so the
same missing-model deny fires.

Opus needs a reason (opt-in, default OFF): measurement on the source project showed Opus
running ordinary contract work a Sonnet gate would have covered. When `FACTORY_REQUIRE_OPUS_REASON=1`
is set, `model` set to `"opus"` (any case) is no longer sufficient on its own — the prompt
text must also carry a `Why Opus:` line followed by at least 12 non-space characters on the
same line, naming the routing-table reason (fuzzy spec / multi-file design freedom /
cross-cutting code / Tier A review). Missing or too short a reason DENIES with a message
quoting the Sonnet-vs-Opus routing table, same mechanism as the missing-`model` deny above.
`subagent_type: "fork"` stays exempt from this too (the exemption check above runs first).
With `FACTORY_REQUIRE_OPUS_REASON` unset or not `"1"`, `model: "opus"` is accepted like any
other non-empty model string — no reason required. The existing `AGENT_MODEL_REQUIRED=0`
off-switch still disables the whole hook (missing-model check included) regardless of this
setting.

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
    "Set `model` explicitly on this Agent() dispatch: "
    "Sonnet = clear brief + machine-checkable gate (eval runs, itemized fix workers, code "
    "edits per plan, research, docs) — DEFAULT for execution; "
    "Opus = fuzzy/multi-file/cross-cutting code, deep debugging, architecture analysis, or any "
    "reviewer role; "
    "Haiku = rubric scoring, blind re-grades, classification, extraction, format checks; "
    "for frontier judgment set model to the project's designated top-tier model explicitly — "
    "omission is never accepted. "
    "Exception: subagent_type: \"fork\" does not need model (forks inherit)."
)

OPUS_REASON_REQUIRED = (
    "model=\"opus\" needs a `Why Opus:` line in the prompt (>= 12 non-space characters) "
    "per the routing table: Sonnet = clear brief + machine-checkable gate "
    "(DEFAULT for execution); Opus = fuzzy spec, multi-file design freedom, cross-cutting code, "
    "or Tier A review. Add `Why Opus: <reason>` to the prompt, or route this dispatch to "
    "Sonnet instead."
)

_WHY_OPUS_RE = re.compile(r"Why Opus:(.*)")


def _has_opus_reason(prompt):
    if not isinstance(prompt, str):
        return False
    match = _WHY_OPUS_RE.search(prompt)
    if not match:
        return False
    return len(re.sub(r"\s", "", match.group(1))) >= 12


def deny(reason):
    print(reason, file=sys.stderr)
    sys.exit(2)


def _allowed_prefixes():
    raw = os.environ.get("AGENT_MODEL_REQUIRED_ALLOW", "fork")
    return [p.strip() for p in raw.split(",") if p.strip()]


def main():
    if os.environ.get("AGENT_MODEL_REQUIRED") == "0":
        return  # off-switch: allow everything, log nothing

    data = json.load(sys.stdin)
    if data.get("tool_name") not in ("Agent", "Task"):
        return
    tool_input = data.get("tool_input")
    if tool_input is None:
        tool_input = {}
    if not isinstance(tool_input, dict):
        return

    model = tool_input.get("model")
    subagent_type = tool_input.get("subagent_type") or ""

    if any(subagent_type.startswith(prefix) for prefix in _allowed_prefixes()):
        return  # exempt subagent_type (default: fork — inherits the parent model)

    if not model or not str(model).strip():
        deny(TIER_TABLE)

    if str(model).strip().lower() == "opus" and os.environ.get("FACTORY_REQUIRE_OPUS_REASON") == "1":
        if not _has_opus_reason(tool_input.get("prompt")):
            deny(OPUS_REASON_REQUIRED)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
