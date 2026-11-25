# Build plan: modular doors, phases 3 to 8 (code-verified, 25 Nov 2026 evening)

Read with `PLAN.md` (the why and the inventory), `RESULTS.md` (what Phases 1-2 did), `spec/decisions/ADR-328.md` (the
owner's five answers of this evening) and `owner-questions.md`. This file is the build order. A fresh session runs it
from top to bottom without asking anything. Where this file and `PLAN.md` disagree, this file wins (see the
"Corrections of 25 Nov evening" section of `PLAN.md`).

Sources: four code-verified research reports of 25 Nov (phase 3; phase 4 + B2; phase 5; phases 6-8), each claim with
file:line, read in full, plus the checks named "settled here" below, made on `refactor/modular-doors` at `b1055c5`.
Line numbers are those of `b1055c5`. After Step 0 (the merge) some lines move by a few rows: find them by the name
given.

## 1. Status and scope

- **1** - Scope: B3 `read_market` + B5 trigger check (D-01, S-20, ADR-327); State on 25 Nov evening: DONE, pushed
  (`fce27095`, `58bd51d9`, `3b8ae9b7`)
- **2** - Scope: B4 `may_act` + F1 `priceState` (D-05 server half, D-39); State on 25 Nov evening: DONE, pushed
  (`707bc5d4`, `0e30edc1`)
- **3** - Scope: F3 + F5 + B6 one paper book source (D-41 (two readers)); State on 25 Nov evening: patch only
  (`phase3-wip.patch.txt`); wrong join key, see 5.3
- **4** - Scope: B1 exit door + F2 exit gate (D-05 builder half, ADR-328 (4)) + R5; State on 25 Nov evening: not started
- **5** - Scope: F6 `useLegDoor` + one dialog (D-60, ADR-328 (1), (2)); State on 25 Nov evening: not started
- **6** - Scope: B2 close list (real path, Tier A), F7, F8; B7 replaced by guard G4; State on 25 Nov evening: not
  started
- **7** - Scope: R2, R3 browser; R1 documented; the rest skipped or parked; State on 25 Nov evening: not started
- **8** - Scope: Guards G1-G5 + one paper-book reader + one dialog / emitter list; State on 25 Nov evening: not started

This file covers Step 0 and Phases 3 to 8, all of them (ADR-328 scope).

Bounds (owner, binding):
- Behaviour unchanged, except the named bugs (D-01, D-05, D-41 (two readers), D-60, S-20) and ADR-328 (1)-(5).
- Exit is "now / market" only. No limit-order exit. No auto-exit from plan targets. Paper only; never a Kite order.
- Money is exact `Decimal` in the backend; the browser does no money arithmetic (ADR-008).
- Never merge `refactor/modular-doors` (or `refactor/leg-door`) into `fix/ic-live-test-1123` until the owner says so.
- "Behaviour unchanged" means the existing tests of every caller pass unmodified. A test that pins one of the named
  bugs, or behaviour ADR-328 changes, is changed in the tests-first commit with the reason in the commit message.

Name for the D-41 of this plan: "D-41 (two readers)" in every commit, PR and issue. The ledger's D-41 (Live and My
Strategies cards show no P&L, ADR-325 (6), fixed in Part E, `pnl-cards-d41.test.js`) is a different, fixed defect.

## 2. Decisions

### 2.1 Owner (ADR-328, 25 Nov evening; binding, not reopened)

- **(1)** - Decision: A strike step or a move (step, Shift, Width, Hedge) that lands a leg on a contract held on the
  OPPOSITE side asks first: "Keep both" / "Cancel". A deliberate add from the strike picker stays silent. SPEC CHANGE to
  ADR-319 (4) and the REQ-109 AC-9 sentence; Built in: Step 0b (spec text), Phase 5
- **(2)** - Decision: a builder that already shows legs and receives a REPLACING draft link (pasted or shared; the `?draft=` watch, `StrategyBuilderPage.vue:626-640`) asks "Replace the N legs?"; Cancel keeps them. NARROWED by ADR-329 (3): it is not the chain's Add Selected (the premise "the builder holds legs when Add Selected arrives" was false, `:121`); Built in: Phase 5
- **(3)** - Decision: The Paper P&L panel shows, per leg, the leg's TOTAL (booked + open), the same figure as the table
  beside it; Built in: Phase 3
- **(4)** - Decision: While the builder shows that the trade changed elsewhere, Exit all and every per-leg Exit are
  disabled with "This trade changed elsewhere. Reload to see the current legs."; Built in: Phase 4
- **(5)** - Decision: The wording of `paper_trigger_price_unreadable` (446) is approved; its "pending owner read" mark
  is cleared; Built in: done in this docs change (`tests/errors/template_pins.json`)

### 2.1b Owner, ADR-329 (25 Nov late evening; binding, not reopened; answers O-1 / OQ-4)

- **(1)** - Decision: going from the builder to the Option Chain KEEPS the builder's unsaved legs; "Add Selected" ADDS the
  ticked contracts to them; a ticked contract that clashes (same contract, same action) asks the usual question
  (Increase / Keep separate / Cancel, ADR-319 (1)); a ticked OPPOSITE-side contract is a deliberate add and is not
  asked; Built in: Phase 5 (Lane B)
- **(2)** - Decision: leaving the builder for any OTHER page while it holds unsaved legs asks "Leave the builder? The N
  unsaved legs will be lost." with "Stay" (keeps page and legs) and "Leave" (discards them); Built in: Phase 5 (Lane B)
- **(3)** - Decision: ADR-328 (2) "Replace the N legs?" stays only for a replacing draft link, never the chain's Add
  Selected; Built in: Phase 5 (Lane B)

Spec text for ADR-007 Q34 and the ADR-319 (1) clause "Option Chain Add Selected asks" is NOT edited now; it is plan
step 5.5.0 of Lane B (below), so the spec change and the code land together.

### 2.2 Coordinator's technical decisions (the owner delegated these)


- **Step 0 merges `origin/fix/ic-live-test-1123` (Part F, head `6574e47` or newer with green CI) into
  `refactor/modular-doors` before any phase** - One-line reason: Phase 3 and 6 edit files Part F changed
  (`TrackingPanel.vue`, `tracking.js`); the owner screen-tests one branch that holds everything
- **Phase 3 joins panel rows to the book by a real `contract_id` added to the tracking leg rows** - One-line reason: the
  `instrument_id` the panel holds is `"NSE_FO:44624"`, the book key is the contract id; no other key is structural (kit
  C3)
- **Phase 3: price and quote time from the same source; per-leg figure = total; `by_contract` lazy** - One-line reason:
  ADR-321 (9) (a price states its time), ADR-328 (3), cost
- **Phase 3 leaves the builder's own leg list (outcome socket) alone; deferred issue** - One-line reason: a third reader
  with its own quote time (ADR-321 (9)); not what the owner reported
- **Phase 4 follows the phase-4 report: `ofo/tracking/closing.py` + `ofo_app/paper_exit.py` (`live_exit_prices`,
  `exit_strategy` -> Exited / Refused / NotYet / Flat)** - One-line reason: one function per capability, each caller
  keeps its writer and commit
- **Strategy row lock first in every door caller; live prices read before the lock; the door never commits** - One-line
  reason: removes the monitor-vs-route deadlock (A3); no 3 s wait under a row lock
- **The manual Positions route shares only the pricing step; no new request body** - One-line reason: the browser picks
  sides and lots (REQ-109 AC-4, editable quantity); a body change is new API surface
- **`POST /strategies/{id}/tracking/exit` is KEPT as the HTTP face of the door (OQ-2 closed)** - One-line reason: its
  premise was wrong: it closes the net book (`book.contract_legs`), and 9 test files plus the IC harness use it
- **`ofo/execution/partial.py` is not shared; Kite `exit_legs` stays byte-identical with an oracle test** - One-line
  reason: different inputs (broker-confirmed legs); the real path must not move for a one-line saving
- **Latent differences L1-L8 and the two-tab double exit are not changed; each is a deferred issue** - One-line reason:
  behaviour bound; L4 and the monitor half of L5 are the exceptions, see 5.4.3
- **Phase 5: `useLegDoor` + one `DuplicateLegDialog` (same test ids); `legDoor.js` stays the pure rule with an
  `opposite` option** - One-line reason: one live question across picker and moves; existing selectors keep every test
- **Phase 5: a pasted `?draft=` with duplicate rows is not asked; ready-made, remove, Undo, saved load keep their
  flows** - One-line reason: they replace or remove, they do not add onto a held contract
- **Phase 5 (ADR-329): the chain trip is held in a new in-memory pinia store `stores/builderHold.js`; no `keep-alive`, no
  `sessionStorage`, nothing sent to the server** - One-line reason: Pinia is already the app's cross-page memory and the
  chain's own ticks already survive route changes in it (`stores/chainSelection.js:27`, `main.js:15`); `keep-alive`
  would keep the whole builder mounted (feeds, timers) behind the chain and would make every builder visit "held"
  (`App.vue:11-13` is a plain `router-view`); `sessionStorage` would also survive a reload, which ADR-329 does not ask
  for, and needs try/catch everywhere (no page uses it for state today: `grep` finds only `SessionEndedCard.vue:15`
  and `lib/execute.js:60,70`)
- **Phase 5 (ADR-329): the leave question is a router-leave guard (`onBeforeRouteLeave`) on the builder page and on the
  chain page, from one composable and one dialog; `beforeunload` is OUT** - One-line reason: ADR-329 (2) says "any other
  page"; a browser tab close or reload is not a page change, and the browser's own `beforeunload` box cannot show the
  ADR sentence or the Stay / Leave labels (it ignores custom text), so it would be a different, worse question; a
  reload loses the unsaved legs silently, as today (stated on the screen-check list). One line to add later if the
  owner wants it (nothing in `src` uses `beforeunload` or `onBeforeRouteLeave` today: `grep`)
- **Phase 5 (ADR-329): "unsaved" = shown legs with no saved copy (`savedId === null`); in Drafts Mode = pending changes
  (`pendingOrders.length > 0`)** - One-line reason: the page already tracks it (`StrategyBuilderPage.vue:350`, `:384`,
  `:644`, `:830`); no new dirty flag
- **Phase 5 (ADR-329): the chain trip holds the legs the builder shows, saved or not; the leave question uses "unsaved"
  only** - One-line reason: the trader opens the chain for the same reason either way; a hold of saved legs is the same
  record and the same code path, and "Add Selected" onto them makes them an edited (unsaved) strategy. READING of
  ADR-329 (1) (it names unsaved legs only): confirmed on the screen-check list, one `if` to narrow
- **Phase 5 (ADR-329): the held legs stay "the builder's" while the user is on the chain, so leaving the chain for a page
  other than the builder asks the same question from the chain page** - One-line reason: otherwise the trip would be a
  silent way to lose exactly what ADR-329 (2) protects; READING of ADR-329 (2), screen-checked

- **Phase 6: B7 `raise_alert` not built; guard G4 instead. F7 = one reader module; F8 = drop one pre-read** - One-line
  reason: three writers with one caller each, different stores and transactions; nothing to merge
- **Phase 7: do R2, R5, R3 browser; skip R4, R7, R11, R12; park R6, R8, R9, R3 server; R1 kept and documented** -
  One-line reason: only identical code is merged; real-path and wording changes are not neutral
- **Phase 8 guards live in `tests/` (Python) and `frontend/tests/` (vitest), never `tests_app/`** - One-line reason: no
  DB, no app import, no PR241 selection pin churn
- **Two build lanes (section 3)** - One-line reason: Phase 5 is frontend-only and file-disjoint except one page

## 3. Lanes, ownership, merge order, ADR numbers

Lane rules come from the parallel-sessions skill: split by files; one branch per lane cut from the same commit; a lane
never edits a file outside its row; the coordinator hands out ADR numbers; merge, never rebase; regenerate generated
files after each merge and grep for functions one side removed and the other still calls.

- **A** - Branch: `refactor/modular-doors`; Session: one session; Work, in order: Step 0, Step 0b (spec text), Phase 3,
  4, 6, 7, merge Lane B, Phase 8
- **B** - Branch: `refactor/leg-door`, cut from `refactor/modular-doors` right after Step 0b is pushed and CI is green;
  Session: one session; Work, in order: Phase 5 only

### 3.1 Ownership table (a lane edits only its rows)

Paths: `be/` = `backend/ofo_app/`, `fe/` = `frontend/src/`, `ft/` = `frontend/tests/`.

| Path | Lane | Phase | Note |
|---|---|---|---|
| `be/strategy_money.py` (new) | A | 3 | |
| `be/routes/paper.py`, `be/routes/tracking.py` | A | 3, 4 | |
| `be/routes/adjustment_history.py` | A | 3 | one line (`live_prices`) |
| `backend/ofo/tracking/closing.py` (new), `be/paper_exit.py` (new) | A | 4 | |
| `be/paper_monitor.py`, `be/paper_settlement.py` | A | 4 | |
| `be/market_read.py` | A | 4 | only if the optional switch lands (5.4.6) |
| `backend/ofo/engine/legs.py` | A | 4 (R5) | |
| `be/execute_plan.py` | A | 6 (B2) | real path, Tier A |
| `be/strategy_store.py` | A | 7 (R2) | adds `owns` |
| `be/strategy_pause_store.py`, `be/tracked_book.py`, `be/strategy_level_watch_store.py` | A | 7 (R2) | |
| `be/execution_plan_store.py`, `be/strategy_alert_style_store.py` | A | 7 (R2) | |
| `backend/ofo/timeutil.py` | A | 7 (R1) | comment only |
| `fe/lib/usePaperBookRead.js`, `fe/lib/tracking.js` | A | 3, 7 (R3) | |
| `fe/components/strategy/TrackingPanel.vue` | A | 3, 6 (F7) | |
| `fe/components/strategy/ChartCard.vue` | A | 3 | comment only |
| `fe/lib/priceState.js`, `fe/lib/usePaperExit.js` (new) | A | 4 | |
| `fe/components/strategy/ExitButton.vue` (new), `PaperBookPanel.vue`, `PaperStrategies.vue` | A | 4 | |
| `fe/lib/paperTriggers.js` (new), `fe/components/strategy/PaperStops.vue` | A | 6 (F7) | |
| `fe/pages/MyStrategiesPage.vue` | A | 6 (F8) | |
| `fe/lib/displayFormat.js` | A | 7 (R3) | |
| **`fe/pages/StrategyBuilderPage.vue`** | **A, then B** | 3, 4 (A); 5 (B) | **shared: see 3.2** |
| `fe/lib/legDoor.js`, `fe/components/strategy/LegPicker.vue` | B | 5 | |
| `fe/composables/useLegDoor.js` (new), `fe/components/strategy/DuplicateLegDialog.vue` (new) | B | 5 | |
| `fe/stores/builderHold.js` (new), `fe/composables/useLeaveBuilder.js` (new), `fe/components/strategy/LeaveBuilderDialog.vue` (new) | B | 5 (ADR-329) | the chain-trip hold and the leave question |
| **`fe/pages/OptionChainPage.vue`** | B | 5 (ADR-329) | was "neither lane"; leave guard only, Add Selected itself is unchanged (`:123-126`) |
| `ft/builder-hold-adr329.test.js`, `ft/leave-builder-adr329.test.js`, `ft/chain-trip-adr329.test.js` | B | 5 | new |
| `ft/leg-duplicate-d60.test.js`, `ft/leg-step-duplicate-d60.test.js` | B | 5 | new `it`s; `:91` changed |
| `ft/leg-door-phase5.test.js`, `ft/leg-emitters-guard.test.js`, `ft/builder-draft-replace.test.js` | B | 5 | new |
| `docs/design/modular-doors-2026-11-25/RESULTS-lane-b.md` | B | 5 | Lane A folds it in at the merge |
| every other new test file named in 5.3, 5.4, 5.6-5.8 | A | 3-8 | |
| `ft/paper-place-refresh.test.js` | A | 4 | one test changed (5.4.4) |
| `spec/**`, `views/spec-digest.md` | A | 0b on | Lane B: no spec change |
| `docs/process/coverage-stages.yaml` and the coverage register | A | 0b on | regenerated |
| `docs/api/openapi.json`, `tests_app/reply_inventory.py` | A | 3 | regenerated only |
| `tests_app/test_paper_order_door.py`, `tests/orchestrator/test_select_app_tests.py` | A | 3, 4 | |
| `docs/design/modular-doors-2026-11-25/RESULTS.md`, `owner-questions.md` | A | all | |

Files neither lane edits: `paperDrafts.js` (`paperOrdersFor`, `legsAfterExit`, `confirmRowsFor`), `LegList.vue`,
`ReadyMadePanel.vue`, `stores/chainSelection.js`, `router/routes.js`, `App.vue`, `ofo/execution/**`, `routes/execute.py`, kit files (`.claude/kit/GUIDE.md`
list: `.claude/rules/kit/`, `.claude/kit/`, `.claude/hooks/`, `tools/`, `.github/workflows/ci.yml`, ...).

### 3.2 The one shared file: `frontend/src/pages/StrategyBuilderPage.vue`

- ADR-329 (25 Nov late evening) adds to this page only on Lane B's side (hold, leave guard, chain-add), and Lane B owns
  `OptionChainPage.vue`; no Lane A file is needed for it (checked: Lane A's rows touch paper, tracking and exit files;
  none touches the chain page, `stores/`, `router/` or `App.vue`). The only overlap stays this page, handled below.
- Lane A owns it from Step 0 until Lane A's Phase 4 is pushed with green CI (Phase 3: `paperTotal`; Phase 4: the exit
  gates, `confirmPending`, the ADR-328 (4) wiring).
- Then it passes to Lane B. Lane B merges `origin/refactor/modular-doors` (at the Phase 4 head) into
  `refactor/leg-door` and only then makes its page commit (5.5.4). Lane A does not touch the page again until it has
  merged Lane B (Phases 6 and 7 do not need it; checked: F7, F8, R2, R3, R5 touch other files).
- Lane B does every other Phase 5 commit before that hand-over, so it is never idle.
- If Lane A's Phase 4 parks, the coordinator moves the page to Lane B at the parked head and records it in the parked
  issue.

### 3.3 Merge order

1. Step 0: `origin/fix/ic-live-test-1123` -> `refactor/modular-doors` (Lane A).
2. Cut `refactor/leg-door` from that head after Step 0b.
3. After Lane A's Phase 4: `origin/refactor/modular-doors` -> `refactor/leg-door` (Lane B, before its page commit).
4. Before Phase 8: `origin/refactor/leg-door` -> `refactor/modular-doors` (Lane A). Conflicts: Lane A resolves; on what
   the screen shows, the fix-branch behaviour wins. After it: regenerate (digest, coverage register; OpenAPI and reply
   inventory must show no diff), rerun the touched tests, grep for functions one side removed and the other still calls.
5. If `fix/ic-live-test-1123` moves again: merge it into `refactor/modular-doors` (step 1 again), never the reverse.
6. End of the plan: DRAFT PR `refactor/modular-doors` -> `fix/ic-live-test-1123`, never merged, never marked ready.

### 3.4 ADR numbers

ADR-329 is taken (owner, 25 Nov late evening: unsaved builder legs; written in this docs commit). Next free: ADR-330.
No phase below needs a new decision row (every product point is in ADR-328, ADR-329 or older rows). If one is needed:
Lane A may use ADR-330, Lane B ADR-331; any further number comes from the coordinator. Before writing one, run
`git ls-tree --name-only origin/fix/ic-live-test-1123 spec/decisions/` and the same for both lane branches.

## 4. Step 0: merge the fix branch (Lane A)

Core: the branch the owner will screen-test holds Part F and Phases 1-2, and every test of both is green on it.
Proof: the merge commit with the generated files regenerated, the Part F and Phase 1-2 tests green, CI green.

Settled here (25 Nov, `git merge-tree --write-tree HEAD origin/fix/ic-live-test-1123` at `6574e47`, result `765ee04`):
only two files conflict, `docs/process/coverage-stages.yaml` and `views/spec-digest.md`. The "known trap" that Part F's
`routes/paper.py` calls `paper_limit.refuse_when_closed` is not a conflict: that line is unchanged diff context on the
fix branch, and the merged tree has `may_act.refuse_unless_allowed(ctx, "place", placed_at)` at the same place (merged
`routes/paper.py:1339`); `git grep refuse_when_closed` in the merged tree finds only the `may_act.py` docstring.

Commands (Lane A, in `/home/user/OptionsForOptions2` or a worktree on `refactor/modular-doors`):

```
git status --short                                    # must be empty
git fetch origin
git checkout refactor/modular-doors && git pull --ff-only
gh run list --branch fix/ic-live-test-1123 --limit 3  # the head to merge must show a green run
git log -1 --format=%H origin/fix/ic-live-test-1123   # 6574e47 or newer; write it in the merge message
git merge --no-ff origin/fix/ic-live-test-1123 \
  -m "Merge origin fix/ic-live-test-1123 (<sha>) into refactor/modular-doors (Step 0 of PLAN-phases-3-8)"
```

Resolve:
- `docs/process/coverage-stages.yaml`: keep both sides' rows (the fix branch's ADR-326 row and this branch's ADR-327
  and ADR-328 rows); stage `S6.7` for each, as each side wrote it.
- `views/spec-digest.md`: take either side, then `python tools/build_spec_digest.py .` (views/ is generated).
- Then, as their own commands: `python scripts/orchestrator/coverage.py . --write --no-gh`,
  `python scripts/generate_openapi.py`, `python scripts/reply_inventory.py`. `git diff --stat` after the last two
  must be empty (neither side changed a reply shape without regenerating); if not, read the diff before committing.

Checks, each must pass (chain with `&&`, never `;`):
- `git grep -n "refuse_when_closed\|_already_crossed(\|PAPER_NOT_CONNECTED =\|PAPER_PAUSED =" -- backend frontend/src`
  returns only the `may_act.py` docstring (functions Phase 1-2 removed, called nowhere).
- `git grep -n "def refuse_when_closed\|def _already_crossed" -- backend` returns nothing.
- `cd frontend && npm ci` (node_modules is missing in fresh worktrees), then `npx vitest run > /tmp/vitest_step0.log
  2>&1`
  and read the tail: whole suite green. It must include Part F's `screen-fail-d18-d44.test.js`,
  `tracking.test.js`, `paper-list-4b.test.js`, `tracking-armed-exit-d24.test.js` and Phase 2's `priceState.test.js`.
- `env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy -u ALL_PROXY -u all_proxy python -m pytest tests/errors
  tests/test_no_12_hour_clock_d57.py tests/test_money_outside_engine.py -q` green.
- DB tests: every file of the phase selection (section 4.1) with base `b1055c5`, on a fresh local Postgres clone.
- `env -u ... python tools/ci_local.py > /tmp/ci_local_step0.log 2>&1`, read the tail: TOTAL PASS.

### 4.1 The phase selection of `tests_app` files and the fresh database (used by every phase)

`scripts/orchestrator/select_app_tests.py` diffs `origin/main...HEAD` (its `main`, line 299-301), which is the whole
branch, wider than one phase. For one phase, call its `select` function on the phase diff (verified to run on 25 Nov
with base `707bc5d`):

```
cat > /tmp/phase_select.py <<'PY'
import subprocess, sys
sys.path.insert(0, "scripts/orchestrator")
import select_app_tests as s
base = sys.argv[1]
names = subprocess.run(["git", "diff", "--name-only", base + "...HEAD", "--", "backend/"],
                       capture_output=True, text=True).stdout.splitlines()
diff = subprocess.run(["git", "diff", base + "...HEAD", "--", "backend/"],
                      capture_output=True, text=True).stdout
print("\n".join(s.select(names, diff, "tests_app")))
PY
python /tmp/phase_select.py <phase-base-sha>
```

Run every file it prints, one file per run, each on a fresh clone of the template database, as
`docs/process/GC-ICLIVE-cloud-setup.md` section 1 says (on the fix branch; after Step 0 it is on this branch too):
initdb + start Postgres 16, create `ofo_test` and `ofo_app` as `app-tests.yml`, `alembic upgrade head`, template
`ofo_h_tpl`, then per file `create database <tmp> template ofo_h_tpl`, `revoke all on database <tmp> from public`,
grant connect to `ofo_app`, point the three URLs at it, run, `drop database <tmp> with (force)`. Never against the
owner's VPS. Long output to a log; read only the tail. A file that needs Redis: `redis-server --daemonize yes`.

### 4.2 Step 0b: spec text for ADR-328 (Lane A, before Lane B is cut)

Kit R4 allows the section text before the code. Doing it here means Lane B never edits spec files. First, for each new
line, `python tools/spec_similar.py . "<text>"` and extend or cite a match. Then, as bracketed notes in the style of the
ADR-327 note already in REQ-109 AC-8 (`spec/requirements/REQ-109.md:123`) and ADR-317 (`spec/decisions/ADR-317.md:10`):

- **`spec/decisions/ADR-319.md`** - Where (grep first): point (4), line 15: "A buy and a sell of the same contract stay
  two legs and are not asked about (AC-11)."; Note to add: `[ADR-328 (1) amends (4) for a strike step or a move (step,
  Shift, Width, Hedge): landing on a contract held on the opposite side asks "Keep both" / "Cancel"; a deliberate add
  from the strike picker stays silent.]` Also after point (1): `[ADR-328 (2): Add Selected asks "Replace the N legs?"
  before replacing held legs.]`
- **`spec/requirements/REQ-109.md`** - Where (grep first): AC-9, line 135-136: "onto a contract held on the other side =
  two exits, because the positions net"; Note to add: append `; a step or move asks "Keep both" / "Cancel" first,
  ADR-328 (1)` inside the bracket
- **`spec/requirements/REQ-109.md`** - Where (grep first): AC-5, the ADR-311 sentence "every leg that has a price shows
  its own unbooked figure"; Note to add: `[ADR-328 (3): on the builder's Paper P&L panel the per-leg figure is the leg's
  total, booked plus open, the same as the legs table.]`
- **`spec/requirements/REQ-109.md`** - Where (grep first): AC-4, after "go through the same confirm list"; Note to add:
  `[ADR-328 (4): while the builder shows the trade changed elsewhere, Exit all and every per-leg Exit are disabled with
  "This trade changed elsewhere. Reload to see the current legs."]`

If a hook refuses an ADR-319 edit, put the note only in REQ-109 and say so in the commit. Then
`python tools/build_spec_digest.py .`, `python scripts/orchestrator/coverage.py . --write --no-gh`, `ci_local`, commit
"Spec: ADR-328 notes in ADR-319 and REQ-109 (owner, 25 Nov evening)", prepush, push, CI green. Then cut Lane B:
`git checkout -b refactor/leg-door && git push -u origin refactor/leg-door`.

Owner screen testing starts on `refactor/modular-doors` once Step 0b is green (it then holds Part F and Phases 1-2).

## 5. Phases

Section 5.N is Phase N (5.3 = Phase 3 ... 5.8 = Phase 8).

Gates for every phase (not repeated below): tests-first commit (red; paste the red tail in the commit message); code
commit(s); `python tools/ci_local.py` with the proxy unset; every `tests_app` file of the phase selection (4.1) on a
fresh clone; prepush (about 31-33 minutes); push; CI green before the next phase starts. Independent review per phase:
Opus (Tier A, fresh, adversarial) for Phase 4 and Phase 6 B2; Sonnet otherwise. Two failed review or CI rounds on a
phase: open a `parked` issue with the evidence and what is left, write it in RESULTS, go on. Every PR body: the
Spec-deviation block (`Class: 3` with ADR-328 for Phases 3, 4, 5; `Class: none` for 6, 7, 8) and no "fixes #N" unless
the whole issue is done. Known gate traps (RESULTS "Gate notes"): the money scan flags `+` in new backend files; the
settings-reader guard; line-pinned exceptions in `paper_monitor.py`; the PR241 selection pin
(`tests/orchestrator/test_select_app_tests.py`); `PAPER_MODULES` (`tests_app/test_paper_order_door.py:21-24`).

### 5.3 Phase 3: one paper book source (F3 + F5 + B6), D-41 (two readers), ADR-328 (3) - Lane A

**Core:** on the real reply shapes, the Paper P&L panel's open-leg LTP, quote time and P&L equal the Net Positions row
of the same contract. **Proof:** vitest `one-source-d41.test.js` with a tracking fixture whose `instrument_id` is
`"NSE_FO:44624"` and `contract_id` 5001, and a book whose LTP differs from the tracking reply's; it is red on today's
code and on the patch, green after.

**Spec basis:** REQ-109 AC-5 ("Paper P&L paused - prices not live, as of <time>"; ADR-311: "every leg that has a price
shows its own unbooked figure; an unpriced leg's cell says 'no price', never 0 or blank"); ADR-328 (3) ("per leg, the
leg's TOTAL result (booked plus still open), the same figure as the legs table"); ADR-212 ("Outside market hours ...
the paper screens ... show each open leg's LTP ... from the last close"); ADR-263 (headline after charges, labelled);
ADR-321 (9) ("a price shown without its time states it"); ADR-008.

**Verified facts today.**
- Two reads on two 5 s timers: Net Positions = `GET /paper/strategies/{id}` (`usePaperBookRead.js:16-26`, called
  `StrategyBuilderPage.vue:423`); panel rows = `GET /strategies/{id}/tracking` (`TrackingPanel.vue:229`, `:246`).
  In market hours both use the same basis (`ofo/tracking/paper.py:130`: `display_price` is `leg_price` then).
- The patch's join key is wrong (settled here): the panel's `leg.key` is `instrument_id` (`lib/tracking.js:210`), which
  the server fills with `found.identity` (`routes/tracking.py:413`), `f"{segment}:{token}"`
  (`tracked_contracts.py:59-67`); the book is keyed by `contract_id`. The patch fixture `instrument_id: String(l.id)`
  hides it.
- `TrackingLegOut` has no `contract_id` (`routes/tracking.py:98-104`); the row is built at `:323`; the contract id is
  `int(held.instrument_id)` (`routes/tracking.py:249`, `contract_ids`).
- Part F changed the panel cell: inner `<span data-testid="tracking-leg-ltp">` and a per-leg
  `tracking-leg-quote-at` fed by `leg.quoteAt` (fix branch `TrackingPanel.vue:33,35`; `lib/tracking.js:223`).
- B6 has five copies of "price answers -> live map -> engine": `routes/paper.py` `_figures` (`:654`), `_extremes`
  (`:701`), `_after` (`:942`); `routes/tracking.py` `_book_figures` (`:296-309`); `routes/adjustment_history.py:256`
  (settled here: `live = {str(cid): p.price ... paper_prices.is_live(p) and p.price is not None}`).
- Pinned signatures: `P._figures(orders, found, prices, connected, today)` (`test_paper_unpriced_names.py:45`),
  `T._figures(...)` (`test_tracking_unpriced_legs.py:50,87`, `test_price_display_tracking.py:13`).

**Design.**
- Server: new `backend/ofo_app/strategy_money.py` from the patch: `live_prices(prices)`, `MoneyView`,
  `strategy_money_view(orders, prices, *, totals_priced=True)` (signature differs from PLAN's `(strategy_id, prices)`:
  callers hold the orders; record in RESULTS). `by_contract` is a `functools.cached_property` (skipped when
  `totals_priced` lets the book be reused). No rounding in the door (`_exact` on the book page, `to_paise` on tracking
  stay per route). `strategy_money` imports only `ofo.tracking` / `ofo.engine`.
- API: add `contract_id: int` to `TrackingLegOut` and to the row (`"contract_id": int(held.instrument_id)`); keep
  `instrument_id` as is. Additive. Regenerate OpenAPI and the reply inventory.
- Screen: `readTracking` adds `contractId: leg.contract_id`. `usePaperBookRead.js` gains pure `legPricesOf(book)` ->
  `Map(contractIdText -> {ltp, at, total, noPrice})` (texts as sent; flat contracts skipped; no booked/unbooked fields)
  and `paperPnlBlock(book, failed)` (the `sharedTotal` result plus the map). `TrackingPanel.vue`: a `rows` computed;
  for an OPEN leg found by `leg.contractId` in the book map, `current`, `quoteAt` and `pnl` come from the book
  (`pnl = own.total ?? own.noPrice ?? LEG_PNL_MISSING`); an exited leg or a leg the book does not hold keeps the
  tracking row. Headline from `paperPnlBlock`. Keep Part F's inner span and quote-at span. `StrategyBuilderPage.vue`:
  `paperTotal` from `paperPnlBlock`. `LegPrice` is a plain object, not a component (a component would change pinned
  markup; record the deviation in RESULTS).
- Polls: still two (book and tracking); one SOURCE for the leg price. RESULTS says so plainly (PLAN said "one poll").

**Reuse of `phase3-wip.patch.txt`:** re-type or `git apply` only these hunks: `strategy_money.py` (then make
`by_contract` lazy), the `routes/paper.py` and `routes/tracking.py` door edits, the AST fix for `int | str`
annotations in `test_strategy_money_view.py`, the `PAPER_MODULES` line, `legPricesOf` / `paperPnlBlock` (drop the
booked/unbooked fields), the builder `paperTotal` swap. Write the `TrackingPanel.vue` hunk by hand on the merged file.
Do not apply the patch's RESULTS hunk, its join, or its fixture. Split the patch with the `sed` lines of RESULTS "How to
resume" as their own command (a hook refuses applying a patch created in the same command).

**Tests-first commit (red).** `frontend/tests/one-source-d41.test.js` (new; mount `PaperBookPanel` + `TrackingPanel`
from one `usePaperBookRead`; legs 5001-5004; tracking `instrument_id: 'NSE_FO:4462x'`, `contract_id: 500x`, tracking
prices different from the book's):

- **1** - Test: every open leg shows the book's LTP on both panels; Exact assertion: `net-ltp` texts and
  `tracking-leg-ltp` (inner span) texts both `['149.70','191.85','122.40','92.60']`; State: stated
- **2** - Test: the panel's quote time is the book's; Exact assertion: `tracking-leg-quote-at` texts == `net-ltp-at`
  texts (`'15:13:27'`); the tracking `price_at` time `'15:10:00'` absent; State: stated
- **3** - Test: rows add up to the before-charges total on both panels; Exact assertion: both sum (paise helper,
  test-only) to `+13.00`; `tracking-leg-pnl-head` contains `before charges`; State: stated
- **4** - Test: headline stays the server's after-charges text; Exact assertion: `paper-pnl` and `book-total` contain
  `-262.86`; State: stated
- **5** - Test: join is by contract id; Exact assertion: tracking legs in another order; each row shows its own
  contract's book LTP; State: ambiguous order
- **6** - Test: a leg the book has no price for; Exact assertion: book position `price_state 'stale'`, `ltp_text null`,
  `no_price_text 'no price'` -> panel LTP `-`, P&L `no price`, no quote-at span; priced legs keep figures; State: absent
- **7** - Test: after hours the panel shows the book's last close; Exact assertion: tracking `price_state 'stale'`,
  `current_price_display null`; panel LTP == book LTP (today `-`); State: stated (closed)
- **8** - Test: read failed: headline pauses, rows follow the table; Exact assertion: `sharedFailed true` -> headline
  contains `Paper P&L paused - prices not live`; `tracking-leg-ltp` == `net-ltp`; State: failed
- **9** - Test: no shared book: panel keeps its tracking rows; Exact assertion: `shared: null` -> rows as
  `tracking.test.js` expects; State: not found
- **10** - Test: closed strategy: no book reads; Exact assertion: all `net_quantity 0`; 3 x 5 s; no
  `/paper/strategies/170` call; rows `Exited at <price>`; State: empty
- **11** - Test: empty `positions`; Exact assertion: `legPricesOf` size 0; rows are tracking's; no throw; State: empty
- **12** - Test: request count unchanged; Exact assertion: 3 x `TRACKING_REFRESH_MS` with fake timers: count(book URL)
  == count(tracking URL); no other price URL; State: stated
- **13** - Test: partial exit: panel P&L == table P&L (ADR-328 (3)); Exact assertion: position `booked_text '-5.00'`,
  `unbooked_text '30.00'`, `total_text '25.00'`, net -65 of 130 -> panel P&L `25.00`, `net-pnl` `25.00`; State: stated
- **14** - Test: a book contract id the tracking reply lacks, and a tracking `contract_id` missing (older reply); Exact
  assertion: the row keeps the tracking figures (fail to the old source, never a wrong contract's price); State: absent
  / ambiguous
- **15** - Test: units: `legPricesOf`, `paperPnlBlock`; Exact assertion: open only, texts as sent, keys contract-id
  text, `null` -> empty map; block `kind 'after'`, `text '-262.86'`, `line 'As of 15:13:27 IST'`, `legs.get('5002').ltp
  '191.85'`, `null` for no book; State: stated / absent

Plus `frontend/tests/tracking.test.js`: one NEW `it` (`readTracking` carries `contractId` from `contract_id`); existing
`it`s unchanged. `tests_app/test_strategy_money_view.py` (no DB; the patch's 13 tests with the AST fix) plus:
`test_tracking_rows_carry_the_contract_id` (`row["contract_id"] == int(held.instrument_id)`, `row["instrument_id"]`
still `"NSE_FO:..."`); `test_book_page_and_tracking_rows_agree_per_contract_at_one_price_set` (all live; one unpriced:
`None` both sides; none priced); `test_history_route_uses_the_door_live_prices` (source scan: `live_prices(` present,
the old literal absent in `adjustment_history.py`); door rows: all live, one unpriced (paused; priced leg keeps
`650.00`), no price (booked known), closed book (booked `1300.00`), `totals_priced=False`; `by_contract` computed at
most once per view (counting stub). Red now: `strategy_money` and `contract_id` do not exist.

**Code commits, in order.** (1) `backend/ofo_app/strategy_money.py`. (2) `routes/paper.py` `_figures`, `_extremes`,
`_after` through it; drop the unused `lifecycles` import. (3) `routes/tracking.py` `_book_figures` through it; add
`contract_id`. (4) `routes/adjustment_history.py:256` -> `strategy_money.live_prices`. (5) regenerate
`docs/api/openapi.json` (`python scripts/generate_openapi.py`) and `tests_app/reply_inventory.py`
(`python scripts/reply_inventory.py`); the diff is exactly the new field (`TrackingOut.legs[]`,
`TrackingListOut.strategies[].legs[]`). (6) `tests_app/test_paper_order_door.py`: add `"ofo_app.strategy_money"` to
`PAPER_MODULES`. (7) run `tests/orchestrator/test_select_app_tests.py`; if `PR241_SELECTION` goes red, add the new
test file with a reason comment (as `0e30edc1` did). (8) `lib/tracking.js` one line. (9) `lib/usePaperBookRead.js`.
(10) `TrackingPanel.vue`. (11) `StrategyBuilderPage.vue` (`paperTotal`; drop the `sharedTotal` import if unused).
(12) `ChartCard.vue` comment. (13) RESULTS: replace "Phase 3: PARTIAL" (5 copies -> 1 door; two polls remain; the
`LegPrice` and signature deviations; the after-hours visible change; the mixed-render window of up to 5 s right after an
exit, where one cell may still show the tracking price by design).

**Generated files:** `docs/api/openapi.json`, `tests_app/reply_inventory.py` (drift tests `test_openapi_drift.py:19`,
`test_reply_inventory.py`).

**Stays unmodified (tests must pass unchanged):** frontend `tracking.test.js` (existing its), `one-read-u130f.test.js`,
`paper-book-live.test.js`, `unpriced-legs-adr311.test.js`, `labels-u130f.test.js`, `price-basis-d15-d17-d18.test.js`,
`priceState.test.js`, `pnl-cards-d41.test.js`, `live-card-paper-figures-d06.test.js`, `screen-fail-d18-d44.test.js`;
server `test_paper_unpriced_names.py`, `test_tracking_unpriced_legs.py`, `test_price_display_tracking.py`,
`test_paper_list_figures.py`, `test_paper_totals.py`, `test_paper_totals_rules.py`,
`tests/test_money_outside_engine.py`.
Not touched: `PaperStrategies.vue`, `usePaperPnl`, `LiveStrategyCard`, My Strategies, Home, `AdjustCompare.vue`,
`LegList.vue` (the third reader), fills / stops / triggers (they keep `leg_price`).

**Risks and guards.** Silent fallback of the join (tests 1, 5, 14 with real-shaped ids). Book price beside tracking time
(test 2). Part F's D-18 cell (its test stays green; test 2 covers the shared case). New API field (regenerate; additive;
`readTrackingItem` has no caller). `MoneyView` cost on the list route (lazy `by_contract`, counting test). After-hours
panel shows closes instead of `-` (ADR-212; test 7; screen check). Partial-exit P&L changes from unbooked to total
(ADR-328 (3); test 13). New module graph (`PAPER_MODULES`; `test_strategy_tracking_imports.py` forbids
`execut|basket|orders` in imports; `strategy_money` imports none).

**Review:** Sonnet, adversarial: join key, `quoteAt`, the partial-exit total, every fail-to-old-source row, request
count.

**Done when:** the 15 vitest rows and the server rows red then green; DB selection green on a fresh clone; `ci_local`
TOTAL PASS; OpenAPI and inventory diff = the one field; CI green; RESULTS section written.

**Size:** 12 files changed, about 350 lines with tests.

### 5.4 Phase 4: the exit door (B1 + F2), D-05 builder half, ADR-328 (4), R5 - Lane A

**Core:** "given a strategy, exit its open legs at market" is one server function; every server path that builds paper
exit orders calls it and the stored rows (side, qty, kind, reason, trigger_id, placed_at, stored order) are exactly as
today. **Proof:** a DB test opens a real 4-leg NIFTY condor (the strategy-155 legs of
`tests_app/test_paper_batch_buys_first.py:60`), exits it through each caller, and compares the stored rows with a
golden list captured from today's code on the same input BEFORE anything moves.

**Spec basis:** REQ-109 AC-4 ("'Exit all' and a per-leg exit go through the same confirm list ... editable quantity up
to the open quantity"); REQ-109 AC-5 / ADR-322 (3) (an exit is judged per leg; a leg with no live price is refused
with "Prices are not live; try again when they update"); REQ-109 AC-7 (settle at intrinsic value from the official
close); REQ-109 AC-8 (stops record at the LTP of the tick that crossed; fire once); ADR-117 / D-02 (buys first);
ADR-212 (no fill at a closing price); ADR-002; ADR-328 (4) (quoted in 2.1); ADR-281 (paper only).

#### 5.4.1 Verified facts today (file:line, `b1055c5`)

- **Manual / builder `POST /paper/strategies/{id}/orders` (`routes/paper.py:1298`)** - Leg pick and side/qty: the
  browser (`exitRowsFor` `paperList.js:197-206`; `paperOrdersFor` `paperDrafts.js:103-143`); server re-checks reducing
  (`paper_store.py:85-95`); Price: `_server_exit_prices` (`:1221-1245`); browser price ignored (`:1309-1310`, `:1326`);
  Writer: `paper_limit.place_checked`; Stored: kind as sent, reason/trigger None, one `now()`; Lock: none before `place`
- **Tracking exit `POST /strategies/{id}/tracking/exit` (`routes/tracking.py:513-556`)** - Leg pick and side/qty: named
  indexes into `book.contract_legs` (net per contract, `ofo/tracking/book.py:57-60`), `_opposite(side)`, whole open qty
  (`:549-551`); Price: `_snapshot` (`:545`), no try (a raise -> 500); Writer: `place_checked` via `_write` (`:475-494`);
  Stored: exit, None, None, quote time per leg (`:550`); Lock: none before `place`
- **Monitor `_fire` (`paper_monitor.py:208-246`)** - Leg pick and side/qty: book read with no lock (`:216-218`); leg
  stop one contract, conditional `sorted(open_net)` (`:223`); `"SELL" if net > 0 else "BUY"`, `abs` (`:235`); Price: leg
  stop: the tick (`:251`); conditional: one provider read, no wait (`:252-262`); Writer: `paper_store.place`; Stored:
  stop, reason text, trigger id, tick clock; Lock: claim (`:227`) BEFORE the strategy lock (`paper_store.py:116`)
- **Settlement `_settle_strategy` (`paper_settlement.py:162-182`)** - Leg pick and side/qty: due contracts only; `"BUY"
  if net < 0 else "SELL"` (`:177`); Price: `settle_price` intrinsic (`:124-130`); Writer: `paper_store.place`; Stored:
  settle, reason, None, 15:30 IST of expiry; Lock: lock FIRST (`:166`)

- Deadlock A3 (reasoned, settled as plausible from the SQL here): the monitor's `_CLAIM` UPDATE locks the trigger row
  (`paper_trigger_store.py:45-46`), then `place` waits for the strategy lock; a route inside `place` holds the strategy
  lock and its `reconcile_triggers` `_STALE_CANCEL` UPDATE (`paper_store.py:51-52`, called from `place`) targets the
  same armed trigger when the exit leaves the strategy (or that leg) flat. Not run; the tests-first commit proves or
  disproves it.
- Builder gate today: Exit all (`PaperBookPanel.vue:15`) never disabled; per-leg Exit (`:64`) only on a bad lots box;
  `exitAllPaper` / `exitPaper` (`StrategyBuilderPage.vue:446-457`) check `paperStale` only; `paperBookFailed`
  (`:430-434`) only swaps the as-of line; `paperContractsChanged` (`:423`) only shows `book-contracts-changed`
  (`PaperBookPanel.vue:23`, `CONTRACTS_CHANGED_TEXT` `lib/tracking.js:176`). `openKey` includes quantities
  (`usePaperBookRead.js:10`), so a lot change elsewhere also sets it.
- Positions rule to copy: `PaperStrategies.vue:239-240` (`usePriceFreshness` -> `readOk`), Exit disabled (`:150`),
  reason `NOT_LIVE_EXIT` (`:151`, `priceState.js:13`), `ask` refuses (`:316`), `doExit` posts nothing (`:326`), a failed
  read closes the confirm (`:281-286`), figures `PAPER_NO_FIGURE` (`:228`).
- Pinned today: `paper-place-refresh.test.js:231` opens the Exit-all dialog, sets `paperContractsChanged = true`, then
  Confirms and expects the post and the mark cleared (settled here). No test asserts Exit all stays enabled on a failed
  read (settled here: grep of `paper-exit-all` in `paper-place-refresh`, `builder-drafts-exit`,
  `exit-preview-not-pending`, `paper-dialog-safe`).
- Real path: `execute_plan.exit_legs` (`execute_plan.py:223-226`) sorts `sorted(held.items())` by the plan's
  instrument string (string order: `"NFO-OPT:10"` before `"NFO-OPT:9"`, `test_execute_route.py:565-569`). A closing
  basket case exists in `tests_app/test_checked_basket.py:185` (settled here).

#### 5.4.2 Design

`backend/ofo/tracking/closing.py` (stdlib only; B2's shared step, used in Phase 6 by the real path):
`Close(key, side, quantity)` and `open_legs_to_close(net, only=None) -> list[Close]`: one close per non-zero net,
opposite side, whole open quantity, in the order of `only` (or of `net`); a key of `only` with net 0 or absent is left
out; no sorting, no float.

`backend/ofo_app/paper_exit.py` (add to `PAPER_MODULES` with `ofo.tracking.closing`):
- `live_exit_prices(ctx, feed, underlying, contracts, *, at, connected_rule, on_read_error)` -> prices or `Refused`.
  The one live exit read; today's two copies (`routes/paper.py:1221-1245`, `routes/tracking.py:537-548`) become it.
  It keeps today's read (`tracking._snapshot` -> `planned_entry.hold_until_priced`, 3 s, `planned_entry.py:45`) so no
  refusal changes. `connected_rule="ctx"` (orders route: `ctx is None`) or `"provider"` (tracking:
  `provider.status().connected`), L3 kept. `on_read_error="refuse"` (orders: `tracking_exit_prices_not_live`) or
  `"raise"` (tracking: today's 500), L2 kept. Market half `may_act.refuse_unless_allowed` before the read; price half
  `may_act.prices_ok("exit", ...)` on it.
- `exit_strategy(conn, *, user_ref, strategy_id, kind, prices, only, closes, reason, placed_at, trigger_id,
  before_write, write) -> Exited | Refused | NotYet | Flat`, in this order:
  1. `store.lock_strategy(conn, user_ref, strategy_id)` first, for every caller (fixes A3 / L4).
  2. `paper_store.load` under the lock -> net per contract.
  3. `open_legs_to_close(net, only)` on the locked net; empty -> `Flat`.
  4. Quantities: `closes="locked"` (monitor, settlement) uses step 3. For the tracking route the caller passes its own
     `closes` (side and qty from its pre-read book, built with the same `open_legs_to_close`), used as given and not
     filtered by step 3. The store's `_check_reducing` then refuses a shrunk or flat leg as today, the whole call rolls
     back (`EXIT_EXCEEDS_OPEN` -> `tracking_leg_already_exited`), and a grown leg is part-closed as today.
  5. Price each close from `prices` (a mapping for Given / Intrinsic, or a callable on the targets for the conditional
     exit's one provider read). Missing: `NotYet` (monitor) or `Refused(tracking_exit_prices_not_live)` (route).
     A live source is read BEFORE step 1 by the route (`live_exit_prices`), never under the lock.
  6. `before_write()` (the monitor's `claim_fire`); False -> `Refused("already_fired")`, mapped to "cancelled".
  7. Build `NewOrder(...)` in `only` order and call `write(...)` (`paper_store.place` for monitor and settlement; a
     closure over `paper_limit.place_checked` for tracking). `place` keeps `buys_first`.
  8. Return `Exited(book, written)`. The door never commits; each caller keeps its transaction.

Callers after the move:
- Tracking exit: validate indexes as today -> `live_exit_prices("provider", "raise")` -> `exit_strategy(kind="exit",
  only=ids in body order, closes=<from bk.legs[i], body order>, placed_at=quote time or answered (L1 kept),
  write=place_checked closure)`.
- Manual orders route: only `_server_exit_prices` is replaced by `live_exit_prices("ctx", "refuse")`. No lock change,
  no body change; `paperOrdersFor` and the mixed basket stay.
- Monitor: `exit_strategy(kind="stop", only=[t.contract_id] or None, closes="locked", prices=tick or callable,
  before_write=claim, reason=stop text callable, trigger_id=t.id, placed_at=now, write=place)`; `Flat` -> cancel as
  today (`:219-222`); `NotYet` -> None; the alert as today from `Exited.book`. The calendar (`:181`) stays its own.
- Settlement: `exit_strategy(kind="settle", only=due ids, closes="locked", prices=intrinsic map, ...)`; its own
  `lock_strategy` / `load` go (the door does them; order unchanged since it already locked first).
- R5 (last code commit of the phase): `ofo/engine/legs.py` gains `intrinsic_value(instrument, strike, level)`;
  `_long_value_at` calls it; `paper_settlement.settle_price` is deleted and its caller uses the engine function.
  No `require_decimal` added (callers hold a Decimal; `expiry_value` keeps its own check).

Frontend F2 + ADR-328 (4):
- `lib/priceState.js`: add `CHANGED_ELSEWHERE_EXIT = 'This trade changed elsewhere. Reload to see the current legs.'`
  (ADR-328 (4) verbatim) beside `NOT_LIVE_EXIT`.
- `lib/usePaperExit.js` (new): `usePaperExit({ readFailed, held, busy, pending, changed })` -> `{ blocked, reason }`;
  `blocked = !readOk || changed || busy || pending`; `reason` = `NOT_LIVE_EXIT` when the read failed (first), else
  `CHANGED_ELSEWHERE_EXIT` when `changed`, else null. Positions passes `changed: false`.
- `components/strategy/ExitButton.vue` (new): `:disabled="blocked || extraDisabled"`; the `paper-exit-reason` line
  when `reason`. Every existing test id kept (`exit-selected-<id>`, `paper-exit-all`, `net-exit`).
- `PaperBookPanel.vue`: Exit all (`:15`) and per-leg Exit (`:64`) through `ExitButton`; when `readFailed`: total,
  Avg, LTP and its time, Booked, Unbooked, P&L show `PAPER_NO_FIGURE` (the Positions rule). `book-contracts-changed`
  line stays as it is.
- `StrategyBuilderPage.vue`: `exitAllPaper` / `exitPaper` return when `paperBookFailed` or `paperContractsChanged`;
  `confirmPending`: when the dialog was opened by Exit all or a per-leg Exit (a new `exitOrigin` flag set in those two
  functions) and `paperBookFailed` or `paperContractsChanged` is true, post nothing, close the dialog, keep the edits,
  show the reason; a watch closes such a dialog when either turns true. A dialog opened by "Review and add" for other
  edits is unchanged (ADR-328 (4) names only the Exit buttons).
- `PaperStrategies.vue`: Exit (n) through `ExitButton` / `usePaperExit` (same text and test ids); its POST
  (`:331`) through `addToPaper` (`lib/tracking.js:76-83`); with no suggestion ids the body is exactly `{ orders }`.

#### 5.4.3 What changes and what does not (race-only, read this before review)

- L4 (lock order) is FIXED, because lock-first is binding; the deadlock test is in the tests-first commit.
- The monitor now reads the net under the lock, so an add committed between today's unlocked read and the lock is
  closed in full (today it stays open with no stop). This is the monitor half of L5 and follows from lock-first; it
  is race-only and safer. The tracking route keeps today's sides and quantities (step 4), so its half of L5 is unchanged
  and stays deferred. (The phase-4 report proposed refusing on a grown leg; overruled here: a new refusal is a behaviour
  change the bound does not allow.)
- Unchanged and deferred: L1, L2, L3, L6 remainder (a "Review and add" dialog of other edits while the trade changed),
  L7 (two-tab partial exit), L8 (conditional exit silent while any contract is not live).

#### 5.4.4 Tests-first commit

Capture golden rows from today's code first (run each new golden test on the pre-phase head and paste the rows into the
test). `tests_app/test_exit_door.py` (DB):

- **1** - Test: `test_tracking_exit_all_four_condor_legs_rows_match_golden`; Assertion: stored (contract, side, qty,
  kind, reason, trigger_id, placed_at) list == golden; buys first; placed_at = quote times; State: stated
- **2** - Test: `test_tracking_exit_one_named_leg_rows_match_golden`; Assertion: subset only; other legs untouched;
  State: stated
- **3** - Test: `test_manual_exit_all_rows_match_golden`; Assertion: server price, browser price ignored; State: stated
- **4** - Test: `test_manual_partial_exit_one_lot_rows_match_golden`; Assertion: one lot stored; State: stated
- **5** - Test: `test_conditional_exit_rows_match_golden`; Assertion: kind stop, reason text, trigger id, sorted ids
  then buys first; State: stated
- **6** - Test: `test_leg_stop_rows_match_golden`; Assertion: tick price, one contract, whole qty; State: stated
- **7** - Test: `test_settlement_rows_match_golden`; Assertion: intrinsic, 15:30 IST, reason, only the due contracts of
  a two-expiry trade; State: stated
- **8** - Test: fail-closed rows, nothing stored, code unchanged; Assertion: no ctx -> `tracking_not_connected`;
  provider disconnected -> tracking `tracking_not_connected`, orders `tracking_exit_prices_not_live` (L3); contract not
  live -> `tracking_exit_contract_not_live`; one named leg stale / missing -> `tracking_exit_prices_not_live`; read
  raises -> orders 409, tracking 500 (L2); market closed -> `gate_market_closed`; exceeds open ->
  `paper_exit_exceeds_open` / `tracking_leg_already_exited`; State: absent / failed / not found
- **9** - Test: `test_monitor_missing_price_keeps_the_trigger_armed_and_stores_nothing`; Assertion: NotYet; trigger
  still armed; State: absent
- **10** - Test: `test_flat_strategy_cancels_triggers_and_stores_nothing`; Assertion: Flat; triggers cancelled as today;
  State: empty
- **11** - Test: `test_monitor_and_tracking_exit_at_once_one_wins_no_deadlock`; Assertion: two connections, driven step
  by step (monkeypatch an `asyncio.Event` pause in the monitor between claim and place today, between lock and claim
  after): exactly one set of closing rows, the loser stores nothing, no `DeadlockDetected`. RED today if A3 is real; if
  green today, keep it as a guard and write "A3 not reproduced" in RESULTS; State: ambiguous (race)
- **12** - Test: `test_a_leg_added_between_read_and_lock`; Assertion: tracking route: rows as today (part close of the
  old qty, golden); monitor: closes the whole locked qty (new, race-only, 5.4.3); State: ambiguous (race)
- **13** - Test: `test_failed_insert_on_order_three_stores_nothing`; Assertion: a raise on the 3rd insert rolls back
  every row (A1); State: failed

Also: `tests/tracking/test_closing.py` (no DB): empty, zero nets, longs, shorts, `only` order kept, `only` key absent
or flat left out, no float, no sorting. `tests/engine/test_intrinsic_value.py`: CE/PE/FUT x (in, at, out of the money)
`intrinsic_value == _long_value_at` == the old `settle_price` values (9 rows). `frontend/tests/exit-gate-d05.test.js`:
builder with a good read then a 503 on `GET /paper/strategies/{id}`: `paper-exit-all` and every `net-exit` disabled;
`paper-exit-reason` = "Prices are not live; try again when they update"; `book-total`, `net-ltp`, `net-avg`,
`net-booked`, `net-unbooked`, `net-pnl` = "—"; `book-as-of` = "Paper P&L paused - prices not live, as of HH:MM:SS";
clicking posts nothing; an open Exit dialog closes; a "Review and add" dialog of adds only stays; the next good read
enables everything again (failed, then stated). ADR-328 (4) rows: `contractsChanged` true -> both disabled,
`paper-exit-reason` = "This trade changed elsewhere. Reload to see the current legs.", `book-contracts-changed` still
shown, clicking posts nothing; an open Exit dialog closes and posts nothing; both flags true -> the not-live reason;
the mark cleared (reload or the builder's own re-read) -> enabled (stated / ambiguous). Positions: the POST goes
through `addToPaper` with body `toEqual({ orders: [...] })`.

Test changed in this commit, with the reason: `paper-place-refresh.test.js:231` ("a 'contracts changed' mark left by a
poll is cleared once the re-read succeeds") Confirms an Exit-all dialog after the mark is set; under ADR-328 (4) that
Confirm posts nothing. Change: set the mark after the Confirm's POST has returned (before the re-read), assertions on
the mark unchanged. Reason line: "ADR-328 (4): an Exit dialog never posts while the trade changed elsewhere".

#### 5.4.5 Code commits, in order (one file group per commit)

1. `backend/ofo/tracking/closing.py`. 2. `backend/ofo_app/paper_exit.py` + `PAPER_MODULES` gains `"ofo_app.paper_exit"`
and `"ofo.tracking.closing"`. 3. `routes/tracking.py` exit route onto the door. 4. `routes/paper.py`:
`_server_exit_prices` -> `paper_exit.live_exit_prices`. 5. `paper_monitor.py` `_fire` onto the door (lock first;
mind the line-pinned exceptions). 6. `paper_settlement.py` onto the door. 7. Frontend: `priceState.js`,
`usePaperExit.js`, `ExitButton.vue`, `PaperBookPanel.vue`, `StrategyBuilderPage.vue`, `PaperStrategies.vue`.
8. R5: `legs.py`, `paper_settlement.py`, `tests_app/test_paper_settlement.py:336` (calls the engine function).
Then: PR241 selection pin for new `tests_app` files; ruff ratchet; money scan.

#### 5.4.6 Unverified, first step of the phase

- A3 is real: run test 11 on the pre-phase head on a fresh clone (`... python -m pytest -c pytest-app.ini
  tests_app/test_exit_door.py -k deadlock`). Red = A3 proven; green = keep as a guard (see row 11).
- Optional switch of `live_exit_prices` onto `read_market(purpose="exit")` (add `"exit"` to `Purpose`,
  `market_read.py:38`): only if `test_paper_server_exit_price.py:48,57,70,78` and `test_strategy_tracking_list.py:242,
  254,274` stay green unmodified; otherwise keep `_snapshot` and record why. Separate commit; not required.

**Generated files:** none (no reply shape changes).

**Stays unmodified:** `paperOrdersFor`, `legsAfterExit`, `confirmRowsFor`, the mixed-basket route and its body,
`LegList`, the socket "Reconnecting" line, `ofo/execution/**`, `routes/execute.py`. Tests unchanged:
`test_paper_monitor.py`, `test_paper_settlement.py` (except `:336`), `test_paper_batch_buys_first.py`,
`test_strategy_tracking_list.py`, `test_paper_server_exit_price.py`, `test_ic_exits_paper.py`,
`test_ic_paper_loop_core.py`, `test_paper_adjustment_limit.py`, `test_paper_save_paths_fx2.py`, frontend
`paper-list-4b.test.js`, `paper-exit-rows-buys-first.test.js`, `builder-drafts-exit.test.js`,
`paper-drafts-diff.test.js`,
`exit-preview-not-pending.test.js`, `paper-strategies.test.js`, `paper-dialog-safe.test.js`.

**Risks and guards:** stored rows drift (goldens); lock order (test 11; reviewer checks every caller); a wait under the
lock (live read before the lock; reviewer); a stale tick as a fill (`stops.crossed` stays the judge; the door never
re-derives); a qty-0 order from a flat `only` key (closing unit tests); float (Decimal only; money scan); the alert
lost (alert from `Exited.book`, `test_paper_monitor.py` stays green); the page dialog flow (`paper-place-refresh`,
`paper-dialog-safe` green).

**Review: Tier A, fresh Opus, adversarial.** It attacks the 15 cases of the phase-4 report section 6 (A1 half exit,
A2 double exit, A3 deadlock, A4 exit during settlement, A5 add between read and write, A6 two-tab partial, A7 stale
price as a fill, A8 exit from an old net (now ADR-328 (4)), A9 buys first, A10 net after partial exits, A11 naked short
by subset, A12 Exit all with one unpriced wing, A13 qty 0 / flat in `only`, A14 Kite order change, A15 first tick after
restart), plus: goldens byte-equal, lock order in every caller, no read with a wait under the lock, no float, R5 parity.

**Done when:** goldens equal; tests 8-13 as stated; vitest gate rows red then green; Tier A PASS (no critical or major);
DB selection green; `ci_local` TOTAL PASS; CI green; RESULTS "server exit builders: 3 + 1 pricer -> 1 door"; the
deferred issues of 6.1 filed.

**Size:** about 14 files, 700-900 lines with tests.

### 5.5 Phase 5: one leg door (F6), D-60, ADR-328 (1) and (2), ADR-329 (chain trip and leave question) - Lane B

**Core:** one door instance per builder page asks every add-or-move question; a step onto an opposite-held contract
asks "Keep both" / "Cancel"; a picker add of the opposite side asks nothing. **Proof:** on the real recorded condor
of `leg-step-duplicate-d60.test.js`, step a SELL onto the held BUY of the same contract: the dialog opens with
exactly "Keep both" and "Cancel"; Escape leaves the legs equal to before and sends no further `leg-edit`.

**Spec basis (ADR-329 added):** ADR-329 (1)-(3) (the hold, the leave question, Add Selected adds); ADR-007 Q34 ("all
ticked contracts arrive in the Builder as legs"); ADR-319 (1) (quoted in the Phase 5 report: "Every way of adding or moving a leg ... that lands on a
contract another leg already holds with the same action asks ..."); ADR-319 (4) as amended by ADR-328 (1); REQ-030
AC-11 ("The same contract with opposite actions stays as two separate legs; no auto-netting"), AC-12; REQ-109 AC-9
("onto a contract held on the other side = two exits, because the positions net", now with the question first);
REQ-079 AC-5 ("Replace the 2 legs in the builder?", `lib/readyMade.js:44-46`); ADR-328 (2).

**Verified facts today.** `sameContract` (`legDoor.js:14`) needs the same action; `admitLegs` (`:19-35`). Moves:
`askMovedDuplicates` (`StrategyBuilderPage.vue:769-791`), called at `:817` inside `:814-826`; the page dialog at
`:1004-1012`; the picker copy `LegPicker.vue:676-684`, its `dup` state `:512-518` (a second ask overwrites the first
and never settles it; no stale-legs guard). The step that pins silence today: `leg-step-duplicate-d60.test.js:91`.
`RELATIVE_CONTROLS` (`legEdit.js:54`). Ready-made replaces after its own prompt (`ReadyMadePanel.vue`, REQ-079 AC-5).

Add Selected, settled here (corrects the phase-5 report): `OptionChainPage.vue:125` pushes the builder route with
`?draft=` from a different route (`router/routes.js:12` builder, `:23` chain; `App.vue:11-13` plain `router-view`, no
keep-alive). The builder is mounted fresh and `legs = ref(legsFromQuery())` (`StrategyBuilderPage.vue:121`), so on
arrival from the chain there are no held legs to replace. The earlier unsaved legs were already dropped when the user
left the builder (no leave question; the builder writes no draft into the URL, `router.replace` only at `:138`, `:174`,
`:361`, `:387`). The only in-page replacement is the `watch(() => route.query.draft)` at `:626-640` (the page stays
mounted when only its query changes, F-4 comment `:617-619`). ADR-329 answered the question this raised (O-1, section 7): see "ADR-329 design" below; the 5.5 design list above
this paragraph (door, moves, the draft-watch question) is unchanged by it.

**Design.**
- `lib/legDoor.js` stays pure: add `oppositeContract(a, b)` (same `instrument_id`, other action) and an `opposite`
  option to `admitLegs` (`'allow'` default, `'ask'` for moves). Texts: `DUP_QUESTION` unchanged; new
  `OPPOSITE_QUESTION(name, heldAction)` = "<contract> is already in this strategy as a Buy." (or Sell) and
  `OPPOSITE_NOTE` = "A Buy and a Sell of one contract cancel each other out." (new wording; on the screen-check list).
- `composables/useLegDoor.js`: one pending slot; `ask(leg, kind)` cancels any open question first; `answer`,
  idempotent `cancel`; `admit(held, incoming, { skipId, opposite })`; `admitMoved(baseLegs, landed)` (the page's
  `askMovedDuplicates`, moved; moves pass `opposite: 'ask'`; moved legs are also checked against each other, as
  `:774-780`).
- `components/strategy/DuplicateLegDialog.vue`: the Modal with the same test ids (`dup-dialog`, `dup-question`,
  `dup-increase`, `dup-separate`, `dup-cancel`). For `kind 'opposite'`: no `dup-increase`; `dup-separate` reads
  "Keep both" (answer `'separate'`); `dup-cancel` "Cancel". Escape / x / overlay = `door.cancel()`.
- The page creates the door, renders ONE dialog, `provide('legDoor', door)`. `LegPicker` does
  `inject('legDoor', null) ?? useLegDoor(...)` and renders its own dialog only when it made its own (tests mount it
  alone). The picker gains the page's stale-legs guard: a changed `props.legs` after the await = Cancel.
- Entry points: picker Done, futures, form Save, edit form (`skipId`) -> `door.admit` with `opposite: 'allow'`
  (deliberate adds and edits stay silent for the opposite side); step, Shift, Width, Hedge -> `door.admitMoved` with
  `opposite: 'ask'`, asked BEFORE `legs.value = landed` (same place as `:817`), in Drafts Mode too. Ready-made, chain
  link, URL / pasted `?draft=` (duplicate rows not asked), saved load, Compare, Undo, remove, Exit keep their flows.
- ADR-328 (2): in the `route.query.draft` watch, when the builder shows legs and the incoming legs differ, ask
  `replacePrompt(count)` (`lib/readyMade.js:44-46`, the REQ-079 AC-5 sentence, singular handled; the earlier name
`replaceQuestion` was wrong) in a small confirm (test ids
  `draft-replace-dialog`, `draft-replace-yes`, `draft-replace-cancel`); Yes = today's path; Cancel = legs, Drafts Mode
  and `openStrategy` unchanged and the previous query put back with `router.replace` so the URL matches the legs.
  A fresh mount (a pasted link, a reload) asks nothing: it holds no legs. A mount that arrives from the chain trip is
  not this question: it is the ADR-329 add (below). This question is only for the page that is already mounted.
- Guard: `frontend/tests/leg-emitters-guard.test.js`: scan `components/**/*.vue`, `pages/**/*.vue` for
  `emit('update:legs'` and `legs.value =`; each hit must be in a function that calls `door.admit*` or on a named
  allow-list (setLegs replacements, `applyEditReply`, ready-made `run`, Undo, remove, Exit, `nameLegsFrom`), with a
  reason each; a stale allow-list entry fails; a pure `problems(files)` with in-memory mutations.

### ADR-329 design (Lane B): the chain trip and the leave question

**Core:** build 3 legs (unsaved), go to Market > Option Chain, tick 2 contracts, Add Selected: the builder shows 5 legs.
**Proof:** the chain-trip vitest below on the 3 legs of `leg-step-duplicate-d60.test.js`'s recorded condor plus two ticked
contracts: 5 rows, the 3 held ones first, then the 2 ticked, no question; a ticked contract equal to a held leg asks the
usual three-button question.

**Verified facts today (`4428e16`, file:line).**
- Legs live only in the page: `const legs = ref(legsFromQuery())` (`StrategyBuilderPage.vue:121`). The builder and the
  chain are two lazy routes (`router/routes.js:12-23` map: `strategies-strategy-builder`, `market-option-chain`; a second
  builder name `strategy-builder-screen` at `routes.js:87`, `/strategy/builder`); `App.vue:11-13` is a plain
  `router-view`; no `keep-alive`, no `onBeforeRouteLeave`, no `beforeunload`, no `router.beforeEach` anywhere in `src`
  (grep). The builder is unmounted on every leave and mounted fresh on every arrival.
- There is no store of builder legs. The only cross-page store of this kind is `stores/chainSelection.js:27` (Pinia,
  `main.js:15`); it keeps the chain's ticks across route changes, and "Add Selected" does not clear them
  (`OptionChainPage.vue:123-126` only pushes the route; the `clear()` at `:80,:85` is the chain's data clear).
  Browser storage: `sessionStorage` only in `SessionEndedCard.vue:15`, `localStorage` only in `lib/execute.js:60,70`.
- "Unsaved" has no flag of its own, but it is derivable: `savedId` (`:350`) is set when a strategy is opened or saved
  (`openSaved` `:370-371`, `onSaved` `:390-391`) and nulled by any edit (`setLegs` `:644`; the leg-edit reply `:830` unless
  the edit was only the include tick, `:704`; delete `:384`); `openStrategy` (`:356`) SURVIVES edits, so a saved-but-edited
  strategy has `openStrategy` set and `savedId === null`. Drafts Mode: `paper` (`:400`); its legs start as the book's net
  (`enterDrafts` `:413-418`), and the unsaved part is `pendingOrders` (`:401`, `paperOrdersFor(net, legs)`), the number the
  bar shows as "N pending changes".
- How the chain is opened from the builder today: there is NO link. "Pick from Option Chain" (`LegList.vue:180`,
  `pickFromChain` `:901`) opens the strike picker drawer on the same page. The chain page is reached by the nav
  (`router/nav.js:40`), Home (`HomeOverviewPage.vue:100`) or Index View (`IndexViewPage.vue:51`): a router navigation to
  route name `market-option-chain`, which leaves (unmounts) the builder. The new leave guard keys on that route name.
- Add Selected: `openBuilder` pushes `{ name: BUILDER_ROUTE, query: { draft: JSON.stringify(selection.draftOf(u)) } }`
  (`OptionChainPage.vue:123-126`, `BUILDER_ROUTE` `:38`); `draftOf` reads `legsOf`, the one choke point (permitted legs with
  an action). That hand-over is KEPT: the `?draft=` link stays the carrier (same JSON, so a pasted or reloaded link and
  `chain-selection.test.js:71-93` are unchanged).
- The door: `admitLegs(held, incoming, { ask, maxLots, skipId })` (`legDoor.js:19-35`) asks only on the SAME contract with
  the SAME action (`sameContract` `:14`); an opposite-side incoming leg is not a clash and is returned in `kept`: it is
  added silently, which is exactly ADR-329 (1) (no new rule). Cancel returns `null` (nothing added); Increase past the
  lots limit returns `{ error }` (nothing changed).
- Pinned today: `chain-selection.test.js:71-93` (Add Selected -> builder route + the `?draft=` legs), `draft-link.test.js:92-`
  (`openBuilder` mounts the real page on a query), `:114` (a `?draft=` opens its own legs), `:265` (a new `?draft=` on a
  mounted page replaces the legs with no question), e2e `chain-selection.spec.ts:72-93` (chain -> Add -> builder url and
  `data-state`). No test navigates the mounted builder to another route with legs.

**Mechanism (one): `stores/builderHold.js`, an in-memory Pinia store.** State: `held` = null or
`{ legs, openStrategy, savedId, savedRevision, shapeName, paperId, netKey }` (copies; legs are the page's own leg
objects; `paperId` and `netKey` only in Drafts Mode, `netKey` = the list of `contract_id|action|lots` of the book's net as
strings, compared for equality, never summed). Actions: `hold(snapshot)`, `take()` (returns and clears at once), `clear()`;
getter `count` (the N of the sentence). Why this one: see section 2.2 (Pinia is where the chain's ticks already live;
`keep-alive` and `sessionStorage` rejected there). Properties the tests pin: the browser does no money arithmetic and
computes nothing (it keeps what the page had; the shape, the outcome and every figure are re-asked from the server by the
page's existing paths when its legs are set, as after any `setLegs`); NOTHING is sent to the server by the hold; the held
legs keep their `planned_entry` and `captured_at` (a price states its time, ADR-321 (9)). **A full page reload (F5, a
closed tab, typing an address) empties the store: the unsaved legs are lost with no question (`beforeunload` is OUT, 2.2),
and a reload on `?draft=` re-opens the ticked legs only, exactly as today.** Hold dies with the tab; nothing survives a
new sign-in because a new load is a new store.

**Which navigations do what** (`useLeaveBuilder(...)`, one composable, `onBeforeRouteLeave` in the builder and in the chain
page; the target is `to.name`):
- Builder -> `market-option-chain`: never asks. If the page shows any legs: `hold(snapshot)`; allow. (No legs: nothing
  held.)
- Builder -> any other route (a route NAME other than the chain; the builder's own two names are not "leaving"): if
  unsaved (below): ask; Stay = cancel the navigation (page, legs, Drafts Mode untouched); Leave = `clear()` and allow. If not
  unsaved: `clear()` and allow, no question.
- Chain page -> builder (either name): allow, never asks (the hold waits for the builder to take it).
- Chain page -> any other route while `held` is set: ask the same question (the held legs are still the builder's,
  2.2); Stay = the user stays on the chain with the hold kept; Leave = `clear()`, allow. With no hold: no question
  (today's chain page).
- Never ask: Save, Save As, Add to Paper (they end with `savedId` set or `pendingOrders` empty, so "not unsaved"; none of
  them navigates, `:138,:174,:361,:387` are same-route `router.replace`), opening the chain, a `?strategy=` or `?draft=`
  change while the page stays mounted (not a leave: `onBeforeRouteLeave` does not fire; the `?draft=` one is the
  ADR-328 (2) question above; a `?strategy=` link replacing unsaved edits keeps today's silent replace, `:613-615`: a
  deferred issue, not ADR-329), `router.replace` writes of the page itself.
- "Unsaved" (`unsavedCount(page)`, a pure function of the page's refs, tested alone): not in Drafts Mode =
  `legs.length > 0 && savedId === null` (so a draft link's legs, ready-made legs, and a saved-but-edited strategy all
  count; N = `legs.length`); in Drafts Mode (`paper` set) = `pendingOrders.length` (a paper strategy shown unchanged
  asks nothing; one with edits asks with N = the pending changes the bar shows). A saved strategy with no edits: not
  unsaved.
- The held record is made for ANY shown legs on the chain trip (saved or not): 2.2.

**Return from the chain (builder mount; `useBuilderHold().take()` runs in `setup` before `legs = ref(...)`, `:121`).**
Cases, by query:
- no `?draft=`, no `?strategy=` / `?adjust=` (nav link, Back): the held legs and context come back (`legs`, `openStrategy`,
  `savedId`, `savedRevision`, `shapeName`), as the page was: "legs still there". Drafts Mode: replace the URL query with
  `?strategy=<paperId>` (the existing watch re-reads the book, `:620-624`); when that read lands, if its `netKey` equals the
  held one the held legs are set (`setLegs`: pending changes reappear), else they are dropped and the page says: "The
  strategy changed while you were away. Your unsaved edits were not restored." (new wording, screen-check list). If this
  Drafts Mode restore costs more than 2 rounds, Lane B ships the plain-builder hold, parks the Drafts Mode restore with a
  `deferred` issue and says so in `RESULTS-lane-b.md`; the leave question covers Drafts Mode regardless.
- `?draft=` with a held record (Add Selected after a trip): the held legs come back first; then the draft's legs go through
  the door (below). `?draft=` with no held record (chain opened directly, a pasted or reloaded link): today's seed
  (`legsFromQuery`, `:121`): fresh builder, no question.
- `?strategy=<id>` or `?adjust=` with a held record: the held record is dropped (`clear()`), today's open path runs and
  replaces unsaved edits without a prompt as it does now (not ADR-329).

**Add Selected adds through the door** (`StrategyBuilderPage.vue`, once, after mount): the incoming legs are
`legsFromQuery()` (`:122-135`), re-id'd `chain-<n>` so they never share an id with a held leg; `door.admit(held, incoming,
{ opposite: 'allow' })`, i.e. `admitLegs` with the page's one dialog (5.5.2). One live question per clash, asked in the
ticked order; "Increase quantity" adds the lots to the held leg (and `base_lots`, `legDoor.js:30-31`); "Keep separate" adds
the ticked leg as its own row; "Cancel" ends the whole add: the held legs stay as they were and none of the ticked legs is
added (the ticks stay in the chain store, so the trader can go back and untick); Increase past `max_lots` shows the lots
sentence through the page's existing `editError` path (same as a moved-leg Increase, `:822-823`), nothing changed. A ticked
OPPOSITE-side contract is not a clash (`sameContract` needs the same action) and is added silently, as ADR-329 (1) says.
Result legs = `result.legs` followed by `result.kept` through `setLegs` (it nulls `savedId`: the page is unsaved now,
`openStrategy` stays, so Save updates the open strategy, REQ-134 AC-2). The `?draft=` stays in the URL, as today.
**This is the only place Add Selected asks, and ADR-328 (2) "Replace the N legs?" never appears for it.**

**The sentences (exact).** Leave question, ADR-329 verbatim: `Leave the builder? The N unsaved legs will be lost.`
(`leaveQuestion(n)` in `lib/readyMade.js`-style pure text in `useLeaveBuilder.js`; N = 1 reads "The 1 unsaved leg will be
lost." following `replacePrompt`'s singular, `readyMade.js:44-46`; a plan choice, flagged on the screen-check list);
buttons `Stay` and `Leave`; Escape, x and overlay = Stay. Test ids: `leave-dialog`, `leave-question`, `leave-stay`,
`leave-leave`. Clash questions: the existing `DUP_QUESTION` and three buttons (`dup-increase`, `dup-separate`,
`dup-cancel`). Drafts Mode changed-book note: the sentence above. Replacing draft link: `replacePrompt(n)` (ADR-328 (2)).

**Answer states (each is a test row below).** No legs: no question. Legs saved, no edit: no question. Unsaved + Stay:
navigation cancelled, legs, URL and Drafts Mode untouched. Unsaved + Leave: left, hold empty, the next builder is fresh.
Chain trip + Add Selected with no clash: held legs + ticked legs, no question. Same-action clash: Increase / Keep separate /
Cancel as above. Opposite-side tick: added silently. Chain trip + return without Add Selected: the legs are there. Chain
opened directly, nothing behind it: fresh builder (today). Chain trip then leaving the chain elsewhere: the question from
the chain page. Paper strategy in Drafts Mode: unsaved = pending changes; chain trip holds it; return re-reads the book.
Replacing draft link on a mounted page: the ADR-328 (2) question, unchanged by ADR-329.

**Tests-first commit (red).** `frontend/tests/leg-door-phase5.test.js` (new):

- **1** - Test: step onto an opposite-held contract asks; Assertion: `dup-dialog` open; `dup-question` = "<name> is
  already in this strategy as a Buy."; buttons `dup-separate` "Keep both" and `dup-cancel` only; no `dup-increase`; legs
  unchanged until answered; State: stated
- **2** - Test: Keep both; Assertion: two rows, B and S of the contract; in Drafts Mode `paperOrdersFor` still gives the
  two exits (REQ-109 AC-9); State: stated
- **3** - Test: Cancel / Escape / x / overlay; Assertion: `ids(w)` == before; no further `leg-edit`; Drafts pending
  count unchanged; State: stated
- **4** - Test: Shift, Width (BUY wing onto SELL body), Hedge onto opposite-held; Assertion: each asks as row 1; State:
  stated
- **5** - Test: picker add of the opposite side stays silent; Assertion: no `dup-dialog`; second row added
  (`leg-duplicate-d60.test.js:161` stays as is); State: stated
- **6** - Test: edit form moving a leg onto an opposite-held contract; Assertion: silent (a deliberate edit); State:
  stated
- **7** - Test: one live question across picker and page; Assertion: a second `door.ask` settles the first as
  `'cancel'`; at most one `dup-dialog` with both mounted; State: ambiguous
- **8** - Test: picker stale legs; Assertion: open the picker question, replace the page legs (new `?draft=`), answer
  Increase: the page shows the NEW legs, unchanged; State: stale
- **9** - Test: same-action entry points still ask Increase / Keep separate / Cancel; Assertion: picker Done, future
  Buy/Sell (no test today), form Save, edit form, step, Shift, Width, Hedge; Increase past max -> the lots sentence,
  nothing changed; State: stated / refused
- **10** - Test: Escape on the PAGE dialog (none today); Assertion: as row 3 for a same-action step; State: stated
- **11** - Test: not door users (pins); Assertion: ready-made on held legs shows its replace prompt and never
  `dup-dialog`; a `?draft=` with two same-action rows opens as two rows; Compare legs replace via `keepHeldFills`;
  State: stated
- **12** - Test: source scan; Assertion: `LegPicker.vue` and `StrategyBuilderPage.vue` no longer contain `title="Already
  in this strategy"`; State: stated
- **13** - Test: a moved leg with no `instrument_id`; Assertion: never asks; State: absent

`frontend/tests/builder-draft-replace.test.js` (new, ADR-328 (2)): builder mounted with 3 legs, push a new `?draft=`:
`draft-replace-dialog` shows "Replace the 3 legs in the builder?"; Cancel keeps the 3 legs and the URL's draft is the
old one; Yes shows the new legs; same draft as shown -> no question; a builder with no legs -> no question; a fresh
mount with `?draft=` -> no question; an unreadable `?draft=` while legs are shown -> today's refusal path unchanged.

**ADR-329 tests (same red commit; new files; real page, real router, real Pinia, the existing mocks of
`draft-link.test.js`'s `openBuilder`; no mock of the hold store).**

`frontend/tests/builder-hold-adr329.test.js` (the store and the pure rule, no page):
- **H1** `unsavedCount`: no legs -> 0; 3 legs, `savedId` null -> 3; 3 legs, `savedId` 7 -> 0; saved-but-edited
  (`openStrategy` set, `savedId` null) -> 3; Drafts Mode with equal legs -> 0, with 2 pending orders -> 2.
- **H2** `hold` then `take` returns an equal copy and empties the store; a second `take` -> null; `clear` empties.
- **H3** `leaveQuestion(3)` === "Leave the builder? The 3 unsaved legs will be lost."; `leaveQuestion(1)` has "1 unsaved
  leg will".
- **H4** the store holds no number field and sends nothing: it imports no `api`; source scan (ADR-008).

`frontend/tests/leave-builder-adr329.test.js` (the leave question):
- **L1** no legs -> `router.push('/home/overview')` resolves with no `leave-dialog` (no legs).
- **L2** saved legs (open `?strategy=7`, unedited) -> push to Home: no dialog (saved).
- **L3** unsaved (3 legs from a `?draft=`) -> push to Home: `leave-dialog` open, `leave-question` text ===
  "Leave the builder? The 3 unsaved legs will be lost.", buttons exactly `leave-stay` "Stay" and `leave-leave` "Leave";
  the route is still the builder (navigation pending).
- **L4** Stay (and Escape, x, overlay): route unchanged, `leg-row` count 3, URL query equal to before, no request sent.
- **L5** Leave: route is Home, `builderHold.held` null; mounting the builder again shows 0 legs (fresh).
- **L6** saved-but-edited (open `?strategy=7`, remove a leg) -> Home: the question with N = the legs now shown.
- **L7** never asks: Save (then push Home: no dialog); Add to Paper confirm done (`pendingOrders` empty); a push to the
  chain; a `router.replace` of the page's own query.
- **L8** Drafts Mode, `?strategy=<paper id>` unedited -> Home: no dialog; after one edit (a step) -> Home: the question with N
  = the "N pending changes" number shown on the bar.
- **L9** a `?draft=` replaced while mounted (ADR-328 (2)) shows `draft-replace-dialog`, never `leave-dialog`.
- **L10** the tab close is not asked: source scan, `src` has no `beforeunload` (pins the decision of 2.2).
- **L11** the chain page: with `held` set, push chain -> Home: the same dialog (Stay keeps the chain and the hold; Leave
  empties the hold); with `held` empty: no dialog (today).

`frontend/tests/chain-trip-adr329.test.js` (chain trip and Add Selected; one router, both pages mounted in turn):
- **C1** (Core) 3 unsaved legs -> push chain: no dialog; `held.legs` has the 3; chain: tick 2 (BUY 24000 CE, SELL 24200
  CE), Add Selected -> builder: 5 `leg-row`, the first 3 are the held ones in order, the last 2 the ticked ones; no
  `dup-dialog`, no `draft-replace-dialog`, no `leave-dialog`; the builder holds nothing (`held` null).
- **C2** same-action clash: a ticked BUY of a contract held as BUY: `dup-dialog` with `dup-question` "<name> is already in
  this strategy."; Increase -> the held row's lots are the sum and `base_lots` rises too, 4 rows total (3 + 2 - 1); Keep
  separate -> 5 rows, two rows of that contract; Cancel (Escape, x, overlay too) -> exactly the 3 held legs, none of the
  ticked ones, and the chain store still has its ticks.
- **C3** two clashes: two questions, one at a time, in ticked order; Cancel on the second leaves the first's Increase
  unapplied (all-or-nothing).
- **C4** Increase past `max_lots`: the lots sentence (`lotsRangeText`) shows, legs unchanged.
- **C5** opposite-side tick: a ticked SELL of a contract held as BUY: no dialog of any kind; two rows of that contract (B and
  S); in Drafts Mode `paperOrdersFor` still gives both orders (REQ-109 AC-9).
- **C6** chain trip, return by nav (push `/strategies/strategy-builder`, no query) and by `router.back()`: the same 3 legs,
  `openStrategy` and `savedId` as before (a saved-but-edited strategy comes back edited and Save still PUTs with its
  revision).
- **C7** chain opened directly (no builder behind it), tick 2, Add Selected: exactly 2 rows, no question (today's
  behaviour; `chain-selection.test.js:71-93` stays green unmodified).
- **C8** chain trip with no legs shown: `held` stays null; Add Selected opens the ticked legs only.
- **C9** reload: `setActivePinia(createPinia())` + a mount on the same `?draft=` -> only the ticked legs (the hold is gone,
  no question).
- **C10** held legs and `?strategy=` / `?adjust=` query: the held record is dropped, today's open path runs.
- **C11** Drafts Mode: paper strategy, one pending edit, push chain, tick 1, Add Selected: net legs + the edit + the
  ticked leg (pending changes = edit + add), no question; when the re-read net differs (`netKey` changed) the held edits
  are dropped and "The strategy changed while you were away. Your unsaved edits were not restored." shows.
- **C12** the held legs keep `planned_entry` and `captured_at` unchanged; no request is sent by the trip itself
  (request log equal before and after the push to the chain, apart from the chain's own).

`frontend/tests/leg-emitters-guard.test.js` (new). Changed, with the reason: `leg-step-duplicate-d60.test.js:91`
("a step onto a contract held with the OTHER action does not ask") now expects the row-1 question; reason "ADR-328 (1) amends ADR-319 (4) for steps and moves". Also changed: `draft-link.test.js:265` ("a new ?draft= link
while mounted seeds that draft's legs"): the page shows strategy 54's legs, so ADR-328 (2) now asks first; the test
answers `draft-replace-yes` and then expects 1 row; reason "ADR-328 (2): a replacing draft link asks" (the earlier
plan listed `draft-link.test.js` as unchanged: wrong for this one `it`; the other `it`s of the file stay). Expected
unchanged (Lane B greps the 40 test files that mount `StrategyBuilderPage` for a push to another route with legs on screen
and, if one exists, adds the `leave-leave` click with the reason named in the commit message; none was found by `grep` of
the route pushes in `chain-selection`, `draft-link`, `clear-legs`): `chain-selection.test.js` (hold empty, the chain guard
asks nothing) and e2e `chain-selection.spec.ts:72-93` (a fresh builder after Add Selected).

**Code commits, in order.** 5.5.0 spec text first, same push: ADR-007 Q34 and ADR-319 (1) get one sentence each saying
the builder's own legs are kept across the chain trip and Add Selected adds to them (SPEC CHANGE notes, from ADR-329; Lane
B edits only these two sentences, with `python tools/spec_similar.py` run first and the digest regenerated; coordinator
approves the wording). 5.5.1 `lib/legDoor.js` (+ unit rows in `leg-duplicate-d60.test.js`'s door describe, new
`it`s only). 5.5.2 `composables/useLegDoor.js` + `DuplicateLegDialog.vue` (+ composable unit tests). 5.5.3
`LegPicker.vue` (inject or own door; stale guard; `doneError` kept). 5.5.2a (before the hand-over, so Lane B is never idle) `stores/builderHold.js`, `composables/useLeaveBuilder.js`,
`components/strategy/LeaveBuilderDialog.vue` (+ `builder-hold-adr329.test.js` green). 5.5.3a `OptionChainPage.vue`: the
leave guard only (rows L11); `openBuilder` / `addSelected` (`:123-126`) untouched. 5.5.4 `StrategyBuilderPage.vue` - ONLY
after the hand-over of 3.2 (merge `origin/refactor/modular-doors` first): door + one dialog + `provide`; ADR-329: `take()`
in `setup`, the leave guard (snapshot to the chain, question elsewhere), the chain-add through the door; `:748-791` and
`:1004-1012` removed; the draft-watch question. 5.5.5 guard green; `RESULTS-lane-b.md` (door, callers before -> after,
tests, the new wording, the O-1 note).

**Generated files:** none. **Stays unmodified:** `paperOrdersFor` and `keptDuplicateIds` (`paperDrafts.js`), the server
duplicate refusal (`routes/paper.py` `_refuse_duplicate_legs`), `LegList.vue` (`duplicateLegText` copy stays; deferred),
`ReadyMadePanel.vue`, `stores/chainSelection.js`, `router/*`, `App.vue`, and the `openBuilder` / `addSelected` code of
`OptionChainPage.vue` (`:123-126`; only its leave guard is added). Tests unchanged: `leg-duplicate-d60.test.js` (existing), the rest of
`leg-step-duplicate-d60.test.js` (`:72-:338`), `builder-paper-duplicate-refusal-d60.test.js`,
`paper-drafts-diff.test.js`,
`ready-made.test.js`, `chain-selection.test.js`, `draft-link.test.js` (except `:265`), `clear-legs.test.js`.

**Risks and guards:** Increase must raise `base_lots` too (`leg-duplicate-d60.test.js:265,271`,
`leg-step-duplicate-d60.test.js:254`); a closer lost in the merge (setLegs, net-zero, newer edit, unmount, route change:
`:173-:338` green); Drafts Mode diff merged by accident (do not touch `paperOrdersFor`; row 2); the draft-watch question
breaking F-4 (`draft-link.test.js:229-` green); `included:false` held legs still ask (leave; deferred).

**ADR-329 risks:** the hold must be taken exactly once (a second mount or a double `take` must not duplicate legs); a stale
hold must never open a different strategy (`?strategy=` / `?adjust=` drop it); Drafts Mode restore against a changed book
(`netKey`); the guard must not fire for the page's own `router.replace` / same-route query changes; `onBeforeRouteLeave` only
runs for a route component, which both pages are; the Escape / overlay of the leave dialog must be Stay, never Leave; the
ADR-328 (2) watch and the ADR-329 mount-time add must never both ask for one arrival; held legs and `planned_entry`
times stay as captured. **Review:** Sonnet, adversarial: one live question, every closer, the opposite rule only on moves, Cancel identity in
Drafts Mode, the draft-watch Cancel URL.

**Done when:** (ADR-329) the three new test files red then green, `draft-link.test.js:265` changed with its reason; rows red then green; whole vitest green; `ci_local` TOTAL PASS; CI green on `refactor/leg-door`;
`RESULTS-lane-b.md` written. Lane B then stops; Lane A merges it before Phase 8.

**Size:** about 9 files, 500-650 lines with tests; ADR-329 adds 3 source files, 2 edited pages and 3 test files, about
350 lines (the Drafts Mode restore is the part that may park).

### 5.6 Phase 6: B2 close list (real path), F7, F8; B7 not built - Lane A

**Core:** the Kite exit basket is byte-identical after `exit_legs` uses `open_legs_to_close`. **Proof:**
`tests_app/test_exit_legs_oracle.py` (no DB): today's `exit_legs` body copied as an oracle; held maps with the string
order trap ("NFO-OPT:10" vs "NFO-OPT:9"), zero nets, a single short, 4-leg condors; `new == oracle` for all four
`LegToPrice` fields, element by element.

**Spec basis:** ADR-281 (paper only; the real path is frozen except maintenance); ADR-016 to ADR-019 (Zerodha is the
authority; no silent substitution); REQ-109 AC-8 (stops panel reads its triggers); B7/F7/F8: none: the spec says
nothing about module shape (searched: raise_alert, triggers reader, rename composable).

**Verified facts.** `exit_legs` (`execute_plan.py:223-226`), called only from `routes/execute.py:361-363` (`_wanted`).
`Action` is an `Enum` with `BUY = "BUY"`, `SELL = "SELL"` (`ofo/engine/legs.py:17-19`). F7: `PaperStops.vue:28`
(path), `:63` (shape check), `:80` (read); `TrackingPanel.vue:174-180` (`readExits`, filter conditional exits not
cancelled; keeps the last good list on error). The two are never on one screen at once (`PaperStops` only in the
non-compact Positions list, `PaperStrategies.vue:60,:154`; the builder shows the compact list and `TrackingPanel`).
F8: `MyStrategiesPage.vue:116-117` reads the revision before `renameStrategy`, which already does the same read for a
non-integer revision (`saveDraft.js:67-77`). B7: `add_alert` (one caller `paper_monitor.py:241`), `open_suggestion`
(one caller `background.py:809`), `notifier.notify` (one caller `worker_watch.py:153`), different stores and
transactions.

**Design.**
- B2: `exit_legs(held, instrument_of)` returns `[LegToPrice(instrument_of(c.key), Action(c.side), c.quantity, None)
  for c in open_legs_to_close(dict(sorted(held.items())))]`; `sorted(held.items())` stays at the call site.
  `execute_plan` gains one import of the stdlib-only `ofo.tracking.closing`, nothing else.
- F7: `frontend/src/lib/paperTriggers.js` (no Vue import): `triggersPath(id)`, `triggerListOf(data)` (array or null),
  `armedIndexExits(list)` (the TrackingPanel filter). Each component keeps its own failure policy and timing.
- F8: `MyStrategiesPage.vue` passes `null` as the revision; the pre-read lines go. No `useRename` composable.
- B7: nothing built; record the evidence in RESULTS; guard G4 (Phase 8) pins one caller per writer.

**Tests-first commit.** `tests_app/test_exit_legs_oracle.py` (green on both sides; it is the guard, written first);
a basket golden: `_wanted` -> `price_legs` -> `checked_basket` on a fixed catalogue for one condor exit, whole basket
repr before == after (extend the closing case of `tests_app/test_checked_basket.py:185` if it fits; else a new file).
`frontend/tests/paper-triggers-lib.test.js` (red: module missing): `triggersPath(48) ===
'/paper/strategies/48/triggers'`;
`triggerListOf({triggers: []})` `[]`; `triggerListOf({})`, `(null)`, `({triggers: 'x'})` `null`; `armedIndexExits` keeps
armed and fired conditional exits, drops cancelled ones and leg stops. F8: no red test (pinned by
`rename-paper-d65.test.js:36,42,47,72`, `my-strategies.test.js:141`, `save-draft.test.js:339`).

**Code commits.** (1) `execute_plan.py` (B2; separate commit; Tier A before it lands). (2) `paperTriggers.js`,
`PaperStops.vue` (script only), `TrackingPanel.vue` (script only). (3) `MyStrategiesPage.vue`.

**Stays unmodified:** `partial.py`, `send_guard.py`, `sequence.py`, `resolution.py`, the Kite client; tests
`test_execute_route.py:565`, `test_exit_adopted_313b.py`, `tests/execution/test_close_slices.py`,
`test_close_refusals.py`, `test_partial.py`, `paper-stops.test.js`, `tracking-armed-exit-d24.test.js`,
`paper-strategies.test.js`, `rename-paper-d65.test.js`, `my-strategies.test.js`, `d53-name-limit.test.js`,
`save-draft.test.js`.

**Risks:** a real basket in a new order (oracle; `sorted` kept at the call site; reviewer diffs the imports); F7
changing a screen's failure line (each component keeps its policy; the pinned tests).

**Review:** Tier A, fresh Opus, for B2 (imports, `sorted(held.items())`, the `Action` mapping, the oracle and basket
golden). Sonnet for F7 and F8.

**Done when:** oracle and golden green; vitest green; Tier A PASS; gates; RESULTS (B7 park with evidence).
**Size:** about 8 files, 250 lines.

### 5.7 Phase 7: helpers R1-R12 - Lane A

**Core:** the five identical ownership SQL copies become one `strategy_store.owns` and every caller keeps its own error.
**Proof:** a DB test for owned, other user and soft-deleted through `owns`, plus one NotFound test each for
`strategy_pause_store` and `strategy_level_watch_store` (none exist today), red then green.

**Spec basis:** ADR-008 (R5 money in the engine; done in Phase 4); REQ-109 AC-7 ("A job runs at 15:45 IST each trading
day", R1); REQ-081 AC-1 (Indian grouping on screens, R3); otherwise none: the spec says nothing about helper layout
(searched: ownership SQL, owns, groupIndian).

- **R1 cut-offs** - Verdict: KEEP three named cut-offs, document only: 15:30 valuation (`timeutil.py:30` `EXPIRY_CLOSE`,
  `outcome/snapshot.py:143-145`), 15:39 reconciliation (`timeutil.py:32`, `reconciliation/settlement.py:58-63`), 15:45
  paper settlement (setting `facts.paper_settle_from`, `paper_settlement.py:117-121`, REQ-109 AC-7; also
  `outcome/service.py:442-444`); Where (verified): one comment block in `ofo/timeutil.py` naming the three questions; no
  code change
- **R2 ownership** - Verdict: DO: `strategy_store.owns(conn, user_ref, strategy_id) -> bool`; 5 copies
  (`strategy_pause_store.py:26`, `tracked_book.py:33`, `strategy_level_watch_store.py:26`,
  `execution_plan_store.py:152`, `strategy_alert_style_store.py:32`); Where (verified): `_OWNED_MANY`
  (`execution_plan_store.py:177`) and the playbook variant (`playbook_store.py:312`, no `deleted_at`) stay
- **R3 browser** - Verdict: DO: export `groupedIndian` (`displayFormat.js:204`), import in `tracking.js`, delete
  `groupIndian` (`tracking.js:119`); Where (verified): `groupMoney` stays
- **R3 server** - Verdict: PARK (visible wording; template pins); Where (verified): `display.py`, `errors/slots.py`,
  `gate_slots.py`
- **R4** - Verdict: SKIP: fail closed vs default differ (`settings_store.py:82-103`, `settings_cache.py:113-129`)
- **R5** - Verdict: DONE in Phase 4 (5.4.5 step 8)
- **R6, R8, R9** - Verdict: PARK: real-order / broker path, failure behaviour differs
- **R7** - Verdict: SKIP: six copies with different errors; NaN gap -> deferred issue
- **R10** - Verdict: DONE before this plan (D-57; `one-date-formatter-d57.test.js`); Where (verified): `localDay` defect
  -> deferred issue
- **R11** - Verdict: SKIP: only two identical copies, tests patch both names
- **R12** - Verdict: SKIP: different inputs; a raising `to_ist` changes behaviour

**Tests-first commit.** `tests_app/test_strategy_owns.py` (DB): `owns` true for owned, false for another user, false
for soft-deleted, false for a missing id; `strategy_pause_store` raises `PauseNotFound` and `strategy_level_watch_store`
raises `WatchNotFound` for not owned and soft-deleted. `frontend/tests/grouped-indian.test.js`:
`groupedIndian('1234567') === '12,34,567'`, `'999'`, `'1000' -> '1,000'`, 8 digits, and `signedRupees('1240.50') ===
'+1,240.50'`. A text guard (in `tests/test_ownership_sql_one_home.py`, repo_scan): the SQL
`FROM public.strategies WHERE id = :s AND user_ref = :u AND deleted_at IS NULL` appears only in `strategy_store.py`.

**Code commits.** (1) `strategy_store.owns` + the 5 stores. (2) R3 browser. (3) R1 comment.
**Stays unmodified:** `test_strategy_alert_style.py:136-140`, `test_execution_plan_store.py`, `test_tracked_book.py`,
`test_level_watch_route.py`, `test_level_watch_worker.py`, `tracking.test.js`.
**Risks:** `owns` lets a soft-deleted strategy through (tests-first rows); R3 on odd text (pure digits only reach it).
**Review:** Sonnet. **Done when:** gates; RESULTS lists every verdict with its reason. **Size:** about 10 files, 200
lines.

### 5.8 Phase 8: guards - Lane A, after merging Lane B

**Core:** a new price read, paper order builder, not-live string, exit POST, paper book reader, duplicate-leg dialog or
alert writer outside its door fails a repo test with a message that names the file, line and door. **Proof:** each
guard's mutation test: an in-memory bad sample gives exactly one problem; the same sample in the allowed home gives
none.

**Spec basis:** none: the spec says nothing about repo guard tests (searched: guard, repo_scan, allow-list); kit C3
(structural guarantee first, detector second).

Common rules: AST or text scans with a pure `problems(source_or_files)`; exemptions keyed by (file, enclosing function,
called name), never by line; each with a category (`own_process`, `display`, `real_path`, `awaiting_phase_N`) and a
reason; a stale exemption fails ("shrink only"); fail closed on aliased imports and unparsable files; marked
`repo_scan`; Python guards in `tests/`, vitest guards in `frontend/tests/`.

- **G1** - File: `tests/test_price_reads_one_door.py`; Rule: a call to `underlying_quote`, `futures_quote`,
  `option_chain_snapshot`, `latest_depth`, `latest_day_stats`, `depth_after_close`, `held_quote_time`, `read_snapshot`,
  `resolve_spot` in `backend/ofo_app` only in `market_read.py`; Exemptions (from the AST scan of the phase-678 report;
  re-run on the merged head): own process: `background.py` `read_prices`, `_window_tokens_of`, `state_from_market`;
  `adjustment_readers.py` `read_market` (a different function of that name: key by file). Display: `routes/outcome.py`,
  `live_push.py`, `chain_push.py`, `index_push.py`, `routes/leg_picker.py`, `routes/leg_edit.py`,
  `routes/ready_made.py`, `routes/planned_entry.py`, `outcome_oi.py`, `adjustment_readers.py` `read`, `_window_spot`.
  Decision read not yet moved: `adjustment_readers.py` `entry_facts_now` (deferred). Exit read: `routes/tracking.py`
  `_snapshot`, `routes/paper.py` `_snapshot` / `_hold_until_ready` (book display; the exit read goes through
  `paper_exit.live_exit_prices` after Phase 4), `paper_monitor.py` `provider_prices`, `_index_now` (in-transaction, no
  wait, by design). Real path: `routes/execute.py` `leg_quote`, `execute_replay.py` `frame_quote`
- **G2** - File: `tests/test_paper_orders_one_door.py`; Rule: `NewOrder(...)` in `backend/ofo_app` only in
  `paper_exit.py` `exit_strategy`, `paper_store.py` / `paper_book.py`, `tracked_book.py` (real book view),
  `paper_trigger_store.py` (rows read back), `routes/paper.py` `place_paper_orders` (the browser's basket); no
  `"BUY"`/`"SELL"` `IfExp` or `_opposite` call in the four paper modules outside the door; Exemptions (from the AST scan
  of the phase-678 report; re-run on the merged head): none `awaiting_phase_4` after Phase 4; non-paper builders
  (`ofo/execution/*`, `reconciliation/resolution.py`, `adjustment/approaches.py`, charge estimates) are out of scope by
  key (say so in the docstring)
- **G3** - File: `frontend/tests/one-door-screens.test.js`; Rule: (1) the not-live strings only in `lib/priceState.js`;
  (2) `.post(` to `/paper/strategies/${...}/orders` only in `lib/tracking.js` `addToPaper`; (3) Phase 3 rule: `api.get`
  of `/paper/strategies/${id}` only in `lib/usePaperBookRead.js`; (4) Phase 5 rule: `dup-increase` / `dup-separate` only
  in `DuplicateLegDialog.vue`, `sameContract` only in `lib/legDoor.js`; Exemptions (from the AST scan of the phase-678
  report; re-run on the merged head): (1) `PaperStrategies.vue` `NO_TOTAL` (same rule, other words; RESULTS Phase 2).
  (3) `lib/paperDrafts.js` `readPaperBook` (Drafts Mode entry read), `LiveStrategyCard.vue` `rereadBook` (D-06 card
  figures); list reads `/paper/strategies` in `paperPnl.js`, `PaperStrategies.vue`, `PositionsPage.vue` are another
  reply. (4) none
- **G4** - File: `tests/test_alert_writers_one_caller.py`; Rule: `add_alert` only in `paper_monitor.py` (or
  `paper_exit.py` if Phase 4 moved it); `open_suggestion` / `playbook_store.record_held` only in `background.py`;
  `notifier.notify` only in `worker_watch.py`; Exemptions (from the AST scan of the phase-678 report; re-run on the
  merged head): none; tests excluded
- **G5** - File: existing; Rule: `frontend/tests/one-date-formatter-d57.test.js`, `tests/test_no_12_hour_clock_d57.py`;
  Exemptions (from the AST scan of the phase-678 report; re-run on the merged head): no new guard
- **Lane B** - File: `frontend/tests/leg-emitters-guard.test.js`; Rule: built in Phase 5; Phase 8 only checks it is in
  the suite; Exemptions (from the AST scan of the phase-678 report; re-run on the merged head): its allow-list

Each guard's failure message names the door, for example `price read outside read_market: <file>:<line> in <function>
calls <name>(). Use ofo_app.market_read.read_market, or add (file, function) to EXEMPT with a category and reason.`
and `stale exemption: <file>::<function> no longer calls <name>; delete the entry`.

**Tests-first commit:** the guards with their exemption lists filled from a fresh scan of the merged head (green on day
one: that proves the list is complete), then a commit of the mutation tests per guard (in-memory sample -> one problem;
allowed home -> none; alias import -> one problem; deleted exempt site -> "stale exemption"), plus one copytree test
for G1 (append a provider call to a temp copy of `routes/paper.py`; the scan names it).
**Code commits:** none (guards only). **Review:** Sonnet: false negatives (a read through a helper that wraps the
provider), stale-entry logic, keys by function. **Done when:** green; each mutation red as intended; `ci_local`; CI.
**Size:** 4 new test files plus the Lane B one, about 400 lines.

## 6. Deferred issues to file, and parked items

File each as a GitHub issue labelled `deferred` (kit C4) when the phase that found it lands; evidence as given.

- **1** - Title: D-41 third reader: the builder leg list shows the outcome socket price, not the paper book's; Evidence:
  `LegList` via `quoteAtById` (outcome reply `leg_quotes`), ADR-321 (9); phase-3 report OQ-2; Found in: Phase 3
- **2** - Title: Tracking panel rows drop a closed lifecycle's booked part; Evidence: `routes/tracking.py:307-309`;
  Found in: Phase 3
- **3** - Title: L1: tracking exit `placed_at` is the quote time, the manual exit is `now()`; Evidence:
  `routes/tracking.py:550` vs `routes/paper.py:1326`; `paper_monitor.py:23-24` "never back-dated"; Found in: Phase 4
- **4** - Title: L2: a tracking exit read that raises gives 500, the orders route a named 409; Evidence:
  `routes/tracking.py:545` vs `routes/paper.py:1238-1243`; Found in: Phase 4
- **5** - Title: L3: "not connected" means `ctx is None` on one route, `provider.status().connected` on the other;
  Evidence: `routes/paper.py:1221-1245`, `routes/tracking.py:226-227,537-538`; Found in: Phase 4
- **6** - Title: L5 (route half): a tracking exit closes only the pre-read qty when a leg grew between read and lock;
  Evidence: phase-4 report A5; `routes/tracking.py:529`; Found in: Phase 4
- **7** - Title: L6 remainder: a "Review and add" dialog of other edits can still post exits while the trade changed
  elsewhere; Evidence: `StrategyBuilderPage.vue:471-503`; `paperOrdersFor` uses the net loaded at `enterDrafts`
  (`:412-418`); Found in: Phase 4
- **8** - Title: L7: two tabs can each store a partial exit of the same lot (no idempotency key); Evidence: phase-4
  report A6; `routes/paper.py:1342-1343` refuses only a second FULL exit; Found in: Phase 4
- **9** - Title: L8: a conditional exit never fires while any open contract is not live, and says nothing; Evidence:
  `paper_monitor.py:252-253`; Found in: Phase 4
- **10** - Title: Keep-this-level route has no price check; Evidence: RESULTS Phase 1 (review finding 4); Found in:
  Phase 1 (already listed)
- **11** - Title: S-20 first-second race after `reload`; Evidence: RESULTS Phase 1 (review finding 3); Found in: Phase 1
  (already listed)
- **12** - Title: Display and advisory price readers not on `read_market`; Evidence: `routes/outcome.py:1263`,
  `live_push.py:170`, `chain_push.py:305`, `index_push.py:84`; Found in: Phase 1 (already listed)
- **13** - Title: `entry_facts_now` (first-fill entry facts) is a decision read outside `read_market`; Evidence:
  `adjustment_readers.py:777`; G1; Found in: Phase 8
- **14** - Title: A held leg with `included: false` still triggers the duplicate question; Evidence: `legDoor.js:23`
  ignores `included`; Found in: Phase 5
- **15** - Title: `LegList` copies the server's duplicate-leg sentence; Evidence: `LegList.vue:84-91` vs
  `ofo/errors/templates.py:302-306`; Found in: Phase 5
- **16** - Title: Playbook ownership check ignores `deleted_at`; Evidence: `playbook_store.py:312` `_OWNS_STRATEGY`,
  used at `:700-702`; Found in: Phase 7 (R2)
- **17** - Title: `execute_plan._money` accepts `Decimal("NaN")`; Evidence: `execute_plan.py:102-105` (real path;
  whether Kite JSON can yield it is unverified); Found in: Phase 7 (R6)
- **18** - Title: The instruments parser accepts NaN / Infinity strike and tick size; Evidence:
  `ofo/instruments/parser.py:52-59, 142-143`; Found in: Phase 7 (R7)
- **19** - Title: `localDay()` uses the browser's day, so "days left" is a day off outside IST near midnight; Evidence:
  `lib/displayFormat.js:137-139`; `useChainLive.js:153-155`; Found in: Phase 7 (R10)
- **20** - Title: The monitor's market calendar is not `may_act`'s; Evidence: `paper_monitor.py:181-182` (own holidays)
  vs `may_act.market_open`; Found in: Phase 2 (RESULTS "Left")

Parked (no code this round; evidence in the phase-678 report): R3 server rupee grouping (wording, template pins), R6
Kite money parsers, R8 Kite token wiring, R9 Kite HTTP paths. Not built: B7 `raise_alert` (replaced by G4). Skipped
with reason: R4, R7, R11, R12.

## 7. Open points

No open point waits on the owner.

**O-1. ANSWERED by ADR-329 (25 Nov late evening; was OQ-4).** The owner chose: the builder's unsaved legs are KEPT across
the chain trip and Add Selected ADDS the ticked contracts to them (a same-action clash asks the usual question; an
opposite-side tick is added silently); leaving the builder for any other page with unsaved legs asks "Leave the builder?
The N unsaved legs will be lost." (Stay / Leave); ADR-328 (2) "Replace the N legs?" stays only for a replacing draft
link. Built in Phase 5 (5.5, "ADR-329 design"). Nothing is built "meanwhile" any more. Four READINGS of ADR-329 are made
in the plan (not owner questions, each a one-line change if the owner reads it otherwise; each is on the screen-check list):
(a) the hold covers the legs the builder shows, saved or not; (b) leaving the chain for another page while the hold is set
asks the same question; (c) a paper strategy counts as unsaved when it has pending changes, with N = the pending changes
the bar shows; (d) closing or reloading the tab does not ask (`beforeunload` out: its box cannot show the sentence).
No genuine business question was found: each reading is the one the ADR's own words give, and the opposite reading would
lose or ask in a way the ADR does not name.

## 8. Screen-check list (owner, on `refactor/modular-doors`) and re-test list

After Step 0b the branch holds Part F and Phases 1-2; each phase below adds its rows. Market hours unless stated.

1. **D-01.** Positions > Paper > Stops > Conditional exit; "Above" a level the index is already beyond; Save:
   "Not saved: the live price is already at or beyond this level ...". Stop the feed; Save: "Not saved: the live price
   could not be read, so this level cannot be checked. Try again in a moment." Market closed: Save saves.
2. **S-20.** Arm only a leg stop; let it fire: the alert carries the NIFTY value, not "not available".
3. **D-41 (two readers)** (Phase 3). Open a paper strategy in the builder. For each open leg the Net Positions LTP and
   time equal the Paper P&L panel's LTP and time (watch 3 refreshes). The panel's leg P&L equals the table's P&L column;
   rows add up to the before-charges total. Exit one lot of a 2-lot leg, then compare again: the panel shows the leg's
   total (booked + open), same as the table. After 15:30: the panel rows show the last close, not "-".
4. **D-05** (Phase 4). In the builder, stop the API (or block `GET /paper/strategies/{id}`): within 5 s Exit all and
   every per-leg Exit grey out, "Prices are not live; try again when they update" shows, figures show "—"; an open Exit
   dialog closes; restore: everything comes back. Positions > Paper: same as before.
5. **Stale Exit, ADR-328 (4)** (Phase 4). Open the strategy in the builder in tab 1; in tab 2 (Positions) exit one leg
   or add a lot. In tab 1 within 5 s: Exit all and per-leg Exit disabled with "This trade changed elsewhere. Reload to
   see the current legs."; reload tab 1: enabled, the legs are the current ones.
6. **D-60 same side** (Phase 5). Step a leg onto a contract held with the same action: "Already in this strategy" with
   Increase quantity / Keep separate / Cancel; Cancel and Escape change nothing.
7. **D-60 opposite side, ADR-328 (1)** (Phase 5). `?strategy=170`: step SELL 25900 CE twice onto 26000 CE (BUY held):
   the question "... is already in this strategy as a Buy." with Keep both / Cancel; Cancel: legs as before; Keep both:
   two rows, and "N pending changes" shows two exits. Add a Sell of a held Buy from the strike picker: no question.
   Shift, Width and Hedge onto an opposite-held contract: the same question.
8. **Add Selected adds to the builder's legs, ADR-329 (1)** (Phase 5). Build 3 legs in the builder (a Short Strangle from
   ready-made, then edit one lot: unsaved). Open Market > Option Chain from the nav: NO question; the chain opens. Tick 2
   contracts, choose Buy / Sell for each, "Add Selected (2)": the builder shows 5 legs, the 3 you built first, then the 2
   ticked; no question. Repeat, but tick a contract you already hold with the same action (e.g. the held Sell 24200 CE,
   tick it and press Sell): "... is already in this strategy." with Increase quantity / Keep separate / Cancel; Increase:
   the lots add up on that row; Keep separate: two rows; Cancel: the 3 held legs only, nothing added. Repeat with the
   OPPOSITE side (tick the held Sell 24200 CE and press Buy): no question, two rows of that contract. Back in the builder
   after a chain trip WITHOUT Add Selected (nav link Strategy Builder, or the browser Back): the 3 legs are still there.
   Open the chain with NO builder behind it (fresh tab): tick 2, Add Selected: the builder opens with only those 2, as
   before. Paper strategy: open `?strategy=170`, step one leg (a pending change), go to the chain, tick 1, Add Selected:
   the book's legs, your step and the new leg all show as pending changes. Reload the builder tab (F5): the added legs are
   gone and nothing asks (stated behaviour).
8a. **Leave question, ADR-329 (2)** (Phase 5). Empty builder: click Home: no question. Open a saved strategy unchanged,
   click Home: no question. With 3 unsaved legs click Home: "Leave the builder? The 3 unsaved legs will be lost." with Stay
   and Leave; Stay (and Escape): you are still on the builder with the 3 legs; Leave: Home opens; the builder from the nav
   is empty. Edit a saved strategy (remove a leg), click Positions: the question. Save, then click Home: no question. With
   unsaved legs open the chain: no question; on the chain click Home: the same question (Stay returns you to the chain,
   Leave drops the legs). Paper strategy with no change: click Home: no question; after one step: the question.
   One leg: "The 1 unsaved leg will be lost." (wording choice). Close the tab with unsaved legs: no question (decision d).
8b. **Replace question, ADR-328 (2)** (Phase 5). With the builder showing legs, open a builder link with another
   `?draft=` in the same tab via the app (or Back to a builder entry with another draft): "Replace the N legs in the
   builder?"; Cancel keeps the legs and the address.

Re-test list (screens the clean-up touches): Positions > Paper (list, Exit, stops panel); builder Net Positions,
Orderbook tab, Paper P&L panel, Review and add, confirm dialog, after-hours rows; Live Strategies card figures; My
Strategies (rename, P&L cell); Home totals; paper alerts (leg stop, conditional exit); expiry-day settlement rows
(Positions > Paper after 15:45 on an expiry day); strike picker, futures button, edit form, step / Shift / Width /
Hedge, ready-made shapes, Compare "Open in builder", Undo of Clear all; Option Chain Add Selected; every place showing
"Paper P&L paused - prices not live" or the not-connected text; a real-order exit review screen (B2: the basket order
must be the same as before).

## 9. Confidence per phase

- **Step 0** - Confidence: 90%; Unverified: vitest and DB tests of the merged tree not run (no node_modules; no DB
  here); First command that verifies it: `git merge --no-ff origin/fix/ic-live-test-1123` then `cd frontend && npm ci &&
  npx vitest run`
- **3** - Confidence: 85%; Unverified: vitest not run; DB files not run; live capture of both replies; First command
  that verifies it: `npx vitest run tests/one-source-d41.test.js` after the tests-first commit (must be red)
- **4** - Confidence: 75%; Unverified: A3 deadlock not run; goldens not captured; `read_market` switch; First command
  that verifies it: on a fresh clone (4.1): `python -m pytest -c pytest-app.ini tests_app/test_exit_door.py -k deadlock`
- **5** - Confidence: 75% (was 80%: ADR-329 adds the hold, two guards and the Drafts Mode restore); Unverified: vitest not
  run; the draft-watch Cancel with `router.replace`; that no existing test pushes the mounted builder to another route
  with legs (grep of 3 files only: the 40 files that mount the page are not all read); `onBeforeRouteLeave` behaviour
  with the page's own `router.replace` and with both builder route names in the test router; the Drafts Mode restore
  (netKey equality, the re-read racing the held `setLegs`); the four READINGS of section 7; the singular wording; that
  Escape on the leave dialog maps to Stay in the shared Modal; First command that
  verifies it: `npx vitest run tests/leg-step-duplicate-d60.test.js tests/leg-duplicate-d60.test.js` on the merged head
- **6** - Confidence: 85%; Unverified: the basket golden fit in `test_checked_basket.py`; First command that verifies
  it: `python -m pytest tests_app/test_execute_route.py -k exit_legs -q`
- **7** - Confidence: 85%; Unverified: DB tests for `owns`; First command that verifies it: `python -m pytest -c
  pytest-app.ini tests_app/test_strategy_alert_style.py -q` on a fresh clone
- **8** - Confidence: 70%; Unverified: exemption lists on the merged head; reads through wrapper helpers; First command
  that verifies it: the G1 scan run on the merged head, count of sites
