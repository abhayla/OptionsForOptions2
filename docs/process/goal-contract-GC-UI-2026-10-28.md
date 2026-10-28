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
- Browser: the owner's Chrome (claude-in-chrome) at 1536 x 864 so the owner can watch; Playwright MCP is headless.

## Items

Row ids are from the differences document; `*` = SPEC CHANGE (approved, ADR-204).

| Step | Item | Rows | What | Tier | Proof | Status |
|---|---|---|---|---|---|---|
| 0 | read first | - | Read the list above; write the overlap list here (which steps share StrategyBuilderPage.vue / ChartCard / the summary block; what each reuses) | C | Overlap list in this file | Not started |
| 1 | CORE: independent data checker | (confirms D-A46, D-A47, D-B33, D-B35, D-B36, D-B38, D-B51, D-C33) | A script in the repo (`scripts/checks/ui_data_check.py`), own Black-Scholes and payoff code, reads what the API/screen shows plus the market inputs it used, recomputes: summary (max profit/loss, breakevens with and without charges, reward/risk, net premium, time and intrinsic value on the spec's basis), payoff points at expiry and estimated-now, P&L table cells, Greeks per leg and total (per unit and per lot), Paper/tracking totals | A | Figure-by-figure table for 3 real strategies; each DATA row confirmed or cleared with numbers | Not started |
| 2 | DATA fixes | D-A46, D-A47, D-B33, D-B35, D-B36, D-B38, D-B51, D-C33, D-C27, D-C31 + every mismatch step 1 finds | Defect-fix contract per class; money maths (A46, A47, C33) Tier A with an Opus review | A (money) / B | Checker green on the same 3 strategies + each fix re-read on the live screen | Not started |
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

## Found during the run

| F | Step | What failed (seen) | Class / RCA | Fix commit | Re-test |
|---|---|---|---|---|---|

## Parked

| Row / item | Why (evidence) | What is left |
|---|---|---|
