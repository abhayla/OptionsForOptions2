# Session handover: GC-UI (Sensibull look + independent data check), 2026-10-28, session 1 of ~3

## UPDATE session 2 (2026-10-28 21:30 -> 2026-10-29 ~04:50 IST, head 05615606 + this commit) - READ THIS FIRST

Every step's code is merged on `build/gcbm-must-have` (LOCAL ONLY, nothing pushed). Each row with its proof is in the
contract's "Found during the run" table, from row `b2 r1` to `review fe fix`.

DONE this session: b2 (payoff table, Greeks order + Decay, lower card, per-leg paper P&L); step 5 Strategy Chart (core
proven on real Kite candles, F-64; route + engine + tab; checked against raw candles at all 3,850 points; 2 review
rounds, F1 connection-held-across-Kite and F2 guard bypass fixed); T-1 per-unit Greeks total; step 6b / 6c / 6d; step 7
Chrome pass at 1536 + Sonnet verdicts (52 matched / 22 differs / 17 not visible, triaged) + polish round; D-PX price
display texts ("now 99.80"); step 8 checker on 5 strategies on the final code: 0 mismatches (2,976 matched); step 9
review part 1 (Opus, backend) and part 2 (Sonnet, frontend) with fix rounds merged.
Last full runs (on 1d4a9d46 / ea4a4b04): guards 960 passed; full backend 7734 passed + the golden fixed after (02bb4a82);
full vitest 93 files / 1457 passed; tests/outcome 255 passed.

PENDING - needs market hours (09:15-15:30 IST), do these first in the next session:
1. Step 8 paper walk with LIVE prices in Chrome: build a NIFTY strategy -> Save -> Start tracking -> Positions > Paper
   (Paper mode strip, three P&L columns move) -> tick one leg -> Exit (1) -> confirm -> booked; then the checker
   `--paper <id>` on it. Never an order route; never click inside a Kite order panel.
2. The Paper tab's LTP / exit text in market hours: every price two decimals (D-PX: "186.1" must read "186.10").
3. Strategy Chart in market hours (live minute candles; 4.8 s cold after hours).
Then step 10: final handover text (DONE / PENDING / BLOCKED / PARKED / OWED-AT-LAND / NEXT), memory note.

NOT RUN (say so, do not claim): the 1366 px no-break check (the window is maximised at the screen's 1536 and
resize_window cannot shrink it - the owner un-maximises Chrome or accepts it untested); e2e (Playwright) - owed at land.

FOR THE OWNER (look choices, not defects): the Strategy Chart's 1-minute line is very spiky on early days (REQ-091 AC-2
allows daily bars); the Futures tab repeats the "Stale..." sentence under every synthetic row after hours; the Straddles
list is not centred on ATM. New texts pending owner read (pinned): chart reasons / notes / future label, Decay
definition, "Paper mode", the "?" tooltip "Your planned entry price", the S5-3 timeout sentence, quantity_not_whole_lots.

PARKED: D-A09 (leg expiry cell 91 / 82 px, "3 Nov (5 days" clipped), D-C27 (drawer grid 2 px over, horizontal
scrollbar). HELD: D-A38 (ADR-206).

DEFERRED (file at land with `gh_issue.py app ... --stage`): routes/execute.py:298 holds its DB connection while awaiting
Kite reads (same class as F1, order route, pre-existing); R2-2 a module importing routes.strategies can reuse
get_history_opener unseen by the history guard; F5 Greeks TOTAL vs chart weight by different gcds (mixed lot sizes
only); F6 oiBarWidth exported; drawer tab arrow keys; the option-chain vitest flake (2nd occurrence); LiveStrategyCard
and DepthPopup print raw prices (no display text on their routes); everything in the older DEFERRED list below.

INCIDENT recorded: the orchestrator re-saved strategy 56 by clicking Save to reach the Save dialog (same legs, only
updated_at changed, no order path).

Process lesson (4 occurrences this session): builders skip whole-repo guards their round did not touch; the
orchestrator's post-merge guard + full backend + full vitest runs caught every one - keep them after every merge batch.
Servers at handover: API on ea4a4b04 (port 8765), Vite (5174). Worktrees from this session stay until the land goal.

Contract: `docs/process/goal-contract-GC-UI-2026-10-28.md` (Status column, "Step 1 result", "Found during the run" and
"Parked" tables hold every number). Branch `build/gcbm-must-have` in `D:\Abhay\Ventures\OptionsForOptions2-gcbm`, LOCAL
ONLY (no upstream; no push / PR / CI of any kind until the owner says so). Head at handover: 7861ff1b. Session 13:30 to
~19:30 IST; ~105 local commits; ~24 builder runs.

## DONE

- Step 0 overlap list. Step 1 CORE: independent checker `scripts/checks/ui_data_check.py` (own BSM, IV solver, parity
  forward, breakevens, charges per ADR-082 exact amounts and per exchange, display strings with its own formatter,
  both curves, payoff table, SD block, per-leg paper P&L; AST test: no `ofo` import).
- Step 2 DATA rows all fixed or re-classed: D-A46 / A47 sentences, B33 / B38 (switch only on Payoff), B35 / B36 / B37
  (server IV percent + Greek display strings, one per-unit / per-position toggle), B51 (Planned entry vs Paper entry),
  C33 (leg expiries on the parity forward, `live_push` holds 5 strikes CE+PE per expiry), C31 (add-by-contract form
  removed), C27 (drawer: parked at 2 px).
- Extra defects found by the checker / live screen and fixed: F-2 per-unit Greek sign, F-3 drawer forwards on parity,
  F-4 breakeven "-0.0%" sign, F-5 after-hours IV from the closing price (a stale quote is not a live side), plus checker
  defects C-1..C-5 (C-5: BSE exchange rate).
- Step 3 (Area A) closed: header, leg rows (37 px), boxed controls, action row, summary block in Sensibull form with
  server-made whole-rupee figures (REQ-152), breakeven percent (REQ-153), sentences behind "?" (SPEC CHANGE REQ-034
  AC-7, REQ-081 AC-10 per ADR-204), payoff tab on the first screen (y 424 at 1536 x 864).
- Step 6a: Ready-made groups / order / names / square cards with shape icons / hint + Learn link; Positions empty state.
- Step 4 so far: frontend round a (instrument text "1 x 3 Nov 22600 CE", tracking panel columns, one-line detections
  with SPEC CHANGE REQ-046 AC-1 and REQ-146 AC-5, no empty band); server: `both_views`, `payoff_step` (default REQ-137
  AC-1: NIFTY 50, SENSEX 100), `sd_bands` (fixed 7 days), per-leg paper `pnl` / `pnl_text` (paisa) / `pnl_kind`.
- Owner decisions this session (in the spec): ADR-205 (charges stay exact, no rounding note), ADR-206 (order flow per
  ADR-165 / ADR-201; REQ-142 Funds needed held, finding F-62). Goal order kept (adjustments after POP; first playbook
  from the owner early).

## Last proof lines (after hours, API on 84a27aa7 + checker 92cd428a)

NIFTY with both curves + step 50 + SD: s54 539/0/1, condor 641/0/1, calendar 390/0/8 (match / mismatch / not
checkable); SENSEX bull put 73000/73200 PE 29 Oct: plain 233/0/1 (twice), with both curves 644/0/1. Live in market hours
(15:24 IST) before step 3b/4: 158/0/1, 219/0/1, 100/0/7. Paper P&L moved live 1,124.50 -> 1,179.75 (15:25:03 -> :16).
Full vitest after the last frontend merge: 83 files / 1328 tests passed. Full non-DB backend suite on 1187d6e6:
7582 passed, 1 failed (the pin test, then fixed), 4 skipped. The run on 84a27aa7 finished: 7657 passed, 7 failed,
4 skipped - all 7 in tests/errors/test_outcome_slots_closed.py (the new `summary_paisa_signed` slot type `SignedPaisa`
was not on the closed-slot allow-list); fixed right after c45a5adb, `tests/errors` 690 passed. The post-merge full
backend run caught it (the builder ran only the pin tests): keep running it after every backend merge.

## UPDATE at session end (~21:15 IST, head ebabbe61 + this commit)

Done since the first handover: step 4 server rounds 3-4 (OI per strike `open_interest`, TOTAL row net per-unit moved
into the engine, Decay column per F-63, checker rules for OI / TOTAL / Decay; merged 5ce3384a, 8d8c8af8; full backend
7693 passed / 0 failed), checker C-5 (BSE exchange rate), SENSEX checked (233/0/1, with both curves 644/0/1), finding
F-63 (Sensibull Decay measured logged out), step 4 frontend b1 payoff chart (both curves, two-value hover, OI bars,
SD bands, zoom, current price + breakeven marks, Sensibull tabs; merged b8e94b0c; full vitest after the leg-picker
fix ebabbe61). Chrome 20:5x: chart matches Sensibull's layout; three defects seen (OI strip "22700.00", doubled
"stale since" line, OI axis raw counts) - in b2's brief.

IN FLIGHT when the session ended: step 4 frontend round b2 (payoff table view, TOTAL row, Decay order, Greeks panel,
SD table, lower card, per-leg paper P&L, round-a carry-overs, the three b1 defects) in worktree
D:\Abhay\Ventures\OptionsForOptions2-gcui-tables, branch build/gcui-tables; its first commit 4a1aabfc (Greeks tab order
with Decay) was in, the rest may or may not be. Its brief: D:\Abhay\scratch\gcui-briefs\brief-tables.md (all 28
briefs of this session are in that folder; the old scratchpad copies may be gone).

NEXT in the fresh session, in order:
1. `git -C D:\Abhay\Ventures\OptionsForOptions2-gcui-tables log --oneline build/gcbm-must-have..HEAD` and `status`:
   if b2 finished, verify (its touched vitest files, money scan), merge, full vitest, guard suite + full backend in
   the background, Chrome check (Greeks tab order, payoff table, lower card, the three b1 defects gone); if b2 stopped
   part-way, dispatch its round 2 from brief-tables.md for the unfinished rows (it is round 1/2 now).
2. Step 5 Strategy Chart (core proof first, PENDING item 3 below).
3. Step 6 rest, then steps 7-10 (PENDING items 4-5 below).
Run ONE builder at a time (the PC ran critically low on memory at ~19:45; the API was killed once).
Servers at session end: API PID 12988 (port 8765, code ebabbe61-equivalent), Vite PID 3964 (port 5174), viewer 31380.

## PENDING (contract order)

(Items 1 and 2 below are DONE except round b2 - see the UPDATE above.)

1. Step 4 server round 3: D-B16 / B17 OI bars + "OI data at" strip (per-strike OI from the chain for the strategy's
   expiry, server display in L / Cr), D-B34 Decay column (REQ-145 AC-1: time-value change to the next market open;
   measure the definition on Sensibull 015 first), D-B28 TOTAL row net per-unit entry / LTP (server), D-B43 portfolio
   Greeks panel figures if any are missing from the reply.
2. Step 4 frontend round b: render both curves on one chart with the "On Expiry / Estimated" legend (D-B06, B07 keep our
   words), hover with two values (B14), axis titles (B08 drop x title, B09 y titles), one Zoom control instead of From /
   To / Apply / Default (B10), axis fitted to points (B11), labelled current-price marker (B12), hatched zones (B15), SD
   bands on the plot (B19, B20), OI bars (B16, B17 after round 3), tab labels (B01 "Payoff Graph", "Strategy Chart";
   B02 "Payoff Graph / Payoff Table"), header in one row (B04), payoff table view with the interval menu, both columns
   and Show % (B24-B26), P&L table multiply toggles (B31, server figures), Greeks columns incl. Decay (B34), SD table +
   Greeks panel + lower card (B43, B45, B46), per-leg paper P&L column printing `pnl_text` (B48), and the carry-overs:
   detection line strike "22400.00" -> REQ-151 trim in `frontend/src/lib/tracking.js:86`; Full table view ISO date and
   "22,800" against REQ-146 AC-5.
3. Step 5 Strategy Chart (D-B40*, D-B41): core proof first - one real Kite historical candle fetch for one leg + the
   index future through `backend/ofo_app/kite_history.py` (F-33 says the account has it), read back; then the chart.
4. Step 6 rest (23 rows: C01, C08, C11, C12, C14, C16, C20-C26, C28, C32, C34, C35, C41, C44, C48, C50, C53, C54).
5. Steps 7-10: Chrome side-by-side per area at 1536 x 864 + 1366 no-break; checker on 5 strategies on the final code
   (NIFTY + SENSEX, ready-made + drawer + calendar) + the GC-BP flow walk; review (fresh Opus for steps 1, 2, 5 and the
   money parts; probe mutant M1 with an off-grid strike); final handover.

## PARKED

- D-C27 drawer columns: 475 px in 473 (2 px) after 2 rounds; one gap change + Chrome re-measure left (owner's call on a
  third touch).
- D-A09 leg expiry cell clipped to "3 Nov (6 days" in the 84 px column; one width change left (owner's call).
- D-A38 Funds needed: held by ADR-206 (REQ-142, F-62).

## FOR THE OWNER TO READ (nothing decided here)

- New texts "pending owner read" in `tests/errors/template_pins.json`: the margin sentences (top-up 0 / top-up > 0,
  checked + short), the breakeven "before about Rs X of charges and taxes", the summary display templates, the
  `summary_paisa_signed` template; Ready-made "Please click on a ready-made strategy to load it", "Learn Options
  Strategies", Positions "No open positions"; renames Sell Put, Call Ratio Back Spread, Put Ratio Back Spread, Iron Fly
  -> Iron Butterfly.
- The planning sentence "for planning, not a recommendation" now sits behind the Important info "?" (no spec line
  requires it visible; REQ-136 AC-3's projections sentence stays visible).

## DEFERRED (file at the land goal with `gh_issue.py app ... --stage`)

1. `tests/option-chain.test.js` failed once under the full vitest load, 23/23 alone x3 (timing flake).
2. Checker live mode: the first SENSEX call after a restart can answer FROM_ENTRIES (quotes not yet in); it should
   retry until COMPUTED instead of reporting 0 / 0 / 2.
3. Mutant M1 (second curve on the table levels) is equivalent on all-on-grid fixtures; add an off-grid strike fixture.
4. The 4 skipped backend tests are unexamined.
5. Everything in the GC-BP handover's deferred list still stands.

## Process rules adopted this session (apply in the next one)

- Builders run only the test files they touch; the guard suite, DB files and the full backend suite run ONCE per merge
  batch by the orchestrator (in the background); full vitest after each frontend merge; Chrome check after each
  frontend merge.
- Every default / behaviour line in a brief quotes its requirement text so `check_brief.py` verifies it (P-1 / P-2:
  three wrong brief rules this session). Example strings in briefs go in backticks, never double quotes.
- When data and spec disagree, the checker reports a server finding; it is never bent to match the server (F-5).
- Measured cost (24 builder runs, ~5.4 builder-hours, ~3.07M builder tokens): ~40% test runs (guards in every builder,
  DB files over the tunnel at 3-7 min each), ~35% second rounds, ~25% first-round code. The orchestrator's long
  context is the largest unmeasured cost: one session per phase.

## OWED AT LAND (not run in this goal, by the owner's rule)

openapi drift check, Playwright e2e (several specs rewritten but never run), `ruff_ratchet.py`, `coverage.py . --check`,
`prepush.py`, the one push, one PR for GC-BM + GC-BP + GC-UI (Spec-deviation block for ADR-201 / ADR-204 / ADR-205 /
ADR-206), CI, `merge.py`, the deferred issues, the regenerated `views/spec-digest.md` and findings index.

## Running at handover

The API (PID 8724, port 8765) was STOPPED by Claude Code at ~19:45 IST because the PC was critically low on memory;
Vite (PID 27948, port 5174) and the viewer (PID 31380, port 8799) were still listening afterwards (only Vite's
launching shell was stopped). The next session checks `netstat -ano`, starts the API with the contract's "Running the
app" command, then restarts Vite (it reads the API's route list at start). 19 GC-UI worktrees
`OptionsForOptions2-gcui-*` are merged into build/gcbm-must-have and stay until the land goal (wt-rm refuses branches
not on main without -Discard); never `rm -rf` them (their frontend\node_modules are JUNCTIONS to the gcbm install).

## NEXT

Start a FRESH session with:
`/goal Resume goal contract GC-UI: docs/process/goal-contract-GC-UI-2026-10-28.md in worktree D:\Abhay\Ventures\OptionsForOptions2-gcbm (branch build/gcbm-must-have, local only). Read docs/process/session-handover-2026-10-28-gcui.md first, then the contract's Found / Parked tables; continue with PENDING item 1. No push, PR or CI until the owner says so. Done = every step closed or owner-accepted.`
