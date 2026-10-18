# Goal contract GC-3P (Sun 2026-10-18): prepare Monday's live gate - real read-only login today, runbook, #380 draft

Chain: `goal-chain.md` (rules, process rules 1-9, scorecard). Written 2026-10-18 by the planning session from the
owner-approved plan (owner, question tool, 2026-10-18: "Approve as revised"), after an independent Opus review of that
plan (CHANGES NEEDED, all 7 findings accepted; they are folded into the items below). GC-3L stays as written; this
contract's item 8 writes its delta. **No order, no basket, no Kite page, ever, in this contract** (ADR-097, ADR-100).
**Owner needed: YES, once** - one Kite login for item 1 (about 5 min). Everything else runs unattended.
**Cap: 5 h from the lock.** Tail reserve: 45 min for item 9.

Core: a real Kite login on the owner's account through the product's own login route, then `probe.py` reading the real
holdings (save + compare, both exit 0), the contract quote and funds - the first live run of the probe; GC-3L L1 depends
on it (`gc-3-p0-results-2026-10-17.md` item 1b: "live mode first runs at L1").
Proof: item 1's evidence rows: `/broker/connected` reached, `holdings --save` exit 0 with the raw key list,
`holdings --compare` printing `holdings_unchanged` exit 0, `contract NFO:<CE>` exit 0, funds value.

## Main stays frozen for product code
GC-3L was reviewed READY on main a43cf3a. No product-code merge today, except a probe-script fix needed by item 1
(Tier B, one review round; `scripts/live/probe.py` is not imported by any route). Docs merge once, in item 9.

## Already measured by the planning session (2026-10-18 ~09:56 IST, ofo_dev, read-only) - re-check in item 2
- `alembic_version` (owner role) = `0017_audit_order_prepared` = main's head file.
- `rates_in_force` = one ChargeRates set dated 2026-10-15. Owner access `AccessLevel.PRO`.
- NIFTY 2026-10-27 CE in the catalogue: 261 contracts, strikes 17000-30000, lot 65, `seen_on` 2026-10-15 (stale ->
  Monday reload, item 8); freeze limit 3511 for all 261 (`exchange_freeze_limits` file 2026-10-15; 65 < 3511).
- Funds decision (owner, question tool, 2026-10-18): keep Rs 873, cheap strike, premium about Rs 5-11. Conforms to the
  2026-10-15 owner input in the master plan ("premium about Rs 5 or less") and GC-3L L1 - No spec change.

## Items (in order; item 1 is the core)
0. Take `lock/gc-3p` (chain rule 2). `git pull` main.
1. **Core: live read-only login + probe.** BEFORE the login (it runs on the API port), start the API on ofo_dev:
   `$env:LIVE_MARKET='1'; python scripts/orchestrator/dev_run.py . python -m uvicorn ofo_app.main:create_app --factory
   --app-dir backend --loop ofo_app.event_loop:selector_loop --host 127.0.0.1 --port 8765` (recipe:
   `session-handover-2026-10-15.md`; the API refuses any other loop; never set `APP_ENV` or `EXECUTE_REPLAY`), then the
   frontend so the redirect lands on a page: in `frontend/`, `npm run build` then `OFO_API_TARGET=http://127.0.0.1:8765
   npm run preview -- --host 127.0.0.1 --port 4173` (`.env` FRONTEND_ORIGIN = `http://127.0.0.1:4173`). `/api/health`
   200 through the preview proxy before asking. Ask the owner with the question tool (one question) "ready for the Kite
   login now?" ONLY if the owner started this session; otherwise park item 1 at once. The owner opens
   `http://127.0.0.1:8765/broker/zerodha/login` in a private window. **Login proof** = the owner reports
   `/broker/connected` (not `/broker/refused`) in the URL bar AND `probe.py holdings` exits 0. The login writes a new
   `broker_sessions` row and ends the previous one (`broker_token_store.py`); Monday's login ends Sunday's the same way.
   Then via `python scripts/orchestrator/dev_run.py . python scripts/live/probe.py` (it reads the stored session from
   ofo_dev itself): `holdings --save <scratchpad>/sunday-before.json` (record the raw key list = first 8-field read), at
   once `holdings --compare <scratchpad>/sunday-before.json` (must print `holdings_unchanged`, exit 0), `contract
   NFO:<any 2026-10-27 NIFTY CE from the catalogue>` (a probe test only: it prints depth, band and `available_funds`,
   no last price; Monday's 09:20 pick reads the price from depth or the screen); funds = that `available_funds` line.
   Also record what the health/socket says about the live feed (Sunday: no ticks expected; not a pass). Every row is
   labelled **pre-run**; the Sunday file is NEVER Monday's baseline.
   - A probe defect (e.g. #386 item 1): fix in a worktree, Tier B review (one round), land it with `land.py`; record the
     new main head. Not fixable in one round -> park, and item 8 names it as a Monday L1 risk.
   - Login fails: the owner retries once; then park item 1 and continue with items 2-9.
   - Stop the API when done.
2. **ofo_dev re-check** (one line each, read-only): the four measurements above still hold.
3. **Deferred-issue triage confirmation** (ADR-107): list open Tier A deferred issues not in the P0 6 table of
   `gc-3-p0-results-2026-10-17.md`; expected only #380, #381, #386, each already covered by GC-3L / ADR-108 (#385 is
   parked, not deferred); any new one is triaged (an Opus check on every "no").
4. **Owner runbook for Monday** `docs/process/gc-3l-runbook-2026-10-19.md`, one page: click by click with times (item 8
   timeline), what the owner types ("go"), the never-place-twice rule, the eight ADR-108 rules in plain words, what to
   do on no fill (15 min) / partial / rejection / EXIT refused, where screenshots go. Built from the GC-3L contract and
   the screen as it is on main (W-104), not from memory; no local replay run (needs ofo_test, which shares the VPS with
   IPODhan production; CI's `execute-screen-e2e` already proves the ENTRY + Check half).
5. **#380 draft (no code)** `docs/process/fix-380-draft-2026-10-18.md`: findings (F-42, #380, #381, #352), the options
   (wire `ofo.reconciliation` / `ofo.execution.partial` into the routes, or re-specify), the order/money behaviour each
   option changes, and the owner's BUSINESS questions written out (partial-fill handling under ADR-105, a manual
   reconcile screen) for asking after Monday - never designed around. Marked DRAFT: the next contract is written from
   GC-3L's results (chain rules 3-4). Fresh Opus review of the draft (findings accepted/rejected in the file).
6. **Leftover agent worktrees** (all 5 are 0 commits ahead of main on 2026-10-18): release the 4 clean ones with
   `python scripts/orchestrator/agentwt.py <id> release` (W-094 `aca80db8db2ae147e`, W-103 `a092609fff34ea9ed`, W-104
   `aa59e4e2fc93b7486`, unnamed `a7b13048dd321ae6f`). W-095 (`a69de5ad7463e69aa`) has an uncommitted
   `backend/ofo_app/execute_plan.py`: save its diff (`agit.py a69de5ad7463e69aa diff`) to the scratchpad, record it,
   leave the tree, and name it in the handover for the owner. Count tracked files AND `frontend/node_modules` packages
   in the main checkout before and after; a mismatch stops the line.
7. **Tidy**: delete the 2 untracked `docs/process/brief-process-cuts-pr2a.md` / `-pr2b.md` in the main checkout (work
   merged in #377/#378); `docs/HANDOVER.md` top line points to the newest handover.
8. **GC-3L delta** `docs/process/goal-contract-GC-3L-delta-2026-10-18.md` (GC-3L itself is not edited):
   - Monday timeline: 08:30 lock + short step 0; **08:45 catalogue reload** (`dev_run.py . python -m
     ofo_app.catalogue_load`; freeze file only if a new NSE file is out: download it first (name the source URL in
     the delta), then `python scripts/orchestrator/dev_run.py . python scripts/load_freeze_file.py <file>` - ofo_dev,
     NEVER `db_run.py` (that is ofo_test, despite the script's docstring); else 3511 stays; record which); 09:00 API up, owner login, `holdings --save` before the open; 09:20 contract probe + strike pick
     (premium Rs 5-11, owner 2026-10-18); ~10:00 L2 (deadline 13:30); EXIT soon after the fill (deadline 14:30); ~12:00 L4.
   - Step 0.1 on a docs-only head: CI green on the newest commit that changed product code, `execute-screen-e2e` named
     in that run, and `git diff --stat <that sha> HEAD` touching only docs.
   - Item 1's results: what was measured, any probe fix and its PR, anything still unproven (Sunday depth, socket).
   - Check per chain rule 3: full fresh Opus review (it precedes a real-money run); findings accepted/rejected in a
     review file. At most 2 review rounds; an unresolved CRITICAL after round 2 -> GC-3L still marked NEXT with the
     blocker named in its row (the owner decides on Monday), never a third round.
9. **Close-out**: one docs PR (runbook, draft, delta, reviews, handover `session-handover-2026-10-18-gc3p.md`,
   goal-chain rows: GC-3P DONE/PARTIAL, GC-3L NEXT) via `land.py`; record the new main head; delete the lock; print the
   chain prompt, the 5-line summary, the scorecard (`stage_scorecard.py --since <start> --until <end>`) and the
   evidence table.

## Contract review (chain rule 3; fresh Opus, 2026-10-18)
NOT READY -> all 9 findings accepted and applied above: (1) exact API start recipe; (2) login proof = URL
`/broker/connected` + `holdings` exit 0, frontend preview started; (3) W-095 tree is dirty - kept, diff saved; (4)
freeze load through `dev_run.py`, never `db_run.py`; (5) `--compare <file>`, funds from `contract`; (6) Sunday contract
probe is a test only, Monday picks from depth; (7) #385 is parked; (8) no question while the owner is away, item 8
capped at 2 review rounds; (9) info: the login writes one `broker_sessions` row, the probe reads it from ofo_dev.
The safety core was confirmed: no path places an order or posts a basket.

## Stops
- Never an order, a basket, an API order, or a Kite page visit by the session. Live runs on ofo_dev only, never ofo_test.
- The owner's Kite login is the only owner step; if the owner is not there, park item 1 (as a GC-3L L1 risk) and do the rest.
- No product-code merge except item 1's probe fix.
