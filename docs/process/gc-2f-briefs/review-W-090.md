# Review brief: W-090 range + column switch (branch build/W-090-range-step) - Tier A, fresh, round 1

Common brief: docs/process/builder-brief.md (review task: read-only; hands-on attacks first)
Core: a user range changes only which levels the engine evaluates; every P&L number for a level is identical to what
the default range gives for that level; bad ranges compute nothing; default requests are unchanged.
Proof: each finding cites path:line and a command run this turn.
Spec basis: REQ-034 AC-4, AC-5, AC-6; ADR-042; spec/business-rules/scenario-calculations.md; work/W-090.md.
Copy from: none - a review.
Findings checked: test-asserts-implementation-output, money-value-computed-outside-engine, guard-without-killing-test, grid values from the grid (builder-brief quality bar)
Threat model: in scope - the range check in resolve_range and its use in build_outcome, the request model, the Builder's range controls; out of scope - the Admin config's own values.
Why Opus: Tier A - the scenario level builder and outcome service feed every P&L column.
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table

Load the project skill options-math-review (Skill tool) first and apply its checklist. Read the diff (git diff
origin/main...origin/build/W-090-range-step); run tests in a scratch worktree under the session scratchpad (remove it).
Attacks:
1. For a range inside the default range, are the P&L values at shared levels byte-identical to the default response?
   (Run both through build_outcome and compare.)
2. Live level and breakevens: still inserted when inside the range; what happens when the live level is outside it
   (shown? the AC-5 "always among the scenario levels" rule - REQ-034 AC-2)? Quote the AC and say pass/fail.
3. Ranges: one end only, reversed ends, off-grid, not a whole number of steps, 201 columns, SENSEX with NIFTY's
   grid -> each refused with nothing computed.
4. A request with `step` -> 422 (extra field forbidden) and no regression for clients that never sent it.
5. Live push: a late push for an old range is dropped (test?).
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: targeted files only)
Report (under 300 words): verdict PASS / REVISE, findings (severity, path:line, one-line fix), evidence table.
