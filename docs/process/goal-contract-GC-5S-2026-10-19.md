# Goal contract GC-5S (Mon 2026-10-19, one trading day): live-market-data screens, built and proven on real ticks, in parallel with GC-3L

Chain: `goal-chain.md` (rules, scorecard). Owner request 2026-10-19 ~10:00 IST: "prioritize the screens ... which
requires live market data for your testing and work on them now ... I will run it in a separate session".
Written 2026-10-19 10:08 IST (PowerShell `Get-Date`) from main 9f028b8.
**Chain-rule exception: "owner-approved parallel run 2026-10-19".** GC-3L holds `lock/gc-3l` and stays RUNNING; this
contract takes its own lock `lock/gc-5s` (chain rule 2 push, other name) and never touches `lock/gc-*`.
**Owner needed: NO** - except one Kite login in a private window if the stored session on ofo_dev has expired (and only
if GC-3L is not mid-step; ask GC-3L's owner window first).
**Cap: one trading day - lock + 7 h, never after 17:30 IST.** Live-data proofs only 09:15-15:30 IST; outside that,
recorded fixtures (`tests/fixtures/kite_ws/`, `OUTCOME_REPLAY=1`).

Core: the existing live outcome socket (`/api/strategies/live`, `backend/ofo_app/routes/live.py:19`, one shared
fan-out, `OutcomeResponse` with `spot_level`/`spot_at` and per-quote `health`, `routes/outcome.py:299-330`) feeds a NEW
screen with real ticks - not the Strategy Builder.
Proof: item 1's page on :4174 against the API on :8766 (`LIVE_MARKET=1`, ofo_dev) during market hours shows at least
3 successive pushes with changing `spot_at` for one saved draft strategy, plus a forced disconnect showing REQ-049
AC-5's message; screenshot + the socket frames' timestamps recorded as evidence rows. **No other item starts until
this passes.** Fails -> STOP, record the output, write the fix as the next contract.

## Isolation from GC-3L (hard rules; any breach = stop)
- **The main checkout `D:\Abhay\Ventures\OptionsForOptions2` is GC-3L's running code.** Its API (8765) and preview
  (4173, serving `frontend/dist`) run from it. This run NEVER runs a mutating git command there (no checkout, switch,
  pull, stash, reset, merge, commit) and NEVER runs `npm run build` / `npm install` in its `frontend/`. All work,
  builds and servers run from this run's OWN worktree (`git worktree add` named `OptionsForOptions2-gc5s`, outside
  the main folder), from `origin/main` fetched with `git fetch` only.
- Never place, prepare, cancel or check an order; never call `POST /strategies/{id}/execute` or
  `.../execution/return`; never edit `backend/ofo_app/routes/execute*.py`, `execute_plan.py`,
  `execution_return.py`, `backend/ofo/execution`, `orders`, `reconciliation`, or `ExecuteStrategyPage.vue` /
  `ExecutionReturnedPage.vue`.
- Never stop or restart anything on ports 8765 / 4173; stop only the PIDs this session started (by PID, run-discipline
  rule 5). Never force a catalogue update. Never edit strategies 1-11 on ofo_dev; this run's own drafts are saved
  with names starting `GC-5S` and are never executed.
- Kite allows 3 websocket connections per app: this run opens at most ONE (its API process). If the feed refuses a
  connection, stop live proofs, use the replay, never retry in a loop.
- **No product merge while GC-3L runs** (tracker status `held #PR` = "HOLD until GC-3L ends"; GC-3L runs on main's
  head). Every PR is a draft until `lock/gc-3l` is gone; then merge in item order.

## Step 0 (before 09:15 IST where possible)
1. `git fetch` (never `git pull` in the main checkout); create this run's worktree from `origin/main`; take
   `lock/gc-5s`; confirm `lock/gc-3l` exists (expected) and record it. This contract file is committed by GC-3L's
   close-out docs PR; until then read it from the path the owner gave.
1b. **Owner decision 2026-10-19 (~10:15 IST), verbatim:** "for look and content of the screen, you should refer other
   brokers, other tools which do the similar work, and then take a decision ... get the right role which will study
   across all the apps ... Obviously our business requirement must be followed, but look and feel ... and what are the
   contents of the screen should be provided by the role ... The font and all those things, the look and feel, you can
   fetch from global.md." Consequences, written into the spec in this run's first docs commit (a new ADR, next free
   number, provenance = this quote plus the owner's follow-up the same minute: "layout question is not only for home
   and option chain screen, it's for all other screens also"): (a) every screen REQ still `Specified` (REQ-008 Home,
   REQ-029/030/031 Option Chain, REQ-010/011 and any other screen REQ this run reaches) moves to `Approved` - its ACs
   are the business rules and stay exactly as written; (b) the CONTENT and LAYOUT of EVERY screen in the app, now and in
   later contracts, inside those ACs is decided by the design role below, never asked of the owner; (c) look and feel (font, colours,
   theme) comes from `D:\Abhay\GLOBAL.md` section 3 "Design & UX preferences" - read it there, never copy its text into
   the repo (GLOBAL.md holds private data; reference it by path).
1c. **Design research (before any screen's builder brief; runs in parallel with item 1's builder):** one agent in the
   role "senior product designer for Indian retail options/broker apps" studies how Sensibull, Opstra, Zerodha Kite,
   Dhan (options trader), Upstox, Streak, AlgoTest and Angel One lay out the same screens (home/dashboard, option chain,
   live strategy/positions, index strip): what each shows first, column sets, defaults, empty states, mobile at 390 px.
   Output: `docs/design/screens-research-2026-10-19.md` with, per screen, a recommended content list and wireframe
   (text), each item mapped to the REQ AC it serves, sources cited (URL or screenshot path), and anything that would
   breach a business rule (e.g. ADR-002 no standalone order entry, ADR-003 no advice wording, REQ-029 AC-6 no order
   placement from the chain) explicitly dropped. The orchestrator decides from it and records the decision in the
   design note; each builder brief then carries `Design basis: <section of that note>`.
2. Run `python tools/build_order.py . --may-start` for REQ-044, REQ-049, REQ-072 (plain command, one per call); a
   non-zero exit = that item is parked unless an `order_override` is written in its work item with the owner basis.
3. Create work items (`W-113`.. via the next free id) for items 1-3 below; `check_brief.py` on every brief; each brief
   carries `Core:`/`Proof:`, `Copy from:` (legacy-reuse.md map rows or `none - <reason>`), Budget, B4 standing items.
4. Start servers FROM THIS RUN'S WORKTREE (GC-3L delta section 3 recipe, other ports): a one-line script file `LIVE_MARKET=1` then
   `python scripts/orchestrator/dev_run.py . python -m uvicorn ofo_app.main:create_app <factory flag> --app-dir backend
   --loop ofo_app.event_loop:selector_loop --host 127.0.0.1 --port 8766`, background; frontend `npm run build`, then
   `OFO_API_TARGET=http://127.0.0.1:8766 npm run preview -- --host 127.0.0.1 --port 4174`. `/api/health` on :4174 = 200.
   Record both PIDs.

## Items (in order; screens table below)
1. **Live Strategies page (core).** `/strategies/live-strategies`: saved strategies from `GET /strategies`
   (`routes/strategies.py:329`), each row subscribed via `useStrategyLive.js` (`LIVE_PATH`, line 13) showing the
   engine's values as given (strings, no browser maths, ADR-008), the index spot + `spot_at`, the REQ-049 health state,
   the AC-5 disconnect message and AC-6 per-strategy paused badge. No REQ-043 colours (GC-4). Done: core proof above +
   Vitest + an e2e on `OUTCOME_REPLAY`; verifier PASS for the ACs claimed.
2. **Market -> Underlying/index view.** `/market/underlying-index-view`: live NIFTY 50 and SENSEX with REQ-072 AC-2
   health states. Needs a NEW read-only route/socket on the shared feed (no index-only route exists today) - Tier A
   (live-data liveness). Done: live run shows both indices ticking with health; a stale index shown as stale; Tier A
   verifier PASS.
3. **Home (REQ-008, approved per 1b).** `/home/overview`: the three adaptive states of AC-2, AC-3's new-user lines,
   AC-4's live strip reusing item 2's index feed, AC-5 (Zerodha offered only in context). Content per the design note.
   Tier B (no money computed). Done: Vitest per state + e2e of all three states; verifier PASS.
4. **Option Chain (REQ-029/030/031, approved per 1b).** `/market/option-chain`: a NEW read-only chain route on the
   shared feed (Tier A: live-data liveness; IV/Greeks only from the one engine, ADR-008), Calls | Strike | Puts, default
   columns and UX-level filters per REQ-029, live LTP/bid-ask, no order placement (AC-6), Pro-only (AC-7). Size L:
   split into (4a) the route + live data proof, (4b) the screen; read REQ-030/031 in full before the brief. Park what
   does not fit the cap with a `parked` issue naming the next step.
5. **Strategy screen "Live Position" tab (REQ-044 AC-2)** reusing item 1's component, if time; else park.
6. **Remaining placeholder screens, in this order, as far as the cap allows** (each: design-note section first, then
   builder -> verifier): Market context (REQ-010/011), Learn, Alerts list shell (display only; alert logic is GC-4),
   Settings pages not held by #397. Screens on held branches (Positions P&L #398/#410, My Strategies #393, Settings
   W-089 #397) and order screens (Orders, Execute) are NOT touched here. Whatever is left is listed in the close-out as
   the next screens contract, in this same order.

## Delivery
`deliver` skill per item: builder (own worktree) -> verifier (fresh context; Tier A = fresh Opus, adversarial) ->
`record_evidence.py` -> trace check -> draft PR (Spec-deviation block; no close keyword before `#N`) -> after GC-3L's
lock is gone: `gh pr update-branch N` then `python tools/merge_when_green.py N`. Fast checks before each push
(CLAUDE.md "Fast delivery" 1); at most 2 review rounds; then park (run-discipline B1). Findings registered the turn they
are proven. One docs PR at close-out (contract row, tracker rows, handover).

## Stops
- Any isolation-rule breach; the core proof failing; a Kite login needed while GC-3L is mid-L2/L3.
- A screen whose requirement is not Approved and not covered by 1b: not built; listed in the close-out.
- **Conflicting business requirements (owner rule 2026-10-19, verbatim: "never take auto decision when there is a
  conflicting business requirement given by me"):** when two business rules (ADR rows, REQ ACs, owner answers, the
  design note vs a REQ) contradict each other, STOP that item only, ask the owner ONE question quoting both texts with
  their ids, the real case where they clash and a recommended resolution; owner away -> park it in the owner-questions
  file. Never resolve it by the design role, technical judgement or "newer wins". The answer goes into the spec as a
  decision row the same turn. Other items continue.
- Owner questions only for BUSINESS rules (what a user may do, see as a rule, or pay; scope); never for layout,
  content or look (1b). Owner away: park the question in `docs/process/owner-questions-2026-10-19.md` and continue.

## Close-out
Tracker rows updated + `tracker_check.py`; servers on 8766/4174 stopped by PID; worktrees removed (prove main intact);
lock deleted; DONE / PENDING / PARKED / NEXT summary + evidence table.

## Screens table (live-data first)

| # | Screen / route | REQ / W | ADRs | Reads (exists?) | Size | Tier | Status |
|---|---|---|---|---|---|---|---|
| 1 | Live Strategies `/strategies/live-strategies` (nav.js:21) | REQ-044 AC-2 (Approved), REQ-049 AC-4..6 (Approved); new W | ADR-008, ADR-010, ADR-015, ADR-077 | `GET /strategies` (strategies.py:329, yes); WS `/api/strategies/live` (live.py:19, yes) | M | B if frontend-only; A if `live_push` changes | **this contract, core** |
| 2 | Underlying/index view `/market/underlying-index-view` (nav.js:41) | REQ-009 AC (Approved), REQ-072 AC-2 (Verified), REQ-049 AC-2/4; new W | ADR-050..065 per REQ-072 | index-only route: **does not exist** (new) | M | A | this contract |
| 3 | Strategy "Live Position" tab | REQ-044 AC-2 | ADR-010 | same socket (yes) | S | B | this contract, if time |
| 4 | Positions P&L/risk `/positions/pnl-risk` (nav.js:33) | REQ-044 AC-3 part 2; W-111 part 1 held #410 on #398 | ADR-109, ADR-110 | Kite positions read (on held branches only) | M | A | **not here** - GC-3F, after #398/#410 merge |
| 5 | Option Chain `/market/option-chain` (nav.js:40) | REQ-029/030/031 | ADR-007, ADR-056, ADR-061, ADR-063 | chain route: none | L | A | this contract, item 4 (approved per 1b) |
| 6 | Home Overview `/home/overview` | REQ-008 | ADR-027 | none | M | B | this contract, item 3 (approved per 1b) |
| 7 | My Strategies / Completed | W-109 | - | `GET /strategies` | S | B | held #393 (GC-3F) |
| 8 | Market context, Learn, Orders, Alerts, Settings pages | REQ-010/011 Specified; Orders = order paths; Alerts = GC-4; Settings = W-089 held #397 / Stage 5 | - | - | - | - | not here |
