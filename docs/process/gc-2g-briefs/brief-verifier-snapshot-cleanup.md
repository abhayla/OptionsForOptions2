# Builder brief: clear a verifier's orphaned write-guard snapshots when it stops - Tier A (a hook every session runs)

Common brief: docs/process/builder-brief.md
Core: when a verifier subagent stops, every write-guard snapshot that ITS shell calls created and that is still on
disk is deleted, so `verifier_inflight_gate` stops refusing evidence writes for a verifier that has finished; another
verifier's live snapshot is never touched.
Proof (step 1, before any other code): measure the real hook input. Wire a throw-away logging hook (scratch copy of
the settings, or a temporary entry you remove before committing) and dispatch ONE real `verifier` subagent that runs
one allowed shell command and one command the kit path guard blocks (any shell command naming `tools/ac_fp.py`).
Record from the real inputs: whether PreToolUse for the verifier's shell call carries `agent_id`, `agent_type`,
`session_id`, `tool_use_id`; whether SubagentStop carries `agent_id` / `agent_type`; and that the blocked call left a
snapshot in <tempdir>/verifier-write-guard/snap/. If PreToolUse lacks `agent_id`, STOP and report (the design changes).
Then build, and repeat the same real run with the new hook: the leftover snapshot is gone after SubagentStop.
Spec basis: none - the spec says nothing about the orchestrator's hooks (searched: snapshot, verifier, hook); this is
process tooling, best practice, recorded as a lesson. Root cause measured 2026-10-18 (GC-2g): the W-112 verifier's two
calls blocked by the kit path guard (its transcript lines 18 and 115) left the two snapshots of 20:12 and 20:13; the
kit guard deletes a snapshot only in PostToolUse (`.claude/hooks/verifier_write_guard.py:484-487`), which a call
blocked by another PreToolUse hook never gets.
Copy from: none - new project hook; the legacy-reuse map has no orchestrator-hook row.
Findings checked: liveness-from-a-file-nobody-deletes, verifier-guard-watches-every-worktree
Threat model: in scope - an honest verifier whose call another hook blocks, parallel verifiers (one must never delete another's live snapshot), a verifier killed without SubagentStop (the 15-min age rule in verifier_inflight_gate stays the fallback), a missing/corrupt ledger (fail open: delete nothing); out of scope - a forger editing the snapshot or ledger as the same user (the kit guard's own threat model).
Why Opus: Tier A - a hook wired into every session of this repo; the hook input fields must be proven on a real run.
Tier: A. Branch: build/verifier-snapshot-cleanup from origin/main.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## What to build
1. `scripts/hooks/verifier_snapshot_ledger.py` (project hook, standard library), two events:
   - PreToolUse, matcher `Bash|PowerShell`, only when `agent_type`'s last `:` part is `verifier`: compute the snapshot
     path the kit guard writes for this call by IMPORTING the kit module's `snap_path(data)` (read-only import of
     `.claude/hooks/verifier_write_guard.py` by file path; never copy its `_key` formula - one home), and append it to a
     per-agent ledger `<tempdir>/verifier-write-guard/owners/<agent_id>.txt` (run-discipline D2: shared state records
     its owner). Never blocks: exit 0 always.
   - SubagentStop, only for a verifier: for each path in that agent's ledger, delete it if it exists and is inside the
     snap folder (refuse any path outside it), then delete the ledger. Exit 0 always.
   Fail open on any error (a broken hook must never block a session or a verifier). The snap folder honours
   `OFO_VERIFIER_SNAP_DIR` like verifier_inflight_gate.py does (reuse its `snap_dir()`; import, don't copy).
2. Wire it in `.claude/project/hooks.json` (PreToolUse Bash|PowerShell and a SubagentStop entry), each command in the
   repo's fail-open form `f="$CLAUDE_PROJECT_DIR/scripts/hooks/<file>"; [ -f "$f" ] || exit 0; python "$f"`, then
   regenerate the settings with `python tools/kit_settings.py .` (bare command) and commit the generated settings file
   (the one regenerated file allowed here). Read hooks.json with the Read tool: the kit guard blocks shell commands
   naming `.claude`.
3. Update the docstring of scripts/hooks/verifier_inflight_gate.py (its "deletes it at PostToolUse" claim is untrue for
   a blocked call) - text only.
4. Tests in `tests/hooks/test_verifier_snapshot_ledger.py` (mirror tests/hooks/test_verifier_inflight_gate.py's style,
   `OFO_VERIFIER_SNAP_DIR` to a tmp dir): Pre records the exact path the kit's `snap_path` gives; Stop deletes only
   this agent's listed snapshots; a second agent's snapshot survives; a ledger path outside the snap folder is not
   deleted; non-verifier agents and the main session are ignored; corrupt ledger -> nothing deleted, exit 0; missing
   kit module -> exit 0. Each guard has a killing test (list them).

## Attack cases the reviewer will run
1. Two verifiers in parallel; verifier A stops while B's call is in flight -> B's snapshot must survive and B's
   PostToolUse must still judge normally.
2. A verifier call that is NOT blocked: its snapshot is removed by the kit guard's Post; the ledger delete at Stop
   finds nothing and does not error.
3. A ledger line naming `../../something` or an absolute path elsewhere -> not deleted.
4. The hook crashes (bad JSON input) -> exit 0, nothing blocked.
5. `kit_settings.py . --check` passes; the hook entries use the fail-open form.

## B4 standing items
(a) no time-budgeted job; (b) no new CI import (stdlib only; the test imports the kit module by path); (c) not a
detector - it is the structural cleanup at the point every verifier passes through (SubagentStop); (d) answer states:
snapshot present / already removed / outside the folder; ledger present / missing / corrupt; agent_id present / absent.

Rules: no new duplicated literal (import `snap_path` and `snap_dir`); reuse the existing helper; ruff/mypy baselines
must not rise; targeted tests only. Kit files are read-only (never edit `.claude/hooks/`, `tools/`). Do not open a PR.
Remove any temporary logging hook before committing; `git status --short` must be empty. Windows pytest: `-p no:metadata`.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus: python -m pytest -q -p no:cacheprovider -p no:metadata tests/hooks/test_verifier_snapshot_ledger.py tests/hooks/test_verifier_inflight_gate.py; python tools/kit_settings.py . --check
