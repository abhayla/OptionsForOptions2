# Goal contract GC-LIVE: every live-market proof owed, Friday 30 Oct 2026 (market hours)

Written 2026-10-30 10:18 IST from the owner-approved plan (`C:\Users\itsab\.claude\plans\read-the-goal-contracts-reflective-cook.md`).
Owner scope pick, 30 Oct ~09:45: "All live items". It replaces GC-TPL (`goal-contract-GC-TPL-2026-10-30.md`, issue #606),
whose run tree and branch (`build/gctp`) were removed at the 29 Oct land. Its items are carried in full below. The owner
starts this contract with /goal in a FRESH session.

Role for the run: live-market QA lead plus options-trading expert. Drive the owner's visible Chrome, run the checker,
and judge every difference against the spec and Sensibull. Fixes go to builders (Sonnet by default; Opus only with a
`Why Opus:` line).

## State at writing (10:17 IST, read from GitHub)

- main = db8cdf91 (PR #609 merged 09:51: after-hours prices on every screen, ADR-212). CI, App tests and coverage on
  db8cdf91 all passed.
- Draft PR #611 (`ui/sensibull-layout-2026-10-30`, head f9619949, base main): Sensibull layout under our brand (ADR-193).
  It replaces #610 (auto-closed). Main is NOT merged into it yet (merge-base 1990d414). Chrome-checked so far: Home,
  Positions, Option Chain, My Strategies, Broker settings; the other restyled screens have not been opened.
- No server listens on 8765 / 5174. The session that landed #609 (`optionsforoptions2-fe`) has finished.

## Where the run works

- Run tree: create with `~/.claude/tools/wt-new.ps1 -Repo D:\Abhay\Ventures\OptionsForOptions2 -Name live1030
  -Branch live/2026-10-30 -Base origin/ui/sensibull-layout-2026-10-30 -Purpose "GC-LIVE run tree" -TtlHours 48`, then
  `git merge --no-edit origin/main` in it. Record both shas (#611 head, main head) in L0. Run `wt-link-modules.ps1` for
  the tree if `frontend/node_modules` is missing (otherwise `npm ci` in `frontend`, log to a file).
- Branch `live/2026-10-30` is LOCAL only, with no upstream.
- Lock: `.run-active.lock` with this session's id at the run-tree root; removed on any stop.
- Database: ofo_dev (never ofo_test for a live run).

## Rules for the run

- **No push, PR, draft PR, GitHub Actions, `ci_local.py`, `prepush.py`, `land.py` or `merge.py` before 15:30.** Local
  commits (`GC-LIVE: ...`) at least every 30 minutes; nothing uncommitted at the end of a turn. Never push to #611's
  branch from this run.
- **Orders never reach Zerodha.** Paper only (ADR-165, ADR-201, ADR-207). Never press Execute, never click inside any
  order panel, never sell holdings, no click after a scroll in the same batch (memories real-order-guardrails,
  no-clicks-inside-order-panels).
- Browser: the owner's VISIBLE Chrome via Claude-in-Chrome, 1536 px wide, one tab per task, closed when done; never
  headless. If the extension is not connected, stop and tell the owner.
- Sensibull first: for any screen question or gap, grep `D:\Abhay\Ventures\competitors\sensibull\2026-10-21` (INDEX.md,
  catalogue-raw.md, bundle-findings.md, screenshots) before deciding or asking. Every owner question has a `Sensibull:`
  line next to `Spec basis:`.
- Technical calls are the session's own. Only business forks (words a user sees, money shown, scope) go to the owner:
  one question per call, with `Business call:`, `Spec basis:` and `Sensibull:` lines. Owner away: write the question to
  `docs/process/owner-questions-2026-10-30.md` and continue.
- Every time written into a file is read from the clock (`date`) in the same step.
- Evidence table at every done claim (the command run that turn + its result line). A builder's report is a claim;
  re-run its test or re-read the screen before relaying it.
- A defect follows the defect-fix contract: RCA (one sentence), Class (data filter, size before/after), failing test
  first, class-level fix, ONE live proof, detection change or `No detection change: <reason>`. It is built in a
  sub-worktree branched from `live/2026-10-30`, merged back locally, and re-proven live. At most 2 rounds, then PARKED.
  Each brief carries `Budget:`, `Core:`/`Proof:`, `Report: evidence-table` and the `.claude/kit/builder-brief.md`
  standing items.
- A defect outside this contract's items becomes a `deferred` issue (`gh_issue.py app ... --stage`), not a fix.
- 15:30 IST: anything not proven is PARKED with what is left. The session does not wait for the next day.

## Running the app (from the run tree)

Check first: `Get-NetTCPConnection -State Listen -LocalPort 8765,5174`; refuse busy ports; stop only PIDs this run
started (by port owner, never `$!`).
- API: `APP_ENV=development LIVE_MARKET=1 python scripts/orchestrator/dev_run.py . python -m uvicorn --factory
  ofo_app.main:create_app --app-dir backend --loop ofo_app.event_loop:selector_loop --host 127.0.0.1 --port 8765`
  (output to `D:\Abhay\scratch\gclive\api.log`).
- Vite: from `frontend`, `OFO_API_TARGET=http://127.0.0.1:8765 npx vite --port 5174 --strictPort`.
- Instrument list: if the chain or the builder shows no strikes, run `python scripts/orchestrator/dev_run.py . python -m
  ofo_app.catalogue_load` (#608: a restart before 08:30 empties it).
- Kite: the token cached this morning should still be valid. If the broker status route says no session, ask the owner
  to log in once in a PRIVATE window at http://127.0.0.1:8765/broker/zerodha/login.

## Items (in this order)

| Step | What | Proof | Status |
|---|---|---|---|
| L0 | Preflight: run tree created and main merged in (record both shas); ports free; API + Vite up (PIDs); Kite session valid via the app's broker status route (no order door); instrument count > 0 for NIFTY and SENSEX; lock written | status lines with times, shas, PIDs, counts | DONE 10:26: #611 head f9619949, main db8cdf91, merge 8c23020d (1 conflict MyStrategiesPage.vue: #611 table kept, main's stack-below-lg carried); ports free 10:24; API PID 13428 :8765, Vite PID 10744 :5174; /api/broker/status account_connection connected; NIFTY 3 Nov 208 contracts, SENSEX 5 Nov 348; lock 10:25:09 (API runs via the main checkout's dev_run.py: the run tree has no .env) |
| L1 | bseindia.com (logged out): SENSEX "Previous Close" must read **74,151.04**, the value the 29 Oct paper settlement used for strategies 52, 60, 61. If it differs: stop the steps that depend on it, record both values, and build a correcting `settle` order path in a sub-worktree (orders are append-only; never edit rows) | screenshot `D:\Abhay\scratch\gclive\L1-bse.png`, value + time | DONE 10:26: bseindia.com/sensex/code/16 (logged out) Previous Close 74,151.04 = settlement value; screenshot D:\Abhay\scratch\gclive\L1-bse.jpg (JPEG, the capture tool's format) |
| L2 | Live-screen sweep (main's ADR-212 code + #611's layout). In market hours every screen must show LIVE prices and live labels (REQ-105 AC-3 / AC-4: "Delayed 1 min - as of <time>", "Prices not updating - as of <time>"), with no "Market closed" banner and no last-close figure. Screens: Home, Positions (Paper tab + current), Option Chain, Index view, Market context, builder (curves, payoff table, target block), strike drawer, Live Strategies, My Strategies, Create Strategy (guided), Alerts, Billing, System health, Learn, Broker settings, one placeholder page. For each #611 screen not yet opened, compare its layout with the Sensibull screen the PR cites (001 Home, 050/090 Positions + Live, 060 Chain, 117 My Strategies, 167/170/171/172 settings, health, empty states) | one line per screen: time, one figure seen to change between two looks, label text; differences triaged as defect / look choice / deferred | DONE 10:35 (sweep lines below; 2 defects F-1, F-2) |
| L3a | REQ-109 AC-5: pause a paper/tracked strategy in market hours; the pause text must say "as of <time>". #608 says the server sends no time. If confirmed, fix it as a defect (server sends the time; the screen prints it) | text seen before / after; route test + vitest red then green | DONE 10:56: before 10:48 "Paper P&L paused - prices not live" (no time; books 65/59/51 paused live, see F-3); fix 274235f7 + a8c76b81 (server `as_of` per book + `totals_as_of` from the engine's one `paused_as_of` rule; screen prints it on Total, Unbooked, Decay, Greeks); route test red 3 failed -> 14 passed (builder), vitest red 3 failed / 2 failed -> 61 passed (session, run tree); after (API PID 4356) 10:56:02 "Paper P&L paused - prices not live, as of 30 Oct 2026, 10:56:01 IST" on every pause line |
| L3b | R-35 (#607 P2-5): open the target what-if of strategies 48 and 56 live. Works live -> record a data-availability finding in `knowledge/findings/` (after hours their contracts have no last close today); still fails live -> a defect, defect-fix contract | one line per strategy; finding file or Found row | DONE 10:51: 48 target 23100 at 10:45:37 -> P&L at target Rs 18,833.75, BE 22,696; 56 target 23100 at 10:51:06 -> Rs 15,689.70, BE 22,727: works live -> finding knowledge/findings/after-hours-what-if-needs-a-close-for-every-leg.json (fd3050f8). Both showed "Stale" + froze: R-26 (F-4) |
| L4 | Expert-trader walk end to end with live prices: build a NIFTY short iron condor, a SENSEX short strangle and a NIFTY calendar; Add to Paper at TYPED prices; watch each on Positions -> Paper (prices moving; Total / Booked / Unbooked / Decay / Charges); in Drafts Mode roll one leg, exit 1 of 2+ lots (partial), add a hedge leg; set a conditional exit 5 points beyond spot on a 1-lot strategy and see it fire once (bell + Alerts page; `stop` orders at the tick LTP), then restart the API and confirm it does not fire again. Live checks in the same walk: **R-26** move the Target slider in the builder during live pushes; the target figures (P&L at target, badge, breakeven at target) must arrive within ~2 s and stay (suspect: `StrategyBuilderPage.vue` onPush -> `guard.cancel('outcome')`). **R-18 / R-19a / R-19b**: move %, days to expiry and the projected badge move with the index; Target sliders sit below the graph; paper cards show Breakeven / Max / Greeks with live prices. **Add Booked P&L** (ADR-209) on strategy 63 shows "includes +Rs 962.00 booked", and switching it off changes the figures by exactly the booked amount | walk lines with times and strategy ids; Sensibull Drafts screens (catalogue 115-119, 090-092; screenshots 115-119, 218-224) named where a difference is judged | Not started |
| L5 | Checker: `python scripts/checks/ui_data_check.py --paper-orders <id>` on 5 strategies (NIFTY + SENSEX; single expiry + calendar; one with a roll, one with a partial exit): every figure matches, 0 mismatches. Target mode (`--target-level` / `--target-at` / `--booked`) on 2 of them. Run once with PYTHONIOENCODING unset (R-1 re-test) | match / mismatch counts per run | Not started |
| L6 | Re-test F-65, F-66, F-67, F-68, F-69, F-70 live, each against its text in `spec/findings.md`; mark each fixed there with the date and proof line, or PARK it with evidence (F-71 stays deferred). Then move `knowledge/findings/paper-plan-diverges-from-position.json` to `guarded`, naming the checker check (`--paper-orders`) and the Drafts Mode diff test, and regenerate the findings index with the repo's regen script | one line per finding; file diff + regen exit 0 | Not started |
| L7 | 15:30 cutoff and handover: PARK what is left; append DONE / PENDING / BLOCKED / PARKED / OWED / NEXT to this file; comment on #606 (close it only if every item is done), #607 (R-35 result), #608 (REQ-109 AC-5 result) and #611 (the L2 layout lines, after 15:30); list the live fixes waiting to land (main-code fixes = their own PR from main; #611-code fixes = into #611's branch; order #611 first, then the fix PR); memory note; lock removed; servers stopped (recorded PIDs only); run tree removed with `wt-rm.ps1` unless fixes wait to land | commit on `live/2026-10-30` (and this file's docs branch) | Not started |

Order rule: fast checks first (L0-L3), so the long walk (L4-L6) runs on code already seen to be sound. If L2 finds a
defect that would corrupt the walk's numbers (a wrong price or label on Positions or the builder), fix it before L4;
any other L2 defect is fixed in parallel by a builder while the walk runs.

## Not in this contract (and why)

- R-24 (a leg stop armed after hours must not fire on yesterday's price before the option's first trade): it must be
  armed BEFORE 09:15. Next chance: Monday 2 Nov, arm by 09:10, watch 09:15-09:20.
- NIFTY 3 Nov expiry settlement proof: after 15:45 on Monday 3 Nov (each settle price = intrinsic from NSE's close).
- Landing #611 (merge main, prepush, push, CI, owner look, `merge.py 611`): not live work.
- #608's layout and display list, #607 Part 2 rows other than R-35, owner question Q1 (`/positions`), the R-36 hook.

## Definition of Done

- [ ] L0 recorded with both shas.
- [ ] L1 recorded (equal, or the correcting path built and proven).
- [ ] L2: every listed screen has a live line; each difference is a fix, a filed issue, or a look choice for the owner.
- [ ] L3a and L3b each have a result (fixed, finding, or PARKED).
- [ ] L4: the walk done; the conditional exit fired once and did not fire again after an API restart; R-26, R-18,
      R-19a, R-19b and Add Booked P&L each have a live line.
- [ ] L5: the checker matches every figure for 5 real strategies, 0 mismatches; target mode on 2.
- [ ] L6: F-65..F-70 each marked fixed with a proof, or PARKED; the class file is `guarded` and the index regenerated.
- [ ] No push before 15:30 (`git rev-parse @{u}` on `live/2026-10-30` reports no upstream).
- [ ] L7 handover committed.

## L2 sweep lines (30 Oct, two looks 6 s apart, script on the page text; no "Market closed" / last-close text on any screen)

- 10:27 Home: NIFTY 22916.70 -> 22916.60, SENSEX 74107.80 -> 74107.86, time stamp ticks; layout = Sensibull 001 shape. Look note: "Already trade with Zerodha? Connect when ready" shows while Zerodha IS connected (look choice for owner).
- 10:28 Positions -> Paper: Total P&L +12,102.40 -> +12,116.90; strategy 67 leg LTP 113.15 -> 110.25. DEFECT F-1: Total Decay "-" with "no implied volatility for this leg" in market hours.
- 10:35 Positions -> Positions: "Read from Zerodha at 30 Oct 2026, 10:34:49 IST. No open Zerodha positions. 16 paper strategies are open - see Paper." (no figures to move).
- 10:28 Strategy-linked positions: Total P&L +11,984.40 -> +12,188.65.
- 10:28 Option Chain: NIFTY 22924.30 -> 22925.20, "as of 10:28:52 AM" + "live"; IV 17.37 shown.
- 10:29 Index view: NIFTY 22924.95 -> 22930.95, "as of 30 Oct 2026, 10:29:01 IST". Sensibull 001 shows change vs previous close; ours does not (look choice).
- 10:29 Market context: NIFTY 22934.10 -> 22930.15, SENSEX 74149.42 -> 74151.62, "Index values are live."
- 10:29 Live Strategies: "Checked at 10:29:25 -> 10:29:29", NIFTY 22931.95 -> 22932.15; card grid = Sensibull 090. DEFECT F-2 (look): "NIFTY 22921.60at 30 Oct".
- 10:33 Builder (strategy 67): spot 22920.10 -> 22921.85, "Prices as of 10:33:43 IST", Estimated-now curve drawn, Greeks Decay -19.33 -> -18.98 (builder solves IV live), Target block below the graph.
- 10:34 Strike drawer: spot 22916.25 -> 22917.60, call delta 0.8953 -> 0.8991, IV 16.05 -> 15.77.
- 10:29-10:33 My Strategies, Create Strategy (guided, step 1 of 4), Alerts (Active lists the 29 Oct conditional exit; History empty = #608, known), Billing ("Free during early access"), System health ("database: ok"), Learn, Orders placeholder ("Orders is coming"): no prices on these screens, no closed text.
- 10:33 Broker settings: account Connected; "Live market data: Partially connected - Live prices start when you open a strategy or option chain screen" (feed idle between screens, by design; look choice); margin Rs 409.00 read 10:33:14.

## Found during the run

| F | Step | What failed (seen) | Class / RCA | Fix commit | Re-test |
|---|---|---|---|---|---|
| F-1 | L2 | 10:28: every paper book greeks_reason no_iv and totals decay_reason no_iv in market hours, while every open contract has a live LTP and the builder solves IV; at 10:46 clean again (flaps with what other screens hold) | RCA (builder, inferred, not caught live): the paper read held only the book's contracts, so with nobody holding the index the spot was absent and no parity forward existed -> solved_iv None | e8697681 (merged 1f245c77) | tests_app/test_paper_iv_forward.py red 2 failed -> 6 passed (session re-run 6 passed); live 10:48 with chain open: 13/13 LIVE books greeks_reason None (0 no_iv). No detection change: live count is the check |
| F-2 | L2 | 10:32 Live Strategies "22921.60at 30 Oct" | Vue whitespace condense drops the space before a text node after a closing tag | d93d7d25 (as a83ce26e) | vitest red 1 failed -> 34 passed (session, run tree); live 10:44 "NIFTY 22959.40 at 30 Oct 2026, 10:44:14 IST" |
| F-3 | L2/L3a | 10:47 after API restart, nothing open: 16/16 books PAUSED prices_not_live; chain open: 13 LIVE, 3 PAUSED (65 SENSEX 5 Nov, 59 + 51 NIFTY 9 Nov legs) for 60 s+; read returns in 1.9 s (< 3 s hold) | the paper REST read's own hold does not price a contract no other screen holds (quote packet arrives with fresh time but no usable LTP); RCA in progress, builder round 1 fix/live-paper-cold-hold | - | - |
| F-4 (R-26) | L3b/L4 | 10:51-10:52 builder 56: target figures froze under "Stale" after the first push; typed 23200 never reached the server (2 outcome POSTs in the log all run) | push carries no target figures -> page marks stale; onPush cancels the target request in flight (suspect); builder round 1 (Opus) fix/live-target-in-pushes | - | - |

## Parked

| Row / item | Why (evidence) | What is left |
|---|---|---|
