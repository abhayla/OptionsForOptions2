#!/usr/bin/env python3
"""agent_model_required.py — PreToolUse hook, matcher: Agent|Task.

Model routing policy: EVERY Agent()/workflow dispatch must set `model` explicitly, and the choice
must be a real family alias; there is no "inherit" value (the Agent tool does not accept it). This hook is the deterministic backstop: a dispatch that breaks one of the rules below is
DENIED (not just logged) before the subagent burns tokens on the wrong model.

The routing table (source capabilities/routing/model-routing.yaml, kit copy
.claude/kit/model-routing.yaml) says which class of job runs on which model and effort. This
script never reads that file at run time (a hook must stay one dependency-free file); the class
list echoed in every deny reason is static text kept equal to the table by a test.

Deny rules, in order (each prints the reason on stderr and exits 2):
  1. `model` missing, blank, or not one of opus, sonnet, haiku, fable (compared after
     strip + lower-case, so "Opus " and "OPUS" are the known aliases; a full dated
     model id and "inherit" are NOT aliases and are denied as unknown).
  2. `opus` without a `Why Opus:` line of at least 12 non-space characters in the prompt.
     ON by default; FACTORY_REQUIRE_OPUS_REASON=0 turns this one part off.
  3. `fable` without a `Why Fable:` line of at least 12 non-space characters in the prompt.
     Always on (no switch except the whole-hook off-switch below): the strongest model runs only
     on escalation (the same failure class red twice, a design the cheaper model failed, or the
     owner names it).
  A reason label counts only at the START of a line (optional spaces, one list marker `-` or `*`,
  optional `**`); a label mentioned inside a sentence, this hook's own deny text pasted back, or a
  placeholder such as `<reason>` is not a reason.

Exemption: `subagent_type: "fork"` may omit `model` — a fork takes the parent model/context
by definition (Agent tool contract), so there is nothing to route. The exemption list is
configurable via `AGENT_MODEL_REQUIRED_ALLOW` (comma-separated subagent_type names; default:
"fork") — a subagent_type EQUAL to one of these names (not a prefix of it) is exempt from all rules.

Off-switch: `AGENT_MODEL_REQUIRED=0` disables this hook entirely (allow everything, no
output) — an emergency escape hatch.

Fail-open ONLY on a genuine parse failure: malformed/non-JSON stdin, or any unexpected
exception while reading it — those exit 0 (allow), because a broken guard must never block
a legitimate dispatch. An Agent tool_use with `tool_input` missing or null is a DIFFERENT
case — a real Agent call always carries tool_input, so a missing one is a malformed
dispatch, not a parse error, and correctly DENIES: `model` is absent either way.

Block mechanism: exit 2 with the reason on stderr, plain text, no JSON. A JSON
`permissionDecision: "deny"` with exit 0 is overridable by ANY other matching hook's
"allow" (measured; finding json-deny-overridden-by-another-hooks-allow) — only exit 2 is
documented as non-overridable.
"""
import json
import os
import re
import sys

ALIASES = ("opus", "sonnet", "haiku", "fable")  # not "inherit": the Agent tool does not accept it

# One line per class of the routing table: `<class> = <model>/<effort>: <first use_for item>`.
# Static text; tests/test_agent_model_required.py loads the table and fails when this drifts.
CLASS_LIST = (
    "lookup = haiku/medium: read-only search and lookup across a codebase (the Explore agent)\n"
    "checking = haiku/low: format, lint and schema checks\n"
    "building = sonnet/medium: implementing a work item with a clear brief and a machine-checkable gate\n"
    "review_b = sonnet/high: Tier B review (diff-focused, time-boxed, no mutation testing)\n"
    "design = opus/high: fuzzy spec or multi-file design\n"
    "review_a = opus/xhigh: Tier A review (adversarial, fresh context, mutation tests on every guard)\n"
    "verify_a = opus/high: Tier A verifier (fresh context, read-only, one evidence block per acceptance criterion)\n"
    "escalation = fable/high: same failure class red twice after fix rounds (independent review)"
)

ROUTING_FOOTER = (
    "Routing classes (model/effort, from the routing table):\n" + CLASS_LIST + "\n"
    "Exception: subagent_type: \"fork\" does not need model (a fork takes its parent's model)."
)

MISSING_MODEL = (
    "Set `model` explicitly on this Agent() dispatch, to one of: opus, sonnet, haiku, fable "
    "(family aliases, never a dated model id). Pick it by the class of the job.\n" + ROUTING_FOOTER
)

UNKNOWN_MODEL = (
    "model=%s is not a model alias. Use one of: opus, sonnet, haiku, fable "
    "(family aliases resolve to the latest model; a dated model id is refused).\n" + ROUTING_FOOTER
)

OPUS_REASON_REQUIRED = (
    "model=\"opus\" needs a `Why Opus:` line in the prompt (>= 12 non-space characters): opus is for "
    "design (fuzzy spec, multi-file design, hard debugging, planning), Tier A review and the Tier A "
    "verifier. Add `Why Opus: <reason>` to the prompt, or route this dispatch to sonnet (building, "
    "Tier B review). FACTORY_REQUIRE_OPUS_REASON=0 turns this check off.\n" + ROUTING_FOOTER
)

FABLE_REASON_REQUIRED = (
    "model=\"fable\" needs a `Why Fable:` line in the prompt (>= 12 non-space characters): the "
    "strongest model runs only on escalation (the same failure class red twice, a design opus already "
    "failed, or the owner names it). Add `Why Fable: <reason>` to the prompt, or route this dispatch "
    "to opus (design) or sonnet (building).\n" + ROUTING_FOOTER
)

# A label counts only at the START of a line (optional spaces, one list marker, optional bold), so text
# that merely mentions the label ("without a `Why Fable:` line?", this hook's own deny text pasted back)
# is not a reason.
_LINE_START = r"^[ \t]*(?:[-*][ \t]+)?(?:\*\*)?"
_WHY_OPUS_RE = re.compile(_LINE_START + r"Why Opus:(.*)$", re.M)
_WHY_FABLE_RE = re.compile(_LINE_START + r"Why Fable:(.*)$", re.M)
# A reason that STARTS with a <placeholder> counts as none, whatever follows it ("<reason> to the prompt, or route
# this dispatch to sonnet" is the hook's own advice line pasted back).
_PLACEHOLDER_RE = re.compile(r"^(?:\*\*)?\s*<[^<>]*>")


def _has_reason(pattern, prompt):
    if not isinstance(prompt, str):
        return False
    for m in pattern.finditer(prompt):
        text = m.group(1).strip()
        if _PLACEHOLDER_RE.match(text):
            continue
        if len(re.sub(r"\s", "", text)) >= 12:
            return True
    return False


def deny(reason):
    print(reason, file=sys.stderr)
    sys.exit(2)


def _allowed_types():
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

    if subagent_type in _allowed_types():
        return  # exempt subagent_type (default: fork — inherits the parent model)

    if model is None or not str(model).strip():
        deny(MISSING_MODEL)

    alias = str(model).strip().lower()
    if alias not in ALIASES:
        deny(UNKNOWN_MODEL % json.dumps(str(model)))

    prompt = tool_input.get("prompt")
    if alias == "opus" and os.environ.get("FACTORY_REQUIRE_OPUS_REASON") != "0":
        if not _has_reason(_WHY_OPUS_RE, prompt):
            deny(OPUS_REASON_REQUIRED)

    if alias == "fable":
        if not _has_reason(_WHY_FABLE_RE, prompt):
            deny(FABLE_REASON_REQUIRED)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
