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

## Owner answers during the run

- 2026-10-28 ~15:4x IST (chat + question tool): the order flow stays ADR-165 / ADR-201 - builder trades are paper,
  never sent to Zerodha, shown on Positions > Paper; real Zerodha positions are imported read-only into Positions;
  adjustments on both. Recorded as ADR-206 (local); REQ-142 Funds needed held; D-A38 stays parked.
- Same time: the goal order is kept - finish GC-UI, then B2, B6/B7, B16/B17, LAND, chain, POP, adjustments; the owner
  sends the first adjustment playbook early. No spec change: an order already recorded in
  docs/process/goal-contracts-builder-phase-2026-10-27.md.

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
| C-4 | checker | After hours (17:13 IST) the checker flagged 31 / 40 / 26 model rows (IV, Greeks, Estimated Now) on the 3 run1 strategies that matched 0 at 15:24 | Checker defect: it implied IV from stale bid/ask mid with a parity forward, ignoring the reply's stated basis (output_label "estimated from spot", greeks_basis SPOT_FALLBACK, quotes stale); the server follows ADR-061 + ADR-172 | e205b9c6 (parity on live strikes only kept; its stale-mid IV rule reversed by F-5) | replay 17:13: 31/40/26 -> 0/0/0; 15:24 live 0/0/0 |
| F-4 | 3b | Chrome after hours: breakeven "22,688 (0.0%)" at spot 22,698.85 = -0.0487%; REQ-153 AC-1's example writes this "(-0.0%)"; REQ-152 AC-4 drops the sign only for a true zero. The display checker (050a2ad3) agreed with the server, so both made the same slip | Class: every breakeven percent that rounds to 0.0 from a non-zero value | e205b9c6 (04ab671e server, 205085c3 checker) | 194 tests; mutants 10/10 |
| checker display rules | 3 | Display strings were not checked independently (only per_unit_display) | Detection gap closed: every server display text recomputed with the checker's own formatter; live after the restart on cd46e9e2: 0 display mismatches on all 3 strategies; first SENSEX strategy (bull put 73000/73200 PE, 29 Oct) fixture | 050a2ad3 | 70 checker tests |
| F-5 | checker | The C-4 builder measured that after hours the server implies IV from the STALE bid-ask mid (8 of 8 legs, 17:13), then changed the checker to match the server. ADR-172 takes the mid only when both sides are live; ADR-197 computes after-hours numbers from the closing prices and the closing-price IV. Strategy 54 leg 22600 CE: stale mid 238.45 vs close LTP 237.90 | Server defect: `model.py` counts a side live when present and above 0, health ignored. Class: every leg whose quote is not live (every leg after hours). C-4's stale-mid checker rule (merged e205b9c6) is reversed with it. Lesson: when data and spec disagree, the checker reports a server finding and is never bent to match the server | 99bff5b8 (08d1ed4d engine `iv_price` needs health AVAILABLE; 546d7f99 checker) | replay live2 (old server): 7 of 8 IV rows now flagged (detection proven); API restarted on 99bff5b8 (PID 23944), checker after hours 17:5x: s54 231/0/1, condor 330/0/1, calendar 172/0/7 incl. every display row; 15:24 live replies 0 non-display mismatches; DB test_chain_live 74, test_outcome_route 25 passed |
| s4a carry | 4 | Step 4 frontend round a (merged c88298a6): (1) D-B48 needs a server per-leg paper P&L field (TrackingLegOut has none; nothing computed in the browser); (2) the detection line's server text prints the strike as "22400.00" (REQ-151: no trailing .00); (3) `paper_pnl` comes as plain text with no currency; (4) the Full table view still shows the ISO expiry and "22,800" against REQ-146 AC-5 "every view" | (1)-(3) -> step 4 server round 2; (4) -> step 4 frontend round b | | |
| P-2 | 3b / 4 | (a) `tests/errors/test_template_pins.py` was red on the integration branch from a35430c0 (step 3b server) to 1187d6e6: 4 summary display templates unpinned; my post-merge checks ran the full vitest and targeted backend files only. (b) Step 4 server brief told the builder the payoff-table default is today's admin step; REQ-137 AC-1 says "default the underlying's strike step: NIFTY 50, SENSEX 100" - second occurrence of P-1 (a brief rule written without reading the requirement in full) | Mechanisms: (a) after every merge that touches backend/, the full non-DB backend suite once (`python -m pytest tests -q`, in the background); (b) every default / behaviour line in a brief quotes its requirement text so check_brief verifies it | 1187d6e6 (pins) | pins 63 passed |
| b2 merge | 4 | Merged 8725b3f3. Chrome 21:5x on W2 P3 IC (strategy 56), after hours: Payoff Table lists both columns with the 10/25/50/100 menu; Greeks head Delta, Theta, Decay, Gamma, Vega, IV; SD table 1SD 452.2 (2.0%) 22246.7 / 23151.0; stale label once; OI axis in L; per-leg paper P&L `+230.75 booked`. DEFECT T-1: in Per unit mode (the default) the Greeks Total row and the whole lower-card Greeks block print `—` for every figure - the server's TOTAL Greek cells carry no `per_unit` / `per_unit_display` (Per position works: Delta -1.63, Theta 112.13, Decay 79.72, Gamma -0.0065, Vega -83.29). Full vitest 1 failed / 1380 passed: `strategy-table.test.js` ADR-168 attack 4 bans the word `Standard` and the new heading `Standard Deviation` contains it (the test is too broad: it targets the old Guided / Standard / Advanced level words) | T-1 class: every reply's TOTAL Greek cells; fix in the engine (per-unit total = sum of sign x lots / gcd x per-unit Greek, the step 5 chart's quantity rule) - server round after step 5 server; the test narrowing goes in the step 5 frontend round | 8725b3f3 | full vitest 87 files: 86 passed, 1 failed (above) |
| step 5 srv r1 | 5 | Builder (Opus) did 3 of 5 items at 67 calls: D-B26 `move_pct` / `move_pct_display` per payoff-table row (d5e84935, REQ-137 AC-2 example +2.1%); `combined_price_per_unit` / `combined_price_series` in ofo/engine/money_summary.py + chart points in ofo/outcome/price_history.py (5cd807c4), on the real F-64 bodies: 09:15 point -5.40, future 22841.1, 83 of 375 minutes of 14 Oct are gaps (22% on that day vs 5.3% over 10 days - liquidity is thinner on early days); REQ-091 SPEC CHANGE per ADR-203 (ef52ff8b); mutants 4/4. NOT built: the route, states, cache, pins, openapi | Round 2/2 sent to the same builder (route + states + pins + openapi + 2 mutants + new ruff findings + spec_refs). Work is in the agent tree `.claude/worktrees/agent-a898bac210657752b`, branch build/gcui-s5srv-agent (the harness refused the orchestrator-made tree, left empty: OptionsForOptions2-OptionsForOptions2-gcui-s5srv, remove at land - wt-rm needs the merge sha) | d5e84935, 5cd807c4, ef52ff8b | orchestrator re-run: 3 files 167 passed; money scan 4 passed |
| step 5 srv r2 + merge | 5 | Round 2: route GET /strategies/{id}/price-history (409 held, 404 other user, 7 states, 5-min cache), texts pinned pending owner read, history allow-list +2 modules per ADR-203 (review at step 9), round-1 defect fixed (`move_pct_display` plain str broke the app import - my round-1 re-run did not import the app). Orchestrator regenerated both openapi files (c2ff51a2); merged 0afd3bae. Not done: 2 route mutants (token in error text, flag removed) -> step 9 Opus review | Live check after restart: 500 on /strategies/56/price-history - defect S5-1 below | 06343a02, 5f1dc1a8, c2ff51a2, 0afd3bae | outcome route 25 passed |
| R-1 | 2-5 | `tests_app/test_response_door.py` RED on the integration branch (2 failed / 212 passed): ~20 reply models from GC-BP / GC-UI rounds not in APP_MODELS; a test still calls `outcome_margin_short` with the slot `needed` that step 2 removed | RCA: the post-merge batch (guard suite + tests/ backend) never ran tests_app files, so every model registration miss stayed invisible; detection: the orchestrator runs test_response_door.py after every server merge from now; fix = item A of the T-1 round | - | gcbm: 2 failed, 212 passed |
| S5-1 | 5 | Route answers 500 live: `kite_history_for` reads the token with `access_token_for` on the request connection already in a transaction -> `BrokerStoreError: token_read_needs_fresh_connection` (GC-6 MAJOR-1 guard working as designed) | RCA: the route tests fake both production seams (opener, finder), so the real token read never ran; class = production seams faked in every route test (2 of 2). Brief brief-s5fix.md (Opus, Tier A): read the token like live_market / history_finalize, a tests_app test with the real seams, store errors -> `no_session`, never 500; dispatch after T-1 | - | curl 500 INTERNAL_SYSTEM_002 ERR-75FDA141 |
| S5-2 | 5 | Batch after the step 5 merge (0afd3bae): guards 1 failed / 953 passed; full backend 3 failed / 7710 passed / 4 skipped - all from step 5's code: (1) strategy_price_history.py imports ofo_app.kite_history outside the Kite adapter (test_provider_replaceable); (2) broker name compared in feature code, strategies.py:545 + 2 more (test_no_broker_name_in_feature_code, also the guard failure); (3) test_select_app_tests PR-241 diff now selects the new route test file | RCA: the builder ran only its touched files (by the memory rule) and the adapter / broker-name guards sit outside them; class = vendor reach outside the adapter in this route. Folded into the S5-1 round as items B1-B3 (brief-s5fix.md) | - | guards-merge.log, backend-full.log in D:/Abhay/scratch/gcui-s5srv |
| T-1 + R-1 fixed | 4 | Merged 1af14e57 (2d912253, 7627aa36, c592fb7b, ff14a229): TOTAL Greek cells carry per_unit / per_unit_display (lot-weighted sum, absent with not_all_iv when a leg lacks it); 17 reply models registered in APP_MODELS + margin test on current slots (R-1); chart future label day-month (`NIFTY 24 Nov FUT`, DayMonth slot pending owner read); 6 unpinned slot types pinned (test_identifier_and_slots was also red); checker rule `check_total_per_unit_greeks`; mutants 3/3 | Chrome 23:0x on strategy 56 (API restarted on 1af14e57): lower card Per unit Delta -0.03, Theta 1.73, Decay 1.23, Gamma -0.0001, Vega -1.28; hand check Delta -0.25+0.32-0.53+0.43 = -0.03 = per position -1.63 / 65 | 1af14e57 | orchestrator re-run 716 passed; builder: response door + outcome route 239 passed |
| S5-1 + S5-2 fixed | 5 | Merged 699c53c3 (ad0a44c5 red test with the real token read + real FUT pick, 35d26b5c token read first on the request connection behind the Kite adapter, store error -> no_session, broker_refused state, broker name out of feature code, selector set; c8667df9 openapi + builder-brief standing item "a faked production seam needs one real test"; 1fe6d352). Builder ran 95 calls (budget 80, 19% over, in its final checks) | LIVE PROOF 23:1x on 699c53c3: /strategies/56/price-history 200 available, 3,850 points 14 Oct 09:15 - 28 Oct 15:39, 0 gaps, future `NIFTY 23 Nov FUT`; independent recomputation from raw Kite candles of the 4 legs (check56.py) matched all 3,850 points to the paisa; last point 76.00 vs builder LTP net 74.15 explained by the 15:39 closing-session candle (F-64 addendum e9963ad4) | 699c53c3, e9963ad4 | batch running (guards, response door, route files, full backend) |
| step 5 fe | 5 | Merged 380598d2 (d512d0de chart tab on the real ph56 reply, minute-index x axis, every state prints its reason; 34d54d2a Show % from move_pct_display + ADR-168 attack 4 narrowed with a planted-label test; fb9abeeb two Greeks tests made stale by T-1's fixture change). History guard (ADR-066 allow-list) red after S5-1 + this merge: price_history_source and StrategyPriceChart.vue's one request added as ADR-203 exact entries, exemption test keeps both load-bearing (eabf5379), 50 passed. Chrome 23:4x strategy 56: tab shows "Something went wrong" - DEFECT S5-3: the app's request is cancelled by the API client's 10 s timeout (services/api.js:46); the route answers 200 through /api (warm 2.8 s; Invert flips the first point 84.85 -> -84.85, future unchanged); a cold call fetches 5 contracts from Kite in sequence | S5-3: measure cold time, then a per-call timeout for this request sized from the measurement and a timeout-specific message; warm 2.8 s also to be looked at (3,850 points) | 380598d2, eabf5379 | full vitest running |
| P-3 | 4-5 | Orchestrator miss: after the T-1 merge (backend round) I ran no frontend suite, but T-1 changed the shared fixture `tests/fixtures/outcome_both_curves/flag_off.json` that frontend tests read - 2 frontend tests went stale and the s5fe builder found them | Rule: any merge that touches `tests/fixtures/` runs the full vitest too, whatever side the round was on | - | recorded |
| S5-3 fixed (unverified live) | 5 | Merged 1005763b (5af5db66): the price-history request passes timeout 60000 (Kite transport 20 s per call x up to 5 contracts in sequence), a timeout prints "The strategy chart is taking longer than usual. Please try again in a moment." (pending owner read), other failures keep the generic text; global 10 s default unchanged; api.js mapError now keeps code ECONNABORTED (interceptor api.js:55 -> component :130 checked by reading) | OWED: the cold-cache time was never measured (the system stopped the API, Vite, the timing run and the full backend suite at ~23:5x for low memory, 1.7 GB free); Chrome re-check of the tab cold + warm; full backend suite after 699c53c3..1005763b; mapError timeout code has no test of its own (step 9) | 1005763b | chart + api tests 23 passed on the integration branch |
| C-5 | checker | First live SENSEX check (bull put 73000/73200 PE, 29 Oct, after hours): 6 rows off by Rs 0.69 - exchange transaction 6.20 (server) vs 6.78 (checker) | Checker defect: its rate table held only the NSE rate 0.03553%; SENSEX trades on BSE at the seed's 0.0325% (migration 0012 l.83; ADR-082 (1) per exchange). Server right | (this commit) | SENSEX 233/0/1 twice; NIFTY unchanged 231/0/1, 330/0/1 |
| step 4 server | 4 | Both curves, payoff-table step, SD block merged (3d74de1d), per-leg paper P&L merged (84a27aa7, pnl_text to the paisa per REQ-109 AC-2); money-outside-engine guard kept green by moving the index-level rounding into ofo.scenario (612bd721); mutants 3/4 killed, M1 (second curve on the table levels) equivalent on the current fixtures, guarded structurally by _both's level check (service.py l.682) - step 9 to probe with an off-grid strike | Live after restart on 84a27aa7 (PID 8724), after hours: NIFTY with both curves + step 50 + SD: 539/0/1, 641/0/1, 390/0/8; SENSEX with both: 644/0/1 (step default 100, SD horizon 1 day) | 3d74de1d, 84a27aa7 | full vitest 83 / 1328 passed |
| step 4 server r3-r4 | 4 | OI per strike (`open_interest`, live push holds the range's strikes; REST reads only streamed contracts), TOTAL row net per-unit Entry / LTP (moved into the engine, money_summary.net_price_per_unit, ADR-008 guard), Decay column (D-B34; F-63 measured on Sensibull logged out: Decay / Theta 0.74-0.84 overnight, formula = model value at the next open minus now), checker rules for OI / TOTAL / Decay (own next-open rule; a holiday = not checkable). Round 3 mutants 3/4 (M2 missing OI as 0 survived) -> round 4 added the one-strike-missing test, M2 killed; round 4 mutants 5/5. Batch after r3: 2 failures (money line in table/model.py; test-selection expectation) - both fixed (r4 item 0; 3133a2ab) | Server column order is Delta, Gamma, Theta, Decay, Vega; the Greeks tab must render REQ-145 AC-2's order Delta, Theta, Decay, Gamma, Vega, IV (frontend round b2) | 5ce3384a, 8d8c8af8 | after r4: guards 954 passed; full backend 7693 passed, 0 failed, 4 skipped |
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
| b2 r1 | 4 | Frontend b2 round 1 (builder, 116 tool calls, stopped at 80% budget): 10 of 13 rows built - Greeks tab in REQ-145 AC-2 order with Decay, Payoff Table from `payoff_table` with the 10/25/50/100 menu and both columns, TOTAL net Entry / LTP, Full table `13 Oct` / `22600`, per-leg paper P&L, detection line `22400`, OI strip `OI data at 22700`, stale label once, OI axis L / Cr. NOT built: lower card (D-B43/B45/B46), Decay info mark (REQ-145 AC-5). Show % (D-B26) NOT built by rule: the reply carries no percent and the browser computes no money (ADR-008) | Round 2/2 dispatched for the lower card + Decay mark (brief-tables-r2.md); D-B26 Show % needs a server percent field and a stated denominator - left for the owner's list (what the % is of is a money-display question) | 4a1aabfc, 9ccdae12, e1d141b2 | builder's touched files: 106 + 54 passed; merge + full vitest after round 2 |
| step 5 core | 5 | Core PROVEN 2026-10-28 ~21:33 IST after hours: stored session + allow-listed history door returned 3,638 minute candles for NIFTY26N0325000CE and 3,840 for NIFTY26NOVFUT (14-28 Oct, 10 days); the leg lacks 202 of the future's minutes (5.3%); only `minute` is allow-listed (60minute / day refused before sending) - REQ-091 AC-2 allows 1-minute bars, so no allow-list change | F-64 (spec/findings.md); quantity rule for the combined price decided as a technical call (lots / gcd, sells +), written into the step 5 server brief and to be added to REQ-091 AC-2 with ADR-203's pending SPEC CHANGE text | 72556621, b62b246c | script D:/Abhay/scratch/gcui-chart/core_proof.py, log core_proof.log |
| P-2 | 4 | Orchestrator miss: the b2 brief described Show % as "each P&L as a percent" and told the builder not to build it without a server percent; REQ-137 AC-2 says Show % is each row's move from spot in percent ("23,450 = +2.1%"), computed by the server - the spec decided it and the brief contradicted it | Spec-first R1 skipped for one row: the brief quoted the diff row, not REQ-137. Fix: server `move_pct` / `move_pct_display` per payoff-table row = item 0 of the step 5 server round; the toggle in the step 5 frontend round. Process: a brief row that names an AC is checked against that AC's text before dispatch | - | recorded |
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
| D-A09 expiry cell (3a) | After round 2/2 (8c0c9484, merged c265c88a), Chrome ~15:35 IST: leg rows 37 px (target met), heads unclipped, Hedge H visible; but the leg's expiry text is clipped to "3 Nov (6 days" in the 84 px Expiry column (same class as D-C21) | Widen the Expiry column or show "3 Nov" with the days in its tooltip; one-line change + Chrome re-check; needs a third touch (owner's call) |
| D-A38 (Funds needed row) | REQ-142 not derivable: Zerodha's basket reply has only order-independent initial / final totals and per-order option_premium, no buy-first figure (finding F-62, spec/findings.md; builder 3b-server on 4 recorded buy-only baskets + strategy 54 live) | Owner decision on REQ-142 (F-62 open): another source, or drop the row |
| D-C27 (drawer columns) | Two rounds: r1 widened columns (558 px in 473), r2 compact OI + tighter grid (475 px in 473, Chrome 15:27 IST); the component's own width sum counts the flexible LTP column at its minimum | One gap or a 2 px column trim, then a Chrome re-measure (scrollWidth <= clientWidth); next goal or step 7 if the owner accepts a third touch |
