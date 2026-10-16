# Goal contract GC-2c (Sun 2026-10-18): the app Execute chain - basket out, Kite's answer back, reconciled

Chain: `goal-chain.md` (rules, process rules 1-8, scorecard). Written by GC-2b from its results (2026-10-17 night).
Owner needed: **no** (recorded replies only; no Kite login; no order; DB steps only through
`scripts/orchestrator/db_run.py` on ofo_test). **Cap: 6 h wall-clock** - this contract's cap governs even though the
chain prompt mentions 8 h. **Tail reserve: 1.5 h** for items 6-8 (docs batch, GC-3 contract and its review, merge);
every time gate is "item estimate + 1.5 h remain", read from the clock (`date`) when the previous item merges, and
written in the handover. **Give-way order (contract review 2026-10-17: items 1-2 alone are about 3 h with the tail
4.5 h):** park (i) item 5b, then (ii) item 5, then (iii) item 4, then (iv) item 3; items 3 and 4 are EXPECTED to park.
Items 1-2 are the contract. (Audit events for the Execute chain, REQ-064, are not in this contract: a later item.)

Core: one Execute request on a saved strategy builds the read-only Kite basket through `ofo_app/checked_basket.py`
(the only basket path, W-081/PR #337) and, on the user's return from Kite, the recorded replies of the owner's real
order (`tests/fixtures/kite_replies/`, W-091) are read back through `ofo_app/kite_replies.py`, applied to the order
book by tag and reconciled - 0 mismatches after entry, flat after exit.
Proof: one route-level test (a DB test: CI proves it; locally only that one file through `db_run.py`). The recorded
orders carry tags `OFS1V1L0` (entry) and `OFS1V2L0` (exit) (`tests/fixtures/kite_replies/orders-151006.json`), so the
test seeds strategy id **1** at version **1** (entry) and version **2** (exit) - a database-assigned id would never
match a tag. POST Execute for v1 -> a basket whose orders carry our tags (REQ-073 AC-2) and are LIMIT + read-only
(AC-1); the return call with the recorded 122104 replies -> order states and the 65-unit position reconciled with 0
mismatches (AC-3); POST Execute for v2 (the exit), then the 151006 replies -> flat, the strategy record exited.

## Why (from GC-2a and GC-2b results)
- Every piece exists in isolation and nothing joins them: `checked_basket` has no route (GC-2a, PR #337; its review
  said the route must type-check the basket and build it again on every request); the reply adapter (GC-2b, W-091)
  has no caller; the fresh eligibility registry for "just before execution" (GC-2b, W-092) has no caller; `ExecutionContext`
  is built nowhere in the app, so #273 stays open until the route fills its margin from Zerodha's figure.
- The order book, fills and adopted holdings are in memory only (#313): a restart between Execute and the return from
  Kite loses the plan.
- GC-2b merged: W-091 Kite reply adapter (PR #343; ADR-102 P&L at the paisa, average price exact; ADR-103 an
  out-of-order fill is refused and blocks, never a side flip), W-092 eligibility from Zerodha (PR #346; ADR-104; the
  gate accepts only a sealed `ZerodhaEligibility`; save/restore refuse NEW ineligible legs), ADR-058 delisted-held
  blocks the holding strategy (PR #347), W-081 AC-1/3/4 verified on main; the CI scale-test flake's root cause
  (#344: generic plan under zero-row statistics) and its fix (PR #348). W-017 for the broker-reply types (PR #349: `broker_response_recorded`, `execution_recorded`; migration 0015; a non-empty
  payload keeping no declared key is refused; session types unproven until GC-3).
- Not done by GC-2b and moved here BY NAME: W-091's "strategy record exits when the ledger reaches 0" (RESULT gap e).

## Done list (order 1 -> 2; 3-5 behind time gates; 6-8 always)
1. **Execute route -> read-only basket (Tier A; REQ-073 AC-1/AC-2, REQ-055 AC-1).** Step 1 IS the core proof's first
   half. The route builds a fresh eligibility registry (`ofo_app.eligibility_from_zerodha.fresh_registry`), builds
   `ExecutionContext` with Zerodha's margin figures (#273), runs the pre-execution gate, then
   `ofo_app.checked_basket.checked_basket` (it needs an exact `KiteMargin` client - offline: the transport replaying
   the recorded funds fixture used by `tests_app/test_checked_basket.py` - and a `freeze_check`; name the freeze-limit
   source in the brief); it type-checks the basket it gets and
   builds it again on every request (no cached basket). Copy from: legacy-reuse map row 101 (`app/api/routes/orders.py`)
   reference only - float money and optional strategy_id there break ADR-008 / ADR-002.
2. **Return from Kite -> read-back -> reconcile (Tier A; REQ-073 AC-3, REQ-057, REQ-060, REQ-058).** The return
   handler reads orders/trades/positions through `kite_replies.py` (in tests: the recorded fixtures through a fake
   transport), matches by TAG, applies fills, reconciles, and moves the strategy record to exited when the ledger
   reaches 0 (W-091's moved-out objective, RESULT gap e). A closed or partly placed basket is a partial execution,
   never retried.
3. **Persisted order book (#313, Tier A: a migration), only if 2 h + tail remain (expected to park).** Store the order
   book, fills and adopted holdings so a restart between Execute and return loses nothing, written in the SAME
   transaction as the strategy version (#313); migration via Alembic as the owner role, with a real downgrade (the
   replay tests downgrade the whole chain). Finding `branch-migration-tests-move-shared-db`: never let the local mirror
   run this branch's migration replay tests against the shared test DB without, afterwards, `alembic current` and
   `alembic upgrade head` from MAIN; prefer leaving the replay files to CI.
4. **Execute screen (REQ-073 AC-1..3 front end), only if 1.5 h + tail remain (expected to park).** The button, the
   hand-off to Kite's page, the return view with Zerodha's states; Playwright via CI. Anything beyond REQ-073's own
   example (layout, wording, states shown) goes to `owner-questions-<the run's date>.md` with a recommendation; all
   wording is decision-support only (ADR-003: never "you should"); AC-3's "shown as a planning estimate" label for the
   platform's margin figure (W-081 verifier caveat) lands here.
5. **Carry-overs, each named in the handover:** #338 (negative balance blocks a closing basket); W-091 MINOR: no >= 0
   check on a broker average price; W-092 MINOR: no limit on how old the last instrument-list load may be (a stopped
   daily load keeps contracts "listed"); the ADR-058 delisted-held function's app caller (needs item 3's persisted
   order book) AND, before that wiring, `clear_reconciliation_block` must refuse while a `delisted_held` position is
   still held (PR #347 review MINOR: today it checks fill counts only); positions keyed by symbol without exchange
   (PR #347 MINOR); W-091 / W-092 / W-017 AC verifier passes on main (their cards are in_review, no evidence yet); the audit
   allowlist's nested-snapshot `{}` (PR #349 MINOR, older than it); the #344 follow-up (whole-table hash per batch
   under zero-row statistics); the verifier-in-flight hook's false block after a verifier ends (finding
   `liveness-from-a-file-nobody-deletes`, 2 occurrences; kit issue #113) - workaround: delete the named snapshot only
   after confirming no verifier agent runs. GC-2b parked nothing.
5b. **Mechanism for `caller-supplied-verdict-trusted` (6 occurrences, 2 in GC-2a/2b nights; Tier A, ~1 h, runs before
   item 3 if 1 h + tail remain).** One shared seal helper in the domain that every proof-object uses (today
   `KiteBasket`, `MarginVerdict`, the sealed eligibility each hand-roll it), and a repo test that every type a gate
   accepts as proof (the parameter types of the pre-execution gate, `build_basket`, `checked_basket`) refuses
   construction, copy, deepcopy, pickle, `dataclasses.replace` and setattr outside its minting function. Proof: the
   test fails on a planted open dataclass passed to a gate.
6. Docs batch. 7. Kit issue #113 state checked. 8. Write GC-3 (the live 1-lot order, owner present), get it
   independently reviewed with the review recorded VERBATIM in a file on main, mark it NEXT, merge with the handover;
   print the prompt, the 5-line summary and the scorecard.

## Process rules (checkable lines; `goal-chain.md` process rules 1-8 apply in full)
- Chain rule 2: `git pull` main, refuse if a row is RUNNING, set this row RUNNING in the first commit.
- Before every merge gate: `merge.py` / `land.py` (update-branch inside); after every merge of main into a branch:
  `merge_audit.py . <branch-tip> <main-ref> <merged-head>`.
- Local before push: `atool.py <worktree> --no-tests` (it runs the ratchet; read its exit and every ` rc ` line);
  `pr_close_check.py`; changed files' tests; `tests/marketdata/` and `tests/test_*.py` whenever an `ofo_app` module is
  added (the adapter scan).
- Kit tools in a scratch worktree run with that worktree as cwd (a launcher like GC-2a's `kit_in.py`).
- Every brief: `check_brief.py`; reviewer checklist + attack cases; `Findings checked:`; `Copy from:`; `Budget:` (at
  most 80 % of the agent type's cap; GC-2b's builders ran 88/80, 122/75 - split an item that will not fit);
  `Report: evidence-table`.
- Reviews of cards/spec-writing work run as `Explore` (no verifier write-guard window) unless an AC verdict is needed.
- A builder's "tests pass / ratchet OK" is a claim: re-run before pushing.

## Stops
- None needs the owner. A choice that changes what a user sees beyond the spec goes to `owner-questions-<the run's
  date>.md` with a recommendation; the run continues.
- DB steps through `db_run.py` only; tunnel down = park that item, continue the offline ones.
- Park rule: two failed rounds or an outside blocker -> a `parked` issue via `gh_issue.py --stage`, named in the
  handover.
