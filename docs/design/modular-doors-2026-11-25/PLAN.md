# Plan: one door per capability (modular clean-up + 5 bug fixes)

Owner request, 25 Nov 2026: "find the areas or features that are called from multiple places and make sure we have
not written multiple codes for the same part; if yes, compact it into a small module which can be called from
multiple other features" (example given: one exit function: given a strategy, exit all open legs at market).

Written 25 Nov 2026 ~16:40 IST from three read-only reviews (evidence/ folder). Base: branch `fix/ic-live-test-1123`
at e98148e1 (= 5d9b53ca + one test-golden commit). Work branch: `refactor/modular-doors`.

## Step 0 review (25 Nov), applied

A fresh Opus reviewer checked this plan against the code. Item numbers are the reviewer's; owner questions are in
`owner-questions.md`.

- 1: B1 is `exit_strategy(strategy_id, reason, kind, price_source, only=None)` and builds sides and quantities only; the
  price source is live (manual), given (leg stop) or intrinsic (settlement). Missing price: NotYet (monitor) or Refused (manual).
- 2: builder Exit / Exit all keep today's Drafts-Mode diff (`paperOrdersFor`, `paperDrafts.js:103`) and the mixed-basket
  route; F2 shrinks to one shared exit gate/button and one exit-POST helper. No new mixed-basket refusal.
- 3: B1 refuses only the named legs, as a set, when one of them has no live price (ADR-322 (3)); Exit all is as today.
- 4: D-05 builder half is the Positions rule (`listIsStale`); the read-only can-act endpoint is dropped (new API surface).
- 5: D-60 as reported is what ADR-319 (4) / REQ-030 AC-11 ask for; the opposite-action case is owner question OQ-1; the
  ADR-322 (1) mis-citation is fixed to ADR-319 (1).
- 6: Phase 1 test timing, injected wait, and the feed dependency on `add_paper_triggers` written in.
- 7: Phase 1 gains test rows for no feed, failed read and a leg with no feed key, a new template code with its pin, and
  the lock-order question.
- 8: S-20 structural fix moved to `reload` (add the strategy's index for every armed trigger).
- 9: Phase 1 limited to trigger save, monitor and exit prices; the Phase 8 guard gets an explicit exemption list.
- 10: more exit-order builders listed; Phase 8 allowlist; new modules go in `PAPER_MODULES`.
- 11: B2 helper returns legs unordered; each caller keeps its own ordering.
- 12: `POST /strategies/{id}/tracking/exit` kept (4 test files), moved onto the B1 door, behaviour unchanged; OQ-2 asks
  whether to delete it later.
- 13: D-41 basis, before/after charges proof and `lib/usePaperBookRead.js` named.
- 14: F7 is now "share one `/triggers` read"; no new mounting.
- 15: citations corrected; F1 string list extended.
- 16: phases 3 and 4 swapped (one book source first, then exit); Phase 1 adds the ADR-327 spec-text step.
- 17: Phase 1 test lives in `tests_app/` and runs without a database; the DB route twin runs in CI.

## Owner decisions that bound this plan (question tool, 25 Nov)

| # | Decision | Effect on this plan |
|---|---|---|
| Q1 | Start now on the fix branch, on its own branch | Build on `refactor/modular-doors` (from the fix branch). The owner screen-tests the fix branch (5d9b53c) tomorrow 26 Nov; this branch must not be merged into it until the owner says so. |
| Q2 | Scope = clean-up + the 5 bugs that come from the duplicates (D-01, D-05, D-41, D-60, S-20); no new features | Every duplicate below becomes one shared module; the 5 bugs are fixed INSIDE those modules. All other behaviour stays exactly as today. Exit supports "now / market" only. |
| ADR-327 | D-01 rule: in market hours, a trigger whose level cannot be checked against a live price (after asking the feed and waiting up to 3 s) is refused: "Not saved: the live price could not be read, so this level cannot be checked. Try again in a moment." Market closed: unchanged (saved, arms at next live tick). | Phase 1 implements it. `spec/decisions/ADR-327.md` is committed on this branch. |

Out of scope (written down so nobody builds them): paper limit-order exit (new feature; needs owner rules on leg order
and partly filled legs, ADR-281 / F-102); plan target / stop-loss / time exit placing orders (today they only alert;
feature S-10); bulk delete; the other 23 bugs of `evidence/combined-findings-2026-11-25.md` (separate fix round);
real (Kite) order placement of any kind (ADR-281: paper only).

## The principle (why)

One capability = one function (a "door") that every screen, rule and route calls. A fix in the door fixes every
caller. Today the same capability is rebuilt in several places, and three of today's defects are exactly that:
D-01 (the stop-save check read the price a different way from the monitor), D-05 (Positions blocks Exit on stale
prices, the builder's own Exit does not), D-41 (two panels on one builder screen read leg prices from two sources).
Prefer a structural guarantee over a detector (kit rule C3): the door is the only path; a guard test keeps it so.

## Inventory (what is duplicated today) — evidence: evidence/review-backend.md, evidence/review-frontend.md

Server (backend/):

| # | Capability | Copies today | Door to build | Bug fixed inside |
|---|---|---|---|---|
| B3 | Read a live price (leg or index) | 9-11 readers, several hold mechanisms, 4-5 hold nothing; `live_push.hold_and_read` (live_push.py:95) is bypassed. Phase 1 moves only trigger save, monitor and exit prices; display/advisory readers go to a deferred issue (RCA). Readers correct today stay: `background.py:272`, `:1192` (own process, own subscription), `adjustment_readers.py:611` (only centres a window) | `read_market(ctx, underlying, leg_keys, need_index, purpose)`: asks the feed to hold what it needs, waits up to 3 s, returns prices + a state per price (live / stale / missing / market closed) | D-01, S-20 |
| B5 | Trigger save: "already crossed?" | `routes/paper.py:1637 _already_crossed` reads with no hold; keep route same shape. Today: no ctx saves (:1641), an exception saves (:1661), a leg with no feed key is skipped and saved (:1656) | `check_trigger_levels(...)` on top of `read_market`; ADR-327 states (no feed in market hours, failed read: refused; market-open comes from the calendar, not the snapshot). Read BEFORE taking the strategy row lock (:1675; monitor `_fire` waits behind it), or record why not | D-01 |
| B4 | "May this act now?" (market open, prices live) | `paper_limit.refuse_when_closed` (paper_limit.py:117), `paper_monitor.on_quote` calendar (:177), `market_state` (`routes/outcome.py:224`), `paper.is_live`, others | `may_act(ctx, action, at) -> Allowed | Refused(reason)`, server-only (no new read-only endpoint: out of scope Q2). Screens use the book-read state instead (F1/F2) | D-05 (server half) |
| B1 | Exit legs (paper) | 4 server builders of "opposite side of the open book" (`routes/paper.py:1296`, `routes/tracking.py:513/550`, `paper_monitor.py:205/231`, `paper_settlement.py:164/171`) + the browser builds the basket (`frontend/src/lib/paperList.js:199 exitRowsFor`). More exit-order builders outside paper, NOT merged (Phase 8 allowlist): `ofo/execution/send_guard.py:131,191` (real path), `ofo/execution/sequence.py:398 exit_orders`, `ofo/reconciliation/resolution.py:343`, `ofo/adjustment/approaches.py:412 close()` (preview), charge-estimate opposite sides (`extremes_charges.py:59`, `round_trip.py:63`, `routes/adjustment.py:446`) | `exit_strategy(strategy_id, reason, kind, price_source, only=None)`: reads the open net book under the strategy lock, builds sides and quantities only, buys first (ADR-117 / D-02). `price_source` is `live` (read_market, manual), `given` (the crossing tick, leg stop; `paper_monitor.py:247`) or `intrinsic(close)` (settlement, after close; `paper_settlement.py:125,:178`). A missing price returns NotYet (monitor stays armed, `:225-226`) or Refused (manual). Refuses the named legs as a set when any of them has no live price (ADR-322 (3); today `paper.py:1240`); Exit all on a trade with an unpriced wing behaves as today. Manual callers keep `paper_limit.place_checked` (`paper.py:1322`, `tracking.py:554`: market-hours refusal and adjustment-limit count); monitor and settlement keep `paper_store.place`. Serves the 4 server paths only: manual Positions exit route, tracking exit, monitor leg stop / conditional exit, settlement. `POST /strategies/{id}/tracking/exit` stays and moves onto this door, behaviour unchanged (closes from the entry legs, `tracking.py:550`) | D-05 (one rule for every Exit) |
| B6 | Strategy money figures (P&L, booked, charges) assembled for the API | `routes/paper.py:651 _figures`, `routes/tracking.py:312 _figures`, `routes/outcome.py:389`, `routes/adjustment_history.py:333`, `routes/adjustment.py:428` | `strategy_money_view(strategy_id, prices)` (engine maths stays where it is; only the assembly is merged) | D-41 (server half) |
| B2 | Real exit "close list" | `execute_plan.py:223 exit_legs`, `ofo/execution/partial.py:788`, + paper copies | share only `open_legs_to_close(book)`; the helper returns legs unordered (or contract-sorted) and each caller keeps its own ordering (Kite basket sorts by contract key, `execute_plan.py:223-226`; paper sorts buys first, `paper_store.py:98`). The real gate stays separate. Tier A review | none (maintenance) |
| B7 | Raise an alert | `paper_trigger_store.add_alert`, `playbook_store.open_suggestion`, `notifier.notify` | `raise_alert(kind, strategy_id, facts)` | S-20 wording path |
| B8 | Order recording | `paper_store.place` — already one door | none; B1 feeds it | — |

Screens (frontend/src/):

| # | Shared thing | Copies today | Module | Bug fixed inside |
|---|---|---|---|---|
| F1 | Price freshness rule + wording | 6 separate checks, 8+ strings (`tracking.js:108` and `paperList.js:16` hold the same text twice; also `PaperStrategies.vue:188,190`, `tracking.js:117`, `legPicker.js:7,100`, `CreateStrategyPage.vue:25`, `useChainLive.js:14`, `IndexStrip.vue:15`; `SummaryCards.vue:160` is the D-17 time-value basis prop, not a freshness string) | `lib/priceState.js` + `usePriceFreshness` | D-05, D-39 label (only where it is the same rule). D-05 builder half: builder Exit, Exit all and per-leg Exit disabled, and figures shown as a dash, when the last book read failed (`paperReadFailed`, `lib/usePaperBookRead.js:25`; the Positions rule `listIsStale`, `PaperStrategies.vue:249`). Today `paperReadFailed` is passed to `PaperBookPanel` but disables nothing (Exit all `PaperBookPanel.vue:16`; `exitAllPaper` checks only `paperStale`), and the panel only swaps one line (`:117`) |
| F2 | Exit paper positions | 2 gates and 2 POSTs: `PaperStrategies.vue:240` (blocks on failed read) vs `StrategyBuilderPage.vue:438,443` (`exitAllPaper`/`exitPaper` only edit draft legs; checks only `paperStale`) + `PaperBookPanel.vue:16` (Exit all never disabled). Builder orders come from `paperOrdersFor` (`lib/paperDrafts.js:103`), the one Drafts-Mode diff: one mixed basket of exit and add orders, adjustments carry suggestion_ids (REQ-163), one transaction (`paper.py:1327-1339`); `legsAfterExit` (`paperDrafts.js:295`) keeps other pending edits, so a builder Exit also posts them. `exitRowsFor` (`paperList.js:199`) is the Positions copy | One shared exit gate/button (`usePaperExit` + one `ExitButton`) and one exit-POST helper. `paperOrdersFor` and the mixed-basket route `POST /paper/strategies/{id}/orders` stay unchanged (behaviour unchanged; pending edits still go with an Exit). B1 serves the 4 server paths only. No new server-side refusal of mixed baskets | D-05 |
| F3 | Leg price per leg | builder alone polls 3 endpoints; Net Positions table vs `/tracking` panel (`TrackingPanel.vue:32`), each with its own 5 s timer. Panel leg rows come from `/strategies/{id}/tracking` (`TrackingPanel.vue:229,:246`), its total from the shared paper book (`sharedTotal`, `:121`); `AdjustCompare.vue:262` also reads `/tracking` | Extend `lib/usePaperBookRead.js` (no new `usePaperBook`): one poll, one source, + `LegPrice`. Name the basis and spec line first: `display_price` includes the last close after hours, `leg_price` is live only (`ofo/tracking/paper.py:110,:120`), so a source change alters the after-hours panel | D-41 |
| F5 | P&L total / booked / unbooked / as-of | 3 parsers, 2 pollers of `/paper/strategies` | `PaperPnlBlock` + the same reader (`lib/usePaperBookRead.js`). Leg rows are before charges, the total after charges (`PaperBookPanel.vue:53`) | D-41 |
| F6 | Add or move a leg | door exists (`lib/legDoor.js`); dialog copied (`LegPicker.vue:676`, `StrategyBuilderPage.vue:996`); strike step, ready-made, chain link and Compare entry points bypass it | `useLegDoor` + one `DuplicateLegDialog`; every entry point through it (ADR-319 (1); the earlier ADR-322 (1) citation was wrong, that one is about review rounds) | D-60 (see Phase 5 and OQ-1) |
| F7 | Stops panel | `PaperStops` and `TrackingPanel` each read `/triggers` | share one `/triggers` read between them; no new mounting (a builder stops panel would be a new feature) | — |
| F8 | Rename | 2 UIs, one write call | `useRename` | — |

Helper-level duplicates from the 23 Nov review (`evidence/duplicates-2026-11-23.md`, RANK 1 RISK R1-R12): expiry
cut-offs (R1), ownership SQL (R2), rupee text (R3), setting-in-force (R4), intrinsic value (R5), Kite money parsers
(R6), Decimal parsing (R7), Kite token wiring (R8), Kite HTTP paths (R9), browser time formatting (R10), database
now (R11), to-IST (R12). R1 needs an owner answer (REQ-109 AC-7 pins 15:45) — park it. RANK 2/3 groups: skip unless a
door above touches them.

## Phases (in this order; each phase = tests first as its own commit, then the code commit)

Each phase states Core / Proof. "Behaviour unchanged" means the existing tests for every caller still pass unmodified,
except tests that pin one of the 5 bugs (change those in the tests-first commit and say why).

1. **B3 read_market + B5 trigger check (D-01, S-20, ADR-327).**
   Core: a save of "Above X" with the index above X is refused even when nothing else holds the index.
   Scope: trigger save, monitor and exit prices only. Display and advisory readers (`routes/outcome.py:1263`, pushes
   `live_push.py:170`, `chain_push.py:305`, `index_push.py:84`) are NOT moved (they would add up to 3 s waits); they go
   to a deferred issue.
   Proof: `evidence/repro_d01.py.txt` (rename to .py to run; it hard-codes REPO = D:\..., use the repo root) turned into
   a test (`tests_app/test_paper_trigger_unheld_index.py`, no database needed; `_kite_fixture` is already imported from
   `tests_app`, e.g. `test_bus_socket.py`; the DB route twin runs only in CI or on local Postgres). Frames are pushed
   only AFTER the hold subscribes (`d01-root-cause.md` section 5): ticks for unheld tokens are dropped
   (`kite_provider.py:114-118`). The 3 s wait comes from an injected clock or wait function (no real sleep;
   `tests/test_no_wall_clock_asserts.py`). The route also needs the feed dependency: `add_paper_triggers`
   (`paper.py:1668`) has none today. Rows: unheld index -> refused `paper_trigger_already_crossed`; held -> refused;
   market open + no price after 3 s -> refused with the ADR-327 line (new template code plus its pin in
   `tests/errors/template_pins.json`); market closed -> saved; market open + no feed (ctx None) -> refused; market open
   + read raises -> refused; a leg with no feed key -> refused in market hours (today skipped and saved). The read
   happens before the strategy row lock, or the plan records why not.
   S-20: `_index_now` is synchronous inside `_fire`'s transaction (`paper_monitor.py:229-230, :262`); do not put a 3 s
   read there. Structural fix in `reload` (`:136-146`): add the strategy's index to `extra` for every armed trigger, not
   only conditional exits. The leg-stop alert then carries the index value when the index ticks.
   Spec text (same commit as the code): add ADR-327 to `views/spec-digest.md` by running
   `python tools/build_spec_digest.py .` (views/ is generated; never hand-edit; the digest lacks ADR-327 today), and add
   a one-line note on `spec/requirements/REQ-109.md` AC-8 and `spec/decisions/ADR-317.md` that ADR-327 supersedes (2) in
   market hours (grep the exact lines first; if a hook refuses the ADR-317 edit, put the note only in REQ-109 and say so).
2. **B4 may_act + F1 priceState (D-05 server half, D-39 where same rule).** `may_act` is server-only: the route and the
   exit door use it. The screen uses the book-read state (`paperReadFailed` / `listIsStale`) through `usePriceFreshness`.
   Proof: a test per action state (open+live, open+stale, open+missing, closed) on the server; a vitest per state on
   `usePriceFreshness`.
3. **F3 + F5 + B6 one paper book source (D-41).** The builder's Net Positions table and Paper P&L panel read the same
   prices from one poll (`lib/usePaperBookRead.js` extended). Name the price basis and the spec line (after hours:
   `display_price` vs `leg_price`) before changing the source. Proof: vitest rendering both panels from one fake book
   shows identical LTP per leg and "sum of leg P&L == the before-charges total"; server test that paper and tracking
   figures for one strategy come from `strategy_money_view` and match.
4. **B1 exit_strategy + F2 shared exit gate (D-05).** The 4 server exit paths (manual Positions exit route, tracking
   exit, monitor leg stop / conditional exit, settlement) call `exit_strategy`; the builder keeps its Drafts-Mode diff
   and mixed-basket route. `POST /strategies/{id}/tracking/exit` stays (tests: `test_strategy_tracking_list.py` ~20
   calls from :137, `test_paper_adjustment_limit.py:197`, `test_paper_save_paths_fx2.py:64,72,103`,
   `test_scenario_isolation.py:99`; also `scenario_mode.py:93`, `paper_limit.py:3` docstring) and moves onto the door;
   OQ-2 asks whether to delete it later. New modules (`read_market`, `exit_strategy`) are added to `PAPER_MODULES` in
   `tests_app/test_paper_order_door.py:24`.
   Proof: one test per caller (manual all, manual subset, conditional exit, leg stop, settlement, tracking exit)
   asserting the same stored rows (side, qty, kind, reason, buys-first order) as before; settlement still prices at
   intrinsic after close; a leg stop with a missing price stays armed; builder Exit, Exit all and per-leg Exit disabled,
   figures a dash, when the last book read failed (vitest, same rule as Positions).
5. **F6 useLegDoor (D-60).** Strike step, Shift, Width, Hedge, picker, edit form, ready-made, chain link, Compare: all
   through the door (ADR-319 (1): same-action moves ask Increase / Keep separate / Cancel; one live question per move).
   D-60's reported case (a Sell onto a held Buy of the same contract) is what ADR-319 (4) / REQ-030 AC-11 ask for today
   (`legDoor.js:15 sameContract` needs the same action), and the strike step already goes through `admitLegs`
   (`StrategyBuilderPage.vue:803-815`; `RELATIVE_CONTROLS` includes step, `lib/legEdit.js:54`), so that proof passes
   today. The opposite-action step is owner question OQ-1; build ADR-319 (4) as written (no question for opposite
   action) unless the owner answers otherwise. Proof: vitest per entry point: moving onto a held same-action contract
   opens the question; Escape = Cancel leaves the draft unchanged.
6. **B2, B7, F7, F8** (maintenance, behaviour unchanged). B2 touches the real-order path: Tier A review (fresh Opus,
   adversarial) before it lands; it must not change what is posted to Kite (basket order stays contract-sorted).
7. **23 Nov helpers R2-R12** where a phase above did not already absorb them (R1 parked for the owner).
8. **Guard tests (keep it modular).** A repo test that fails when: a route/monitor calls `read_snapshot` or a
   provider quote outside `read_market`; something other than `exit_strategy`/`paper_store` builds paper exit orders; a
   frontend file defines its own not-live string or exit POST. Explicit exemption lists: price readers correct today
   (`background.py:272`, `:1192`, `adjustment_readers.py:611`) and the non-paper exit-order builders named in B1
   (real path, reconciliation, preview, charge estimates). Detector is the second layer; the door is the first.

## How the cloud session works (rules)

- Read first: CLAUDE.md, `docs/process/runbook.md`, `.claude/kit/GUIDE.md`, this PLAN.md, the evidence files,
  `spec/decisions/ADR-327.md`, ADR-317, ADR-322, ADR-117, ADR-281, F-102 (spec/findings.md).
- Model routing (CLAUDE.md hard rule): the main session manages; builders Sonnet; Opus only for Tier A (B1 exit,
  B2 real path, B3 price door) review.
- Each phase: tests-first commit (red), code commit (green), then `python tools/ci_local.py`. Targeted pytest/vitest
  per file; long output to a log, read the tail. No DB test runs against the owner's VPS from the cloud; DB tests run
  in CI on the PR.
- Money is Decimal, never float (ADR-008). Never call a broker order endpoint. Paper only.
- Every PR body carries the Spec-deviation block (`Class: 3` for ADR-327 with the decision id; `Class: none`
  otherwise) and `Fixes`-free wording for partial items (no "fixes #N" unless the whole issue is done).
- Park, don't drag: 2 failed rounds on a phase -> write a `parked` note in this folder with evidence and go on.
- Questions for the owner are NOT asked in the cloud session: append them to
  `docs/design/modular-doors-2026-11-25/owner-questions.md` with a recommendation and continue with the spec-conformant
  choice.
- End: push `refactor/modular-doors`, open a DRAFT PR into `fix/ic-live-test-1123`, never merge, never mark ready.
  The owner merges after tomorrow's screen tests on the fix branch.

## Done means

- Phases 1-5 landed with their proofs green; 6-8 landed or parked with a note.
- `python tools/ci_local.py` TOTAL PASS on the final head; CI green on the draft PR (or every red explained).
- A results file `docs/design/modular-doors-2026-11-25/RESULTS.md`: per phase, the door, the callers moved
  (before -> after counts, e.g. "price readers: 11 -> 1 door + 0 bypasses"), the tests, and anything parked.
- A screen-check list for the owner (what to click to see D-01, D-05, D-41, D-60, S-20 fixed), since the cloud
  session cannot drive the live app.

## Who owns what (added 25 Nov ~16:50 IST, to stop two sessions fixing the same thing)

Two cloud sessions work at once. No item belongs to both.

| Session / branch | Owns | Must not touch |
|---|---|---|
| GC-ICLIVE session, Part F, on `fix/ic-live-test-1123` | The owner's Q2-Q6 answers (its ADR-326: Take profit refused at a loss after charges; 24-hour IST everywhere incl. the disconnect sentence; adjustment pop-up quiet 5 min after entry when its rule was already true; header totals and timeout messages kept), Q7 and Q8, screen-check FAILs D-18 and D-44 | D-01, D-05, D-41, D-60, S-20 and the shared modules of this plan |
| Modular session (this plan), on `refactor/modular-doors` | Phases 1-8 and the bugs D-01, D-05, D-41, D-60, S-20 (D-01 rule = ADR-327) | The Part F items above, `docs/process/owner-questions-2026-11-24.md` |

ADR numbers: ADR-326 = the GC-ICLIVE session's Q2-Q6 answers; ADR-327 = the D-01 rule (this branch). Any new
decision record on either branch takes the next number free on BOTH branches (`git ls-tree` both before writing).
Merge order: Part F lands on the fix branch first; this branch merges the fix branch head before its final push.
