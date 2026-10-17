# Builder brief: W-096 Return from Kite - read back by tag, close the plan from Zerodha's answer, reconcile per strategy (Tier A: order state, reconciliation)

Core: with strategy 1's plan 1 stored open (OFS1V1L0, BUY 65 NIFTY26O1923650CE LIMIT 5.45 - the real basket), `POST
/api/strategies/1/execution/return` on the recorded 12:21:04 replies (`tests/fixtures/kite_replies/*-122104.json`)
closes plan 1 `filled` (65 of 65), shows the platform position 65 = Zerodha's 65 with 0 mismatches; then with plan 2
stored open (OFS1V2L0, SELL 65 LIMIT 3.10 - the real exit) the 15:10:06 replies close plan 2 `exited`, position 0,
Zerodha flat for this strategy, the strategy reads exited, 0 mismatches, and the fills' realised P&L is -130.00 (ADR-102;
equals Kite's flat-row `unrealised`). Replaying the same replies again changes nothing (exactly once).
Proof: step 1 is `tests_app/test_execution_return.py::test_core_real_order_return_entry_then_exit` (a DB test; CI
proves it - no local DB run this round, see Rules). Write it FIRST; the non-DB parts of it run locally. Seed plans through the W-094 store with
the real prices; reply files are served by a replay transport into `KiteReads`.

Tier: A (order state, reconciliation, REQ-057/058/060). Model: opus.
Why Opus: reconciliation by strategy with partial and closed-basket states, multi-module, adversarial cases.
Budget: 80 min wall-clock, 72 tool calls. HARD limit: at call 68 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words, plus each guard and its
killing test (mutation-run where the test runs without a database; say which guards only CI can prove).
Copy from: none - spec/technical-design/legacy-reuse.md has no return / read-back row (searched: reconcile, positions
sync, order status); algochanakya's order sync is not copied (ADR-054).
Findings checked: fill-not-exactly-once, trust-broker-status-word, resolution-on-stale-broker-copy,
held-without-platform-fill-invisible-to-ledger, state-read-after-await, caller-supplied-verdict-trusted,
state-with-no-working-exit, design-misses-cross-cutting-safeguard
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py
(Run all of `tests/errors/` before every push: 10 s, no database; three builders met the producer scan only in CI.)

Read first: `docs/process/builder-brief.md` (every line applies), `CLAUDE.md`, `docs/process/gc-2c-design-review-2026-10-17.md`
(findings 3, 5, 6 are this item's design constraints), `spec/decisions/ADR-105.md`, `backend/ofo_app/kite_reads.py`,
`backend/ofo_app/kite_replies.py`, `backend/ofo_app/execution_plan_store.py`, `backend/ofo_app/routes/execute.py` and
`backend/ofo_app/execute_plan.py` (W-095: reuse its platform-position function; never a second copy),
`backend/ofo/orders/model.py` (`OrderBook`, `reconcile_cumulative`, `realised_pnl`),
`backend/ofo/reconciliation/compare.py`, `blocking.py`, `resolution.py`, `backend/ofo/strategy/versions.py`,
`tests_app/test_kite_replies_to_domain.py` (the W-091 sequence on the same files).

## Spec basis
- REQ-073 AC-3: "When the user returns from Kite, the platform reads the actual order states and positions from Zerodha and
    reconciles them (REQ-057, REQ-060); a basket the user closed or only partly placed is handled as a partial
    execution (REQ-058), never retried automatically."
- REQ-057 AC-2: "A submitted order never changes strategy state or positions until the broker confirms execution (Q195)."
- REQ-058 AC-5: "A strategy is never marked complete just because all intended orders were submitted."
- REQ-058 AC-6: "V1 never resubmits a failed order automatically; the failure is shown with its reason and the user chooses
    the next action (Q193)."
- REQ-060 AC-7: "A broker position in no strategy and not recorded as standalone is offered the grouping choice (Q24)
    and blocks no strategy. A mismatch blocks only the strategy whose contract quantity disagrees (Q199)."
- ADR-050 item 4: "(d) record orders placed
   outside the platform as external, never drop them"

## Design (decided; ADR-105 and the design review)
- Stateless per call: everything is rebuilt from the database (stored plans, their filled quantities) plus ONE fresh
  Zerodha read (orders, trades, positions through `KiteReads`). No in-process registry; a `StrategyRecord` may be built
  inside the request from stored data and thrown away.
- Matching: every order whose tag `parse_tag` decodes to this strategy. Tag in a stored plan -> that plan's order.
  Tag for this strategy in NO stored plan -> an EXTERNAL order: listed in the reply and written to the audit store as
  a `broker_response_recorded` event within the W-017 allow-list keys (if a needed key is not allowed, list it in the
  reply only and say so in your report - never widen the allow-list here). Never dropped.
- Per OPEN plan, from Zerodha's rows for its tags (status word kept as read, finding trust-broker-status-word: the
  decision uses `filled_quantity` and whether the word is terminal; terminal = COMPLETE, CANCELLED, REJECTED; any
  other or unknown word = still working):
  - any order still working -> the plan stays open; nothing changes (REQ-057 AC-2); the reply's plan state is `waiting` (any text a user sees comes from the
    error/message catalogue, never an ad-hoc string).
  - all terminal, every order filled == quantity -> close `filled` (ENTRY) or, for an EXIT, `exited` only when the
    strategy's platform position after this plan is 0 on every contract AND the reconciliation for this strategy
    shows no mismatch; otherwise close `filled` and report the mismatch.
  - all terminal, nothing filled, or no tag of the plan in today's book (the user closed the basket) ->
    `nothing_placed`.
  - all terminal, some filled -> `partial` (REQ-058 exception: the reply carries the four choices' ids from REQ-058
    AC-2 for the screen, and nothing is resent).
  - Zerodha's `filled_quantity` disagrees with the sum of today's trades for that order -> plan stays open,
    reconciliation required (never pick one).
  `close_plan(..., filled=...)` stores each order's filled quantity (W-094).
- Reconciliation per strategy through `ofo.reconciliation.compare.compare` (and `blocking.blocked_strategy_ids`):
  platform side = the same DB-derived position W-095 uses; broker side = Zerodha's net; units on a contract beyond
  what this strategy (and any other stored strategy) explains are unexplained and block NO strategy (REQ-060 AC-7);
  fewer units than the strategy holds, or the wrong side, block this strategy with REQ-060 AC-3's fields.
- Fills exactly once by trade id (the W-091 adapter and `OrderBook` already refuse a repeat; prove a replay changes
  nothing). P&L only through `realised_pnl` (one engine, ADR-008); money out as 2-decimal strings.
- The strategy reads `exited` when its latest EXIT plan is closed `exited` (derived; no status migration).

## Reviewer checklist (each red when mutated; write these first)
- A plan with an OPEN (or unknown-word) order is closed -> red; positions change while an order only shows
  submitted -> red.
- The basket closed on Kite's page (no tag in the book) -> `nothing_placed`, never `filled`, never retried.
- One of two orders filled -> `partial`; nothing resent (assert no Kite write; the door refuses anyway).
- Exit with Zerodha still holding 65 -> not `exited`.
- An order tagged OFS1V9L0 with no stored plan 9 -> external, listed and recorded, never dropped.
- A standalone 65 on the same contract beyond the strategy -> blocks no strategy; Zerodha 0 while the strategy holds
  65 -> blocks this strategy.
- Same replies twice -> identical state, trade ids once, P&L -130.00 once.
- `filled_quantity` 65 vs trades summing 60 -> plan stays open, reconciliation required.

## Parallel work you build on (orchestrator, 07:40 IST)
- W-094 (store, migration 0016) is on main or about to be: `git log origin/main --oneline -5`; if not, merge
  `origin/land/W-094`.
- W-095 round 3 is running on `build/W-095-execute-route`: it adds ONE function `held_units(plans)` (net filled
  units per contract over all plans; BUY +, SELL -) in `backend/ofo_app/execute_plan.py` and corrected ADR-105 says the
  held position is that net. Write the parts that do not need it first (matching by tag, per-plan classification,
  external orders); then `git fetch origin && git merge origin/build/W-095-execute-route` and CALL `held_units` - never
  a second copy. If it is not pushed by your call 45, say so and stop at a clean commit.

## Rules
- NO local database run this round: another builder's core test inserts the same strategy id 1 into the shared test
  DB at the same time. Your DB tests are proven by this PR's CI (its own PostgreSQL). Write them so they would pass
  there; run every non-DB test locally.
- `python scripts/orchestrator/atool.py <your worktree> W-096 --no-tests` (read its exit and every ` rc ` line);
  `python scripts/ruff_ratchet.py` must not rise - write small functions from the start (W-095 raised 7 rules).
- Commit FIRST `work/W-096.md` (frontmatter shape of `work/W-091.md`: id W-096; title "Return from Kite: read back by
  tag, close the plan from Zerodha's answer, reconcile per strategy (REQ-073 AC-3)"; requirement_ids [REQ-073];
  tier A; depends_on [W-093, W-094, W-095]; tests_required ['AC-3: tests_app/test_execution_return.py']; core/proof =
  the lines at the top; status in_progress) and add `W-096: 4b` under `work_items:` in
  `docs/process/coverage-stages.yaml`.
- No UI, no change to the Execute route's behaviour, no Kite write. No kit or `spec/` edit, no `views/`, no findings
  INDEX, no regenerated files, no `evidence/`.
- Commit and push `build/W-096-return-route`. No PR.
