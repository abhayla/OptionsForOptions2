# Goal contract GC-3L (a trading day, from Mon 2026-10-19): the 4b live gate - one real 1-lot ENTRY and EXIT

Chain: `goal-chain.md` (rules, process rules 1-9, scorecard). Written by GC-3 (PARTIAL, 2026-10-17) from its P0 results
(`gc-3-p0-results-2026-10-17.md`): GC-3's P0 is done and merged; its L1-L4 are this contract, unchanged except by
ADR-108 and this contract's review (`gc-3l-contract-review-2026-10-17.md`: NOT READY -> all findings applied -> two
re-checks -> READY).
**Owner needed: YES** - the Kite login, the typed "go", and every click on Kite's page (ADR-097 (2), (3)).
Unattended it does only step 0 and stops at L1.
**Cap: ~2.5 h of owner time in market hours. L2 placed by 13:30 IST; L3 placed by 14:30 IST** (so an unfilled EXIT
has an hour to fill before the close). Tail reserve: 1 h.

Core: one real NIFTY CE order of the 2026-10-27 expiry (ADR-108 (2)) goes the whole product path on the owner's account
and comes back exactly: the Execute screen shows the exact ENTRY and its full cost, the OWNER places it on Kite's page,
"Check with Zerodha" closes the plan filled with 0 mismatches, the EXIT goes the same way, holdings are unchanged on the
eight fields, gross P&L equals Kite's, and the audit events read back with the hash chain verified.
Proof: L1-L4 below, each step's output read back and written as an evidence row (time, values, ids).

## Step 0 (unattended, before the owner is asked for anything; by 09:00 IST)
1. Take `lock/gc-3l` (chain rule 2). `git pull` main; confirm on main: #379 (probe), #382 (P0 docs), #383 (W-107),
   #384 (ADR-108), the GC-3 close-out; main's CI green on the head being run, `execute-screen-e2e` named in `gh run view`.
2. ofo_dev re-check (one line each): `alembic current` = main's head (owner role, ALEMBIC_DATABASE_URL in memory);
   `rates_in_force` returns a set; the owner is Pro (`access_at` = PRO). Any miss: fix it, record it.
3. Load the `zerodha-expert` skill; re-read ADR-097, ADR-100 (no API order, no static IP), ADR-105, ADR-108.
4. Every open Tier A deferred issue NOT in GC-3's P0 6 table (`gc-3-p0-results-2026-10-17.md`): triage per ADR-107
   (Opus checks every "no"). Known: #381 (orders read before trades) is covered by ADR-108 rule 1; #380 is F-42,
   accepted for this run by ADR-108 (1); #386 item 1 is finding 4 below.
5. Start the API (port 8765, factory start through a script; `LIVE_MARKET` on, never `EXECUTE_REPLAY`) and Vite
   (`OFO_API_TARGET`) on ofo_dev; `/api/health` 200. All `probe.py` commands run as
   `python scripts/orchestrator/dev_run.py . python scripts/live/probe.py ...` (ofo_dev only).

## Live steps (owner present; ADR-108's eight operating rules apply throughout)
- **L1 login + no-order probe.** The owner opens `http://127.0.0.1:8765/broker/zerodha/login` (the API port, as on
  2026-10-16; no login button exists in the app yet; Kite calls back on `127.0.0.1:8765/kite/callback`, which forwards
  to FRONTEND_ORIGIN) in a private window, logs in -> `/broker/connected`. Then `probe.py holdings --save
  <before.json>` (record the REAL reply's key list - first measurement of the 8-field read) and at once `probe.py
  holdings --compare <before.json>` -> it must print `holdings_unchanged`; `probe.py contract NFO:<chosen CE>`
  (5-level depth, circuit band, funds). **Any probe exit other than 0 at L1 = STOP, no order** (one in-session fix with
  one review round, before 12:00; else park). Strike: a 2026-10-27 CE with premium x 65 + Rs 100 <= funds (#338).
  Positions: net 0 on that contract and no trades in it today (Kite's `day` list); one strategy only.
- **Save the strategy from the Strategy Builder while the feed is live** (one BUY leg; planned entry captured, OQ-13);
  open Execute Strategy and see it reach "live".
- **L2 ENTRY (placed by 13:30 IST).** The screen shows contract, side, quantity 65, NRML, LIMIT, limit price, net
  premium, charges, Zerodha margin and funds. The owner types "go" for those exact values; the owner clicks through to
  Kite's page in the SAME private window, checks Kite's user id there equals the connected user (rule 4), and places it.
  **Never place a basket twice:** press "Open Kite's page again" only if no Kite tab opened AND Kite's Orders page shows
  no order with the strategy's tag. Kite returns the browser to `/execution/returned` (F-41; record the real URL and
  query keys from the browser's address bar / history - the server's access log drops the query by design). **Not a
  stop:** Kite does not redirect at all, or the return carries a `state` and lands on the login-refusal page - in both
  cases go back to the Execute tab and use its "Check with Zerodha"; record which case happened in F-41. Check only
  after Kite shows the order final (rule 1); twice (rule 2) -> plan 1 `filled`, 0 mismatches. A rejection: copy Kite's
  rejection text into the handover (rule 7). Not filled in 15 min -> the owner cancels on Kite; Check closes the plan;
  no exit; go to L4. Partly filled -> cancel the rest; Check closes `partial`; L3 exits exactly the held quantity.
  Never a retry of the ENTRY (ADR-017).
- **L3 EXIT, the same way (placed by 14:30 IST).** Funds read first: `equity.net` < 0 refuses the 0-margin exit (#338)
  -> the carry-over branch below. SELL the held quantity (65 unless partial) at its LIMIT (priced from the live
  5-level depth), money received + charges
  shown -> the owner's "go" -> the owner's click and placement (same once-only rule) -> Check (rules 1-2) -> plan
  closed `exited`.
  **EXIT not filled, or refused by the screen (carry-over branch):** no cancel and no second EXIT (ADR-108 rule 6 allows
  Cancel only on the ENTRY's 15-minute branch; ADR-017 no retry). The LIMIT stays working to the close; an unfilled
  day order ends at the close and the position carries over as NRML, loss capped at the premium (ADR-097
  consequence). Record it (Kite's Orders and Positions screenshots, the refusal's catalogue message); no further
  ENTRY; the next contract exits it first (#352: the open plan is not read back the next day; next session Wed
  2026-10-21, Tue is a holiday).
- **L4 read back.** `probe.py holdings --compare <before.json>` = `holdings_unchanged`; `probe.py pnl --tag-prefix
  <strategy tag>` = `pnl_equal` (gross from the two fills vs Kite's position P&L, ADR-102) - only when the position is
  flat; in the carry-over branch record both numbers instead (Kite's figure then includes unrealised P&L); `probe.py audit --since
  <L2 time>` lists `order_prepared` per plan, `broker_response_recorded` per order, `execution_recorded` per trade,
  "hash chain verified". A probe failure at L4: screenshots of Kite's Holdings and Positions pages are the evidence;
  the probe fix goes to the next contract.

## Done list
1. Step 0 evidence rows. 2. L1-L4 evidence rows; F-41 updated with the measured return shape; the holdings key list
recorded. 3. Findings from the live run registered the same turn. 4. Docs batch; write the next contract on one page:
if L4 passed, recommended a FIX contract whose core is #380 (wire `ofo.reconciliation` / `ofo.execution.partial` into
the routes, or re-specify), with #352, #381, OQ-13 as candidates, before GC-4 builds alerts on reconciliation; if the
run stopped or was parked, the next contract is built around that failure plus a re-run of L1-L4 (chain rule 4).
Check it per chain rule 3 (full fresh Opus review); mark NEXT; merge with the handover; delete the lock; print the
prompt, the 5-line summary and the scorecard.

## Stops
- The owner's login, the typed "go", every click on Kite's page. Never an API order (ADR-100); never a sale of
  holdings, never a cash symbol; NRML and LIMIT only (ADR-097 (1)).
- Any ADR-108 STOP: `nothing_placed` while Kite shows a fill; a mismatch after Check; a holdings difference; a P&L
  difference -> no further order (W-107 refuses any EXIT while a plan has drifted), record the finding, the next
  contract is the fix; a position left open carries over as NRML (ADR-097 consequence), as in the L3 carry-over branch.
- The Execute screen refuses on live data: record the catalogue message; fix only a code defect found in the session
  while the owner is present before 13:30 (ENTRY); an EXIT refusal is the L3 carry-over branch; otherwise park and
  write the fix contract.
- Kite login fails or the session drops: the owner retries once; then park.

## Process rules
- Live runs on ofo_dev only (`dev_run.py`), never ofo_test. The owner's clicks and "go" are quoted with their time.
- One review round per code fix in session at most; anything larger is parked to the next contract.
