# Goal contract GC-TP: an expert trader can place, watch and adjust a paper strategy, the Sensibull way (2026-10-29)

Written 2026-10-29 ~11:00 IST in a planning-only session (no code changed). Docs branch `docs/gctp-trader-paper`
(worktree `D:\Abhay\Ventures\OptionsForOptions2-gctp-docs`, local only, based on `build/gcbm-must-have` 5052f82a). The
owner starts this contract with /goal in a FRESH session.

## Owner decisions behind this contract (2026-10-29; recorded in ADR-207)

1. Judge the app as an expert option trader from "build a strategy" to "track it on Positions" and "adjust it";
   market analysis (chain, IV, OI) is left out for now (owner chat ~10:20 IST).
2. Orders never reach Zerodha: a placed strategy is a paper position shown on the Positions screen (ADR-165, ADR-201,
   ADR-206 kept).
3. All eight gaps from the trader review are built in ONE goal (question tool: "All 8 items in one goal").
4. "Make sure the functionality and UI should be similar to Sensible" (owner chat): Sensibull's Draft Portfolios model
   is the default for every part (ADR-152).
5. ADR-207 approved as listed ("Approve all as listed (Recommended)"): (1) Add to Paper confirm list; (2) order book +
   builder Drafts Mode, Profit left / Loss left, no silent drift; (3) Paper tab on Positions kept, Sensibull Draft
   Portfolio content, no portfolio layer; (4) target level + date sliders; (5) Conditional Exit + per-leg stop, auto
   paper exit + in-app alert; (6) expiry settlement at the official closing index value; (7) Charges figure beside P&L;
   (8) percentages of margin needed (SPEC CHANGE, REQ-081 AC-9/10/11 already edited with ADR-207).
6. Standing (owner, 2026-10-28 and 2026-10-29): NO push, PR, draft PR, GitHub Actions, `ci_local.py`, `prepush.py`,
   `land.py` or `merge.py` in this goal. Local commits only. The owner says when to create a PR.
7. Standing (owner, 2026-10-28): every browser step in the owner's VISIBLE Chrome via Claude-in-Chrome, never headless.

Spec basis: ADR-207 (this goal's decision), ADR-201 (Paper tab on Positions), ADR-206 (order flow; Funds needed held,
F-62), ADR-165 (no orders; (6) playbooks wait for the owner), ADR-152 (Sensibull default except safety, legal, money),
ADR-008 (one engine, exact Decimal; the browser computes no money), ADR-082 (charges), ADR-193 (our brand, Sensibull
layout), ADR-197 (after hours from the last close), REQ-109 (paper tracking), REQ-077 (typed entry price), REQ-084
(what-if), REQ-144 (projected badge), REQ-145 (decay, F-63), REQ-041 AC-3 (exit conditions), REQ-045 / REQ-046 /
REQ-112 (detections, before/after, outcome record), REQ-081 (summary money, edited), REQ-044 AC-2/AC-3. Findings:
`spec/findings.md` F-65 to F-71; defect class `knowledge/findings/paper-plan-diverges-from-position.json`.
Sensibull (private study `D:\Abhay\Ventures\competitors\sensibull\2026-10-21`, cite numbers, never copy images into this
public repo): Add to Drafts flow catalogue 166-173; Drafts Mode in builder catalogue 274-279; Draft Portfolios page
090-092; Positions 050-053 (totals, Charges, closed toggle); what-if sliders 020 (catalogue 57-58); Conditional Exits
bundle-findings 7.4 and catalogue 221-224; stop-loss rows bundle-findings line 387.

**Core:** one paper order book per paper strategy, from which the one engine derives the net position (per contract:
quantity, average price, booked and unbooked P&L) - and the existing paper positions migrate into it without changing
a single rupee of their P&L.
**Proof:** step 1. On ofo_dev's REAL paper data (15 strategies with open legs on 2026-10-29, including strategy 63 and
the calendars P6), (a) before migration, record every strategy's Total / Booked / Unbooked P&L and every leg's entry /
exit from `GET /tracking` at one timestamp; (b) migrate; (c) recompute from the order book at the same prices: every
figure equal to the paisa; (d) on strategy 63 record a roll (exit 1 lot 22900 CE, add 1 lot 22950 CE) and show the
net position, booked P&L of the exited leg and unbooked of the new one, each recomputed independently by
`scripts/checks/ui_data_check.py` (extended in this step, still importing nothing from `backend/ofo/engine`). If the
migration cannot reproduce today's figures exactly, the work stops there (Core-first R3).

## §0.1 Where the run works (worktree isolation)

- First action: `gh pr view 604 --json state,mergeCommit` (read only). If #604 is MERGED: create the run tree from
  `origin/main` with `~/.claude/tools/wt-new.ps1 -Repo D:\Abhay\Ventures\OptionsForOptions2 -Name gctp-run -Branch
  build/gctp -Base origin/main -Purpose "GC-TP run" -TtlHours 72`, then `git -C <run tree> merge --no-ff
  docs/gctp-trader-paper` (this contract, ADR-207, F-65..F-71, REQ-081 edit). If #604 is NOT merged: base the run tree
  on `build/gcbm-must-have` (it holds GC-UI's checker and screens this goal builds on) with `-Base build/gcbm-must-have`,
  then merge `docs/gctp-trader-paper` the same way. Never work in the main checkout or in `-gcbm`.
- Builder sub-worktrees: `wt-new.ps1 -Name gctp-<item> -Base build/gctp`; link `frontend\node_modules` to an existing
  install as a JUNCTION (`~/.claude/tools/wt-link-modules.ps1`), never `npm install`; merged locally into `build/gctp`.
- Lock: write `.run-active.lock` with the session's token at the run tree root; remove it on any stop.

## §0.2 Preflight (idempotency: never redo finished work)

- Read the Status column below, the "Found during the run" and "Parked" tables, and `git log --oneline build/gctp` for
  `GC-TP step N` commits. A step with a DONE status AND its commit is verified (re-read its proof) and skipped; a partly
  done step builds only its missing part. Record every skip in the handover.
- Read before any code: ADR-207; `spec/findings.md` F-62, F-63, F-65..F-71; REQ-109, REQ-084, REQ-041, REQ-081;
  `docs/process/runbook.md`; `.claude/kit/builder-brief.md`; `docs/process/session-handover-2026-10-28-gcui.md`;
  `knowledge/findings/INDEX.md`; code `backend/ofo/tracking/paper.py`, `backend/ofo_app/tracking_store.py`,
  `backend/ofo_app/routes/tracking.py`, `backend/ofo_app/alembic/versions/0027_strategy_tracking_exits.py`,
  `backend/ofo/charges/calculator.py`, `backend/ofo/charges/round_trip.py`, `backend/ofo/engine/metrics.py`,
  `backend/ofo/engine/money_summary.py`, `backend/ofo_app/feed_bus.py`, `frontend/src/pages/StrategyBuilderPage.vue`,
  `frontend/src/pages/PositionsPage.vue`, `frontend/src/components/strategy/{PaperStrategies,TrackingPanel,
  SummaryCards,SaveDraftBar,ChartCard}.vue`, `frontend/src/lib/{tracking,usePaperRefresh}.js`,
  `frontend/src/pages/AlertsPage.vue`, `scripts/checks/ui_data_check.py`.

## §0.3 Progress log

- The Status column of the Items table and the "Found during the run" table in THIS file (in the run tree) are the
  live log: update them in the same commit as each step's work, before moving on. A crash leaves them current.

## Rules for the run

- **No PR, push or CI of any kind** (decision 6). Stacked local commits `GC-TP step N: ...` on `build/gctp`.
- **Commit so nothing is lost if the PC crashes** (owner, 2026-10-29: "code should be committed ... Nothing should get
  lost if the PC crashes"): every builder commits its work in its sub-worktree at least every 30 minutes and before it
  reports (WIP commits allowed, message `GC-TP step N WIP: ...`); the session merges each finished builder branch into
  `build/gctp` at once and commits this file's Status / Found tables in the same commit; no uncommitted change is left
  in any tree at the end of a turn longer than a few minutes. Local commits survive a crash or restart; they do not
  survive a disk failure (that would need a push, which decision 6 forbids).
- Tests: builders run only the test files they touch (+ ruff on touched Python, `npx eslint --max-warnings 0` on touched
  frontend files); output to a log, read the tail. After each local merge, the FULL frontend vitest once with
  `FULL_SUITE_BUDGET=<n> npx vitest run --maxWorkers=2`. DB tests one file at a time via the MAIN checkout's
  `scripts/orchestrator/db_run_fresh.py` (the PostgreSQL host also serves IPODhan production: targeted files only).
- Migrations touching paper data are Tier A: before the first run against ofo_dev, dump the tracking tables
  (`public.strategy_tracking`, `public.strategy_tracking_legs` from 0021, `public.strategy_tracking_exits` from 0027) to `D:\Abhay\scratch\gctp-backup-<time>.sql` and record the file and its
  row counts in this file; the downgrade path is tested on ofo_test (fresh) before ofo_dev is touched.
- Every defect follows the defect-fix contract: RCA, Class (data filter, size before and after), failing test first,
  class-level fix, ONE real-data proof, detection change. A defect outside a step's done list becomes a `deferred` note
  in "Found during the run" (run-discipline C4) and is not fixed in this goal.
- Every requirement text a step changes is edited in the same commit as the code, citing ADR-207.
- Money: every rupee and percent on screen comes from the server engine in exact Decimal (ADR-008); the browser
  formats only. Paper is labelled paper everywhere and never added to real totals (ADR-201 (2)).
- Orders: no code path in this goal may call a Zerodha order, GTT, alert-trigger or basket-placement endpoint; paper
  routes must refuse to run if any such door is reachable from them (test: import-graph check in the step-1 tests).
  The session never presses Execute and never clicks inside any order panel (memories real-order-guardrails,
  no-clicks-inside-order-panels).
- Privacy: the repo is PUBLIC. Never copy a Sensibull image into it; never write the owner's funds, client id, name or
  email into a repo file (use placeholders such as "<available funds>"). Screenshots stay in `D:\Abhay\scratch`.
- Owner present: one question per call (`Business call:` + `Spec basis:` lines) only for business forks; technical
  calls are the session's own, complex ones with an independent reviewer first. Owner away: write the question to
  `docs/process/owner-questions-2026-10-2x.md` and continue.
- Every Agent brief: `Core:` / `Proof:`, `Budget:`, `Sensibull:` (screen numbers), `Report: evidence-table`, the
  `.claude/kit/builder-brief.md` standing items (check with `scripts/orchestrator/check_brief.py`), an explicit `model`
  (Opus only with a `Why Opus:` line).
- At most 2 rounds per item, then park (`Parked` table with evidence) and continue with the next step.
- Evidence table at every done claim (command run that turn + its result line); a worker's report is a claim.

## Running the app

- Same as GC-UI "Running the app" (`docs/process/goal-contract-GC-UI-2026-10-28.md`), with the run tree path instead of
  `-gcbm`: check ports 8765 / 5174 first; stop only recorded PIDs; API via `scripts/orchestrator/dev_run.py` on
  ofo_dev; Vite with `OFO_API_TARGET=http://127.0.0.1:8765 npx vite --port 5174 --strictPort`, restarted after a new
  route. Kite token expires 06:00 IST: the one owner step is a login in a PRIVATE window at
  http://127.0.0.1:8765/broker/zerodha/login.
- Live checks (stop-loss triggers, LTP fills, prices moving) only in market hours 09:15-15:30 IST; settlement checks
  after 15:30 on an expiry day; the data checker also runs after hours on the last close (ADR-197).
- Browser: owner's visible Chrome only, 1536 x 864, one tab per task, closed when done; no agent drives a browser. If
  the Chrome extension is not connected, stop and tell the owner instead of using a headless browser.

## Design decisions (pre-made; the run does not pause on these)

- **Data model.** New table `paper_orders` (id, user_ref, strategy_id, contract instrument_id, side BUY/SELL, quantity
  in units, price Decimal(12,2), kind `open|add|exit|settle|stop`, placed_at timestamptz, reason text nullable, trigger
  id nullable). A paper strategy = the strategy row + its orders; the net position per contract = signed quantity sum;
  average price = FIFO-free weighted average of the orders that increased the absolute quantity (Zerodha's average
  rule for F&O: average of buys for a long, of sells for a short; booked P&L when quantity falls = (exit price - average)
  x quantity x side). Engine function lives in `backend/ofo/tracking/` (one place, Decimal); the checker recomputes it
  independently.
- **Migration 0028.** Each existing tracked leg -> one `open` order at its recorded paper entry and `price_at` time;
  each recorded exit -> one `exit` order at its exit price and `exited_at`. The three tracking tables (0021, 0027) are kept read-only until
  step 12 passes, then dropped in a separate migration 0029 written but NOT run on ofo_dev until the owner's land goal.
- **Place (Add to Paper).** Replaces "Start tracking" (button text and the `...` menu item; the old route
  `POST /strategies/{id}/tracking` is removed with its tests, dead patterns deleted). The button sits in the builder
  action row beside Save (Sensibull 041: Add/Edit | Add to Drafts | Trade All; ours has no Trade All, ADR-165). It
  needs no prior Save: Add to Paper on an unsaved strategy saves it first under the shown name. The confirm dialog lists
  each ticked leg: B/S, contract, lots, price (editable, default = the leg's builder entry price per REQ-077), footer
  "This is not a real trade. Paper orders use no real money."; Confirm records `open` orders in one transaction; the
  toast offers "Open in Builder" and "Open Paper positions" (Sensibull 173). A price that is not a positive multiple of
  the tick (0.05) is refused in the dialog and on the server.
- **Drafts Mode.** Opening a paper strategy (Positions -> Open in Builder, or the builder's Paper tab) loads its NET
  position, not its saved plan: legs at average prices, lots = net quantity. The legs panel gets a dashed frame and the
  label "Paper mode - not real trades" (Sensibull Drafts Mode frame, 274-279); a panel switch Net Positions | Orderbook
  (per leg Lots, Avg, LTP, Booked, Unbooked, P&L; orderbook rows: time, B/S, contract, qty, price, kind). Every leg edit
  in this mode (strike step, lots change, remove leg, add leg, Shift/Width/Hedge) is collected as pending paper orders
  and shown as "N pending changes"; "Review and add" opens the same confirm dialog listing the exact orders (an exit of
  the old contract and an add of the new one for a strike step); nothing changes until Confirm; "Discard" restores the
  net position. Save / Save As in Drafts Mode are hidden; Save As a copy creates a new plan (not paper). This is the
  structural guarantee for the class of F-65 (one code path for every edit) - no detector.
- **Exit.** "Exit all" and per-leg exit open the confirm dialog pre-filled at LTP (editable price, editable quantity in
  lots up to the open quantity: partial exit). Exits during market hours only for a price default; after hours the
  price box is required (no LTP default) and labelled "last close".
- **Summary of an open paper position.** Profit left = max over index levels of the expiry P&L of the OPEN legs valued
  from their current LTP; Loss left = the min of the same; shown first, "Profit left +x / Loss left -y", with the
  original Max Profit / Max Loss (whole order book at average prices, booked included) below (Sensibull 278-279).
  Greeks, payoff, P&L table and breakevens use the net position at average prices. Multi-expiry: no exact breakevens
  (MultiExpiryError, as today), Profit/Loss left at the first expiry with the far legs at model value - labelled.
- **Positions -> Paper tab.** Top strip across all paper strategies: Total P&L, Booked P&L, Unbooked P&L, Total Decay
  (REQ-145 formula, F-63), Charges (sum). "Show closed positions" toggle, off by default (fully exited strategies and
  closed legs hidden). Per strategy: name, index, "N of M positions", Total / Booked / Unbooked / Charges, per-leg Lots,
  Avg, LTP, Booked, Unbooked, P&L, actions Open in Builder, Add orders (opens the builder in Drafts Mode with the leg
  picker), Exit (n), a Greeks toggle (per-strategy net Greeks, per position). Newest strategy first. The Positions page
  opens on the Paper tab when the user has at least one open paper strategy and no real Zerodha position; the
  Positions-tab empty text no longer says "none of your strategies holds any" while paper is open: "No open Zerodha
  positions. N paper strategies are open - see Paper." The bare `/positions` page redirects to
  `/positions/current-positions`.
- **What-if.** A "Target" block above the payoff graph: index slider (spot -10% to +10%, step = the index strike step,
  plus a number box) and date slider (now to the strategy's last expiry, 15-minute steps in the last day, daily before;
  "< >" steppers; each with Reset) (Sensibull 020). Server recomputes: Breakeven Target side (D-A34), the projected
  P&L badge (REQ-144, D-B21), the target-date curve, the P&L table Target columns, Greeks at target. No browser maths.
  Debounce 250 ms; a stale reply is dropped by request id.
- **Stop-loss on paper.** On a paper strategy (Positions row menu and Drafts Mode): "Conditional exit": index crosses
  ABOVE x or BELOW y (either or both) -> every open leg exits; "Leg stop": a leg's LTP crosses ABOVE/BELOW a price ->
  that leg exits. The server monitor runs inside the API process as one asyncio task started in the app lifespan,
  subscribed to the feed bus (`feed_bus.py`), checks each tick, fires once per trigger (row marked `fired_at`), records
  `stop` orders at the LTP seen in that tick, and writes an alert row. Market hours only; a trigger set after hours arms
  at 09:15. In-app alerts: the header bell shows an unread count and a list (time, strategy, what fired, exit prices);
  the Alerts page lists the same rows (no WhatsApp / Telegram in this goal). Restart safety: on startup the monitor
  reloads armed triggers; a trigger is never fired twice (unique constraint on trigger id in `paper_orders`).
- **Expiry settlement.** A settlement job runs in the same lifespan task at 15:45 IST on each trading day and at API
  start (catch-up for any past expiry with open legs): every open leg whose expiry < now settles with a `settle` order
  at intrinsic value = max(0, close - strike) for CE, max(0, strike - close) for PE (futures at close), where close is
  the official closing value of the index on the expiry day. Source: decided by the step-5 core proof (below); if no
  allow-listed Kite read gives the published value, step 5 is parked, not guessed.
- **Charges.** Per paper order via `ofo/charges/calculator.py` (ADR-082 rules, exact Decimal); a `settle` order of an
  in-the-money option uses the exercise rule if the calculator has one, otherwise its charge is 0 and the Charges figure
  is labelled "excludes settlement charges" (never estimated). Charges are shown beside P&L, not subtracted from it
  (Sensibull 050).
- **Percent basis.** `% of margin needed` per REQ-081 AC-9/10/11 (edited): denominator = the margin needed the Funds &
  Margins block shows; absent when it could not be read; label exactly "% of margin needed".

## Items

| Step | Item | ADR-207 part / rows | What | Tier | Proof | Status |
|---|---|---|---|---|---|---|
| 0 | read first + spec text | - | §0.1, §0.2; write the REQ text the steps need, citing ADR-207, in one docs commit: REQ-109 (Add to Paper, order book, net position, partial exit, Drafts Mode, no silent drift), REQ-084 (target level + date ACs marked built in this goal; IV parts unchanged), REQ-041 AC-3 note (paper stop = automatic paper exit, no broker), a new AC in REQ-109 for expiry settlement; overlap list of shared files (as GC-UI step 0) | C | Docs commit + overlap list in this file | DONE 2026-10-29 ~11:05 (REQ-109 AC-1/4/7/8 rewritten + AC-9/10 new; REQ-084 note; REQ-041 AC-3 paper note; overlap list below) |
| 1 | CORE: order book + migration + checker | (2), F-65, F-66 | `paper_orders` table, migration 0028, net-position engine, routes `GET /paper/strategies`, `GET /paper/strategies/{id}` (net + orderbook), `POST /paper/strategies/{id}/orders` (list of orders, one transaction); checker extended | A (data migration, money) | Core proof above: 15 real strategies equal to the paisa before vs after; roll on 63 recomputed independently | Not started |
| 2 | Add to Paper | (1), F-67, D-A23 | Button + confirm dialog + toast; old Start tracking path removed | B | vitest red first; live: place a NIFTY iron condor and a SENSEX strangle at typed prices; the orderbook shows the typed prices | Not started |
| 3 | Drafts Mode in the builder | (2), F-65, F-66, D-C14, D-C52 | Net Positions / Orderbook, pending changes + review, partial exit, roll, add leg, Profit left / Loss left, Greeks / payoff on the net position | A (money figures) | Live on strategy 63: roll 22900 -> 22950 shows 2 pending orders, Confirm records them, net position + Profit/Loss left re-checked by the checker; a discarded edit leaves the orderbook unchanged | Not started |
| 4 | Positions -> Paper tab | (3), F-69, D-C39 (Charges + closed part), D-C42, D-C49, D-C50, D-C51 (Add orders part), D-C52 | Totals strip, closed toggle, per-leg columns, actions, newest first, default tab rule, Positions empty text, `/positions` redirect | B | vitest red first; live: totals equal the sum of strategies (checker), closed toggle hides GCBP P5 / P8, default tab opens on Paper | Not started |
| 5 | Expiry settlement | (6), F-68 | Core first: read the closing value of SENSEX for 2026-10-29 through an allow-listed Kite read and compare with BSE's published close (read logged out on bseindia.com); then the job, catch-up and `settle` orders | A (money, scheduled job) | The four SENSEX 29-Oct paper strategies settle; each settle price = intrinsic from the published close, checked by the checker; a NIFTY expiry (3 Nov) checked the same way when it passes, else listed as owed | Not started |
| 6 | What-if sliders | (4), D-B22, D-B23, D-A34, D-B21 | Target block, server recompute of every projected figure | B (A where a number changes) | vitest red first; checker recomputes target P&L, target breakevens and Greeks at target for 3 strategies at 2 target settings each | Not started |
| 7 | Paper stop-loss + alerts | (5) | Conditional exit + leg stop, monitor task, alerts bell + Alerts page | A (scheduled task, money) | Live in market hours: a conditional exit set 5 points beyond spot on a 1-lot paper strategy fires once, records `stop` orders at the tick LTP, the bell shows it; a restart does not refire; the exits never touch an order door (import-graph test) | Not started |
| 8 | Charges + percent basis | (7), (8), F-70 | Charges per order and per strategy; `% of margin needed` | A (money) | Checker recomputes charges for 3 strategies from the order rows; strategy 63's percent reads ~7.0% / 3.6% of margin needed at the walk's figures | Not started |
| 9 | Side-by-side layout check | all above | Screenshot pairs vs Sensibull study 020, 050-053, 090-092, 166-173, 274-279 (study images, never copied into the repo) in `D:\Abhay\scratch\gctp-ui`; 1366 x 768 no-break pass on builder (Drafts Mode) and Positions | C | Viewer pairs + per-part matched / not list in this file | Not started |
| 10 | Expert trader walk + data re-verification | all | Repeat the 2026-10-29 walk end to end: build NIFTY iron condor, SENSEX strangle, NIFTY calendar; Add to Paper at typed prices; watch on Positions; roll, partial exit, add a hedge; set a conditional exit; checker on 5 strategies all figures match | B | Walk lines with times + checker table; F-65 to F-70 each re-tested and marked fixed | Not started |
| 11 | Review, no land | - | Fresh Opus (Tier A) for steps 1, 3, 5, 7, 8; Sonnet for 2, 4, 6; at most 2 rounds; accepted findings fixed and re-verified | A | Verdicts; `git rev-parse @{u}` still "no upstream" on `build/gctp` | Not started |
| 12 | Handover | - | DONE / PENDING / BLOCKED / PARKED / OWED-AT-LAND / NEXT; migration 0029 (drop the 0021 / 0027 tracking tables) listed as owed at land; worktrees merged and removed only via `wt-rm.ps1` where it allows | C | Handover committed locally | Not started |

Out of scope: market analysis screens (chain, OI, IV pages); Strikewise IVs and IV offset (D-B42); portfolio folders
(D-C15, ADR-207 (3)); Convert To Real Trades and Import Zerodha Trades into paper (D-C51 rest, ADR-165); Share Verified
P&L and View Funds (D-C39 rest); WhatsApp / Telegram alerts; adjustment playbooks and suggestion rules (ADR-165 (6),
owner's input); the entry-time adjustment-alert threshold (F-71, deferred); phone layout.

Size, stated honestly: a data migration, a new order model, a background monitor and a scheduled settlement job plus
four screens. Expect two to three sessions; the Status column makes it resumable.

**Order: live-market work first (owner, 2026-10-29 ~11:10 IST: "start with features that require live market data,
because market is open now ... focus on the live market data related features").** At every point in the run, while
the market is open (09:15-15:30 IST) the next item picked is the live-data one; after-hours items are built only when
no live-data item is ready, and their live proofs are scheduled into the next market window.
- Market open: step 0 kept short (spec text + overlap list only, ~20 min), then step 1 (core; its proof runs on live
  prices), then step 7 (paper stop-loss: needs ticks), step 2 (Add to Paper: LTP default and typed prices), step 3
  (Drafts Mode: live roll, partial exit and Profit/Loss left moving with LTP), then the LIVE proofs of steps 4 and 8.
- After 15:30 on 2026-10-29: step 5 core proof (today's SENSEX expiry close) and settlement; then steps 6, 4, 8 builds
  (they work on the last close, ADR-197), 9.
- Next market session: step 10 walk (all live), then 11, 12.
- 4 and 8 may run in parallel with 6 where step 0's overlap list shows no shared file.

## Definition of Done

- [ ] Every step 0-12 has Status DONE with its proof recorded in this file, or PARKED with evidence and what is left.
- [ ] Findings F-65, F-66, F-67, F-68, F-69, F-70 each re-tested live in step 10 and marked fixed in `spec/findings.md`
      (F-71 stays deferred), and `knowledge/findings/paper-plan-diverges-from-position.json` moved to `guarded` naming
      the checker check and the Drafts Mode test.
- [ ] The independent checker reproduces every figure on the Paper tab and in Drafts Mode for 5 real strategies
      (NIFTY + SENSEX; single expiry + calendar; with a roll and a partial exit), all matching.
- [ ] No push, no PR, no CI run happened (`git rev-parse @{u}` on `build/gctp` reports no upstream).
- [ ] Handover written and committed locally; the owner's next steps (land, 0029) listed.

## Overlap list (step 0, 2026-10-29)

Run tree `D:\Abhay\Ventures\OptionsForOptions2-gctp-run`, branch `build/gctp`, base `build/gcbm-must-have` 5052f82a
(#604 OPEN at 10:52 IST) + merge 806bfe6f of `docs/gctp-trader-paper`. `frontend\node_modules` installed by `npm ci`
(the repo's `link_guard.py` refuses a junction into the main checkout; `wt-link-modules.ps1` knows only IPODhan's
folders).

| Step | Files it writes (expected) |
|---|---|
| 1 | NEW `backend/ofo/tracking/orderbook.py`, `backend/ofo_app/paper_store.py`, `backend/ofo_app/routes/paper.py`, alembic `0028_paper_orders.py`; `backend/ofo_app/main.py` (router), `scripts/checks/ui_data_check.py` |
| 2 | `StrategyBuilderPage.vue`, `StrategyActions.vue`, `SaveDraftBar.vue`, NEW `PaperConfirmDialog.vue`, `lib/tracking.js` (-> paper), `routes/tracking.py` (POST removed) |
| 3 | `StrategyBuilderPage.vue`, `LegList.vue`, `StrategyLegRow.vue`, `SummaryCards.vue`, `PaperConfirmDialog.vue`, engine Profit/Loss left (`ofo/tracking/orderbook.py` or `engine/metrics.py`), `routes/paper.py` |
| 4 | `PositionsPage.vue`, `PaperStrategies.vue`, `router`, `lib/usePaperRefresh.js`, `routes/paper.py` (totals) |
| 5 | NEW settlement module, `main.py` (lifespan), `paper_store.py` |
| 6 | `ChartCard.vue`, `ScenarioControls.vue`, `StrategyBuilderPage.vue`, scenario route |
| 7 | NEW monitor module + alembic `0029_paper_triggers.py` (so the drop of the old tables becomes 0030, not 0029), `main.py`, `feed_bus.py`, `AppHeader.vue`, `AlertsPage.vue` |
| 8 | `ofo/charges/*` (read), `routes/paper.py`, `engine/money_summary.py`, `SummaryCards.vue`, `PaperStrategies.vue` |

Shared hot files: `StrategyBuilderPage.vue` (2, 3, 6), `main.py` (1, 5, 7), `routes/paper.py` (1, 3, 4, 5, 8),
`PaperStrategies.vue` (4, 8), `SummaryCards.vue` (3, 8). So 4 and 8 run one after the other; 6 may run beside 4
(no shared file); 2 and 3 in order.

Step-1 "before" record: `GET /tracking` at 2026-10-29 10:55:17 IST (answered_at 05:25:17Z) from the GC-UI API on
ofo_dev, saved at `D:\Abhay\scratch\gctp\before-20261029T105515.json`: 18 tracked strategies (46-63), 16 with open
legs, 2 fully exited (50, 53), 4 with one exited leg (48, 56, 62; 53 both), 2 calendars (51, 59).

## Found during the run

| F | Step | What failed (seen) | Class / RCA | Fix commit | Re-test |
|---|---|---|---|---|---|

## Parked

| Row / item | Why (evidence) | What is left |
|---|---|---|
