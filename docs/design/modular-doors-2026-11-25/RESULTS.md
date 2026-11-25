# Results: one door per capability (modular clean-up)

Plan: `PLAN.md`. Owner questions: `owner-questions.md`. Branch `refactor/modular-doors`.

**Status: Step 0 DONE at `4350f336` (merge of `fix/ic-live-test-1123` at `6574e475` into `refactor/modular-doors`;
pushed state to be filled at push). Before it, PAUSED 25 Nov 2026 on the owner's instruction (relayed by the GC-ICLIVE
orchestrating session) after Phase 2, pushed head `0e30edc1`. Phases 1 and 2 are done and pushed; Phase 3 is part-way,
saved as a patch (`phase3-wip.patch.txt`); Phases 4-8 are not started.** This file is written so a fresh session can carry
on from it alone. Read `PLAN.md` for the why and the per-phase Core / Proof, then this file for what is done.

| Phase | Scope | State | Where |
|---|---|---|---|
| 1 | B3 `read_market` + B5 `check_trigger_levels` (D-01, S-20, ADR-327) | DONE, pushed | `fce27095`, `58bd51d9`, `3b8ae9b7` |
| 2 | B4 `may_act` + F1 `priceState` (D-05 server half, D-39) | DONE, pushed | `707bc5d4`, `0e30edc1` |
| 3 | F3 + F5 + B6 one paper book source (D-41) | PARTIAL: red tests committed in the patch; code written but unreviewed and ungated | `phase3-wip.patch.txt` (not on the branch) |
| 4 | B1 `exit_strategy` + F2 shared exit gate (D-05) | NOT STARTED | `PLAN.md` Phase 4 |
| 5 | F6 `useLegDoor` (D-60) | NOT STARTED | `PLAN.md` Phase 5, OQ-1 |
| 6 | B2, B7, F7, F8 (maintenance; B2 needs Tier A review) | NOT STARTED | `PLAN.md` Phase 6 |
| 7 | 23 Nov helpers R2-R12 (R1 parked) | NOT STARTED | `PLAN.md` Phase 7 |
| 8 | Guard test with exemption list and allowlist | NOT STARTED | `PLAN.md` Phase 8 |

## Step 0: merge of fix/ic-live-test-1123

| Claim | Evidence |
|---|---|
| Merge | `4350f336` of `6574e475`; the fix branch's App tests CI was green (run 45645290337) |
| Conflicts | `coverage-stages.yaml` (all four rows ADR-326..329 kept, S6.7); `spec-digest.md` (regenerated); `coverage-register.md` (regenerated, 1035 rows) |
| Generated files | OpenAPI and reply inventory regenerate with no diff |
| vitest | 223 files, 2622 tests passed |
| pytest tests/errors + d57 + money scan | 721 passed |
| DB selection, base `b1055c5` | 218 of 218 files exit 0 on fresh clones (4089 passed, 1 skipped = `test_execute_replay_api` live-server test) |
| ci_local | TOTAL 16 passed, 0 failed, 5 skipped |

### Section 9 first commands

| Phase | First command | Result |
|---|---|---|
| Step 0 | vitest | green (agrees) |
| 3, 4 | run at phase start | tests not yet written |
| 5 | `leg-step-duplicate-d60` + `leg-duplicate-d60` | 36 passed (agrees) |
| 6 | `test_execute_route -k exit_legs` | 1 passed (agrees); `exit_legs` at `execute_plan.py:223-226` sorts `sorted(held.items())` |
| 7 | `test_strategy_alert_style` | 37 passed (agrees) |
| 8 | G1 AST scan | 34 sites by `file::function`, 44 calls in 17 files; all in plan-named files except the door itself (`market_read.py::_read`); exemptions must be keyed by `file::function` |

Verdict: no result contradicts any phase; no phase parked.

## Phase 1: B3 read_market + B5 trigger check (D-01, S-20, ADR-327)

**Door.** `backend/ofo_app/market_read.py`: `read_market(ctx, feed, underlying, leg_keys, need_index, purpose, *, wait)`
holds the legs (and the index) through `live_push.hold_and_read`, waits up to 3 s, and returns a state per price
(live / stale / missing / market_closed). `hold_and_read` gained optional `sleep` and `now` seams (loop defaults), so
tests never sleep. `check_trigger_levels` in `routes/paper.py` replaces `_already_crossed`: market closed saves; market
open with no context, a leg with no feed key, a failed read or no live price after the wait is refused with the new
template `paper_trigger_price_unreadable` (ADR-327); a live crossed price keeps `paper_trigger_already_crossed` /
`paper_trigger_leg_already_crossed`. The read runs before the strategy row lock; open legs are re-validated under it.

**Callers, before -> after.**
- Trigger save (`add_paper_triggers`): raw `read_snapshot`, no hold -> `read_market` (needs the `get_live_feed` and
  answer-clock dependencies).
- Monitor (S-20): `reload` held the index only for conditional exits -> holds the index for every armed trigger. No read
  in `_fire`.
- Manual exit price (`_server_exit_prices` via `tracking._snapshot`): unchanged, left for Phase 4 (it already holds the
  legs with its own loop; moving it changes the wait and the refusal mapping).

**Tests.** `tests_app/test_paper_trigger_unheld_index.py`: 22 (no DB); `test_paper_triggers_routes.py`: 65 (DB, incl. the
unheld-feed route twin); `test_paper_monitor.py`: 23 (DB, incl. S-20); `test_paper_order_door.py` (`market_read` added to
`PAPER_MODULES`); `tests/errors`: 710 (new template pin, "pending owner read").

**Commits.** `fce27095` tests (red), `58bd51d9` code (green), `3b8ae9b7` gates (ruff ratchet, ADR-327 coverage stage,
repo scans) and two review pins. **Review:** Tier A, Opus: PASS, no critical or major finding. Minors fixed in
`3b8ae9b7`: the production 3 s wait is pinned by a test, and a route twin test was added. **Prepush:** TOTAL PASS on
`3b8ae9b7`.

**Owner read (25 Nov evening, ADR-328 (5)): approved, mark cleared.** Before that: the error template `paper_trigger_price_unreadable` (STRATEGY_VALIDATION_446, pin in
`tests/errors/template_pins.json`): only its first sentence ("Not saved: the live price could not be read, so this level
cannot be checked. Try again in a moment.") is ADR-327's. Its impact and next-action lines are builder wording and need the
owner's read (open question 3 below).

**Deferred.**
- The Keep-this-level route (`keep_paper_trigger`) has no price check (review finding 4; ADR-317 treats it as low risk).
- The first-second S-20 race (review finding 3): a fire in the first second after `reload`, before the index tick
  arrives, can still record "not available".
- Display and advisory readers not moved: `routes/outcome.py:1263`, `live_push.py:170`, `chain_push.py:305`,
  `index_push.py:84` (they would add up to 3 s waits).
- Manual exit price read: Phase 4.

## Phase 2: B4 may_act + F1 priceState (D-05 server half, D-39 where same rule)

**Door, server.** `backend/ofo_app/may_act.py`: `may_act(ctx, action, at, prices=None) -> Allowed | Refused(reason, failure)`,
actions `place`, `exit`, `set_trigger`. Market half (`market_open`, the one `market_state` answer, no context fails
closed) then price half (`prices_ok`: every state must be `live`; stale, missing and unknown are not live). Refusal codes
and failures are the ones the routes raised before: `gate_market_closed` (CONFLICT), `tracking_exit_prices_not_live`
(CONFLICT), `paper_trigger_price_unreadable` (no failure). `set_trigger` with the market closed is Allowed with
`market_open=False` (ADR-327 (3): saved, arms at the next live tick). Server-only; no endpoint. Added to `PAPER_MODULES`.

**Callers, before -> after.** 7 separate "may this act" decisions -> 1 door + 0 copies of those 7:
- `paper_limit.refuse_when_closed` (function removed) and its 3 callers: `place_checked`, the orders route
  (`routes/paper.py`), the tracking exit route (`routes/tracking.py`) -> `may_act.refuse_unless_allowed` (`place`; `exit`).
- `check_trigger_levels` market-closed test (`market_state(...).closed`) -> `may_act.market_open`.
- `market_read.read_market` market-closed test -> `may_act.market_open`.
- `_server_exit_prices` final "every leg live" check -> `may_act.prices_ok("exit", ...)` (a price with no number reads
  as missing, as before).
- `_judge_levels` "price not live -> unreadable" -> `may_act.prices_ok("set_trigger", ...)`; the crossed-before-unreadable
  order is unchanged. The literal `paper_trigger_price_unreadable` now lives once (`may_act`), `routes/paper.py` aliases it.

**Left, with the reason.**
- `paper_monitor.on_quote` (`is_market_open(now, self._holidays)`): its own injected holidays and the feed clock; the
  door asks the provider's feed state (`market_closed_for`), whose default calendar has no holidays. Not provably the
  same answer, so not moved (the monitor's fire path is Phase 4).
- `paper_monitor` `paper.is_live` at `:259`, `:273`: the price a fire is recorded with (missing: stays armed, NotYet) -
  Phase 4 `exit_strategy`.
- `routes/tracking.py` `paper.exit_prices_now` raising `PricesNotLive`: domain-layer raise with the same code; Phase 4.
- `adjustment_readers.py:854` `paper.is_live`: display prices, not an act gate.
- `paper_settlement.py:223` `is_market_open` at midday: "is that day a trading day", a different question.
- `routes/outcome.market_state` is the source the door uses; its display callers (`chain_push`, `index_push`,
  `leg_picker`, `indices`, `planned_entry`, `outcome`) answer "what to show", not "may it act".
- `ofo/execution/safety.py` market-open gate: the real-order path, out of scope (ADR-281).

**Door, screen.** `frontend/src/lib/priceState.js`: `priceState({readFailed, held, serverState, closedText})` ->
`live | stale | missing | closed | read_failed` and `usePriceFreshness` -> `{state, live, readFailed, readOk, exitReason}`.
`readOk` is the Positions rule (`listIsStale`, D-05); the builder's `paperReadFailed` goes through it
(`StrategyBuilderPage.vue`: `paperBookFailed`), and `readOk` / `exitReason` are ready for the Phase 4 Exit gate (NOT wired:
no Exit button changed).

**Merged (same rule, same text, no visible change).**
- `NOT_CONNECTED_TEXT` (`tracking.js`) and `PAPER_NOT_CONNECTED` (`paperList.js`): one constant.
- `PAPER_PAUSED` (`paperList.js`, also `paperPnl.js`, `PaperStrategies.vue`) and the base of `pausedText` (`tracking.js`):
  one constant `PAUSED_TEXT`; `pausedText` is one function. `withAsOf` stays (it leaves the bare sentence without a time,
  `pausedText` says "not available": different results).
- `listIsStale` (one definition; `paperList.js` re-exports it); used by `PaperStrategies.vue` and `paperPnl.js` through
  `usePriceFreshness`.
- `NOT_LIVE_EXIT` (was local to `PaperStrategies.vue`) moved to `priceState.js`, ready for the builder gate.
- "Book is paused or not connected" (`state === 'PAUSED' || 'NOT_CONNECTED'`, twice: `tracking.js` `sharedTotal`,
  `PaperBookPanel.vue`) -> `bookNotLive`.

**Left, with the reason (different rule or different words; merging would change visible text).**
`UNREADABLE_TEXT` (`tracking.js`) vs `PAPER_BOOK_UNREADABLE` (`paperDrafts.js`): different wording. `NO_TOTAL`
(`PaperStrategies.vue:188`): the same rule in other words, kept as shown. `legPicker.js:7` `NOT_CONNECTED_LABEL` (a draft,
mirrors a backend constant) and `:100` `LIST_REASON_TEXT` (the server's reason map), `CreateStrategyPage.vue:25`
`NOT_PRICED`, `useChainLive.js:14` `NOT_LIVE_LABEL`, `IndexStrip.vue:15` "Index values are not live.": other surfaces,
other sentences. `sharedStateText.js` `RECONNECTING_PREFIX` and the builder `pricesStamp`: socket state, not the book
read. `paperDrafts.js` `confirmRowsFor` per-leg `price_state === 'live'`: a per-leg rule. `SummaryCards.vue:160`: D-39
basis prop, not a freshness string (not changed here).

**Tests.** `tests_app/test_may_act.py`: 19 (no DB; per state open+live, open+stale, open+missing, closed, session-edge
parity with `market_state` at 09:14, 09:15, 15:29, 15:30, 15:44, 15:45); `frontend/tests/priceState.test.js`: 17 (live,
stale, missing, closed, read failed, wording identity). Callers' existing tests unmodified and green (DB: paper routes,
server exit price, adjustment limit, save paths, batch buys first, triggers routes, builder after hours, duplicate leg,
tracking, tracking list, IC exits, monitor); whole vitest suite green. One pin updated:
`tests/orchestrator/test_select_app_tests.py` PR241_SELECTION gains the new test file (it imports modules that diff changes).

**Not wired yet.** `readOk` / `exitReason` (`usePriceFreshness`) and `NOT_LIVE_EXIT` are ready for the Phase 4 Exit gate;
no Exit button changed in Phase 2.

**Commits.** `707bc5d4` tests (red), `0e30edc1` code (green). **Review:** Tier B, Sonnet: PASS, no critical or major
finding. **Prepush:** TOTAL PASS on `0e30edc1`.

## Phase 3: PARTIAL (F3 + F5 + B6, D-41), saved as `phase3-wip.patch.txt`

**What the patch holds.** One file, two parts, separated by the line `# ---- uncommitted green-attempt diff on top of 8de187b4 ----`:
1. A `git format-patch` of commit `8de187b4` (Phase 3 tests first, red): `frontend/tests/one-source-d41.test.js` (5 tests:
   same LTP per leg on both builder panels, rows add up to the before-charges total on both, headline stays the
   after-charges text, `legPricesOf`, `paperPnlBlock`) and `tests_app/test_strategy_money_view.py` (13 tests, no DB: engine
   parity, paper page and tracking page agree at one price set, the four routes call the door and no engine function, no
   arithmetic in the module).
2. An uncommitted, UNREVIEWED code diff on top (green attempt): new `backend/ofo_app/strategy_money.py`
   (`strategy_money_view(orders, prices, *, totals_priced=True)` -> `MoneyView`; the signature differs from the plan's
   `(strategy_id, prices)` because callers already hold the orders and the paper `_figures` signature is pinned by
   `test_paper_unpriced_names.py`); edits to `routes/paper.py` (`_figures`, `_extremes`, `_after`), `routes/tracking.py`
   (`_book_figures`), `TrackingPanel.vue`, `lib/usePaperBookRead.js` (`legPricesOf`, `paperPnlBlock`),
   `StrategyBuilderPage.vue`, `ChartCard.vue`, `tests_app/test_paper_order_door.py` (`strategy_money` added to
   `PAPER_MODULES`), `tests_app/test_strategy_money_view.py`, and a Phase 3 draft of this RESULTS file (superseded by the
   section you are reading; its facts are kept here).

**State at the stop.** The builder reported: whole vitest 2613 passed; the DB test files it ran green. NOT run: repo scans,
ruff ratchet, coverage, `ci_local`. NO review. Nothing from Phase 3 is on the branch or pushed. A copy of the work may
exist in the machine-local worktree `/home/user/wt-p3` (branch `wt/phase3`, at `8de187b4` plus uncommitted files); it is
gone on a new container, the patch file is the durable copy.

**Price basis (decided before the source changed).** The Paper P&L panel's leg rows now use the paper book's own price,
`ofo.tracking.paper.display_price` (book route `_prices`, `routes/paper.py`), the price the Net Positions table, the Total
and the P&L table already use. Before, the rows came from `/strategies/{id}/tracking`, which prices each leg with
`leg_price` (live only) on its own poll. Spec: ADR-212 ("After market hours, paper positions show LTP and P&L from the last
close, as the builder does"); REQ-109 AC-5 unchanged in market hours (`display_price` is exactly `leg_price` then). Visible
change: only the after-hours panel rows (a dash before, the last close now). Fills, stops and triggers keep `leg_price`.

**Callers, before -> after (as written in the patch).** Server "price answers -> live map -> engine call": `_figures`,
`_extremes`, `_after` (paper), `_book_figures` (tracking) = 4 copies -> 1 door. Screen: the panel's `/tracking` leg rows
(a second poll of the same legs) -> the book's `LegPrice`; headline and the builder's `paperTotal` -> `paperPnlBlock`.

**Left, with the reason (as written in the patch).** `routes/outcome.py read_booked`, `routes/adjustment_history.py
closed_figures`, `routes/adjustment.py price_after`: other questions. Rounding stays per route (`_exact` on the book page,
`to_paise` on tracking): reply shapes must not change. `PaperBookPanel` total, `readPaperList` / `usePaperPnl`,
`readTracking`, `AdjustCompare.vue :262`: other replies or wording. The `/paper/strategies` list pollers stay separate from
the builder's per-strategy read. The panel's `/tracking` poll still runs for detections, rules and exits.

**How to resume.** These commands were verified on 25 Nov in a throwaway worktree at `0e30edc1`: the first part applied with
`git am`, the second with `git apply`, and `git status` showed the 10 entries below; the worktree was then removed. The
first part's sha changes on `am` (it was `8de187b4`). Run the `sed` lines as their own command first: a hook refuses
`git am` / `git apply` of a patch file created in the same command.

```
git checkout -b wt/phase3-resume 0e30edc1
sed -n '1,/^# ---- uncommitted/p' docs/design/modular-doors-2026-11-25/phase3-wip.patch.txt | head -n -1 > /tmp/p3a.patch
sed -n '/^# ---- uncommitted/,$p' docs/design/modular-doors-2026-11-25/phase3-wip.patch.txt | tail -n +2 > /tmp/p3b.patch
git am /tmp/p3a.patch
git apply /tmp/p3b.patch
git status --short
```

Expected `git status --short` (10 entries): modified `backend/ofo_app/routes/paper.py`, `backend/ofo_app/routes/tracking.py`,
`docs/design/modular-doors-2026-11-25/RESULTS.md`, `frontend/src/components/strategy/ChartCard.vue`,
`frontend/src/components/strategy/TrackingPanel.vue`, `frontend/src/lib/usePaperBookRead.js`,
`frontend/src/pages/StrategyBuilderPage.vue`, `tests_app/test_paper_order_door.py`, `tests_app/test_strategy_money_view.py`;
untracked `backend/ofo_app/strategy_money.py`. Note: the `RESULTS.md` change in the patch is a draft that replaces the
"Phases 4..8" line of an older RESULTS; on the resume branch (which already has this file) keep this file and fold in only
what Phase 3 needs. If the resume branch is not based on `0e30edc1`, merge first, then re-apply.

## Phases 4..8: not started

## Next step (exact)

Superseded on 25 Nov evening. Build from `PLAN-phases-3-8.md` (code-verified plan for phases 3 to 8, with the owner's
ADR-328 answers, the two lanes and the ownership table):

1. Step 0 (section 4 of that file): merge `origin/fix/ic-live-test-1123` (head `6574e47` or newer, CI green) into
   `refactor/modular-doors`; resolve `coverage-stages.yaml` and `views/spec-digest.md`; regenerate; run the checks.
2. Step 0b: the ADR-328 spec notes in ADR-319 and REQ-109; push; CI green; cut Lane B (`refactor/leg-door`).
3. Lane A: Phase 3 (resume the patch only as section 5.3 says; its join key is wrong), 4, 6, 7, merge Lane B, 8.
   Lane B: Phase 5 only.
4. The owner screen-tests `refactor/modular-doors` once Step 0b is green (section 8 of that file).

## Screen-check list so far (click by click), for what is fixed

- **D-01 (Phase 1).** Positions > Paper > Stops > Conditional exit. Choose "Above a level the index is already beyond",
  in market hours, Save: "Not saved: the live price is already at or beyond this level ..." (the already-crossed text).
  With the price feed stopped (market hours), Save: "Not saved: the live price could not be read, so this level cannot be
  checked. Try again in a moment." With the market closed, Save: saved (arms at the next live tick).
- **S-20 (Phase 1).** Arm only a leg stop (no conditional exit) on a paper strategy in market hours, let it fire: the
  alert carries the NIFTY value, not "not available".
- **D-05, D-41, D-60:** not fixed yet (Phases 3-5). Once Phase 3 lands: the builder's Net Positions table and the Paper
  P&L panel show the same LTP per leg, the leg P&L rows add up to the before-charges total; after hours the panel rows
  show the last close.

## Re-test list (screens touched so far)

- Positions > Paper > Stops (trigger save).
- Paper alerts for leg stops.
- Paper exit from Positions (the market-closed refusal path now goes through `may_act`).
- Builder paper panels (`paperBookFailed` rename, no visible change).
- Every place showing "Paper P&L paused - prices not live" or the not-connected text (constants merged, no text change).
- With Phase 3 resumed: builder Net Positions and Paper P&L panel, and the after-hours panel rows.

## Gate notes for the next session

- Run python gates with the proxy variables unset: `env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy
  -u ALL_PROXY -u all_proxy python tools/ci_local.py`.
- Prepush takes about 31-33 minutes per head, and a hook refuses a push without it.
- Known guard traps: the money-outside-engine scan flags `+` in new backend files; the settings-reader guard;
  line-pinned exceptions in `paper_monitor.py`; the `tests/orchestrator/test_select_app_tests.py` PR241 selection set
  (new test files that import changed modules); `PAPER_MODULES` in `tests_app/test_paper_order_door.py` (add every new
  paper module).
- Hooks refuse `git worktree remove --force`, `git stash` in a worktree and `git reset --hard`; commit scratch changes in
  the throwaway worktree, then run a plain `git worktree remove`.
- `/root/ofo-dbtest.sh` and `/root/ofo-db-start.sh` are machine-local and gone on a new container: set up the test
  database per `docs/process/GC-ICLIVE-cloud-setup.md` section 1 (a template clone needs
  `revoke all on database <clone> from public`). DB tests run one file at a time (see CLAUDE.md).

## Open owner questions

Answered or closed on 25 Nov evening (see `owner-questions.md`): OQ-1 by ADR-328 (1), OQ-2 closed (keep the route),
3 by ADR-328 (5), OQ-4 by ADR-329 (unsaved builder legs kept for the chain trip; leaving elsewhere asks).

1. **OQ-1 D-60 (opposite-action step).** Should a strike step or move that lands on a held contract of the OPPOSITE action
   ask Increase / Keep separate / Cancel? Spec basis: REQ-030 AC-11; ADR-319 (1) and (4); the spec is silent on a step as
   distinct from a deliberate add. Recommendation: yes for a step or move, no question for a deliberate add (picker,
   ready-made), since two opposite rows on one contract net to nothing. Built meanwhile: ADR-319 (4) as written, no
   question for opposite action.
2. **OQ-2 `POST /strategies/{id}/tracking/exit`.** No frontend caller, four test files use it. Recommendation: keep it for
   now, moved onto the B1 exit door with behaviour unchanged (closes from the entry legs); delete in a later round with its
   tests moved onto the Positions exit route. Built meanwhile: kept and moved (Phase 4).
3. **Wording of `paper_trigger_price_unreadable` (STRATEGY_VALIDATION_446).** Only the first sentence is ADR-327's; the
   impact and next-action lines are builder wording and need the owner's read before they are final.
