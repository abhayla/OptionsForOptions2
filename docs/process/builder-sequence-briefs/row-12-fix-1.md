# Row 12 fix round 1: REQ-072 AC-2 (W-140) - a missing index value is refused with the INDEX as the reason

Row-ahead: yes (ADR-171: built while row 11 is verified; closes after row 11)
Overlap: none (checked against row 11's files - kite_ws.py, feed_health.py, reconnect_policy.py, market_calendar.*,
timeutil.py, feed_main.py, the errors templates, order_limits_registry.py; this fix touches only
`backend/ofo/outcome/service.py` and one test file; the orchestrator runs `overlap_gate.py` with this plan before dispatch)

Common brief: docs/process/builder-brief.md (Budget hard stop: at 32 calls start nothing new, commit, report). Run
`python scripts/orchestrator/mutation_gate.py` on the reordered gate before reporting; quote its results file (R18).
Size: S, 2 files, 2 items
CI: kit tests job (`tests/outcome/test_spot_gate_reason.py` (new), `tests/outcome/`; vars: none). No database.
Expected (orchestrator, before dispatch): 20 min / ~90k (a small fix, fresh agent - R5).

Core: when the feed is connected and only the index quote is missing, the user is told the index value is missing -
not that the forward could not be derived from the option chain.
Proof: step 1 is `tests/outcome/test_spot_gate_reason.py` failing first: the recorded frames
(`tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz`) with the NIFTY index quote removed and the chain
present -> today the reason reads "forward for 2026-10-13: the forward price could not be derived from the option chain"
(service.py:439-443 adds forward errors before the spot gate at :445-456); after the fix it renders `outcome_spot_missing`.

Spec basis: REQ-072 AC-2 (the index spot is the gated live spot; a missing or unhealthy index value is refused with
that as the reason). ADR-015 (no stale data shown as live). The rows 12-14 verifier (2026-10-23) found that the
spot-missing and spot-unusable reasons never show on the real path.
Copy from: none.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-next-12` (made by the orchestrator with wt-new.ps1), branch
`build/seq-row-12`, from the chunk head. Work, test and commit ONLY there; never write in row 11's worktree. Commit with
`git commit -F <msg> -- <your paths>`; do NOT push. BINDING: never stop a process by name. Scratch:
`...\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row12-fix1`.

## What to do
1. In `build_outcome` (`backend/ofo/outcome/service.py`), check the spot (missing, not a live price, unhealthy or
   unavailable) BEFORE collecting the forward errors, so a missing index gives `outcome_spot_missing` /
   `outcome_spot_unusable`; a missing chain with a good spot keeps the forward reason. No change to what is computed.
2. Tests: index missing + chain present -> the spot reason; index stale -> `outcome_spot_unusable` naming the health;
   index good + chain missing -> the forward reason (unchanged); every existing `tests/outcome/` test still passes.

Attack list: (each names its test file)
1. Index missing, chain present -> the index reason (`tests/outcome/test_spot_gate_reason.py`).
2. Index stale (+90 s) -> the unusable reason with the health (same file).
3. Index good, chain missing -> the forward reason unchanged (same file).
4. Both missing -> the index reason (the earlier gate wins) (same file).
5. Nothing computed in any refused case (no P&L, no IV) (same file).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) the snapshot's answer states for the spot - present and live, stale, unavailable, absent, a last price of 0 - each in the test file with what the user sees.
Threat model: in scope - a refusal naming the wrong cause, a refusal path computing anything; out of scope - the feed's own health rules (row 11).
Findings checked: wall-clock-assertion-flakes-under-load
Reviewer checklist: only the order of the gates changes; reasons from the explanation templates' one home; real
recorded frames in the core test; gate results quoted; no new duplicated literal; reuse the existing helper; ruff/mypy
baselines must not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 20 min wall-clock, 30 tool calls
Report: evidence-table
