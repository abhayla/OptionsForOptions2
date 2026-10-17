# Brief W-107: Execute refuses while the strategy's own closed plan has drifted at Zerodha (Tier A)

Core: a strategy whose CLOSED plan's tagged order, in today's Zerodha book, is still working or filled other than the
quantity stored at close is refused by POST /strategies/{id}/execute (ENTRY and EXIT) with the reconciliation block,
nothing stored, no plan number consumed.
Proof: the real 2026-10-16 replies (tests/fixtures/kite_replies/ orders-122104 + trades-122104, tag OFS1V1L0, BUY 65
COMPLETE): a stored plan 1 closed `nothing_placed` (filled 0) + that book -> Execute ENTRY refused (reconciliation
blocked) and EXIT refused; the same plan closed `filled` 65 + the same book -> not refused for drift.

Common brief: docs/process/builder-brief.md
Work item: create `work/W-107.md` in your PR (copy the frontmatter shape of work/W-105.md): requirement_ids [REQ-060],
depends_on [W-095, W-096], affected [backend/ofo_app/routes/, tests_app/], tests_required
['AC-6: tests_app/test_execute_drift_block.py'], status in_progress, tier A, the core/proof above. Its body says: this
covers the drift half of AC-6 only; Q222's rule that the block stays until a recorded resolution and the stored mismatch record
(REQ-060 AC-3/AC-5) are not built here, so no evidence is written for AC-6 from this item alone.

Why (RCA, defect-fix contract): the live Execute route decides reconciliation with `ep.strategy_blocked(positions,
held)` per request and never reads `execution_return.drifted`; so when the owner presses "Check with Zerodha" before
Kite's book shows the order, plan 1 closes `nothing_placed`, the order then fills (65 held at Zerodha, 0 on the
platform), the EXIT is refused (held 0) and a second ENTRY is ALLOWED (130 long). Found by the GC-3 P0 go/no-go review
(2026-10-17) on main 85e38e0.
Class: every strategy with a closed plan whose tagged rows in today's book are non-terminal or whose summed
filled_quantity differs from the stored filled_quantity (the population `drifted(history, book)` returns). Before: 0
of them blocked at Execute. After: all of them blocked, for ENTRY, EXIT and adjustment alike.
Detection: the new test file is the detection; no other detection change (No detection change beyond it: the return
route already reports drift as `blocked`).

Spec basis:
- REQ-060 AC-6: "While a mismatch is unresolved, new execution and adjustment execution are blocked (Q199)."
- REQ-060 AC-4: "Changes made directly in Zerodha are detected" (here: detected at Execute; "recorded" is NOT built).
- REQ-060 AC-7: "A broker position in no strategy and not recorded as standalone is offered the grouping choice (Q24)
  and blocks no strategy." - so DO NOT block an untagged surplus; only the strategy's own tagged drift blocks.
- ADR-105: held units come from stored plan fills; Zerodha is the authority (CLAUDE.md hard rule: an unresolved
  reconciliation mismatch blocks execution).

Copy from: none - reuses this repo's own `ofo_app.execution_return.drifted`; the legacy map has no row for drift
between stored plans and Zerodha's book.

## What to build (small: aim under 80 product lines)
- In `backend/ofo_app/routes/execute.py`, build the `TodaysBook` the same way the return route does (reuse its reader;
  never re-implement tag parsing) from the order book Execute ALREADY reads (line ~304) plus trades if `drifted` needs
  them - read once per request, inside the same transaction order as the module docstring states; update the docstring.
- If `execution_return.drifted(held.history, book)` is non-empty, the strategy id goes into
  `reconciliation_blocked_strategy_ids` (so the gate's existing reconciliation refusal and catalogue message apply,
  the same as a positions mismatch). An unreadable book is already a refusal - keep it so.
- Nothing else changes: no new message id unless the existing reconciliation one cannot be reused (then add it to the
  catalogue the normal way), no API model change (if one is unavoidable, regenerate docs/api/openapi.json).

Threat model: in scope - a closed plan of THIS strategy whose tagged order later fills, partly fills, is still working,
or was cancelled after a recorded fill; ENTRY, EXIT and adjustment; a book read that fails. Out of scope - untagged
positions (AC-7 says they block nothing), other strategies' drift on a shared contract, a mismatch that later agrees
(Q222 stickiness), persisting the mismatch.
Findings checked: caller-supplied-verdict-trusted, guard-without-killing-test, design-misses-cross-cutting-safeguard, margin-gate-blocks-closing-basket

## Attack cases (write these tests first; the reviewer runs them)
1. Real replies: plan 1 closed nothing_placed + book shows OFS1V1L0 COMPLETE 65 -> ENTRY refused, EXIT refused, nothing
   stored, no plan number consumed (assert the plan count before/after).
2. Same, plan closed filled 65 -> not refused for drift (positions agree) - the normal exit still works.
3. Book shows the tag OPEN (still working) on a closed plan -> refused.
4. Book shows partial 30 filled on a plan closed with 65 stored -> refused.
5. A tag of ANOTHER strategy drifted -> this strategy is NOT refused by this guard.
6. An untagged surplus on the strategy's contract (positions 130, held 65, no drift) -> NOT refused (AC-7).
7. Mutation: delete the new `if` -> tests 1, 3, 4 go red (name them in the report).

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus the changed files' tests: `tests_app/test_execute_drift_block.py` and every tests_app file that names the execute
route or `reconciliation_blocked` (grep first). If the -m repo_scan line crashes with INTERNALERROR from
pytest-metadata, add `-p no:metadata` and say so.
No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no
regenerated files in the PR.
Budget: 45 min wall-clock, 90 tool calls
Report: evidence-table
