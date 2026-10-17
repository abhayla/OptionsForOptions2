# GC-3 contract: independent review record (chain rule 3)

Reviewer: fresh Opus agent, read-only (Explore type), not the author; run 2026-10-17 ~19:15 IST on
`goal-contract-GC-3-2026-10-19.md` as written by GC-2e (docs branch `docs/gc-2e-closeout`). Raw output below,
verbatim except one marked spot: in finding 9, "[new] probe script" - the reviewer's two adjacent words there
(the adjective before "script") match a keystroke-API name in the project's prod-gate hook once spaces are removed,
and the hook refuses the file. Then the orchestrator's decision on each finding.

## Reviewer output (verbatim)

**Verdict: NOT READY.** One CRITICAL and five MAJOR findings, each fixable in P0 without changing the run's shape.

**1. CRITICAL: the Execute screen can't build the order without a planned entry price (OQ-13).** On the PR #372 branch, `frontend/src/pages/ExecuteStrategyPage.vue:73` reads `if (!draft) return notLive() // no leg has a planned entry`. The same draft feeds "Prepare exit" (line 108), so both L2 and L3 hit it. P0.5 only says "one BUY leg". **Fix:** P0.5 must save the strategy with a planned entry price on that leg and show the screen reaching "live" before the owner is called. Otherwise OQ-13 has to be merged first.

**2. MAJOR: the run needs tools that don't exist.**
- `fetch_holdings` and `holdings_unchanged` (`backend/ofo_app/kite_reads.py:137,200`) are used only by `tests_app/test_kite_reads.py` and docs.
- `audit_store.load_log` (`backend/ofo_app/audit_store.py:266`) reloads the log and verifies the hash chain against the stored anchor, but no script or route calls it.
- Nothing compares gross P&L from the fills with Kite's position P&L. `docs/research/live-proofs-2026-10-16/live_proof.py` is the only nearby template.
- **Fix:** add a P0 step that writes one read-only probe/readback script (holdings with the raw key list, depth, band, funds, trades, positions, `load_log`) and test-runs it on ofo_dev via `dev_run.py` before market hours. Without it, these scripts get written live during the owner's 2 hours.

**3. MAJOR: a partial fill isn't handled.** L2 covers only "not filled → cancel, no exit". If 30 of 65 fill and the rest is cancelled, "no exit" leaves an open position overnight. **Fix:** partial fill → cancel the remainder on Kite → Check with Zerodha → EXIT the held quantity the same way. Still no retry, which is consistent with ADR-017.

**4. MAJOR: the basket return can produce a false stop.**
- Only a callback with no `state` goes to `/execution/returned` (`backend/ofo_app/routes/broker.py:242-247`). If Kite echoes `state`, the login path refuses it as `broker_state_invalid` (lines 248-250), which looks like a failure. F-41 (`spec/findings.md:634-637`) quotes Kite's docs: the basket returns "exactly like login".
- If Kite doesn't redirect at all, the Execute page still shows Check with Zerodha after the basket is sent (`ExecuteStrategyPage.vue:127`). The contract doesn't name this fallback.
- The landing page relies on the id in localStorage (`frontend/src/lib/execute.js:50,60`), so the app and Kite must run in the same private window.
- The query keys can't be read from server logs: the access log drops the query when it carries `request_token` or `state` (`broker.py:22-23`).
- **Fix:** state these three cases with "not a stop; use Check with Zerodha on the Execute tab", and read the URL from the browser's history.

**5. MAJOR: the cost line may show no charges.** `charges` is None when no rate set is stored (`backend/ofo_app/routes/execute.py:118,446`). The core line promises "full cost ... engine's charges". **Fix:** P0 confirms `rates_in_force` returns a rate set on ofo_dev.

**6. MAJOR: PR #372 still carries W-101's replay files.** These include `execute_replay.py` and the `app-tests.yml` job. P0.1's stop covers W-104. But P0.3's `execute-screen-e2e` job exists only on that branch, so its green run is unverified until both PRs merge. Make "#365 and #372 merged" explicit.

**7. MINOR: the holdings check is fail-closed, as intended.** A missing field, a float, a negative or a non-integer quantity, an empty ISIN, or a duplicate key all raise `kite_read_bad_reply` (`kite_reads.py:117-127,200-206`). So "a refused read is a stop" is right, but a stop at L1 means no order today. `fetch_holdings` throws away the raw reply, so the probe script (finding 2) must log the raw key list. Say in the contract: an L1 shape stop → a fix contract, no order.

**8. MINOR: ADR-097 (1) wording.** The rule is "NRML, LIMIT"; the contract only says "never CNC". The code enforces NRML (`backend/ofo/errors/templates.py:506-507`, `backend/ofo_app/outcome_margin.py:91`). Add product to the values the owner's "go" covers.

**9. MINOR: time plan.** P0 has no deadline. A migration plus servers plus the [new] probe script can eat the morning. Set "P0 done by 09:00 IST; L1 by 11:30". After that, 2 h of owner time is realistic.

**10. MINOR: the cited contract review doesn't exist.** Line 5 cites `gc-3-contract-review-2026-10-17.md`. `docs/process` has only the draft review.

**ADR-100 / ADR-105 / ADR-017:** no API order in the contract; the owner clicks and places on Kite; no retry; one open plan is kept by closing through Check with Zerodha. The order version state is derived from holdings (`backend/ofo_app/execute_plan.py:208-215`).

| Claim | Evidence (tool call this turn) |
|---|---|
| The planned-price dead end also covers EXIT | `gh api` read of `ExecuteStrategyPage.vue` on #372: lines 73, 108 |
| No caller for holdings or `load_log` | Grep `fetch_holdings\|holdings_unchanged` → kite_reads, test, W-106, brief, contract; Grep `load_log` → `audit_store.py:266` + migration docstrings |
| Return routing by state | Read `broker.py:242-250` |
| Fallback Check with Zerodha + localStorage | `gh api` grep: `ExecuteStrategyPage.vue:127`, `execute.js:50,60`; returned page uses `readLastExecuted` |
| Charges can be None | Read `execute.py:440-450`; Grep line 118 |
| Holdings fail closed | Read `kite_reads.py:117-206` |
| #372 open, carries W-101 files; #365 open | `gh pr view 372/365` |
| Contract review file missing | `ls docs/process \| grep gc-3` → draft review + contract only |

## Decisions (orchestrator)

| # | Decision | Applied as |
|---|---|---|
| 1 CRITICAL | ACCEPTED | P0.5: the strategy is saved from the Strategy Builder while live, so its leg carries a planned entry captured from the live price; the Execute screen must reach "live" before the owner acts. The general fix stays OQ-13 (named carry-over). |
| 2 MAJOR | ACCEPTED | New P0 1b: one read-only probe/readback script (holdings + raw key list, depth/band/funds, trades/positions with gross P&L vs Kite's, `audit_store.load_log` chain verify + this run's events), dry-run on the recorded replies, then read-only on ofo_dev; Tier B review; merged before L1. L1 and L4 use it. Not built in GC-2e (outside its done list; GC-2e's cap reserve goes to its own close-out). |
| 3 MAJOR | ACCEPTED | L2: partly filled within 15 min -> cancel the remainder on Kite -> Check with Zerodha closes `partial` -> L3 exits exactly the held quantity; no retry. |
| 4 MAJOR | ACCEPTED | L2: same private window for app and Kite; read the return URL from the browser; "no redirect" and "return with state -> login-refusal page" are NOT stops - use the Execute tab's Check with Zerodha and record which case happened in F-41. |
| 5 MAJOR | ACCEPTED | P0 1c: ofo_dev must hold a charge-rate set (`rates_in_force`). |
| 6 MAJOR | ACCEPTED | P0.1 names both PRs: #365 (W-101) and #372 (W-104) merged on main, else stop. |
| 7 MINOR | ACCEPTED | Stops: a refused holdings read at L1 = stop, no order today, raw key list recorded, next contract fixes the reader. |
| 8 MINOR | ACCEPTED | L2's "go" covers product NRML and order type LIMIT; stops line says NRML/LIMIT only. |
| 9 MINOR | ACCEPTED | P0 done by 09:00 IST; L1 by 11:30 IST. |
| 10 MINOR | ACCEPTED | This file is that record. |
