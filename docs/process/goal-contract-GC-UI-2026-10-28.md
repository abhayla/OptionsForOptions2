# Goal contract GC-UI: builder, strike drawer and Positions look like Sensibull, and every number on them is right (2026-10-28)

Written 2026-10-28 ~13:30 IST in a planning-only session (no code changed). Branch `build/gcbm-must-have`, worktree
`D:\Abhay\Ventures\OptionsForOptions2-gcbm` (local only, no upstream; GC-BM + GC-BP already on it, head 7909f6a0 + this
contract's docs commit). The owner starts this contract with /goal in a FRESH session.

## Owner decisions behind this contract (2026-10-28, question tool; recorded in the spec where they are product)

1. A differences document first, then this goal contract built only from its confirmed rows (process).
2. Screens in scope: the Strategy Builder in full (incl. lower tabs and dialogs), the Add/Edit strike drawer, the
   Positions page (Positions tab vs Sensibull Positions 050-053, Paper tab vs Sensibull Draft Portfolios 090-092).
3. Every visible difference tagged LOOK / FEATURE / DATA; default LOOK = Match now, FEATURE = Later, DATA = Fix now.
4. ADR-202: keep every required meaning, take Sensibull's FORM (explanations behind "?", price-moved = dot + header
   icon, "estimated from spot" small label, funds warning one line, one Important info note).
5. Side by side is ONLY for layout, UI and look and feel. Every NUMBER is verified independently (own calculation),
   never against Sensibull's numbers (owner: "you cannot refer sensible, because the screenshot data may be old or
   incorrect").
6. ADR-203: every wrong number found is fixed in this goal; the Strategy Chart is built from Kite Connect historical
   candles (display-rights risk accepted by the owner; REQ-091 hold lifted for this chart only).
7. Desktop 1536 x 864 now, plus a no-break check at 1366 x 768; phone layout = Later.
8. ADR-204: the differences document `docs/process/ui-match-differences-2026-10-28.md` is approved as recommended,
   including its ten SPEC CHANGE rows: 104 rows in scope (94 Match now + 10 Fix now), 47 out of scope.
9. PR / CI (owner, verbatim): "We will not create PRs for every changes. We will create PR only at the end when
   everything is working. And I will let you know when to create PR." -> NO push, PR, draft PR, GitHub Actions,
   `ci_local.py`, `prepush.py`, `land.py` or `merge.py` in this goal. Local commits only.
10. Browser always VISIBLE (owner, 2026-10-28): every browser step runs in the owner's own Chrome via
   Claude-in-Chrome, never a headless browser (details under "Running the app").

Spec basis: ADR-193 (Sensibull layout under OUR brand: our colours and fonts from GLOBAL.md, not Sensibull's), ADR-152
(Sensibull default except safety, legal, money), ADR-165 (no orders: no Trade All / Add to Drafts / Convert to real),
ADR-008 (one engine, exact Decimal; the browser computes no money), ADR-061 (forward / spot fallback, never silent),
ADR-197 (after hours from the last close), ADR-201 (Paper tab on Positions), ADR-202, ADR-203, ADR-204, REQ-136, REQ-091.
Sensibull: private study `D:\Abhay\Ventures\competitors\sensibull\2026-10-21` (INDEX.md, catalogue-raw.md, screen numbers
cited per row) and live logged-out `https://web.sensibull.com/option-strategy-builder` for the builder.

**Core:** an independent checker reproduces every number our builder, P&L table, Greeks, payoff and Paper screens show
for a real strategy, from the same inputs, with its OWN formulas (no import from `backend/ofo/engine`), and names each
figure that differs.
**Proof:** step 1. On live (or after-hours closing, ADR-197) data, run it on three real strategies (a debit spread, an
iron condor, a mixed-expiry calendar) and record figure by figure: ours, independent, match / mismatch. The eight DATA
rows below are confirmed or cleared by it. If the checker cannot be made independent, the work stops there
(Core-first R3).

## Read first (before any code; do not rebuild what exists)

- The differences document (all three area tables and their "Matches already" / "Not checkable" lists).
- The private side-by-side viewer: `D:\Abhay\scratch\ui-match-2026-10-28\viewer.html` (serve that folder only, e.g.
  `python -m http.server 8799 --bind 127.0.0.1` from inside it; never serve D:\Abhay: GLOBAL.env lives there). Frames:
  `ours\ours-01..14`, `sensibull-live\sb-01..07`, `study\`.
- `docs/process/session-handover-2026-10-28-gcbp.md` (deferred items 1-10 and the owner-read list), the GC-BP contract.
- Code: `frontend/src/pages/StrategyBuilderPage.vue`, `frontend/src/components/strategy/*` (ChartCard, SaveDraftBar,
  ReadyMadePanel, LegPicker, PaperStrategies, TrackingPanel, the summary / numbers blocks), `frontend/src/pages/
  PositionsPage.vue`, `frontend/src/lib/*` (tracking, displayFormat, saveDraft), the outcome / scenario / tracking
  routes and `backend/ofo/engine`, `backend/ofo/outcome`, `backend/ofo/tracking`.
- Step 0 writes the overlap list into this file (what each step reuses, which files two steps would both touch).

## Rules for the run

- **No PR, push or CI of any kind** (decision 9). Stacked local commits on `build/gcbm-must-have`; builder
  sub-worktrees via `~/.claude/tools/wt-new.ps1` (pass `-Name gcui-<item>`; the tool adds the repo prefix; link
  `frontend\node_modules` to the gcbm tree's install as a JUNCTION, never npm install there), merged locally.
- Tests: builders run only the test files they touch (+ ruff on touched Python, `npx eslint --max-warnings 0` on touched
  frontend files); output to a log, read the tail. After each local merge, the FULL frontend vitest once with
  `FULL_SUITE_BUDGET=<n> npx vitest run --maxWorkers=2` (with the dev servers up, default workers time out: 84 false
  failures measured 2026-10-28). DB tests one file at a time via the MAIN checkout's
  `scripts/orchestrator/db_run_fresh.py` (ofo_test is dirty; that PostgreSQL also serves IPODhan prod).
- Every defect (DATA rows and anything the checker finds) follows the defect-fix contract: RCA, Class (data filter,
  size before and after), failing test first, class-level fix, ONE real-data proof, detection change.
- Every SPEC CHANGE row edits its requirement's text in the same commit as the code, citing ADR-204.
- Privacy: the repo is PUBLIC. Never copy a Sensibull image into it; never write the owner's funds, client id, name or
  email into a repo file (the differences document uses placeholders). Screenshot pairs stay in `D:\Abhay\scratch`.
- Sensibull: read it logged OUT only; never log in on the owner's behalf; never click inside any order panel
  (memories real-order-guardrails, no-clicks-inside-order-panels). Our app: never press Execute or call an order route.
- Owner present: one question per call (`Business call:` + `Spec basis:` lines) only for business forks; technical
  calls are the session's own, complex ones with an independent reviewer first. Owner away: write the question to
  `docs/process/owner-questions-2026-10-2x.md` and continue.
- Every Agent brief: `Core:` / `Proof:`, `Budget:`, `Sensibull:` (screen numbers), `Report: evidence-table`, the
  `.claude/kit/builder-brief.md` standing items, an explicit `model` (Opus only with a `Why Opus:` line).
- At most 2 rounds per item, then park (`parked` note in this file with evidence) and continue.
- Evidence table at every done claim (command run that turn + its result line); a worker's report is a claim.

## Running the app

- Check ports 8765 / 5174 first (`netstat -ano`); a previous session may have left the API / Vite running (2026-10-28:
  API PID 11976, Vite PID 7980, viewer PID 31380). Stop only recorded PIDs with `Stop-Process -Id <pid>` (PowerShell).
- API: `LIVE_MARKET=1 APP_ENV=development python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/dev_run.py
  D:/Abhay/Ventures/OptionsForOptions2-gcbm python -m uvicorn --factory ofo_app.main:create_app --app-dir backend
  --loop ofo_app.event_loop:selector_loop --host 127.0.0.1 --port 8765` (ofo_dev, at migration 0027). Frontend: in
  `frontend/`, `OFO_API_TARGET=http://127.0.0.1:8765 npx vite --port 5174 --strictPort`. The Vite proxy reads
  openapi.json at start: restart Vite after a new route.
- Kite token expires 06:00 IST: the one owner step is a login in a PRIVATE window at
  http://127.0.0.1:8765/broker/zerodha/login.
- Live checks in market hours (09:15-15:30 IST); after hours the builder works from the last close (ADR-197), which is
  enough for the data checker (same inputs on both sides) but not for "prices move" checks.
- Browser (owner, 2026-10-28: the browser must always be on screen "so that I can see it"): EVERY browser step - live
  walks, screenshot pairs, side-by-side checks, live re-tests, Sensibull logged out - runs in the owner's own VISIBLE
  Chrome through Claude-in-Chrome (`mcp__claude-in-chrome__*`), at 1536 x 864. Never the headless Playwright MCP
  browser for anything the owner should see (on 2026-10-28 a walk ran there and the owner saw nothing). Only the
  session drives Chrome: one tab per task, closed when done, no builder or reviewer agent drives a browser. If the
  Chrome extension is not connected, stop and tell the owner instead of falling back to a headless browser.

## Items

Row ids are from the differences document; `*` = SPEC CHANGE (approved, ADR-204).

| Step | Item | Rows | What | Tier | Proof | Status |
|---|---|---|---|---|---|---|
| 0 | read first | - | Read the list above; write the overlap list here (which steps share StrategyBuilderPage.vue / ChartCard / the summary block; what each reuses) | C | Overlap list in this file | DONE (section "Step 0") |
| 1 | CORE: independent data checker | (confirms D-A46, D-A47, D-B33, D-B35, D-B36, D-B38, D-B51, D-C33) | A script in the repo (`scripts/checks/ui_data_check.py`), own Black-Scholes and payoff code, reads what the API/screen shows plus the market inputs it used, recomputes: summary (max profit/loss, breakevens with and without charges, reward/risk, net premium, time and intrinsic value on the spec's basis), payoff points at expiry and estimated-now, P&L table cells, Greeks per leg and total (per unit and per lot), Paper/tracking totals | A | Figure-by-figure table for 3 real strategies; each DATA row confirmed or cleared with numbers | DONE (merge 9659e6f8; live run 13:40 IST; see "Step 1 result") |
| 2 | DATA fixes | D-A46, D-A47, D-B33, D-B35, D-B36, D-B38, D-B51, D-C33, D-C27, D-C31 + every mismatch step 1 finds | Defect-fix contract per class; money maths (A46, A47, C33) Tier A with an Opus review | A (money) / B | Checker green on the same 3 strategies + each fix re-read on the live screen | In progress (2 builders: gcui-data-be, gcui-data-fe) |
| 3 | Builder top half (Area A) | D-A01, D-A04, D-A06, D-A07, D-A08, D-A09, D-A11, D-A12, D-A14, D-A15, D-A16, D-A17, D-A19, D-A20, D-A21, D-A22, D-A28, D-A29, D-A30*, D-A31*, D-A32*, D-A33, D-A36, D-A37, D-A38, D-A40*, D-A41, D-A42, D-A43* | Header strip, legs panel (dot price-moved marker), controls, action row, summary block in Sensibull form (ADR-202); goal of D-A28: the payoff graph starts on the first screen at 1536 x 864 | B | vitest red first; screenshot pair per row group; above-the-fold check | Not started |
| 4 | Graph and analysis (Area B) | D-B01, D-B02, D-B04, D-B05, D-B06, D-B08, D-B09, D-B10, D-B11, D-B12, D-B14, D-B15, D-B16, D-B17, D-B19, D-B20, D-B24, D-B25, D-B26, D-B28, D-B29, D-B30*, D-B31, D-B34, D-B37, D-B39, D-B41, D-B43, D-B45, D-B46, D-B47, D-B48, D-B49, D-B50* | Chart card, payoff (both curves on one chart, display-only), P&L table, Greeks (per unit + multiply toggles, IV in %), lower panel, tracking panel form; partial rows build only their "Match now" half | B (A where a number changes) | vitest red first; screenshot pairs | Not started |
| 5 | Strategy Chart | D-B40* | ADR-203: strategy combined price vs index future over recent trading days from Kite historical candles on the owner's connection, legs combined by the one engine, data source and range labelled, one flag to switch it off; REQ-091 AC-1/AC-4/AC-7 texts and the AC-7 production-flag test updated to cite ADR-203 | A (new data path) | Core of this item first: one real fetch of candles for one leg + the index future, read back; then the chart on 2 real strategies, values spot-checked by the step-1 checker | Not started |
| 6 | Tabs, dialogs, drawer, Positions (Area C) | D-C01, D-C02, D-C03, D-C04, D-C05, D-C07, D-C08, D-C11, D-C12, D-C14, D-C16, D-C20, D-C21, D-C22, D-C23, D-C24, D-C25, D-C26, D-C28, D-C30, D-C32, D-C34, D-C35, D-C40, D-C41, D-C44, D-C48, D-C50, D-C53, D-C54 | Ready-made cards, Saved / Tracked tabs, dialogs, strike drawer (incl. Straddles / Strangles tabs), Positions page tabs and Paper groups; per-leg money needs SERVER figures (ADR-008) | B | vitest red first; screenshot pairs | Not started |
| 7 | Side-by-side layout verification | all in-scope LOOK rows | At 1536 x 864: a screenshot pair per area (ours vs Sensibull live logged out for the builder, study screens for the rest) added to the private viewer; each row marked matched / not in the differences document's Status column; 1366 x 768 no-break pass on every screen | C | Viewer pairs + per-row status | Not started |
| 8 | Data re-verification + functional regression | all in-scope DATA rows + checker | Checker on 5 real strategies on the final code (NIFTY + SENSEX, ready-made + drawer + calendar), all figures match; GC-BP flow still works: build -> Save -> Start tracking -> Paper tab moves -> paper exit (one leg) | B | Checker table + walk lines with times | Not started |
| 9 | Review, no land | - | One combined review of this contract's diff: fresh Opus for steps 1, 2 (money), 5; Sonnet for the rest; at most 2 rounds; accepted findings fixed and re-verified | A | Verdicts; `git rev-parse @{u}` still "no upstream" | Not started |
| 10 | Handover | - | DONE / PENDING / BLOCKED / PARKED / OWED-AT-LAND / NEXT; the out-of-scope rows (47) and any parked rows listed; worktrees merged and removed only via `wt-rm.ps1` where it allows (branches not on main stay until the land goal) | C | Handover committed locally | Not started |

Out of scope (ADR-204): D-A02, D-A03, D-A05, D-A10, D-A13, D-A18, D-A23, D-A24, D-A25, D-A26, D-A27, D-A34, D-A35, D-A39,
D-A44, D-A45, D-B03, D-B07, D-B18, D-B21, D-B22, D-B23, D-B27, D-B32, D-B42, D-B44, D-C06, D-C09, D-C10, D-C13, D-C15,
D-C17, D-C18, D-C19, D-C29, D-C36, D-C37, D-C38, D-C39, D-C42, D-C43, D-C45, D-C46, D-C47, D-C49, D-C51, D-C52 (incl.
what-if sliders, OI bars, SD bands, POP, phone layout, per-leg Paper P&L and page totals that need new server
figures - each stays a known difference for its own goal).

Size, stated honestly: 104 rows plus a new data path (Strategy Chart) and an independent checker. Expect more than one
session; the Status column and the per-row status in the differences document make the contract resumable. Order: step
0, step 1 (core) before anything else; step 2 next (wrong numbers outrank looks); steps 3-6 may run as parallel builders
only where step 0's overlap list shows no shared file (StrategyBuilderPage.vue layout belongs to step 3); 7-10 last.

## Step 0: overlap list (2026-10-28, from the import graph of `frontend/src`)

Files two or more steps touch, and the rule for each:

| File | Steps | Rule |
|---|---|---|
| `pages/StrategyBuilderPage.vue` | 3 (layout owner: A28, A42, A43), 4 (B46 lower panel, B47 band), 6 (lower tabs placement) | Step 3 lands first; steps 4 and 6 change it only after step 3 is merged, and only the slots they own |
| `lib/displayFormat.js` | 3 (A04, A21 one rupee/number rule), 4 (B29, B30, B49 contract form), 6 (C53) | One format sub-step inside step 3 adds the shared helpers; steps 4 and 6 call them, never add a second formatter |
| `components/strategy/SummaryCards.vue` | 2 (A46 breakeven basis), 3 (A29-A33, A36, A37) | Step 2 first (number), then step 3 (form) |
| `components/strategy/MarginLine.vue` | 2 (A47), 3 (A38, A40, A41) | Step 2 first |
| `components/strategy/ChartCard.vue` + `lib/chartCard.js` | 2 (B33, B38 switch per tab; B35, B36 Greeks), 4 (B01-B39), 5 (B40 Strategy Chart tab body) | Step 2 first; step 4 next; step 5 only adds the Strategy Chart tab body (a new component) |
| `components/strategy/PayoffChart.vue` | 4 only (B06-B17, B19) | - |
| `components/strategy/LegPicker.vue` | 2 (C27 columns, C31 form overlap, C33 forward label), 6 (C20-C35) | Step 2 first; C30 (remove the contract form) is the class fix for C31, so C31 lands in step 2 by removing the form |
| `components/strategy/TrackingPanel.vue`, `PaperStrategies.vue`, `lib/tracking.js` | 2 (B51 entry label), 4 (B48, B49, B50), 6 (C14, C41-C54) | Step 2 first; step 4 owns TrackingPanel, step 6 owns PaperStrategies |
| `components/strategy/SaveDraftBar.vue` | 3 (A22 action row), 6 (C01, C11, C12, C14, C16 lower tabs, Saved list, Save dialog) | Step 3 first |
| `components/strategy/LegList.vue`, `StrategyControls.vue` | 3 only | - |
| `components/strategy/ReadyMadePanel.vue`, `lib/readyMade.js` | 6 only (C02-C08) | Can run in parallel with step 3/4 |
| `pages/PositionsPage.vue` | 6 only (C40) | Can run in parallel |
| backend `ofo/engine`, `ofo/outcome` (breakeven, funds needed, forward) | 2 only (A46, A47, C33); 4 reads (B19/B45 SD, B16 OI via existing replies); 5 (new history route) | The checker (step 1) imports NOTHING from `backend/ofo/engine` |

Reuse: SD bands (B19, B45) use the server's spot / ATM IV / days already in the outcome reply; OI bars (B16, B17) reuse
the strike drawer's OI (G-074); the Greeks multiply toggles (B31, B37) are one shared control; per-leg Paper P&L stays
Later (ADR-008). Parallel-safe sets: {ReadyMadePanel, PositionsPage} alongside step 3; everything else sequential
2 -> 3 -> 4 -> 5 -> 6.

## Step 1 result (core proven, 2026-10-28 13:40 IST, live)

Checker `scripts/checks/ui_data_check.py` (own BSM, IV solver, parity forward, breakevens, charges; AST test: no `ofo`
import; 31 tests; Tier A mutants 5/5 killed). Raw replies and tables in `D:\Abhay\scratch\gcui-checker\run1*` (private:
they hold the funds figure). Counts match / mismatch / not checkable: debit spread (strategy 54) 126/0/0, its paper
reply 3/0/0; iron condor 148/7/0; calendar 66/2/6 (no expiry payoff across two expiries, ADR-143; calendar Estimated Now
checkable only to about Rs 80 because the reply does not carry the far-expiry forward).

DATA rows, all CONFIRMED with numbers: D-A46 (shown breakeven 22,687.80 is on the pre-charges payoff, which is the spec
basis, section 1/3; P&L at it incl. charges is -140.79; incl.-charges breakeven 22,689.97), D-A47 (needed = Zerodha's
32,029.59 to the paisa; the sentence "With the premium" claims a premium is added that is not), D-B33/D-B38 (table P&L
and Greek cells identical under view=at_expiry and view=estimated_now), D-B35 (iv sent as a fraction 0.160347), D-B36
(Greeks per position: delta 40.7883 = 0.6277 x 65), D-B51 (planned 194.40/106.60 vs paper 193.70/106.35 -> two P&Ls,
1,738.75 vs 1,768.00), D-C33 (23 Nov forward from spot 22,828.46 vs the traded 23 Nov future 22,819.00, 9.5 pts).

Mismatches triaged against the spec: condor TOTAL P&L % (reply 2.4% = P&L / max loss) is the SPEC basis (REQ-035 Q233
"TOTAL P&L % = unrealized P&L ÷ max loss") -> checker defect C-1; condor margin needed 60,429.35 vs broker 60,413.10 is
the ADR-094 top-up -> checker must model it, C-2; charges total vs sum of shown parts (+0.02 condor, +0.01 calendar, GST
on unrounded parts) -> real defect F-1.

## Found during the run

| F | Step | What failed (seen) | Class / RCA | Fix commit | Re-test |
|---|---|---|---|---|---|
| F-1 | 1 | Charges breakdown: condor total 263.15 vs parts 263.13; calendar GST 18.63 vs 18% of shown parts 18.64 | Class: every strategy's charges breakdown (and the max profit / max loss that include it) where a part rounds; RCA (to confirm in step 2): parts and GST computed unrounded, each shown rounded, total rounded once | | |
| F-1 (re-classed) | 2 | NOT a server defect. ADR-082 (1): "every amount is exact Decimal; STT and stamp duty are not rounded at order level (as Kite's order-level charges reply, F-35)"; its worked example rounds the exact total once (214.95956479500 -> 214.96). The round-1 per-part rounding fix (fd25009c) was an unapproved SPEC CHANGE and is reverted (02e4b968). Rounded lines can therefore differ from the total by 1-2 paise; a note explaining that is a product-wording question for the owner (asked) | Checker defect C-3 | 02e4b968 (revert) | outcome tests 177 passed after revert |
| C-1 | 1 | Checker computed TOTAL P&L % on net entry value | Checker defect: spec basis is max loss (REQ-035 Q233) | 77666b86 | replay: s54 126/0/1; mutant survived (debit spread cannot tell the bases apart) -> credit case in round 2a |
| C-2 | 1 | Checker did not model the ADR-094 top-up in margin needed | Checker defect: needed marked not checkable (per-leg option_premium not in the reply) | 77666b86 | replay counts above |
| C-3 | 2 | Checker expected charge lines to add up to the total | Checker defect: must follow ADR-082 (1) exact amounts; owner 14:2x kept it, no note (ADR-205) | 36c07515 | replay run1: 0 mismatches on all 3; live run2 0 |
| F-2 | 2 | Live screen 14:52: Greeks "Per unit" shows the SOLD 22800 CE delta +0.42 while "Per position" is negative: the toggle flips a sign | Class: every per-unit Greek on a SELL leg; RCA: per_unit is the contract Greek, unsigned; REQ-084 AC-8 per position = per unit x lot size x lots | 4169e3f9 (95c9e418, 87284899) | Chrome 15:27: SELL 22800 CE per unit delta -0.42, gamma -0.0009, theta 14.28, vega -11.37; live checker s54 158/0/1 (signed rule added) |
| F-3 | 2 | Live screen 14:55: drawer Futures tab "23 Nov Forward used for pricing 22815.45 (estimated from spot)" beside the 23 Nov future 22789.90; after D-C33 a 23 Nov leg is priced on parity, so the label is false for every expiry the drawer does not have open | Class: every option expiry on the Futures tab (1 of 18 on parity); RCA: the futures lease holds futures + index only | f000f155 (78c4b8ba) | Chrome 15:27: 3 Nov ... 29 Dec all "from put-call parity"; 23 Nov 22,778.20 vs future 22,775.30 |
| 3a r1 | 2-3 | Chrome 15:27: moved leg rows 45 px (was 53; target ~36), Lots head clipped into Planned entry, Hedge mark only in a tooltip although REQ-076 AC-8 requires legs to carry a Hedge mark (D-A12 was not one of ADR-204's SPEC CHANGE rows) | Round 2 (build/gcui-legs2): visible compact Hedge mark (D-A12 kept), heads, height; unmoved legs keep the ADR-197 source caption (second line kept by spec) | fb0f6c73 | |
| D-C27 r1 | 2 | Live screen 14:52: values no longer touch, but the strikes grid is 558 px in a 473 px panel: horizontal scroll, Put LTP / Put Delta cut | Round 1 widened columns without a total-width check (jsdom cannot measure) | c7d32e9d (round 2: OI in L / Cr, grid 464 px by its own sum) | Chrome 15:27: scrollWidth 475 vs clientWidth 473 - 2 px over after round 2/2; shipped with the finding (run-discipline B1), see Parked |

Step 2 live proof (API restarted on 9cc7ac58, PID 30792; Vite PID 4100; 14:50 IST): checker run2 live, all replies
COMPUTED with no "estimated from spot" label: s54 126/0/1, condor 155/0/1, calendar 68/0/7 (not checkable = calendar
expiry figures, ADR-143, and margin needed, C-2). Screen (Chrome, 1536 x 864): amber "estimated from spot" banner gone;
switch only on Payoff (D-B33/B38); "Planned entry" heading (D-B51); IV "15.63%"; Greeks per unit 2 dp, gamma 4 dp;
margin sentence "which already includes the premium of the legs you buy" (s54, top-up 0) and "adds about Rs 1,069.25"
(condor); breakeven "before about Rs 140.79 of charges and taxes"; add-by-contract form gone. Full vitest 79 files /
1285 passed.
| P-1 | 2 | Orchestrator miss: decided the charges rounding rule as "spec silent" without grepping ADR-082 for rounding (spec-first R1 skipped); a builder found it | Process: R1 grep by every key term (here: round, paisa, GST) before a technical call that touches shown money | - | recorded; the R2 business/technical split also applies: money shown = owner's call |
| D-C33 | 2 | Every leg expiry in market hours priced on the spot fallback | RCA: the strategy socket subscribed only legs + index, so parity never had 3 two-sided strikes; fix holds the 5 nearest strikes CE+PE per leg expiry (+10 contracts per expiry on the feed) | 1c65f911 | recorded 2026-10-08 frames; live re-run after merge |

## Last live reads before the close (2026-10-28, code f000f155)

- Checker live 15:24:31-15:25:00 IST, all three strategies, 0 mismatches: s54 158/0/1, iron condor 219/0/1, calendar
  100/0/7 (not checkable: calendar expiry figures per ADR-143, margin needed per C-2). Raw replies:
  D:\Abhay\scratch\gcui-checker\run4-live-close\ (private: funds figure inside) for after-hours replays.
- Paper P&L moves live: strategy 54 tracking unbooked 1,124.50 at 15:25:03 -> 1,179.75 at 15:25:16 IST, state LIVE
  (step 8's "Paper tab moves" half; the screen walk on the final code is still owed).

## Parked

| Row / item | Why (evidence) | What is left |
|---|---|---|
| D-C27 (drawer columns) | Two rounds: r1 widened columns (558 px in 473), r2 compact OI + tighter grid (475 px in 473, Chrome 15:27 IST); the component's own width sum counts the flexible LTP column at its minimum | One gap or a 2 px column trim, then a Chrome re-measure (scrollWidth <= clientWidth); next goal or step 7 if the owner accepts a third touch |
