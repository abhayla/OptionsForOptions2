# Goal contract GC-TP: an expert trader can place, watch and adjust a paper strategy, the Sensibull way (2026-10-29)

Written 2026-10-29 ~11:00 IST in a planning-only session (no code changed). Docs branch `docs/gctp-trader-paper`
(worktree `D:\Abhay\Ventures\OptionsForOptions2-gctp-docs`, local only, based on `build/gcbm-must-have` 5052f82a). The
owner starts this contract with /goal in a FRESH session.

## SESSION 2 HANDOVER (2026-10-29 ~19:35 IST) - READ THIS FIRST

Owner split the goal at ~17:05: this contract = after-hours work, finished tonight; live-market work = GC-TPL
(`docs/process/goal-contract-GC-TPL-2026-10-30.md`), owner runs it with /goal at 09:15 on 30 Oct.

DONE tonight (local commits on `build/gctp`, head after this commit; no upstream, nothing pushed, no CI):
- Step 13 (new): R-19a Target sliders below the graph + move % + days to expiry + projected badge (Sensibull 020);
  R-19b Breakeven / Max / Greeks on paper cards (090); R-20 + ADR-210 sentences; R-18 Add Booked P&L switch (ADR-209);
  fix round fix1; badge "Projected loss: Rs 203" per REQ-144 AC-1; Drafts Mode Breakeven from the book. Proven on the
  last close by the checker (step 13 row) and in Chrome.
- Owner decisions written into the spec: ADR-209 (booked in target figures + switch, note shape "includes +Rs 962.00
  booked"), ADR-210 (7 sentences), ADR-211 (8 sentences); REQ-084 AC-4, REQ-144 AC-2/AC-3 edited.
- Step 11 review: PARTIAL by design (owner asked for speed): two reviewers, one fix round; Tier A coverage gaps named in
  its row (migrations, checker, order-door test not reviewed).
- Step 9 DONE (1366 x 768 via an in-app frame), step 12 DONE (this block).

OPEN for GC-TPL (live): R-24 (stale first tick vs leg stops at 09:15), R-26 (live push may cancel the target request -
MAJOR candidate), the live proofs of step 13, F-65..F-70 re-tests, BSE previous close 74,151.04.
DEFERRED (Found table): R-22, R-23, R-27, R-30, R-32..R-35. OWED: R-36 mechanism (clock-stamp hook).
OWED AT LAND: migration 0031 (drop 0021/0027 tables); remove worktrees gctp-s1..s8, gctp-r18/r19a/r19b/r20/fix1 and
the harness trees under `OptionsForOptions2\.claude\worktreesgent-*` via wt-rm.ps1 (refuses until on origin/main);
NIFTY 3 Nov settlement proof.
Servers left running: API 8765 (run tree, merged code, started ~19:27), Vite 5174 (session 1, PID 17664). Lock removed.

## SPLIT (2026-10-29 ~17:05 IST, session 2) - READ THIS FIRST

Owner: "update the goal and include only features which ... do not require live market data, and work only on those
things. There should be a separate contract ... which requires the live market data, and I will run that at 9:15
tomorrow." So THIS contract now holds only work that needs no live prices, finished tonight. Everything that needs the
market moved to `docs/process/goal-contract-GC-TPL-2026-10-30.md` (BSE previous-close check, step 10 walk, F-65..F-70 live
re-tests, the defect class to `guarded`, the R-1 live re-run). In the old NEXT list below, items 1 and 2 are MOVED there.

Tonight's scope (no live data; after-hours checks use the last close, ADR-197):
- Step 13 (new): R-19a Target block below the graph + move % + days-to-expiry + projected badge (Sensibull 020); R-19b
  Breakeven / Max Profit / Max Loss + Greeks toggle on paper cards (Sensibull 090); R-20 the ADR-210 sentences; R-18 the
  "Add Booked P&L" switch, ON by default (ADR-209, Sensibull 020).
- Step 11 review (cut to two reviewers: Opus on 1, 3, 5, 7, 8; Sonnet on 2, 4, 6) and ONE fix round.
- Step 9 rest: 1366 x 768 pass (needs the Chrome window un-maximized, no market).
- After-hours proof of step 13 on the last close: checker on 3 strategies + screens in Chrome.
- Step 12 handover ("SESSION 2 HANDOVER" block) + memory; then GC-TPL is ready for 09:15.
Worktree removal: `wt-rm.ps1` refuses every merged gctp-s* tree until its work is on origin/main (measured 17:0x: "not
on origin/main; nothing removed") - OWED AT LAND, not tonight.

## SESSION 1 HANDOVER (2026-10-29 16:47 IST) - READ THIS FIRST

The live contract is THIS file in the run tree `D:\Abhay\Ventures\OptionsForOptions2-gctp-run` (branch `build/gctp`,
head after this commit; no upstream, nothing pushed, no PR, no CI). The copy in `OptionsForOptions2-gctp-docs` is the
STALE planning copy - do not use it.

DONE (live-proven, review owed): steps 0, 1, 2, 3, 4, 5, 6, 7, 8 (each Status cell below has the proof). Step 9 PARTIAL
(pairs done; 1366 x 768 pass owed - the Chrome window would not resize). Steps 10, 11, 12 NOT STARTED.

Servers (started by session 1; they may die when the session is cleared - check ports first): API on 8765 = uvicorn PID
25896 (run tree, ofo_dev at migration 0030, LIVE_MARKET=1); Vite on 5174 = PID 17664 (run tree frontend). Restart
commands: see "Running the app" (use the run tree path). ofo_dev head = 0030_paper_settle_zero. Kite token expires
06:00 IST: owner logs in once in a PRIVATE window at http://127.0.0.1:8765/broker/zerodha/login before 09:15.
Lock: `.run-active.lock` at the run tree root holds session 1's token - the new session overwrites it.

NEXT, in order:
1. 09:15-09:20 tomorrow: bseindia.com SENSEX "Previous Close" must read 74,151.04 (final official close for the 29 Oct
   settlement; step 5 owed check). If it differs: STOP, a correcting settle is needed (orders are append-only).
2. Step 10 (market hours): the expert-trader walk end to end (NIFTY iron condor, SENSEX strangle, NIFTY calendar; Add to
   Paper at typed prices; watch on Positions; roll, partial exit, add a hedge; set a conditional exit; checker
   `--paper-orders` on 5 strategies incl. a calendar and a partial exit); retry the 1366 x 768 pass (ask the owner to
   un-maximize Chrome if `window.innerWidth` stays 1536); re-test F-65..F-70 and mark them fixed in spec/findings.md;
   move knowledge/findings/paper-plan-diverges-from-position.json to guarded (checker `--paper-orders` + the
   paper-drafts-diff test).
3. ONE owner question (business: user-visible words), batched: R-15 (stale sentence for what-if figures), R-20 (nine
   reason codes with no sentence), R-18 (does the target P&L include booked P&L), R-16 (rupee sign on some money texts).
4. R-19 (Sensibull parity gaps: sliders below the graph with move-% + projected badge; per-card Breakeven / Max / Greeks
   toggle) - layout is a technical/design call (memory screen-design-by-research-role): decide, build as a small item.
5. Step 11 review: fresh Opus (Tier A) on steps 1, 3, 5, 7, 8; Sonnet on 2, 4, 6; at most 2 rounds; open points for the
   reviewers: R-13, R-17, the history-guard door for the settlement job (ADR-066), builders' red-first misses (2, 4b r2,
   6b r2), the per-leg theta tolerance.
6. Step 12 handover: worktrees gctp-s1, s1b, s2, s3a, s3b, s4a, s5, s6, s7, s7b, s8 are ALL merged into build/gctp and can
   be removed with `wt-rm.ps1` (never rm -rf; each has its own npm-ci node_modules, not a junction); plus the harness
   trees under `D:\Abhay\Ventures\OptionsForOptions2\.claude\worktrees\agent-*` made by this session's builders;
   migration 0031 (drop the 0021/0027 tracking tables - renumbered: 0029 = triggers, 0030 = settle-zero) is owed at land;
   NIFTY 3 Nov settlement proof owed after the goal window.

Process lessons from session 1: builders hit their call caps 6 times - keep the HARD RULE stop line and put verification
commands in the brief; stamp every time with the clock (memory stamp-times-from-clock); the repo hooks block `;`-chained
commits and multi-line python before a commit - run edit scripts as separate calls.

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
  `scripts/orchestrator/db_run_fresh.py` (the PostgreSQL host is shared with a production database: targeted files only).
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
| 1 | CORE: order book + migration + checker | (2), F-65, F-66 | `paper_orders` table, migration 0028, net-position engine, routes `GET /paper/strategies`, `GET /paper/strategies/{id}` (net + orderbook), `POST /paper/strategies/{id}/orders` (list of orders, one transaction); checker extended | A (data migration, money) | Core proof above: 15 real strategies equal to the paisa before vs after; roll on 63 recomputed independently | DONE 12:40 (review owed in step 11). (a) t0 `GET /tracking` 12:31:14 (`D:\Abhay\scratch\gctp\t0-20261029T123114.json`), backup #2 `gctp-backup-20261029T123114.sql` 18/44/6; API PID 4660 stopped; (b) `alembic upgrade 0028_paper_orders` on ofo_dev as owner (`D:\Abhay\scratch\gctp\migrate_dev.py`) exit 0, `current` = 0028 (head); paper_orders 50 rows = 44 open + 6 exit; (c) `prove_migration.py` (engine on ofo_dev's orders at the snapshot's prices) vs t0: 18 strategies, 0 mismatches (every total / booked / unbooked and every leg); vs the 10:55 reply: 0 mismatches; API restarted from the run tree (uvicorn PID 25452), `GET /tracking` 200, 18 strategies; (d) roll on 63 at 12:33: POST exit BUY 65 22900 CE @132.00 + add SELL 65 22950 CE @108.00 (typed: the chain route answered NOT_CONNECTED) -> 201; booked -633.75 = (122.25-132.00)x65 by hand; `ui_data_check.py --paper-orders 63`: 41 match, 0 mismatch. Part 4 MERGED 12:28 (79aaab25): /tracking on paper_orders, tracking_store deleted; session re-run: test_tracking_from_orders 4, test_strategy_tracking 22, test_strategy_tracking_list 33, repo scan 959/1 skipped; 0027 grant test fixed by the session (7f4d180d, 4 passed); DB mutants: append-only guard -> 2 failed, exit-above-open -> 1 failed (both killed). Earlier: engine + 0028 + store merged (ca13562b), 53 passed. 1b MERGED 11:50 (abcef9e0): /paper routes, order-door guard, checker `--paper-orders`; re-run by the session: unit 83 passed, test_paper_routes 24 passed, test_paper_order_door 9 passed, test_response_door 214, test_order_closure_all_routes 13, repo scan 959 passed / 1 skipped, ruff clean, forbidden-import mutant on routes/paper.py -> 1 failed (killed). The 1b builder overran its budget (127 tool uses vs 70) and stopped at its turn limit with no report |
| 2 | Add to Paper | (1), F-67, D-A23 | Button + confirm dialog + toast; old Start tracking path removed | B | vitest red first; live: place a NIFTY iron condor and a SENSEX strangle at typed prices; the orderbook shows the typed prices | PARTIAL 13:28 (merged fc584ae0): session re-run response-door 214, order-closure 13, repo scan 959/1 skipped; builder: vitest 1495 passed (paper-add 21; red-first NOT observed - written after the code), test_strategy_tracking 15, tracking_list 33. LIVE in Chrome (API PID 15992, Vite PID 17664, run tree, ofo_dev at 0029): NIFTY 3 Nov short iron condor, unsaved -> Add to Paper saved it as strategy 64 then opened the list (~3 s later); 68.03 refused "Enter a price in steps of 0.05", Confirm disabled; 68.00 typed -> orders 13:25:32 BUY 22650 PE 68.00 / SELL 22750 PE 96.30 / SELL 22950 CE 104.50 / BUY 23050 CE 66.50, kind open. SENSEX 5 Nov short strangle -> strategy 65, typed 570.00 / 495.50 -> orders 13:27:44 at exactly those prices, qty 20. Open: the toast was not seen (R-6) |
| 3 | Drafts Mode in the builder | (2), F-65, F-66, D-C14, D-C52 | Net Positions / Orderbook, pending changes + review, partial exit, roll, add leg, Profit left / Loss left, Greeks / payoff on the net position | A (money figures) | Live on strategy 63: roll 22900 -> 22950 shows 2 pending orders, Confirm records them, net position + Profit/Loss left re-checked by the checker; a discarded edit leaves the orderbook unchanged | PARTIAL 13:51. 3b1 MERGED bdb19883 (builder: diff red-first on the real 63 book, 11 passed; page tests red first 10 failed; 4 mutants killed; session re-run 5 files 127 passed; full vitest on the merged run tree 1534 passed). REQ-109 AC-9 reworded (per-contract netting: a strike step onto a held opposite position = two exits). LIVE on 63: opens in Drafts Mode (dashed frame, "Paper mode - not real trades", legs = net at averages 72.60 / 102.00 / 80.95 / 108.00, closed 22900 CE not shown, Save hidden); step 22950 CE -> 23000 CE (held long) = "2 pending changes": SELL 23000 CE 85.05 + BUY 22950 CE 106.40, Cancel + Discard -> still 6 orders; roll 22700 PE -> 22650 PE: BUY 22700 PE 77.45 exit + SELL 22650 PE 63.25 add, Confirm 13:50:15 -> 8 orders, booked +962.00 (= -633.75 + (102.00-77.45)x65 = +1,595.75), checker 48 match / 0 mismatch (plain console: R-1 fix live). 3a MERGED ab5befa6 14:03 (engine `ofo/engine/extremes.py`; session re-run repo scan 959/1 skipped, tests/tracking 125; builder: response-door 214, paper_routes 27, tracking 14, tracking_list 33, 4 mutants killed; dead `paper_store.start` / `ALREADY_TRACKED` / `capture_entry` removed). Hand check on 63 (book after the first roll): credit 56.45 x 65 = 3,669.25, max loss 3,669.25 - 6,500 - 633.75 = -3,464.50, max profit 3,035.50 = the engine's. Live reply on the merged API (PID 13672) at about 14:02 (captured before the 14:03 commit) after the second roll: Profit left +2,132.00 / Loss left -1,118.00 / Max Profit +2,112.50 / Max Loss -1,137.50 (by hand: net credit 17.70 x 65 = 1,150.50 + booked 962.00 = 2,112.50; above 23000 (-50 + 17.70) x 65 + 962 = -1,137.50), saved as the 3b2 fixture. 3b2 MERGED 7befa4a4 (builder: red first 16 failed -> 17 passed, 4 mutants killed, full vitest 1549 + 3 failed of which 2 its own fixed and 1 = known flaky R-12; session re-run 5 files 60 passed). LIVE ~14:35: 63 in Drafts Mode shows Profit left +2,171.00 / Loss left -1,079.00 first, Max Profit +2,112.50 / Max Loss -1,137.50 below (= hand check), legs "Paper average" (R-11 fixed), funds-% lines hidden in Drafts Mode, Orderbook view lists the 8 orders. FOUND by 3b2: after Add to Paper the page stays a plan with Add to Paper live -> a second press would add the opening orders twice. 3c MERGED e30541cd (red first 3 failed / 5 -> 5 passed; builder full vitest 1557 passed, repo scan 959; session re-run 4 files 37 passed); LIVE ~15:09 strategy 66: after Confirm the page entered Drafts Mode (Net Positions panel, Exit all, Profit left +7,185.75 / Loss left -5,814.25) and Add to Paper is gone. LEFT before this note (now built): Profit left / Loss left on screen, Net Positions / Orderbook switch, Exit all + partial exit, the dialog title for exits (shows "Add to Paper"), R-6 toast, R-11 (legs say "Your price, typed <now>" for paper fills) |
| 4 | Positions -> Paper tab | (3), F-69, D-C39 (Charges + closed part), D-C42, D-C49, D-C50, D-C51 (Add orders part), D-C52 | Totals strip, closed toggle, per-leg columns, actions, newest first, default tab rule, Positions empty text, `/positions` redirect | B | vitest red first; live: totals equal the sum of strategies (checker), closed toggle hides GCBP P5 / P8, default tab opens on Paper | PARTIAL ~15:51. 4a MERGED (session re-run paper_routes 27, triggers_routes 10, totals 9, repo scan 959/1 skipped; hand check: booked 731.25 = -1,504.75 (48) + 2,236.00 (50)). 4b round 1 MERGED 090deba7 (session fixed the broker-name allow-list for the moved F-69 lines; repo scan 959/1, full vitest 1554), round 2 MERGED 8800ceb6 (lot_size from the server, Lots column, exits through PaperConfirmDialog; builder vitest 1559, repo scan 959, paper_routes 29; NOT red-first; session re-run 3 files 45 passed). LIVE after the close (API PID 16464): /positions redirects to /positions/current-positions and opens on Paper (no real positions; F-69); totals strip Booked -21,300.85, Total / Unbooked / Decay absent (prices not live, AC-5); Show closed positions toggle; newest first (66 "Bull Call Spread"); "2 of 2 positions"; Lots "1 lot"; Stops panel shows a "Stop on a leg" row per open leg (R-10 FIXED). LEFT: the totals strip prints the raw code "prices_not_live" (R-14); the checker over the totals; Charges column (step 8) |
| 5 | Expiry settlement | (6), F-68 | Core first: read the closing value of SENSEX for 2026-10-29 through an allow-listed Kite read and compare with BSE's published close (read logged out on bseindia.com); then the job, catch-up and `settle` orders | A (money, scheduled job) | The four SENSEX 29-Oct paper strategies settle; each settle price = intrinsic from the published close, checked by the checker; a NIFTY expiry (3 Nov) checked the same way when it passes, else listed as owed | IN PROGRESS. CORE PROVEN 14:10 on real data (F-72): 5a MERGED 7261cf1f (one read-only allow-list entry GET /instruments/historical/{token}/day; session re-run 41 passed + test_no_order_placement 53 passed; builder repo scan 959/1 skipped, 2 mutants killed); `index_close.py SENSEX 2026-10-28` -> 73246.03 = bseindia.com "Previous Close: 73,246.03" (logged out, same minute). NIFTY 28 Oct read 22698.85, not yet compared with NSE. 5b MERGED (session: history-guard door for the lifespan settlement job decided as a technical call - ADR-066's threat model excludes internal jobs; history guard 56 passed, repo scan 959/1 skipped, settlement DB test 21 passed; builder: 3 mutants killed, 0029/0030 migration tests pass). 0030 on ofo_dev 15:06 after backup `gctp-backup-paper-20261029T150651.sql` (64 orders / 3 triggers / 1 alert); API restarted on the merged code (PID 8988). LIVE 29 Oct: Kite day close SENSEX 74,151.04 at 15:32:33 and 15:47:20; bseindia.com 74,151.04 at 15:32 and 15:47 (banner still "Open"); dry run 15:32 "nothing to settle" (before 15:45 by rule). The API's 15:45 job settled all three: 52 BUY 72600 PE 0.00 + BUY 73000 CE 1,151.04 -> EXITED, booked -10,626.80; 60 BUY 72800 PE 0.00 + BUY 73200 CE 951.04 -> -8,192.80; 61 SELL 73000 PE 0.00 + BUY 72600 PE 0.00 -> -3,161.00 - each equal to the hand figures from close 74,151.04. OWED: tomorrow 09:15 bseindia.com "Previous Close" = 74,151.04 (final official value; step 10); NIFTY 3 Nov expiry proof after this goal's window |
| 6 | What-if sliders | (4), D-B22, D-B23, D-A34, D-B21 | Target block, server recompute of every projected figure | B (A where a number changes) | vitest red first; checker recomputes target P&L, target breakevens and Greeks at target for 3 strategies at 2 target settings each | PARTIAL 16:03. 6a MERGED (round 2 fixed the reflection + money-guard failures; session re-run guards 305, target 17, app 15). Owner approved the three what-if sentences (question tool "Approve all three", ADR-208, REQ-084 AC-2 / AC-5). 6b round 1 MERGED f06d9334 (full vitest 1573), round 2 MERGED fd655adb (limits on every reply, sliders always visible, "Set a target" button and an unapproved stale sentence removed; builder full vitest 1571, repo scan 959; session re-run route 15 + vitest 17). LIVE 16:03 on 63 (API PID 18340): Target block visible at once (level slider + box + Reset, date slider with < > + Reset); level 23,100 -> "P&L at target -Rs1,354.60" with the approved estimate label, Greeks at target delta -1.9287 / gamma 0.0000 / theta 27.0805 / vega -6.7978. OPEN: "Breakeven at target" blank (checker to say if right); whether the target P&L includes the 962.00 booked (checker 6c prints both); R-15, R-16. 6c MERGED (checker `--target-level/--target-at/--booked`, own Black-Scholes, 164 checker tests). PROOF 16:12 (after the close, last-close prices) - 3 strategies x 2 settings, checker vs server: 63 @23,000 30 Oct 15:00 P&L -1,100.45 = -1,100.45; 63 @22,800 2 Nov 12:00 93.60 = 93.60; 66 @23,000 705.90 = 705.90; 66 @22,800 -4,561.05 = -4,561.05; 65 (SENSEX) @74,300 -180.60 = -180.60; 65 @73,800 3 Nov 12:00 10,946.40 = 10,946.40; breakevens and total Greeks match; the only mismatches are per-leg theta in the 3rd-4th decimal (e.g. -1,211.1394 vs -1,211.1382, ~1e-6 relative: the two sides value a few seconds apart) - checker tolerance, R-17. The target P&L is OPEN LEGS ONLY (63: open-only row matches, open+booked 962.00 row does not) - R-18. Checker caveat: the reply carries no dividend yield, the checker solves it from the reply's own leg prices (~0.0776), so a shared wrong yield would not be caught (R-17). DONE except the review |
| 7 | Paper stop-loss + alerts | (5) | Conditional exit + leg stop, monitor task, alerts bell + Alerts page | A (scheduled task, money) | Live in market hours: a conditional exit set 5 points beyond spot on a 1-lot paper strategy fires once, records `stop` orders at the tick LTP, the bell shows it; a restart does not refire; the exits never touch an order door (import-graph test) | PARTIAL 13:34. 7a MERGED c4506c40 (session re-run: test_paper_monitor 18, test_paper_order_door 12, test_paper_triggers_routes 10 (builder), response-door 214, repo scan 959/1 skipped, ratchet OK after the session moved one import; mutants: live-price guard, market hours, open-quantity cap killed; once-only killed by the double-claim test). 0029 on ofo_dev 13:19 (owner role, `migrate_dev.py`, exit 0, head). LIVE: strategy 64 (1-lot NIFTY iron condor, Add to Paper 13:25) armed 13:29:41 conditional exit below 22,845.00 / above 22,855.00 (spot 22,849.80) -> FIRED 13:31:08 below: 4 `stop` orders at the tick LTPs (SELL 22650 PE 70.90, BUY 22750 PE 100.50, BUY 22950 CE 98.00, SELL 23050 CE 62.45), strategy EXITED, booked +74.75 = 188.50 - 273.00 + 422.50 - 263.25 by hand; 1 alert "Paper strategy - ... Conditional exit: NIFTY crossed below 22,845.00; exited 4 legs at ...". API restarted 13:31:59 (PID 25484): at 13:33:37 still 8 orders / 4 stop / 1 alert (no refire); the other trigger (above) cancelled 13:33:37 at the monitor's reload, not at the fire. Order doors: import-graph test 12 passed. 7b (bell, Alerts page, trigger form) building |
| 8 | Charges + percent basis | (7), (8), F-70 | Charges per order and per strategy; `% of margin needed` | A (money) | Checker recomputes charges for 3 strategies from the order rows; strategy 63's percent reads ~7.0% / 3.6% of margin needed at the walk's figures | PARTIAL 16:33. 8a MERGED 12a76b8a (paper charges engine `ofo/charges/paper_charges.py`; ITM bought settle = exercise STT, sold / OTM settle = 0; percent basis switched to margin needed; finish round: wiring 8, response-door 214, 3 mutants killed, repo scan 959/1; session re-run charges + percent 143 passed). Strategy 63's 8 orders: charges 248.80 (exact 248.79754728500; one order by hand BUY 65 @72.60 = 25.725598046 - builder's test). LIVE (API PID 25896): GET /paper/strategies/63 charges 248.80; builder on an unsaved NIFTY short iron condor: Max Profit +4,098 (6.6% of margin needed), Max Loss -2,402 (3.9% of margin needed) with margin needed 61,743 (4,098 / 61,743 = 6.64%; 2,402 / 61,743 = 3.89% by hand) - F-70 FIXED. The charges text prints a rupee sign (R-16 class). 8b MERGED d76abf43 (red first 5 failed; builder full vitest 1581, repo scan 959; session re-run 3 files 38 passed). LIVE 16:46 (page text read by script - Chrome screen capture timed out, the page itself rendered): Paper totals strip Charges 2,257.43 beside Total / Booked / Unbooked; cards "Charges 59.63" (66) and "87.37" (65); Booked figures unchanged (nothing subtracted); totals.charges 2,257.43 = sum of the 21 strategies' charges 2,257.43 (script). R-14 FIXED live ("Paper P&L paused - prices not live" in place of the code). Nine other reason codes show only a dash (no approved sentence): rates_unavailable, not_priced, no_iv, no_next_open, model_refused, contract_retired, contract_delisted, token_reassigned, contract_missing (R-20). DONE except the review |
| 9 | Side-by-side layout check | all above | Screenshot pairs vs Sensibull study 020, 050-053, 090-092, 166-173, 274-279 (study images, never copied into the repo) in `D:\Abhay\scratch\gctp-ui`; 1366 x 768 no-break pass on builder (Drafts Mode) and Positions | C | Viewer pairs + per-part matched / not list in this file | PARTIAL ~16:15. Pairs (ours in D:\Abhay\scratch\gctp-ui: ours-paper-tab-1536.jpg, ours-builder-drafts-target-1536.jpg; Sensibull images read in place, never copied). The study has images only for 020, 050-053, 090-092; 166-173 and 274-279 are catalogue text lines. MATCHED: dashed paper frame + "not real" label (090/091 Drafts Mode frame); totals Total / Booked / Unbooked / Total Decay (090); Show closed positions toggle (090); "N of M positions" (090); per-leg Avg / LTP / Booked / Unbooked / P&L (090); Open in Builder, Add orders, Exit (090); Net Positions | DONE ~19:30 (session 2). Pairs as in session 1 (matched / not matched list unchanged, R-19 built since: Target sliders below the graph with move % and days to expiry, projected badge, paper-card Breakeven / Max / Greeks, Add Booked P&L switch). 1366 x 768: Chrome stayed maximized (resize ignored, innerWidth 1536), so each page was loaded in a 1366 x 768 same-origin frame inside the app (real media queries): builder Drafts Mode on 63 and Positions -> Paper: scrollWidth 1351 = clientWidth 1351, 0 elements past the right edge; picture D:\Abhay\scratch\gctp-ui\ours-builder-drafts-1366.jpg (holds the owner funds figure: scratch only) |
| 10 | Expert trader walk + data re-verification | all | Repeat the 2026-10-29 walk end to end: build NIFTY iron condor, SENSEX strangle, NIFTY calendar; Add to Paper at typed prices; watch on Positions; roll, partial exit, add a hedge; set a conditional exit; checker on 5 strategies all figures match | B | Walk lines with times + checker table; F-65 to F-70 each re-tested and marked fixed | MOVED to GC-TPL (goal-contract-GC-TPL-2026-10-30.md, steps L1-L4), owner split 2026-10-29 ~17:05 |
| 13 | Sensibull parity + owner wording | R-18, R-19, R-20 (ADR-209, ADR-210) | R-19a target block (020), R-19b paper card figures + Greeks (090), R-20 sentences, R-18 Add Booked P&L switch | B | builders red-first; session re-run of touched files; checker on the last close for 3 strategies (target with --booked) | DONE ~19:30. Merged: R-19a 759f19d7, R-20 d0f992bf, R-19b 97532f26, R-18 9c11c25c, fix1 e5336365; slot pins 2e577d6b; checker booked basis 31b6ac2a; badge Rs whole rupees a0d51c0b; Drafts Mode breakeven from the book a4773085. Final suites on the merged tree: vitest 111 files / 1612 passed; repo guard 959 passed / 1 skipped. PROOF on the last close 19:14 (checker vs server, API on the merged tree): paper-orders 63 43/0, 66 17/0, 65 17/0 mismatches; target with booked: 63 @23,000 30 Oct 15:00 -142.35 = -142.35 (open -1,104.35 + booked 962.00), breakevens match; 63 @22,800 2 Nov 12:00 22/22; 66 715.00 = 715.00; 65 SENSEX 1,433.80 = 1,433.80 (only per-leg theta 4th decimal, R-17). Chrome ~19:20-19:30: badge "Projected loss: Rs 203 | includes +Rs 962.00 booked | 0.3% of margin needed"; switch OFF -1,165.45, ON -203.45 (diff 962.00 = booked); move +0.3%, 5D to expiry; Paper card 63 Breakeven 22,618, 22,983 = builder 22,618, 22,983 after a4773085 (hand: 22,650 - (17.70 + 962/65) = 22,617.50). NOT red-first: R-19a, R-19b, R-20, fix1 item 4 (R-18, fix1 items 1-3 and a4773085 red-first). 48 / 56 target not checkable after hours (no last close for their contracts: R-35) |
| 11 | Review, no land | - | Fresh Opus (Tier A) for steps 1, 3, 5, 7, 8; Sonnet for 2, 4, 6; at most 2 rounds; accepted findings fixed and re-verified | A | Verdicts; `git rev-parse @{u}` still "no upstream" on `build/gctp` | PARTIAL ~18:05 (session 2). Cut by the owner's speed instruction to 2 reviewers, 1 fix round. Tier A (Opus, steps 1/3/5/7/8): no CRITICAL/MAJOR, 4 MINOR (R-22..R-25) - but only 14 tool calls in 62 min (stopped at budget): migrations 0028-0030, the checker, the order-door test and the red-first question NOT reviewed (stated, not counted as a pass). Engine averaging re-derived by hand on 3 cases, all equal. Tier B (Sonnet, steps 2/4/6): 1 MAJOR candidate (R-26, live only -> GC-TPL), 4 MINOR (R-27..R-30); #3 and #4 in fix1. Fix round fix1 building |
| 12 | Handover | - | DONE / PENDING / BLOCKED / PARKED / OWED-AT-LAND / NEXT; migration 0029 (drop the 0021 / 0027 tracking tables) listed as owed at land; worktrees merged and removed only via `wt-rm.ps1` where it allows | C | Handover committed locally | DONE ~19:35 (session 2): SESSION 2 HANDOVER block above; memory note; worktree removal OWED AT LAND (wt-rm.ps1 refuses until the work is on origin/main) |

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

- [ ] Every step 0-13 except 10 (moved) has Status DONE with its proof recorded in this file, or PARKED with evidence and what is left.
- [ ] (MOVED to GC-TPL: the live F-65..F-70 re-tests, the class file to `guarded`, the 5-strategy live checker run.)
- [ ] Step 13 merged into build/gctp and proven on the last close: the checker matches the target figures (with booked)
      and the paper card figures for 3 strategies; the screens seen in Chrome.
- [ ] GC-TPL contract committed and its L0 preflight possible from the handover alone.
- [ ] No push, no PR, no CI run happened (`git rev-parse @{u}` on `build/gctp` reports no upstream).
- [ ] Handover written and committed locally; the owner's next steps (land, 0029) listed.

## Overlap list (step 0, 2026-10-29)

Run tree `D:\Abhay\Ventures\OptionsForOptions2-gctp-run`, branch `build/gctp`, base `build/gcbm-must-have` 5052f82a
(#604 OPEN at 10:52 IST) + merge 806bfe6f of `docs/gctp-trader-paper`. `frontend\node_modules` installed by `npm ci`
(the repo's `link_guard.py` refuses a junction into the main checkout; `wt-link-modules.ps1` does not know this repo's
`frontend` folder).

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

Tier A backup (before any migration on ofo_dev): `D:\Abhay\scratch\gctp-backup-20261029T105953.sql`, read-only
INSERT dump by `D:\Abhay\scratch\gctp\backup_tracking.py` via `dev_run.py` (no pg_dump on this PC):
strategy_tracking 18, strategy_tracking_legs 44, strategy_tracking_exits 6 (equal to the before record's 44 legs and 6
exits).

## Found during the run

| F | Step | What failed (seen) | Class / RCA | Fix commit | Re-test |
|---|---|---|---|---|---|
| R-1 | 1 | `ui_data_check.py --paper-orders 63` crashed (UnicodeEncodeError on U+2212) on the Windows console after computing 41 match / 0 mismatch | Class: every checker mode printing a server display text with U+2212 on a cp1252 console (all modes share `main`). RCA: stdout used the console code page. Fix: `main` reconfigures stdout / stderr to UTF-8. Test on the REAL strategy-63 reply under PYTHONIOENCODING=cp1252: red on the unfixed checker (1 failed), green fixed (15 passed). No detection change: the test is the detection | this commit | live re-run exit 0 with PYTHONIOENCODING unset owed at step 10 |
| R-2 | 1 | deferred (C4): starting tracking on a strategy that holds the same contract on two legs answers 500 (nothing stored) | the start route is removed in step 2 (Add to Paper), which must refuse a duplicate contract with a text | - | step 2 test |
| R-3 | 1 | observation: `GET /api/market/chain?underlying=NIFTY&expiry=2026-11-03` answered state NOT_CONNECTED, 0 rows at 12:33 while paper prices were live | not yet diagnosed (outside step 1's done list); re-check at step 3 (Drafts Mode add-leg needs the chain) | - | - |
| R-4 | 7 | 7a monitor text shows a level as "22850.00", not grouped like other index levels | `format_index_level` + `paper_trigger_level` template (no existing formatter gave "22,850.00") | f1838bd7 + 7a routes round | live 13:29: trigger reply level_text "22,845.00" / "22,855.00" |
| R-5 | 7 | 7a mutant "drop fired_at IS NULL" survived: the DB guard OF029 and the empty book stop a second fire first, so the store's own once-only check was untested | double `claim_fire` test | b952ad0c | builder: red on the mutant (1 failed), green restored; session re-run test_paper_monitor 18 passed |
| R-6 | 2 | live 13:25 and 13:27: after Confirm the "Added to Paper" toast was not on screen (5 s after, first try) nor in the page (about 2 s after, second try); the code shows it 8 s (`SaveDraftBar.vue` `paperToast`, inline below the action row) | not yet diagnosed; both tries were the save-first path (unsaved strategy -> save -> the URL moves to ?strategy=N -> list opens ~3 s later), suspected remount or reset after the save navigation. Class: every Add to Paper on an unsaved strategy | 3b2 (toast fixed at the bottom of the screen) + 3c | LIVE ~15:09 strategy 66 (NIFTY bull call spread, unsaved -> Add to Paper): toast "Added to Paper / Open in Builder / Open Paper positions" on screen 2 s and 5 s after Confirm - FIXED |
| R-8 | 7 | Alerts page row shows "Strategy 64", not the name: the `GET /paper/alerts` row carries only strategy_id (the body text does name it) | add the strategy name to the alert reply; fold into step 4 (Paper tab / names) | - | - |
| R-9 | 1-7 | strategy names come back with literal quote marks (`"\"Short Iron Condor\""`, `"\"GCBP P1 BCS\""`) in /tracking, /paper and the alert text | not diagnosed; probably older than GC-TP (names 46-63 predate it): check how the save path stores the name before fixing (C4: deferred if older) | - | - |
| R-12 | 3 | `frontend/tests/live-strategies.test.js` "13 strategies, one card loading at a time" fails intermittently: base 7befa4a4 -> 1 failed; same tree twice -> 30 passed, then 2 failed | timing-dependent test, not caused by GC-TP files (fails on the base). Deferred (C4) | - | - |
| R-13 | 3 | Drafts Mode writes the words for `extremes_reason` (multi-expiry, prices not live) in the browser; the book sends only a code | should come from a server template like every other shown text; for the step 11 review | - | - |
| R-20 | 8 | nine reason codes have no approved sentence and show only a dash on the Paper tab / Drafts Mode (rates_unavailable, not_priced, no_iv, no_next_open, model_refused, contract_retired, contract_delisted, token_reassigned, contract_missing) | user wording = owner; batch into one question with R-15 (session 2: owner approved 6 sentences 16:58, ADR-210; 3 codes reuse reviewed texts; build R-20 item) | - | - |
| R-14 | 4 | live ~15:51: the Paper totals strip prints the raw code "prices_not_live" under each absent total | the reason must be the existing sentence "Paper P&L paused - prices not live" (already used on the cards); step 8b d76abf43 | LIVE 16:46: sentence shown - FIXED |
| R-15 | 6 | 6b round 2 reused the app's stale sentence "Stale: the latest price for this contract is older than expected, so the figure may be out of date." for stale what-if figures - existing text, but its meaning (a contract price) does not fit a target figure | needs owner wording or a fitting existing text; for the step 11 review / owner (session 2: owner approved the sentence 16:58, ADR-210 (7); build R-20 item) | - | - |
| R-16 | 6 | live 16:03: the target P&L prints "-Rs1,354.60" with a rupee sign while every other money figure in the app prints none (e.g. -1,137.50) | money display format of the target block differs from the app's; check which template the server used (REQ-152 sign / format rule) (session 2, technical call: CONFORMS - the target P&L uses the engine's exact-money formatter `display.py` (ADR-008), whose spec examples print the rupee sign; REQ-152 AC-1's no-sign list covers only summary figures; no change) CORRECTED ~19:23 in the Chrome check: that call read the general money rule, not the badge's own requirement - REQ-144 AC-1 writes "Projected profit: Rs 7,714" (whole rupees; Sensibull 020 "7,714"), and the badge showed "Projected loss: ₹203.45" above "includes +Rs 962.00 booked". Fixed: badge label Rs + whole rupees half-up, zero "Projected P/L: 0" (ADR-211 (1); the old test expected "Projected P/L: ₹0.00", never the approved text). The P&L-at-target figure in the Target block keeps the exact-money format (REQ-084, not a badge) | - | - |
| R-17 | 6 | checker target mode: per-leg theta differs in the 3rd-4th decimal (valuation instants seconds apart), and the dividend yield is solved from the reply itself (a shared wrong yield is invisible) | checker limits, not server defects; for the step 11 review (widen per-leg theta tolerance by the time gap; the server could send its q) | - | - |
| R-18 | 6 | the target P&L on a paper strategy in Drafts Mode excludes the booked P&L (63: -1,100.45 open legs vs -138.45 with the 962.00 booked) | spec silent (REQ-084 AC-4 "the P&L at the target level and date"; ADR-207 (2) Profit left also excludes booked, Max includes it): open point for the review / owner (session 2: owner 16:57 'Include booked'; Sensibull 020 shows an 'Add Booked P&L' switch ON -> ADR-209: switch on the chart card, ON by default; build after R-19a) | - | - |
| R-19 | 9 | side-by-side vs Sensibull 020 / 090: the Target sliders are above the graph (020: below, with move-from-spot %, days-to-expiry and a Projected profit badge); paper cards lack Breakeven / Max Profit / Max Loss and a Greeks toggle (090) | ADR-152 makes Sensibull the default: candidates for a follow-up item; the slider position came from this contract's own design note (a planning-session call, not an owner decision) | - | - |
| R-21 | session 2 | owner asked a 4th time (16:59) whether Sensibull is referred to: two owner questions went out with a Spec basis but no Sensibull check (screen 020 had the answer to R-18) | Class: owner product questions asked without grepping the study. Mechanism owed: the repo's spec_basis_gate hook also requires a `Sensibull:` line in product questions (memory sensibull-first updated) | - | - |
| R-22 | 11 (Tier A) | paper_store.py:85: an `open`/`add` order on the opposite side is stored with that label although it reduces or flips the position (long 75 then open SELL 100 -> net -25, booked -500, label "open") | money correct (engine averages the Zerodha way); orderbook label wrong. Deferred (C4): the UI never sends it; refuse at the store in a later item | - | - |
| R-23 | 11 (Tier A) | an expiry whose close cannot be read before 18:00 settles only next trading day 15:45; meanwhile a conditional exit on that strategy cannot fire (expired leg has no live price) | deferred; affects calendars only | - | - |
| R-24 | 11 (Tier A) | a tick counts as live by feed health only, never by its time: at 09:15, before an option's first trade, a stale last price could fire a leg stop set after hours (unverified) | LIVE check in GC-TPL (09:15-09:20 watch a leg stop armed after hours) | - | - |
| R-25 | 11 (Tier A) | settle price = Kite day-candle close at 15:45; equal to the official close proven for SENSEX only (F-72), not NIFTY | owed: NIFTY 3 Nov expiry proof (already listed) | - | - |
| R-26 | 11 (Tier B) | MAJOR candidate: a live push cancels the in-flight target request (StrategyBuilderPage.vue onPush -> guard.cancel('outcome')) and carries no target figures, so in market hours the target figures may never arrive | live only: GC-TPL L2 moves the target slider during live pushes and records whether figures arrive; if not, fix in a sub-worktree | - | - |
| R-27 | 11 (Tier B) | for 250 ms after a slider move the old pick's figures stay beside the new slider position (the text names its own level, so no wrong number is labelled new) | deferred | - | - |
| R-28 | 11 (Tier B) | targetPick not reset on an underlying / expiry swap | fix1 item 4a | - | - |
| R-29 | 11 (Tier B) | compact Paper list says "Turn on Show closed positions" while the switch is hidden there | fix1 item 4b | - | - |
| R-30 | 11 (Tier B) | PaperConfirmDialog: price not coerced with String() (a numeric price would throw on Confirm); not reachable today (prices arrive as text) | deferred | - | - |
| R-31 | 13 | two builders added reply models without registering them in the response-door sweep (R-19b six models, R-19a TargetBadgeOut); the sweep test caught both at merge | registered (a00e7442, 97532f26); the fix1 brief now names the sweep test | a00e7442, 97532f26 | test_response_door 214 passed |
| R-32 | 13 | Target block prints "−₹203.45" right above the approved note "includes +Rs 962.00 booked": two currency marks in one block (the engine exact-money format vs the REQ-089 note shape) | app-wide split older than GC-TP (engine display ₹, approved notes Rs); deferred, one owner wording call for the whole app | - | - |
| R-33 | 13 | breakevens at target print "22578.12  22864.84" without Indian grouping, while every other index level prints grouped ("22,618") | deferred (cosmetic, step 6b text) | - | - |
| R-34 | 13 | in Drafts Mode the Breakeven line lost its move-from-spot % ("22,632 (−1.3%)" -> "22,618") after a4773085, because the book reply has no breakevens_display | deferred: the book route could send the same display shape | - | - |
| R-35 | 13 | after hours the target what-if of strategies 48 / 56 answers "Estimated Now needs live prices" (their contracts have no last close today) while 63 / 65 / 66 work | a data-availability class, not a code defect seen tonight; GC-TPL sees them live | - | - |
| R-36 | session 2 | three times today a time was written into a file from memory, not the clock ("~17:10" at 17:05, "~17:00" at 16:58), despite the memory note | each corrected the same turn; a note did not stop it: needs a mechanism (a hook flagging a written HH:MM differing from the clock by > 2 min) - owed, not built tonight | - | - |
| R-10 | 7 | live 13:40: the Stops panel shows no per-leg Stop rows (only Conditional exit), on every paper strategy | RCA: `PaperStrategies.stopLegs` keeps legs with a `contractId`, but the cards are built from `GET /tracking`, whose legs carry no `contract_id`; the 7b vitest stubbed legs WITH `contract_id`, a shape the server never sends. Class: frontend fixtures not shaped like the real reply. Fix in step 4 (Paper tab reads `GET /paper/strategies`, which has contract_id) with a test fed the REAL reply (`tests/fixtures/paper/strategy-63-roll.json`); the trigger list should also say above / below | step 4b 090deba7 | LIVE ~15:51: "Stop on a leg" rows present on the Paper card - FIXED |

## Parked

| Row / item | Why (evidence) | What is left |
|---|---|---|
