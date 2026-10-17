# Goal contract GC-3 (a trading day, from Mon 2026-10-19): the 4b live gate - one real 1-lot ENTRY and EXIT through the product path

Chain: `goal-chain.md` (rules, process rules 1-8, scorecard). Written by GC-2e from its results (2026-10-17). Shaped
by the GC-3 draft review (`gc-3-draft-review-2026-10-17.md`: preparation moved to GC-2e) and this contract's own
review (`gc-3-contract-review-2026-10-17.md`).
**Owner needed: YES** - the Kite login, the typed "go", and every click on Kite's page (ADR-097 (2), (3)). Unattended,
this contract does only P0 and stops at L1.
**Cap: ~2 h of owner time in market hours; L2 starts no later than 13:30 IST** (so the EXIT can be placed before
15:00). Tail reserve: 1 h after L4 (docs, the next contract, merge).

Core: one real NIFTY option order goes the whole product path on the owner's account and comes back exactly: the
Execute screen shows the exact ENTRY and its full cost from Zerodha's figures and the engine's charges, the OWNER
places it on Kite's page, "Check with Zerodha" closes the plan filled with 0 mismatches, the EXIT goes the same way,
holdings are unchanged on the named fields, gross P&L equals Kite's, and the audit events read back with the hash
chain verified.
Proof: L1-L4 below, each step's output read back and written as an evidence row (time, values, ids).

## Preconditions (P0, unattended, before the owner is asked for anything; done by 09:00 IST, L1 by 11:30 IST)
1. `git pull` main; GC-2e's DONE/PARTIAL row names what merged. If W-101 (the replay, PR #365) or W-104 (the Execute
   screen + `/execution/returned`, PR #372) is not on main, STOP: GC-3 cannot place a basket without them - report and
   leave GC-3 NEXT.
1b. **The read-only probe/readback script** (none exists; review finding 2): one script under `scripts/live/` run
   through `dev_run.py` on ofo_dev that (a) reads holdings with `KiteReads.fetch_holdings` AND logs the raw reply's key
   list, (b) reads depth + circuit band + funds for a named contract, (c) after the run reads trades and positions,
   computes gross P&L from the two fills and prints Kite's position P&L beside it, (d) reloads the audit log with
   `audit_store.load_log` (it verifies the hash chain against the stored anchor) and lists this run's
   `order_prepared` / `broker_response_recorded` / `execution_recorded` rows. Dry-run (a)-(d) against the recorded
   2026-10-16 replies first (no network) - that is all P0 can prove, since no Kite session exists before the owner's
   L1 login; its first live run (part (a) + (b)) is L1's probe itself, read back before anything else happens.
   Tier B review, merged before L1.
1c. ofo_dev holds a charge-rate set (`charge_rates_store.rates_in_force` returns one) - otherwise the Execute reply's
   `charges` is null and the core's "full cost" fails (review finding 5).
2. ofo_dev at main's migration head (`dev_run.py` + `alembic upgrade head`; the head includes GC-2e's audit migration).
3. The API and the frontend start on ofo_dev with `LIVE_MARKET` on (never `EXECUTE_REPLAY` - it is refused outside
   `APP_ENV=test` anyway); `/api/health` green. Main's CI `execute-screen-e2e` job (W-104, on the 2026-10-16 replay)
   was green on the head being run - read it with `gh run list`, do not assume it.
4. Load the `zerodha-expert` skill; re-read ADR-097, ADR-100 (no API order, no static IP), ADR-105 (one open plan).
5. Pick the contract: the nearest-expiry NIFTY CE whose premium x 65 fits the funds read in L1, strike chosen by the
   owner in L1's question; nothing in the strategy but that one BUY leg. **The strategy is saved from the Strategy
   Builder while the feed is live, so the leg carries a planned entry captured from the live price** - the Execute
   screen builds its live request from planned entry prices and dead-ends without one, for ENTRY and EXIT alike
   (review finding 1, CRITICAL; the general fix is OQ-13). Before the owner is asked to act, open the Execute screen
   and see it reach "live".

## Live steps (owner present)
- **L1 login + no-order probe.** The owner logs in to Kite in a private window -> `/broker/connected`. Then a
  NO-ORDER live probe for the chosen contract: depth (5 levels) and the circuit band read live, funds read
  (`GET /user/margins`), holdings read (`KiteReads.fetch_holdings`, W-106) = the BEFORE snapshot on the eight
  fields W-106 keeps: tradingsymbol, exchange, isin, quantity, t1_quantity, used_quantity, authorised_quantity,
  collateral_quantity (record the REAL reply's field list - W-106 was built on Kite's documented shape; a refused read
  is a stop, never a skipped check). Not through the Execute route (a stored plan would block the next press).
- **L2 ENTRY (no later than 13:30 IST).** The owner opens the saved strategy -> Execute Strategy -> the screen shows
  the exact ENTRY (contract, side, quantity, product NRML, order type LIMIT, limit price) and its cost (net premium,
  charges, Zerodha's margin and funds). The owner types "go" in chat for those exact values (ADR-097 (1), (3)). The
  OWNER clicks the button that opens Kite's page and places the basket there - the app and Kite in the SAME private
  window (the landing page reads the strategy id from that window's storage). Kite returns the browser to
  `/execution/returned` (F-41; record the real URL and query keys from the browser's address bar / history - the
  server's access log drops the query by design). **Not a stop** (review finding 4): Kite does not redirect at all,
  or the return carries a `state` and lands on the login-refusal page - in both cases go back to the Execute tab and
  use its "Check with Zerodha"; record which case happened in F-41. -> the owner clicks "Check with Zerodha" -> plan 1 closed
  `filled`, 0 mismatches. **Not filled within 15 min** -> the owner cancels on Kite; "Check with Zerodha" closes the
  plan; no exit; nothing retried (ADR-017); go to L4. **Partly filled within 15 min** (review finding 3) -> the owner
  cancels the remainder on Kite; "Check with Zerodha" closes the plan `partial`; L3 EXITs exactly the held quantity
  (ADR-105: the exit is the net held), the same way - never a re-try of the unfilled part.
- **L3 EXIT, the same way.** Execute Strategy (EXIT) -> the screen shows SELL 65 at its LIMIT and the money received +
  charges -> the owner's "go" -> the owner's click and placement on Kite -> "Check with Zerodha" -> plan closed
  `exited`.
- **L4 read back.** Holdings AFTER snapshot equal to BEFORE on the eight fields (`holdings_unchanged`); gross P&L from
  the two fills = Kite's position P&L (ADR-102, gross); the run's audit events (`order_prepared` per plan,
  `broker_response_recorded` per order, `execution_recorded` per trade) read back and the hash chain verified - all
  three through the P0 1b script ((a), (c), (d)). Record the real basket-return URL in F-41 (unverified -> measured).

## Done list
1. P0 complete (evidence rows).
2. L1-L4 as above, each with an evidence row; F-41 updated with the measured return shape.
3. Findings from the live run registered the same turn (spec findings list + registry where a defect class).
4. Docs batch; write the next contract (GC-4 if L4 passes, otherwise a fix contract built around the failure); get
   it independently reviewed (record verbatim); mark NEXT; merge with the handover; print the prompt, the 5-line
   summary and the scorecard.

## Stops
- The owner's login, the typed "go", every click on Kite's page. Never an API order (ADR-100); never a sale of
  holdings, never a cash symbol, product NRML and order type LIMIT only (ADR-097 (1)).
- A mismatch after "Check with Zerodha", a holdings difference, or a P&L difference: STOP the run, no further order;
  record the finding; the next contract is the fix.
- The Execute screen refuses on live data (no live frame, band unknown, margin): read the catalogue message, record
  it, fix only if it is a code defect found in the session and the owner is still present before 13:30; otherwise
  park and write the fix contract.
- Kite login fails or the session drops: the owner retries once; then park.
- L1's holdings read refused (the real reply's shape differs from Kite's documented one - W-106 fails closed): STOP,
  no order today; record the raw key list (P0 1b (a)); the next contract fixes the reader (review finding 7).

## Process rules
- Chain rule 2: pull main, refuse if a row is RUNNING, set this row RUNNING in the first commit.
- Live runs on ofo_dev only (`dev_run.py`), never ofo_test.
- The owner's clicks and "go" are quoted with their time in the handover.
