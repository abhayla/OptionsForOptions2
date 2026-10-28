# Goal contract GC-BP: builder -> paper trade -> Positions, tested as a user until clean (2026-10-28)

Written 2026-10-28 ~10:15 IST in a planning-only session. Branch `build/gcbm-must-have`, worktree
`D:\Abhay\Ventures\OptionsForOptions2-gcbm` (local only; head 303dc8c3 = GC-BM's 86 commits + ADR-201). GC-BM is
DONE and on hold before its push (`docs/process/session-handover-2026-10-28-gcbm.md`). GC-BP builds on top of it.
No push, PR or CI in this goal: a later "ready to land" goal the owner starts carries GC-BM + GC-BP in ONE push and ONE PR.

## Owner decisions behind this contract (2026-10-28, question tool and chat; recorded as ADR-201)

1. "Place" a strategy = **paper tracking** ("Start tracking" at the live price, REQ-109). No order goes to Zerodha
   (ADR-165 (1)). Owner: "paper trading, no, not the actual orders, but it should be visible on [the] position screen".
2. Positions screen = **two tabs: "Positions" (real Zerodha, unchanged) and "Paper"**. Each paper strategy is a group
   showing its legs, entry price, LTP, P&L (total / booked / unbooked), Open in Builder and an exit action, labelled
   as not a real trade (Sensibull Draft Portfolio content, study 090-092). Paper and real totals are never added
   together. This is a SPEC CHANGE to ADR-138 (2) / W-111. Sensibull keeps paper trades on a separate page.
3. Scope = **functional only**. Everything on the flow must WORK. Visual differences from Sensibull go into a list
   for the owner and are not fixed (same rule as GC-BM).
4. Process (owner, verbatim): "do not create PRs, do not push, do not start any CI, local or this thing, until all
   those things are complete ... before making any changes, you read that code and do not duplicate things ... once
   everything starts working, only then we will create a PR and push and run the CI."

Spec basis: ADR-201 (this round), ADR-165 (no orders; Start tracking; (8) every item names its Sensibull screens),
REQ-109 AC-1..AC-8 (paper tracking; AC-2 paper P&L from the one engine and never mixed with real; AC-4 paper exit,
partial by leg; AC-5 paused when prices are not live), ADR-008 (one engine, exact Decimal), ADR-102 (paper never
summed with real), ADR-138 (2) + W-111 + REQ-044 AC-3 (today's Positions page), ADR-200 (closing-price walks),
ADR-152 (Sensibull default). Sensibull: private study `D:\Abhay\Ventures\competitors\sensibull\2026-10-21`
(`catalogue-raw.md` 010-039, 050-053 Positions, 090-092 Draft Portfolios, 100-134, 209-234; INDEX.md). Never copy
its images into this repo.

**Core:** a strategy built in the live builder can be saved, paper-tracked, and its paper P&L read back moving with
live prices.
**Proof:** step 1. On the live app in market hours, BEFORE any code: build a NIFTY Bull Call Spread, Save, press
Start tracking, read the TrackingPanel's "Paper P&L (not real)" figure at two times at least 2 minutes apart, and
read `GET /api/strategies/{id}/tracking` (entry per leg, price_state, paper P&L). If this fails, fixing it IS the
work; nothing else starts (Core-first R3).

## What already exists (read before writing ANY code; do not rebuild)

Measured 2026-10-28 on 303dc8c3:
- `backend/ofo_app/routes/tracking.py` (W-122): `POST /strategies/{id}/tracking` (start) and `GET` (view: stored
  entry, current prices, paper P&L from the engine or the paused state, one detection). Domain: `backend/ofo/tracking/paper.py`.
- Frontend: `frontend/src/lib/tracking.js` (`START_TRACKING_LABEL`), `components/strategy/TrackingPanel.vue`, the
  builder's "..." menu item Start tracking (`StrategyBuilderPage.vue` ~l.422), the builder's "Tracked" tab
  (`SaveDraftBar.vue` l.55/l.322, an empty state that points to My Strategies), and `MyStrategiesPage.vue`'s tracked
  text (`trackedText` in `lib/saveDraft.js`).
- `frontend/src/pages/PositionsPage.vue` (W-111): reads ONLY `GET /api/positions` (Zerodha), quantities grouped by
  strategy, no P&L. No Paper tab.
- NOT built: paper exit (REQ-109 AC-4: no exit route in tracking.py), a list of all of a user's paper strategies,
  and the Paper tab.
- Step 0 re-checks this list with `git log origin/main..HEAD --stat` and grep. Any extra overlap goes on the list
  before code is written.

**Step 0 result (2026-10-28 10:15 IST, head 1422770a, 88 commits ahead of origin/main):** the list above holds. No
GC-BM commit touches tracking or positions code (the only matches in `git log origin/main..HEAD --stat` are this
contract and ADR-201). No exit code anywhere in `ofo/tracking/paper.py` or `routes/tracking.py`. Extra reuse points:
`ofo_app/tracking_store.py` has `start`, `load` and `tracked_ids(conn, strategy_ids)` (step 4 builds on these, no new
store); `routes/strategies.py` already calls the store (its tracked flag). Grep hits in `AppHeader.vue`
(`tracking-wide` CSS) and `legPicker.js` (a comment) are not tracking code. Deferred issues #596-#602 are all open and
none touches tracking, paper or Positions.

## No-CI rules (owner instruction 4; same as GC-BM)

- **No push, no PR, no draft PR, no GitHub Actions in this goal at all** (owner, 2026-10-28: market hours are for building and live testing).
- **No `ci_local.py`, `prepush.py`, `land.py` or `merge.py`** per item. Builders run only the tests of the files they
  touch, plus `ruff` on touched Python and `npx eslint` on touched frontend files. Long output goes to a log file;
  read only the tail. After each local merge, run the FULL frontend vitest once (memory: targeted runs missed 3 stale
  assertions in GC-BM). It needs `FULL_SUITE_BUDGET=N` for the session hook.
- DB tests: the main checkout's `scripts/orchestrator/db_run_fresh.py`, one file at a time (ofo_test is dirty; the
  VPS serves IPODhan prod).
- All work is stacked commits on `build/gcbm-must-have`. Builder sub-branches (`build/gcbp-<item>`, worktrees via
  `wt-new.ps1`, 48h TTL) merge into it locally.
- No closing keywords ("Fixes #N") in commit subjects.

## Running the app (from the GC-BM launch note; the wrong line cost two restarts)

- API: `LIVE_MARKET=1 APP_ENV=development python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/dev_run.py
  D:/Abhay/Ventures/OptionsForOptions2-gcbm python -m uvicorn --factory ofo_app.main:create_app --app-dir backend
  --loop ofo_app.event_loop:selector_loop --host 127.0.0.1 --port 8765` (ofo_dev).
- Frontend: in `frontend/`, `OFO_API_TARGET=http://127.0.0.1:8765 npx vite --port 5174 --strictPort`.
- Before starting, check the ports are free. Record each PID from `netstat -ano` and stop ONLY those, with a literal
  `taskkill //PID <digits> //T //F`. Git Bash `$!` is not the Windows PID (memory e2e-orphan-servers).
- Kite token: the owner's cached token. If it has expired (06:00), the one owner step is a login in a PRIVATE window
  at http://127.0.0.1:8765/broker/zerodha/login.
- Paper P&L needs LIVE prices (REQ-109 AC-5/AC-6 pause it otherwise). Steps 1, 2, 6 and 8 run in market hours,
  09:15-15:30 IST. Code steps can run any time.
- Safety: never press Execute or any order button, never call an order endpoint, never click inside a broker order
  panel (memories real-order-guardrails, no-clicks-inside-order-panels). Browser: Playwright MCP at 1536 x 864.

## Items

| Step | Item | What | Tier | Proof (read back on the live screen) | Status |
|---|---|---|---|---|---|
| 0 | read first | Read `git log origin/main..HEAD`, the GC-BM contract + 10-28 handover, deferred issues #596-#602, and the "already exists" list above; write the overlap list here | C | List written in this file | DONE 10:15 (step 0 result block) |
| 1 | core proof | The Core/Proof above, before any code | C | Two paper P&L readings with times + the GET reply | DONE 10:25 with F-1: strategy 46 "GCBP P1 BCS" (NIFTY 3 Nov 22550/22750 CE) saved + tracked 10:18:19 IST, entry 187.35 / 107.30. Server: 3.25 (10:18:27) -> -130.00 (10:20:31), state LIVE, both legs live; hand check 65x(186.45-187.35)+65x(107.30-106.35)=3.25. Screen did NOT move (F-1); after the fix: -104.00 (10:24:34) -> -84.50 (10:24:43) |
| 2 | walk 1 | The P-list below on the live app, before code changes (except a step-1 fix). Every functional failure becomes an F-row; visual differences go to the visual list | C | P-list filled in, screenshot names | DONE 10:16-10:52: 'Walk 1 results' block; F-1, F-2, F-3 found; O-1, O-2 observed (not reproduced in walk 2) |
| 3 | fix F-rows | Each F-row: RCA, Class, failing test first, class-level fix, re-test on the live app (defect-fix contract E5). At most 2 rounds per row, then park (`parked` issue) | B (A if it touches engine maths, order path or tracking writes) | Each row's re-test line | DONE: F-1 ece1be8f, F-2 e810a5f2, F-3 e9565c47; each re-tested live (F-rows table); 1 round each |
| 4 | paper list API | `GET /api/tracking` (name per house style): every paper-tracked strategy of the signed-in user (REQ-125: never another user's), each with legs, entry, LTP, paper P&L total / booked / unbooked from the ONE engine (reuse `ofo.tracking.paper` + the W-122 view code, do not copy it), price state and paused reason. Openapi regenerated. Answer states: none tracked, all live, some paused, no Zerodha session, expired leg (AC-7), read failure | B; Opus review if engine code changes | Route tests red first (db_run_fresh); live read with 3 tracked strategies | DONE (built; review owed at step 8) 1c9094a7: GET /tracking. 11:17 live: 8 strategies (46-53) in 2.02 s, all LIVE, total/booked/unbooked each. Also batched tracked_contracts.resolve for every caller incl. Execute (same answers, read by me; Tier A review must cover it). Mutants 5 of 5 killed (builder: booked-with-entry-price; my re-run 11:21-11:24 with a fixed runner that counts only a failed test: user filter, exit with a leg not live, double exit, one snapshot per strategy; worktree clean after) |
| 5 | paper exit | REQ-109 AC-4: "Paper exit" of a whole strategy and of one leg records the exit price at that moment, freezes that part's P&L into booked, appended to the timeline labelled paper; refused when prices are not live (AC-5 wording). Never reaches Execute (AC-3 test) | A (writes money records) | Tests red first; live: exit one leg of a condor, booked moves and unbooked drops by that leg | DONE live (review owed) 1c9094a7 + migration 0027 on ofo_dev (11:15): 11:20:36 exit leg 2 (SELL 22600 CE) of 48 at 190.05: booked -1,504.75 = (166.90-190.05)x65; unbooked 84.50 -> 1,644.50 (3 open legs, hand-checked); total 139.75. 11:20:52 exit all of 50 at 217.70: EXITED, booked 2,236.00 = (217.70-183.30)x65. Second exit of 48 leg 2 refused (STRATEGY_VALIDATION_434), nothing changed |
| 6 | Paper tab | ADR-201 (2): Positions page tabs "Positions" / "Paper"; Paper lists each strategy as a group (legs, entry, LTP, P&L total / booked / unbooked, price state, Open in Builder, Paper exit with a confirm), the banner "Paper trades - not real money", and its own totals, never added to real. Both Positions menu items show the tabs. The builder's "Tracked" tab lists the same strategies (one shared component, no copy). Sensibull: 090-092 for the group content, 050-053 for the tab look | B | vitest red first; live: 3+ paper strategies visible with moving P&L | DONE (review owed at step 8) 08ddc6e2, merged 711cc107: Positions tabs + Paper list + builder Tracked tab, one component, one refresh composable; live in walk 2 |
| 7 | re-walk | Full P-list again on the final code; new F-rows go to step 3; repeat until a full pass is clean | C | Clean P-list with times | DONE 11:26-11:37: 'Walk 2 results' block; clean on the final code, no new F-rows |
| 8 | review, NO land | One combined code review of this contract's diff: fresh Opus for steps 4-5 (Tier A), Sonnet for the rest, at most 2 rounds; accepted findings fixed and re-walked. NOT in this goal (owner, 2026-10-28: no PR and no CI "until certain features are fully complete and we are ready to create a PR"): openapi drift, Playwright, ruff_ratchet, coverage, `prepush.py`, push, PR, CI, merge. Those run once, in a later "ready to land" goal the owner starts. List them in the handover as OWED | A | Review verdicts; commits on the local branch; `git rev-parse @{u}` still has no upstream | Not started |
| 9 | handover | Visual-differences list, gap-list re-verdicts (G-029, G-030 and touched rows), a list of deferred issues WRITTEN IN THE HANDOVER (not filed on GitHub until the land goal), DONE / PENDING / BLOCKED / PARKED / OWED-AT-LAND / NEXT block (NEXT = GC-B2 per the owner order in goal-contracts-builder-phase-2026-10-27.md "Re-ordered by the owner, 2026-10-28"), committed on the local branch. Worktrees: builder sub-worktrees merged locally are removed with `wt-rm.ps1 -Discard`-free removal only after their commits are on `build/gcbm-must-have`; the gcbm worktree stays | C | Handover file committed locally | Not started |

## The P-list (a user's walk: build, paper-trade, follow)

At least 8 strategies, both indices, each built as a user would, then Saved and paper-tracked. Compare each screen
with the Sensibull screen named. Write pass / FAIL (functional) / visual-only.

| P | Strategy | How it is built | Then | Sensibull |
|---|---|---|---|---|
| P-1 | NIFTY Bull Call Spread | Ready-made card | Save, Start tracking | S-011, 115-119 |
| P-2 | NIFTY Short Straddle | Quick pick | Save, Start tracking | S-037 |
| P-3 | NIFTY Short Iron Condor | Ready-made card | Save, Start tracking; later Paper exit ONE leg (step 5) | S-011 |
| P-4 | NIFTY custom 4 legs | Strike drawer: 2 B + 2 S, lots 2 on one leg | Save, Start tracking | S-032 |
| P-5 | NIFTY Long Call (1 leg) | Drawer, one pick | Save, Start tracking; later Paper exit all | S-032 |
| P-6 | NIFTY Calendar (mixed expiry) | Drawer: sell near, buy next expiry | Save, Start tracking | S-104 |
| P-7 | SENSEX Short Strangle | Quick pick on SENSEX | Save, Start tracking | S-038 |
| P-8 | SENSEX Bear Put Spread | Ready-made on SENSEX | Save, Start tracking | S-011 |

For every P-row check: legs load priced; summary numbers present (max profit / loss, breakevens, margin); chart and
P&L table agree; Save reads back; Start tracking stores an entry per leg at the shown price; the Paper tab
(after step 6) shows the strategy with P&L that moves between two readings ~2 minutes apart; Open in Builder reopens
the same legs; the browser console has no uncaught error. Plus these cross-checks:
- PX-1: Positions tab (real) still loads and shows no paper strategy; Paper totals never appear in it.
- PX-2: a paper strategy cannot reach Execute (no Execute link from the Paper tab; REQ-109 AC-3).
- PX-3: after a Paper exit, that strategy's P&L stays frozen across two readings.
- PX-4: reload the page; every paper strategy and its entry prices come back the same.

## Walk 1 results (step 2, 2026-10-28 10:16-10:52 IST, live market, owner's Chrome)

Every P-row built as a user would, Saved, Start tracking pressed; paper P&L hand-checked against entry and LTP per leg.
The Paper tab does not exist yet (step 6), so its checks wait for walk 2.

| P | Strategy id | Built | Numbers checked by hand | Tracked (first reading) | Result |
|---|---|---|---|---|---|
| P-1 | 46 | Ready-made Bull Call Spread 22550/22750 CE 3 Nov | breakeven 22,631.9 | 3.25 (10:18:27) | pass after F-1 |
| P-2 | 47 | Quick pick Sell Straddle 22500 | breakevens 22,088.55 / 22,911.45 | -42.25 (10:31:46) | pass; O-1 on the first click |
| P-3 | 48 | Ready-made Short Iron Condor 22300/22400 PE, 22600/22700 CE | credit 77.20; BE 22,322.8 / 22,677.2; max loss 1,756.75 | -55.25 | pass |
| P-4 | 49 | Drawer 2 B + 2 S, 22750 CE at 2 lots | debit 36.95; BE 22,886.95; max loss 9,186.48 | +26.00; reload +315.25 (2-lot leg qty 130) | pass |
| P-5 | 50 | Drawer Buy 22550 CE | BE 22,733.65 | +16.25 | pass |
| P-6 | 51 | Drawer calendar Sell 3 Nov / Buy 9 Nov 22550 CE | max P/L 'can't be estimated' (ADR-143 (1), REQ-148 AC-4/6) | -87.75 | pass after F-2 (two drawer passes worked before it) |
| P-7 | 52 | SENSEX quick pick Sell Strangle 200 pts: 72600 PE / 73000 CE 29 Oct | BE 71,981.4 / 73,618.6 | -15.00 | pass |
| P-8 | 53 | SENSEX ready-made Bear Put Spread 72800/72400 PE | debit 175.30; BE 72,624.7 | +45.00 | pass |
| PX-1 | - | /positions/current-positions | - | - | FAIL: F-3 |
| PX-4 | 49, 51 | reload ?strategy= | same legs, lots, planned entries, tracked entries | - | pass |

Observations, not reproduced (re-checked in walk 2; an F-row if seen again): O-1 the first Straddle click (P-2) showed 'could not get an answer' and the API logged no quick-pick request; the second click worked. Likely the same 10 s client timeout as F-3 while the 145-query attribution or a cold start held the server (unproven). O-2 the browser saw 503 on one POST /strategies/outcome that the API logged as 200 (unproven); outcome requests ending with status 0 are the page cancelling a superseded request.

## Walk 2 results (step 7, 2026-10-28 11:26-11:37 IST, final code 711cc107, live market, owner's Chrome)

| Check | Result | Evidence |
|---|---|---|
| Paper tab (step 6) | pass | /positions/current-positions?tab=paper: tabs Positions / Paper, banner 'Paper trades - not real money', 8 groups (46-53) with legs, expiry, qty, entry, LTP, total / booked / unbooked; P-1 hand-checked +1,176.50 |
| P-list figures move | pass | 11:26:20 -> 11:28:21: 46 +1,121.25 -> +1,069.25; 47 +851.50 -> +984.75; 49 +1,589.25 -> +1,407.25; 51 +152.75 -> +211.25; 52 +807.00 -> +964.00 |
| PX-1 | pass (failed in walk 1: F-3) | Positions tab: 'Read from Zerodha at 11:25:47 IST', no positions, no paper figure |
| PX-2 | pass | 0 links or buttons to Execute on the Paper tab |
| PX-3 | pass | 50 (exited 11:20:52) +2,236.00 at 11:20, 11:26:20 and 11:28:21; 53 (exited by the screen 11:27:15) -1,098.00 at 11:27:15 and 11:28:21 |
| PX-4 | pass | reload: 8 groups, 19 legs, entry prices identical before and after |
| Exit all by the screen (P-8, 53) | pass | inline confirm 'Paper exit - no order is sent. Exit Buy 72800 PE, Sell 72400 PE ...'; EXITED, booked -1,098.00 = 20x(245.10-404.70)+20x(231.70-127.00) |
| Exit one leg by the screen (W2 P-3, 56) | pass | Sell 22700 CE exited at 147.45: booked +230.75 = (151.00-147.45)x65; unbooked -250.25 (3 open legs hand-checked); total -19.50 |
| Open in Builder (49) | pass | reopened ?strategy=49 with the 4 legs incl. 22750 CE 2 lots |
| Builder Tracked tab | pass | lists the same 8 strategies with live totals and the banner (old 'appear in My Strategies' empty state gone) |
| Second Positions route | pass | /positions/strategy-linked-positions?tab=paper shows the tabs and 16 groups |
| P-1..P-8 rebuilt on final code | pass | W2 strategies 54-61: ready-made BCS 22600/22800 (BE 22,687.8); straddle 22600 (O-1 not seen); condor 22400/22500/22700/22800 (BE 22,424.65 / 22,775.35); drawer custom 4 legs (57; my script set a hidden Lots box, so all legs 1 lot - the 2-lot path re-proven separately: visible Lots box -> 22850 CE '2 lot'); drawer long call 22650 (BE 22,825); calendar in ONE drawer pass '2 selected' (F-2 holds); SENSEX strangle 72800/73200 (BE 72,256.75 / 73,743.25); SENSEX bear put 73000/72600 (BE 72,844.35); each tracked |
| W2 figures move | pass | 11:34:42 -> 11:37:02: 54 +29.25 -> +152.75; 55 +97.50 -> -42.25; 57 -13.00 -> +52.00; 58 -256.75 -> +143.00; 59 +52.00 -> +169.00; 60 -22.00 -> -132.00; 61 -21.00 -> -162.00; 50 and 53 unchanged (exited) |
| O-1 / O-2 | not seen in 8 more builds | request watch on every build: only the expected not-yet-tracked 404 and cancelled (status 0) superseded outcome requests |
| Full frontend vitest on 711cc107 | pass | 78 files, 1260 tests passed (2 workers) |

No new functional failure in walk 2, so no new F-rows: the P-list is clean on the final code.

## Found in the walks (steps 2 and 7)

| F | P-step | What failed (seen) | Class / RCA | Fix commit | Re-test |
|---|---|---|---|---|---|
| F-1 | step 1 (P-1) | TrackingPanel showed -120.25 at 10:21:57 IST while GET answered -188.50: the paper figure and leg LTPs never changed after the page opened | RCA: `TrackingPanel.vue` read GET /tracking once, on strategy-id change, with no re-read. Class: every screen showing a paper P&L figure (today 1: TrackingPanel; step 6's Paper tab and the Tracked tab must reuse the same refresh). Fix: re-read every `TRACKING_REFRESH_MS` = 5000 (the strike picker's rate; spec silent, searched refresh/seconds/tick in REQ-109, REQ-033) while tracked, one read at a time, late answers for another strategy dropped, a failed read shows no figure. 7 tests red first (5 failed on old code), 4 mutants each killed. Detection: the P-list now reads the screen twice, not only the API | see git log (GC-BP F-1) | 10:24:34 -104.00 -> 10:24:43 -84.50 on screen, owner's Chrome |
| F-2 | P-6 | Drawer: Sell 3 Nov 22550 CE, change the drawer expiry to 9 Nov, Buy 22550 CE: footer '1 selected', Done added only the 9 Nov leg; the user's first pick vanished with no message | RCA: `LegPicker.vue` cleared picks on any expiry/width change because Done looked contracts up in the list on screen. Class: every pick made before an expiry or width change (before: lost; after: kept); an underlying change still clears. Fix: the contract is stored at the pick (`pickedContracts`). 5 tests, 3 red first. Detection: the leg-picker tests now pin cross-expiry Done | e810a5f2 | 10:52 live: '1 selected' -> '2 selected', Done added 3 Nov 22550 CE (199.65) + 9 Nov 22550 CE (289.35) |
| F-3 | PX-1 | Real Positions page /positions/current-positions: 'The page could not get an answer from the server' every time; the same GET by hand: 200 in 14.06 / 15.31 / 18.50 / 13.06 s; the client gives up at 10 s (api.js:46) | RCA (measured): attribute_and_compare makes 145 DB queries for ~47 strategies (StoreReader: plans_for per strategy, ~3 queries each) at 136 ms per round trip over the tunnel = 10.6-12.0 s; Zerodha is cached 45 s and the session dependency answers in 0.74 s. In production (DB on the same host) about 0.2 s, but the count grows with every strategy and breaks every local walk. Class: per-strategy query loops on every attribute_and_compare caller. Fix: `execution_plan_store.plans_for_strategies` (4 queries for any count; attribution refuses a malformed batch). Probe: 145 queries 11.50 s -> 5 queries 0.41-0.82 s; real-data equivalence equal=True (47 strategies, 5 plans - weak: few plans); 3 mutants killed. Detection: query-count test (2 vs 6 strategies) | e9565c47 (merge df122aeb) | 11:17 live: /positions 200 in 1.34 s and 1.26 s (was 13-18 s) |
| F-4 | step 8 review (Sonnet, REVISE) | Builder Tracked tab: 'Open in Builder' on 49 while the builder shows 54 -> URL ?strategy=49 but the screen keeps 54's legs (live 11:44 IST); a reload then opens 49 | RCA: StrategyBuilderPage opens the URL only on mount; the router-view is unkeyed, so a same-route query change never re-opens. Class: every in-page link/push to a builder URL (?strategy=, ?draft=, ?template=) while the builder is mounted. Walk 2 missed it: Open in Builder was tested only from the Positions page (a fresh mount). Fix (round 1, Sonnet builder): the builder follows its own URL; + review minors R1-2 (TrackingPanel stale load), R1-4 (stale confirm/error), R1-5 (per-leg Exit names, tab aria); tests red first (draft-link 3 failed -> 17 passed; tracking 1 failed -> 19; paper 5 failed -> 32). Unsaved edits on an in-page open are replaced without a prompt, as the Saved tab's Open already does (owner list). ?template= links not covered (deferred) | 1c0abf1f (merge e8724760) | 11:5x live: builder on 54 -> Tracked tab Open in Builder 49 -> screen 'GCBP P4 custom', 4 legs incl. 22750 CE 2 lots; Save on 49: PUT 200 and no re-open request, legs unchanged |

## Visual differences for the owner (not fixed here)

| P-step | Ours | Sensibull (screen) | Gap row |
|---|---|---|---|
| P-1 | Save's name field has no accessible label (screen readers and test tools miss it) | named dialog | - |
| P-1 | Paper panel: Entry and LTP columns run together ('187.35182.8') | spaced columns (090-092) | - |
| P-1..P-8 | Summary says 'Price data: estimated from spot' in market hours: the builder reads only its legs, so IV/Greeks use the spot fallback forward (ADR-061, labelled as required) | ATM IV from the full chain | accuracy note |
| P-4 | Drawer: Call Delta and Call LTP digits run together ('0.8389564.35') | separate cells | G-075 (re-check) |
| P-4 | '2 lot' (should be '2 lots'); drawer Lots select has no accessible label | 'Lots 2' | - |
| P-4, P-6 | Paper panel shows no quantity and no expiry per leg (P-6's two legs both read '22550.00 CE') | qty + expiry per leg (090-092) | step 6 shows both |
| P-6 | Calendar max profit / loss / breakeven 'can't be estimated' (spec: ADR-143 (1)) | model estimate, e.g. max loss -7,730 (108) | spec choice |
| P-8 | '(1 days)' | '1 day' | - |
| PX-1 | Top 'Positions' opens a placeholder hub with 4 links | lands on positions | - |

## Rules for the run

- Run to the end: stop only for the owner's Kite login, an irreversible act, or a true product fork (owner present:
  one question per call with a `Business call:` line and Spec basis; owner away: write it to
  `docs/process/owner-questions-2026-10-28.md` and continue).
- Technical calls are the session's own; complex ones get an independent reviewer first.
- Every Agent brief carries `Core:` / `Proof:`, `Budget:`, `Sensibull:`, `Report: evidence-table`, the
  `.claude/kit/builder-brief.md` standing items and an explicit `model`.
- Evidence table at every done claim: a command run that turn plus its result line. A worker's report is a claim.
