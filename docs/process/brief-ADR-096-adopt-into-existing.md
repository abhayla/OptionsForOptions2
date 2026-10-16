# Builder brief: ADR-096 order-free adopt of a held position into an existing strategy (REQ-061 AC-2) - Tier A

Core: adding a held Zerodha position to an EXISTING strategy records the held legs as a NEW version of that strategy
whose intended position equals (old intended + held units), with Zerodha's average price as each added leg's entry,
and prepares NO order (no proposal, no `propose_execution`, nothing to execute); the next reconciliation against
Zerodha's positions shows no difference for the adopted contract.
Proof: a test on today's REAL position (`D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/real-order/positions-*.json`, the
`net` row for NIFTY26O1923650CE: BUY 65 NRML avg 5.10, real order 2026-10-16 12:20:50 IST): copy only that row (no
account fields beyond the row) into `tests/fixtures/kite_positions/positions-2026-10-16-one-ce.json` (numbers as JSON
numbers), add it to an existing 1-leg strategy holding a different contract, and assert: new version, intended
position = both contracts, zero orders/proposals created, reconciliation against that positions reply = agree.

Model: opus.
Budget: 45 min wall-clock, 75 tool calls. At budget STOP and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 300 words, branch + head sha.
Copy from: none - extends this repo's `backend/ofo/reconciliation/grouping.py` (W-083) and
`backend/ofo/strategy/versions.py`; legacy-reuse map has no adopt-into-existing row.

## Spec basis
- ADR-096 decision, verbatim: "Adding a held position to an existing strategy records the held legs (Zerodha's
  quantity, average price as the entry per ADR-084) as a new version of that strategy and prepares NO order for them."
- REQ-061 AC-2; ADR-084 (entry = Zerodha's average price, editable; OQ-6: finer than paise asks the user, never rounds
  silently); ADR-002 (every order belongs to a strategy).

## What to build
- Replace W-083's "not available yet" refusal for add-to-existing with the order-free path; keep create-new and
  standalone unchanged.
- In `StrategyRecord` (or a sibling function), an explicit order-free version path, e.g. `adopt_held(...)`: never calls
  `edit`/`propose_execution`; the new version is immediately the active one with its actual position updated from the
  observed Zerodha position (it is held, not intended-to-be-executed).
- Refuse (blocking, user-facing catalogue error) when: the target strategy is exited, blocked by an unresolved
  reconciliation mismatch (ADR-019), has a proposed/unconfirmed version, already holds the same contract on the
  opposite side or a different quantity than Zerodha shows, or the underlying differs.
- Audit every choice the way W-083 does (same audit store calls).
- Add a new error/explanation template only if needed, with a unique code (guard `tests/errors/test_template_codes_unique.py`).

## Reviewer checklist (Tier A reviewer attacks these - test each first)
1. Zero orders anywhere: assert no proposal/version in "proposed" state and no ExecutionPlan built (mutation: route
   through `edit` -> a test fails).
2. Reconcile after adopt: agree for the adopted contract; a later Zerodha qty change is still detected.
3. Blocked / exited / proposed target strategy refused; underlying mismatch refused.
4. Same contract already in the strategy: opposite side or different qty refused, never netted silently.
5. Average price finer than paise follows OQ-6 (asks, never rounds); Decimal only.
6. Half-adoption impossible: a group adopts all rows or none.
7. Audit row written for success and for each refusal.
Findings classes checked: grep `knowledge/findings/` for `reconcil`, `adopt`, `double`, `order`.

## Rules
- Your own worktree, branch `build/ADR-096-adopt-existing` from `origin/main` (must contain ADR-096).
- Targeted tests only: `python -m pytest -q -p no:cacheprovider tests/reconciliation tests/strategy tests/errors`;
  app tests for any route you touch via `scripts/orchestrator/db_run.py` (one file); `python scripts/ruff_ratchet.py`.
- No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; no regenerated files in the PR.
- Commit and push; do not open the PR; never write `evidence/`, `work/` or the spec. Never call Kite.
