# Goal contract GC-2e (Sun 2026-10-18): live-order preparation - everything the live 1-lot run needs, unattended

Chain: `goal-chain.md` (rules, process rules 1-8, scorecard). Written by GC-2c from its results (2026-10-17). Two
independent reviews shaped it: a GC-3 draft review (`gc-3-draft-review-2026-10-17.md`, NOT READY - the live run could
not start on what is merged, so the preparation moved here) and this contract's own review
(`gc-2e-contract-review-2026-10-17.md`, NOT READY on its first draft - all findings accepted and applied below).
Owner needed: **no** (recordings and replays only; no Kite login; no order; DB steps only through
`scripts/orchestrator/db_run.py` on ofo_test, ONE holder at a time). **Cap: 6 h wall-clock. Tail reserve: 1.5 h**
(docs batch, GC-3 contract + review, merge).
**Order and give-way:** item 6 runs in parallel from the start; items 2 -> 3 -> 5 are the critical chain (the screen
needs the replay and the cost); item 4 (audit) runs beside item 3. Give way in this order: (i) item 9, (ii) item 8.
Items 1-7 are the contract and are never given way (each still follows the park rule). If item 5 (the screen) parks, GC-3 is NOT started: the next contract finishes the screen
first (GC-3 cannot place a basket without it).

Core: the product path for one real order exists end to end on main, proven on the recordings: a saved strategy's
Execute screen shows the exact orders AND their full cost from Zerodha's figures and the engine's charges, the
owner's click posts the sealed basket to Kite's page, and the owner's "Check with Zerodha" click runs the return
route, which closes the plan from Zerodha's answer and writes the audit events the live run will read back.
Proof: one Playwright run in CI against the test-only Execute/return replay of item 2 (recorded Kite replies,
2026-10-16): Execute -> the screen shows BUY 65 NIFTY26O1923650CE LIMIT 3.35 with Zerodha's required margin (from the
DERIVED entry reply `margins-basket-entry-derived.json` - no raw entry reply was recorded), the net premium
-217.75 (paid) and the charges from `ofo/charges/calculator.py`, all as strings -> the owner's click POSTs
`basket.url` with `basket.api_key` / `basket.data` byte-equal to the route's reply (asserted on the intercepted
request; nothing reaches Kite) -> "Check with Zerodha" on the 122104 replies shows plan 1 filled, 0 mismatches ->
the audit table holds `order_prepared` for plan 1 and `broker_response_recorded` / `execution_recorded` for its
order and trade ids (they carry order / trade ids, not plan numbers - the link to the plan is the order id).

## Why (GC-2c results + the two reviews)
- Merged in GC-2c: W-093 (#354), W-094 (#357), W-095 (#359), W-097 (#356), W-098 (#355), W-099 (#360); W-096 (#358)
  and W-100 - their state at GC-2c's close is in the GC-2c handover; item 1 covers either case.
- Missing for a live order: no replay that drives the Execute and return routes outside a live Kite session; no
  cost in the Execute reply; no audit writer on the execute path (and the event a stored plan needs, `order_prepared`,
  is undeclared in the W-017 allow-list); no screen; no live subscription while a screen is open (the route refuses
  a leg without a live full frame); no holdings read; where Kite returns the browser after a basket is unverified.

## Done list
1. **Land what GC-2c left open**: W-096 (#358) and W-100 (`brief-W-100.md`) if either is not on main. Proof: merged
   (`gh pr view`), their route tests green in CI.
2. **W-101 - test-only Execute/return replay** (Tier A: test code inside the order path): refused outside
   `APP_ENV=test` (the `replay_mode.require_test_env` pattern); serves the recorded Kite replies to both routes
   (orders/trades/positions 122104 and 151006, funds, the basket-margin replies, the quote), depth for the leg
   (`tests/fixtures/kite_ws/full-frame-12080386-150720.bin`), a pinned market-hours clock, a seeded strategy id 1 and
   a real Pro grant (through `entitlement_store.append`, database clock). Wired into `app-tests.yml`'s replay API the
   way the outcome replay is. Proof: the routes' own core sequences pass against the running replay API.
3. **W-102 - the cost in the Execute reply** (Tier A, money): `ExecuteOut` gains the signed net premium (BUY pays,
   SELL receives; quantity x LIMIT per leg), the charges from `ofo/charges/calculator.py` with the stored rates the outcome route already loads
   (`load_charge_rates`, `charge_rates_store`; no rates -> no charges figure and the reply says so, never a default)
   (ADR-082 (1); REQ-056 AC-8),
   and Zerodha's funds and required margin - the figures the route's context read in the same request, labelled with
   their read time (the sealed basket carries no figures; `checked_basket` reads again, W-098 unchanged). Every figure
   a 2-decimal string; the browser computes nothing. The exit shows its own cost (money received, charges paid).
4. **W-103 - audit events on both routes** (Tier A; migration in the 0015 pattern with a real downgrade): declare
   `order_prepared` in the allow-list (strategy id, plan number, action, tags); the Execute route writes it in the
   same transaction as `record_plan`; the return route writes `broker_response_recorded` (W-017 keys) per read-back
   and `execution_recorded` per trade row of `GET /trades` (W-017's trade shape - its meaning unchanged). Audit times
   on the database clock.
5. **W-104 - the Execute screen** (Tier A front end; Playwright in CI = the core proof): an "Execute Strategy" button
   on a saved strategy (REQ-056 AC-1); the orders and the full cost exactly as the route returns them; a live
   subscription for every leg's contract held while the screen is open, made BEFORE it calls the route (test: a leg
   without a live frame is refused with the catalogue text); one OWNER click that POSTs `basket.data` with
   `basket.api_key` to `basket.url` in a new tab (never a client-rebuilt JSON); one owner click "Check with Zerodha"
   that calls the return route and shows each order's Zerodha state, the plan outcome and the reconciliation result.
   Wording decision-support only (ADR-003); any layout, wording or state beyond REQ-073's example goes to
   `owner-questions-<run date>.md` with a recommendation and the run continues; the platform's own margin estimate,
   if shown, is labelled a planning estimate (REQ-055 AC-3).
6. **W-105 - where Kite returns the browser after a basket** (no order; runs from the start): the `zerodha-expert`
   skill and Kite's offsite-basket documentation; the answer recorded as a finding (spec findings list; registry if a
   defect class). If Kite redirects, the landing URL is a page that only shows the "Check with Zerodha" action - it
   never calls the return route by itself and never shows a login error. "Unverified until GC-3's first basket" where
   no source settles it.
7. **W-106 - holdings read for ADR-097 (4)** (Tier A door entry like W-093/W-099): `("GET", "/portfolio/holdings")`
   on the read door, returning tradingsymbol, exchange, isin, quantity, t1_quantity as exact values (prices and P&L are
   not compared).
8. **Mechanism for `request-clock-for-database-stamped-fact`** (3 occurrences): the audit and entitlement stores stamp
   their own times from the database clock (callers cannot pass one); lands after items 1 and 4 and updates their
   callers.
9. **Mechanism for `repo-wide-scan-outside-targeted-tests`** (7 occurrences): a `repo_scan` pytest marker on every
   repo-wide scan test, `pytest -m repo_scan` in every brief and before every push, and a collection check that fails a
   scan test without the marker.
10. Docs batch; write GC-3 (below); get it independently reviewed (record verbatim); mark NEXT; merge with the
    handover; print the prompt, the 5-line summary and the scorecard.

## GC-3, to be written by item 10 (owner present, ~2 h, a trading day)
L1 Kite login on ofo_dev in a private window -> `/broker/connected`; then a NO-ORDER live probe (depth + band for the
chosen contract read live; not through the Execute route - a stored plan would block the next press). L2 no later
than 13:30 IST: the screen shows the exact ENTRY and its full cost; the owner types "go" (ADR-097 (3)); holdings
snapshot; the OWNER clicks the button that opens Kite's page and places the basket (ADR-097 (2)); "Check with
Zerodha" closes the plan filled, 0 mismatches. Not filled within 15 min -> the owner cancels on Kite, the return route
closes the plan, no exit, nothing retried (ADR-017). L3 the EXIT the same way, closed exited. L4 holdings (named
fields) equal; gross P&L from the fills = Kite's position P&L (ADR-102); the run's audit events read back and the hash
chain verified. Stops: login, the typed go, every click on Kite's page; never an API order (ADR-100). ofo_dev must be
at main's migration head first (`dev_run.py`).

## Carry-overs (named; only after items 1-7)
W-100 review MINORs (no test kills a `bands.get(key, quote.band)` fallback; no two-leg keying test; an expired token
shown as "could not read today's price band" instead of a re-login prompt; a missing catalogue entry for an EXIT leg
-> AttributeError 500, older than W-100); W-099 review MINORs (tab/newline URL parse quirk, huge upper band,
`&`/space symbols); W-093 MINOR (HTTP-200
TokenException code); #353; #352 (close-of-day read); W-095 MINOR (second database-clock read); W-096 MINOR
(drifted-closed case unit-tested only); duplicate quote fixtures (`quote-151720.json` vs `quote-150720.json`); W-097
MINOR (feed-level staleness, by design); GC-2c contract item 5's list (#338; W-091 average >= 0; W-092 list-age limit;
ADR-058 delisted-held caller + `clear_reconciliation_block`; positions keyed without exchange; W-091/W-092/W-017
verifier passes; audit allowlist nested `{}`; #344 follow-up; the verifier-in-flight hook's false block - a project
hook; GC-2c's contract cited kit #113, which is a different issue); #313 remainder (adopted holdings in memory); the CI
e2e "too many connections for role ofo_app" seen once on PR #359 (passed on re-run; cause unproven - a question).

## Process rules (checkable; `goal-chain.md` process rules 1-8 apply in full)
- Chain rule 2: pull main, refuse if a row is RUNNING, set this row RUNNING in the first commit.
- ONE holder of the shared test DB at a time, named in every brief that touches it; the orchestrator runs no DB command
  while a builder's DB step may run (finding branch-migration-tests-move-shared-db, 3 shapes in GC-2c).
- The integrator runs the full domain suite once (no DB) and the ratchet after every main merge, before every push of
  a builder branch (GC-2c: 7 repo-scan reds and 3 ratchet rises surfaced only this way or in CI).
- A builder's report is a claim: `agentwt.py <id> status` (dirty / on_origin) before reading it as the branch.
- Every brief: `check_brief.py`; reviewer checklist + attack cases; `Findings checked:`; `Copy from:`; `Budget:` at most
  80 % of the agent type's cap; `Report: evidence-table`; the three guard-test literals.
- Front-end work: Playwright in CI only; stop every local server started.

## Stops
- None needs the owner. A choice that changes what a user sees beyond the spec goes to `owner-questions-<run date>.md`.
- DB steps through `db_run.py` only; tunnel down = park the DB items, continue the offline ones.
- Park rule: two failed rounds of one class or an outside blocker -> a `parked` issue via `gh_issue.py --stage`.
