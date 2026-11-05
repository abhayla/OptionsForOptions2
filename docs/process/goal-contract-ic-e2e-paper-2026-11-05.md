# Goal contract: iron condor end to end on paper + test data (2026-11-05)

**Status: APPROVED by the owner 2026-11-05 ~18:2x IST** (question tool: plan + delivery plan "Approve").
**Last updated: 2026-11-05 18:41 IST** - added §0.4 (live trading first: frozen live tree, Stage D dev move after hours
only), §0.5 (branch rules: feature/adjustments only, main untouched), disk check, decisions 16-17 (marker backfill,
live behaviour locked), final-report extras. This is the version to run.
**Executor:** `/goal` in a fresh session of this project. **Run tree:** `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`,
branch `feature/adjustments` (start commit b5ae7021, pushed). **Created:** 2026-11-05 18:28 IST.

**Mission:** one paper iron condor on test data goes through the whole trade loop IN THE RUNNING APP, and every rule and
adjustment that is ON in the approved iron condor playbook works in that loop: the test market moves frame by frame,
the background worker (no screen open) raises ONE in-app record per crossing, the user picks an approach, prepares it,
places it on paper, the paper legs change, the trade exits by each of its real exits, and the history shows the
whole-trade totals. Done = every stage below accepted, one `prepush.py --full` TOTAL PASS, one push of
`feature/adjustments`, handover written. Nothing to main.

Core: one scenario-marked paper iron condor replayed over moving test frames raises exactly one opportunity from the
background worker and is adjusted, exited and totalled on paper.
Proof (Stage A, step 1): on a THROWAWAY test database (`scripts/orchestrator/db_run_fresh.py`, never ofo_dev), path
scenario PATH-01 (built from ADJ-02): paper entry at frame 0 -> frame k crosses T-01 -> the worker writes exactly 1
opportunity (0 at frame k-1) -> A-01 prepared at frame k -> paper orders accepted at frame k's mid prices, linked to the
suggestion (legs changed) -> paper exit -> history totals = sum of the paper fills. Counted from the DB by a test.

## §0.1 Run tree and lock
1. Run every orchestrator step in the run tree above (a dedicated tree, not the main checkout). Builders work in their
   OWN agent worktrees: first command of every builder is `git checkout -b <branch> <wave start sha>` inside its own
   tree; it never `cd`s or `git -C`s into another tree (2026-11-05: two builders lost a start on this).
2. Claim: write `D:\Abhay\scratch\ic-e2e\.run-active.lock` with this session's id and start time. A session that finds
   a lock from another session stops and reports (shared state records its owner, run-discipline E2).
3. Release: delete the lock as the final action (DONE, PARKED or HALT).
4. Worktrees: remove each builder tree with `~/.claude/tools/wt-rm.ps1 -Path <tree> -MergedInto origin/feature/adjustments`
   after the final push; on HALT keep them (needed to resume).

## §0.2 Idempotency preflight (first action after §0.1)
1. Read the progress log (§0.3), `git log --oneline b5ae7021..HEAD` in the run tree, and this contract's stage list.
2. For each stage: if its acceptance tests already exist and pass (run only that stage's test files), mark it
   "verified, skipped" in the log and move on; if partly done, build only the missing part.
3. Never redo a merged stage. Every skip goes into the final report's "skipped (already covered)" list.
4. Machine check before Stage A and before Stage D: free space on C: and D: at least 10 GB each
   (`Get-PSDrive C,D`), and no Claude Code task output file over 1 GB in the temp tasks folder. Below that: free space
   first (2026-11-05: C: filled by a 36.5 GB task log and broke the API, tests and a decision file); never start a
   wave on a nearly full disk.

## §0.4 The owner's live trading comes first (non-negotiable)
1. The owner's live dev app (`uvicorn` on 127.0.0.1:8765, database `ofo_dev`) serves REAL strategies (strategy 82, a
   live NIFTY iron condor). Since 2026-11-05 ~18:4x IST it runs from a FROZEN tree, `D:\Abhay\Ventures\OptionsForOptions2-live`
   (branch `live/serve-1105` at b5ae7021, purpose recorded in its `.worktree-meta.json`), started with:
   `APP_ENV=development LIVE_MARKET=1 python D:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\dev_run.py
   D:\Abhay\Ventures\OptionsForOptions2-live python -m uvicorn --factory ofo_app.main:create_app --app-dir backend
   --loop ofo_app.event_loop:selector_loop --host 127.0.0.1 --port 8765` (logs `D:\Abhay\scratch\gcic1pi-live-tree.*`).
   So the run tree (settings tree) is free: merges there never reach the live app.
2. The run MUST NOT, at any time: edit, merge into or check out anything in the frozen tree; stop or restart the app
   on 8765; or run anything against `ofo_dev` - EXCEPT the Stage D dev move in point 3. All proofs use throwaway
   databases (`db_run_fresh.py`).
3. Stage D dev move, only between 15:35 and 09:00 IST: (a) read strategy 82's stop lines (`GET
   /api/strategies/82/adjustment-check` is empty after hours, so compute them as the 2026-11-05 evening check did: its
   plan body from `ofo_dev` through `settings_in_force.stops_of`); (b) `git -C D:\Abhay\Ventures\OptionsForOptions2-live
   merge --ff-only <pushed sha>`; (c) `python D:\Abhay\scratch\gctp\migrate_dev.py D:\Abhay\Ventures\OptionsForOptions2-live
   upgrade head` (0043, 0044); (d) stop the app by its PID (port 8765 owner and its `dev_run.py` parent) and start it
   with the command in point 1; (e) read the stop lines again: they must equal (a) (on 2026-11-05: T-06 50 / 50 / 40,
   T-16 on 4 / 4 / 3, no 2x-credit line) and strategy 82 must have `scenario_id IS NULL`. Any difference: HALT that
   step and report; never change the owner's position data.
4. If the run is still going at 09:00 on a trading day, Stage D's dev move waits for 15:35; everything else continues.

## §0.5 Branch rules (owner, 2026-10-30 and 2026-11-05: nothing goes to main)
1. ALL work of this contract lands on `feature/adjustments` (run tree `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`).
   Builder branches are cut from `feature/adjustments` commits and merged back into it by sha. The final push is
   `git push origin feature/adjustments` and nothing else.
2. `main` is never touched: no checkout of main in the run tree, no merge into main, no push to main, no PR (to main or
   anywhere), no `gh pr` command at all. The main checkout `D:\Abhay\Ventures\OptionsForOptions2` stays on `main` at
   its current tip and is used only to run the shared helper scripts it holds (`dev_run.py`, `db_run_fresh.py`); nothing
   is written there.
3. The frozen live tree (`live/serve-1105`, §0.4) is a local serving copy of `feature/adjustments` commits; it is never
   pushed and never becomes a PR.
4. Check at start and at the end (both lines go into the progress log): `git -C D:\Abhay\Ventures\OptionsForOptions2
   log -1 --format=%h main` and `git ls-remote origin refs/heads/main` must show the same tip as at the start
   (4119c8c5 on 2026-11-05). A different main tip caused by this run is a HALT.
5. Merging `feature/adjustments` into main needs the owner's NEW explicit approval in a later session; it is not part
   of this contract.

## Scope boundary
- **In scope:** backend/ofo_app (scenario_mode.py, background.py, routes/paper.py, routes/tracking.py,
  routes/adjustment_opportunities.py, adjustment_check.py, a new scenario frame route), backend/ofo/adjustment
  (playbook_eval.py, approaches.py, offered.py), backend/ofo (the engine, for T-14 only), backend/ofo_app/alembic/versions
  (new migrations 0043+), frontend/src (AppHeader.vue, lib/paperAlerts.js or a sibling lib, AlertsPage.vue,
  PreferencesTab.vue), tests/fixtures (new path scenarios), tests/adjust_scenarios_gen.py, tests/, tests_app/,
  tests/errors/template_pins.json, the message catalogue.
- **Out of scope (named by the owner or cut by the review):** live market day and real orders; WhatsApp / push / email
  (ADR-028 channels later); rules OFF by default (T-16 for new plans, T-04, T-05, T-06b, T-08, T-11b, T-11c, T-12, T-14t,
  T-14v, T-15, T-20, T-20b); new rules; alert latency (#636); approach speed (#644); worker restart / heartbeat (#627
  item 3); liquidity limits (#624); drawer details (#647); other strategy types; any PR; any push before Stage H; main.
- **Goal type:** feature build + test-coverage completion on an existing feature branch.

## Context to read first (in this order)
1. `D:\Abhay\scratch\ic-e2e\plan.md` - the approved plan: scan table (what is done / not), stages, delivery plan.
2. `D:\Abhay\scratch\ic-e2e\scope.md` - the owner's 4 scope answers.
3. `backend/ofo_app/scenario_mode.py` - test-data mode: ONE reader `_raw()` of `OFO_SCENARIO`; `ORDER_ROUTES`,
   `NON_ORDER_ROUTES`, `refuse_orders`; start-up refusal outside development/test; "twins" reuse real instrument tokens.
4. `backend/ofo_app/background.py` - `owner_lister` (line ~1548, lists EVERY tracked strategy of the owner), `_serve`
   (~1595, always builds `KiteProvider`), `margin_needed`, the check cycle (~333-381 already reads `scenario_mode.current()`).
5. `backend/ofo/adjustment/alert_gate.py` (`step`: the one record writer), `backend/ofo/adjustment/playbook_eval.py`
   (`_t14` always raises `T14_PENDING`), `backend/ofo/adjustment/approaches.py` (`APPROACH_IDS`, `_ordered`,
   `guard_debit`), `backend/ofo_app/routes/paper.py` (paper orders: typed prices, REQ-109 AC-1), `routes/tracking.py`
   (paper exit), `backend/ofo_app/paper_settlement.py`.
6. Test harnesses to reuse: `tests_app/test_background_worker.py` (T-01 worker -> gate -> record), `test_background_cycle.py`,
   `test_day_rules_worker.py`, `tests/adjustment/test_playbook_eval.py`, `tests_app/test_adjustment_approaches_route.py`,
   `frontend/tests/adjust-acted-handoff.test.js`; scenario library `tests/fixtures/adjust_scenarios/*.json` (59 files)
   and its generator `tests/adjust_scenarios_gen.py` (prices from its own path, so tests check the engine against it).
7. Migrations pattern: `alembic/versions/0040_*`, `0041_*`, `0042_*` and
   `knowledge/findings/cutoff-by-version-number-not-by-the-row-written.json`.
8. Spec: `spec/decisions/ADR-247.md`, `ADR-250.md`, `ADR-251.md`, `ADR-252.md` (with its addendum), `ADR-244.md`,
   `ADR-028.md`; `spec/requirements/REQ-109.md`, `REQ-112.md`, `REQ-115.md`, `REQ-158.md`..`REQ-163.md`, `REQ-165.md`, `REQ-170.md`.
9. Process: `docs/process/runbook.md`, `.claude/kit/builder-brief.md`, `.claude/rules/kit/run-discipline.md`,
   `.claude/rules/kit/evidence-and-proof.md`, `.claude/rules/kit/spec-first.md`.

## Pre-made design decisions (the run must NOT pause on these)
1. **Path scenarios.** A new fixture kind `tests/fixtures/adjust_paths/PATH-NN.json` = `{id, base: "ADJ-xx", frames:
   [{clock, spot, atm_iv, day_open?}...]}`. `tests/adjust_scenarios_gen.py --paths` expands each frame into a full
   ADJ-shaped snapshot priced by the generator's own pricing (`iv_at` + its own formula), written to
   `tests/fixtures/adjust_paths/PATH-NN/frame-KKK.json` and committed (deterministic: same input, same files).
   `OFO_SCENARIO=PATH-NN` is accepted by the same `_raw()` reader (id pattern widened to `PATH-[0-9]{2}`).
2. **One shared frame index** in the DB: table `public.scenario_frames (scenario_id TEXT PRIMARY KEY, frame INT NOT NULL
   CHECK (frame >= 0), moved_at TIMESTAMPTZ NOT NULL)`, migration 0043. API and worker read it on every check; a
   missing row = frame 0. Moved only by a dev/test route `POST /api/scenario/frame {frame}` (in `NON_ORDER_ROUTES`;
   404 when scenario mode is off; 422 outside 0..last). Tests move it directly.
3. **Scenario marker on strategies:** migration 0043 also adds `public.strategies.scenario_id TEXT NULL`. Set by the
   SERVER from `scenario_mode.current()` when a strategy is created in scenario mode; never accepted from the client.
4. **Isolation both ways:** in scenario mode the worker lister returns only strategies with `scenario_id` = the current
   scenario; in live mode only `scenario_id IS NULL`. The screen check refuses a scenario strategy in live mode and a
   live strategy in scenario mode (409 with a catalogue reason). One test each way.
5. **Guard split:** `ORDER_ROUTES` splits into `REAL_ORDER_ROUTES` (execute, execution / return; refused in scenario
   mode, unchanged) and `PAPER_ORDER_ROUTES` (paper orders, paper triggers, tracking exit): allowed in scenario mode
   ONLY when the strategy's `scenario_id` equals the current scenario, else 409 `scenario_no_orders`. Fail closed: a
   new mutating route in neither set still blocks start-up. Mutation tests: removing either check turns a test red.
6. **Paper prices:** REQ-109 AC-1 stays (the client sends typed prices). The prepared basket is pre-filled with the
   current frame's mid for each leg; the core test asserts the stored fill = frame k mid. No server-side price change.
7. **Worker in scenario mode:** `_serve` picks the provider by process mode only: scenario mode -> the scenario feed
   (the same seam the worker tests inject), live -> `KiteProvider`. The worker refuses scenario mode outside
   development/test at start-up (`scenario_mode.require_dev_or_test`), like the API.
8. **T-14 gamma** = the worst whole-position P&L change from repricing at spot x 1.01 and spot x 0.99 (same IV, same
   clock), through the one engine (ADR-008), as a % of the margin blocked; fires when >= the stage value (3 / 3 / 2).
   Margin absent or unreadable -> "not checked" with its reason, never passed. Money in Decimal.
9. **T-16 is out:** off by default since migration 0040 (ADR-247). Older plans that keep it on are not re-tested here.
10. **Bell:** the existing header bell (`AppHeader.vue` `alerts-bell`) counts paper alerts unread + OPEN adjustment
    records (no new "seen" state). The existing toast (`composables/useToast.js`) shows when a new open record id
    appears on the poll; clicking it opens the strategy with its suggestion drawer. No second bell.
11. **Outcomes (REQ-112):** acted on = paper orders placed with that suggestion id (exists: `link_orders`); completed =
    every leg of the prepared basket placed; partly completed = some; lapsed = the crossing clears (gate behaviour).
12. **#657 wording:** the settings screen text becomes "Stop at 2x the credit received: for plans accepted from
    5 Nov 2026; older plans keep their own stops" (catalogue entry + pin "pending owner read").
13. **#658 wording:** a new iron condor system playbook version via migration 0044 (pattern of 0042: row found by its
    REASON; guard function re-pinned if changed; ends with the allow-list `post` check): S-06 rule text says "the loss
    at your carry gap" instead of "2%". Seed JSON unchanged (as 0042).
14. **Second adjustment:** `adjustments_used` counts stored paper adjustment orders (`adjustment_readers.py:148-175`);
    after max adjustments (T-18) only exit / reduce approaches are offered (`offered.py`), with the T-19 cost warning.
15. **A-11 recentre** calls `guard_debit` like every roll. Order sequence (buy back before selling) asserted by a test.
16. **Existing scenario strategies get the marker.** `scripts/seed_scenario.py` already writes paper strategies named
    "Scenario ADJ-xx" into `ofo_dev` (e.g. 72, 73, 74); today the LIVE worker checks them at live prices. Migration
    0043 backfills `scenario_id` from that name (`'Scenario ' || id` pattern, exact match only, counted in the migration
    test) and `seed_scenario.py` sets `scenario_id` on every new seed. Effect: the live worker stops checking them;
    a test asserts a seeded strategy is listed in scenario mode and never in live mode. Real strategies (no such name)
    keep `scenario_id NULL`.
17. **Live behaviour must not change.** The only live-mode change allowed is the lister filter
    `scenario_id IS NULL`. A test runs the live lister on a fixture with one real and one scenario strategy and asserts
    the real one is listed exactly as before.

## Stages (waves: A alone; B1-B5 in parallel; C1-C3 in parallel after B3; then D)
### Stage A - CORE (Opus builder, Tier A review)
- **Do:** design decisions 1-7: path scenario PATH-01 from ADJ-02 with 10 frames, frame k = 6 crossing T-01; migration
  0043; frame route; marker; isolation; guard split; worker provider by mode; the core proof test
  `tests_app/test_ic_paper_loop_core.py` run via `db_run_fresh.py`.
- **Acceptance:** the Proof above passes on a throwaway DB (1 record at frame 6, 0 at frame 5; fills = frame 6 mids;
  totals = sum of fills); the 2 isolation tests and the 2 guard mutation tests pass; a reviewer (fresh Opus,
  read-only, 25 min / 40 calls) returns PASS, or its MAJOR findings are fixed in at most 2 rounds.
### Stage B1 - every ON rule raises its record (Sonnet)
- **Do:** one parametrised worker -> gate -> record test over path scenarios for T-02, T-03, T-06 and the 2x-credit
  line, T-07, T-09, T-10b, T-11, T-13, T-19 (T-18 is proven in C1, after paper adjustments exist), and the situation
  RULES among S-01..S-12 (Guidance situations S-03, S-04, S-05, S-08, S-09 shown, never raised); T-21 withholds. New
  path scenarios where none crosses. Reuse the existing harnesses.
- **Acceptance:** for EACH listed rule: exactly 1 record at its crossing frame and 0 one frame before.
### Stage B2 - T-14 gamma (Opus builder, Tier A review)
- **Do:** design decision 8 on screen and in the worker.
- **Acceptance:** crossing / not-crossing pair; margin missing -> not checked; the value equals an independent
  repricing in the test within Rs 1; reviewer PASS (25 min / 40 calls).
### Stage B3 - all 14 trade approaches change the paper legs (Sonnet)
- **Do:** one parametrised test over A-01, A-02, A-04, A-05, A-06, A-11, A-24, A-25, A-26, A-27, A-28, A-29, A-31, A-35:
  prepare -> paper orders with the suggestion id -> the paper legs equal the built After legs; A-11 `guard_debit`;
  buy-back-first order test.
- **Acceptance:** 14 of 14 pass + 2 guard tests pass.
### Stage B4 - bell + toast (Sonnet)
- **Do:** design decision 10.
- **Acceptance:** vitest: count = paper unread + open records; toast on a new id; click route; one route test.
### Stage B5 - wording #657 + #658 (Sonnet)
- **Do:** design decisions 12 and 13.
- **Acceptance:** vitest on the screen text; migration 0044 test via `db_run_fresh.py` (upgrade + downgrade + allow-list).
### Stage C1 - second adjustment (Sonnet, after B3)
- **Do:** design decision 14 on one path scenario: adjust -> new crossing -> second adjust -> crossing -> only exit /
  reduce offered, T-19 warning shown; T-18 record raised.
- **Acceptance:** that one scenario test passes end to end.
### Stage C2 - every exit (Sonnet, after B3)
- **Do:** a multi-day weekly path scenario reaching expiry: profit target (T-07 -> A-24 / A-31), stop (T-06 or 2x
  credit -> A-31), 14:30 expiry exit (time_exit + day rule 5 -> A-35), close for pennies (T-09 -> A-27), legs held to
  expiry settled (`paper_settlement.py`). Each: record -> approach -> paper fills close the legs -> final P&L in history.
- **Acceptance:** one test per exit (4) + 1 settlement test pass.
### Stage C3 - outcomes (Sonnet, after B3)
- **Do:** design decision 11.
- **Acceptance:** one test per outcome (acted on, completed, partly completed, lapsed).
### Stage D - close
- **Do:** merge all stages; regenerate generated files once (`tools/build_findings_index.py .`,
  `tools/build_spec_digest.py .`, `PYTHONPATH=backend python scripts/generate_openapi.py`); re-run the core proof once;
  `python scripts/orchestrator/prepush.py --full` once (detached `Start-Process`, log to `D:\Abhay\scratch\gcic1\`);
  on TOTAL PASS `git push origin feature/adjustments`; handover `docs/process/session-handover-<date>-ic-e2e.md`; memory.
- **Acceptance:** TOTAL PASS marker for the pushed sha; push line read back; handover committed.

## Verification gates (adapted to the owner's delivery plan of 2026-11-05)
| Gate | What it checks here | Fires |
|---|---|---|
| Builder tests | new failing-first tests for what it changed + `python scripts/orchestrator/select_app_tests.py <tree>` list + `python scripts/ruff_ratchet.py` OK; logs to a file, tail only | every builder, before its last commit |
| Lead re-run | the orchestrator re-runs that same list once on the builder's tip before merging (evidence-and-proof E4: a worker report is a claim) | every merge |
| Persistence | DB read-back in the core proof (records, orders, legs, totals counted by queries), never a UI message | Stage A, Stage D |
| Plausibility | T-14 value equals an independent repricing within Rs 1; paper fills equal the frame mids | Stages A, B2 |
| Review | fresh Opus, read-only, after that wave's builders finish (a review blocks builder writes) | Stages A and B2 only |
| Full gate | `prepush.py --full` TOTAL PASS | once, Stage D |
Not run, by owner decision: full suites per stage, end-to-end, browser checks, live day, blind second verifier.

## Builder brief requirements (hooks refuse a brief without them)
First lines `Core:` and `Proof:`; `Budget: <N> min wall-clock, <M> tool calls` within the agent's limit (builder-b:
45 min / 60 calls max; Explore / reviewer per their caps); `Report: evidence-table`; `Why Opus:` for Opus; `Class:` for
fixes; `Spec basis:` lines; and these checklist items from 2026-11-05: (1) own-tree branch from the wave sha; (2)
`select_app_tests.py` + `ruff_ratchet.py` before the last commit; (3) never edit generated files; (4) new user text gets
a pin in `tests/errors/template_pins.json` ("pending owner read"), no strategy type name in backend code (use the
constant), new scan tests carry `pytestmark = pytest.mark.repo_scan`; (5) Decimal money, every answer state tested;
(6) migrations find their row by REASON, re-pin changed guard functions, end with the allow-list `post` check.

## Failure-recovery budget
- At most 2 fix rounds per stage; then park: `python scripts/orchestrator/gh_issue.py app parked "<title>" <body-file>
  --stage S6.7` from the run tree, a PARKED line in the log, the stage stays PARTIAL; continue with the rest.
- A builder blocked by a hook or tree lock: read the block reason, fix the brief, re-send once; never bypass a hook.
- Low-memory kill of a waiting script: check the real process by PID before restarting anything.
- Hard halt only for: a contradiction inside this contract; a missing credential; dependency install failure; an
  irrecoverable build break after the budget.

## Commit + push policy
- Builders commit per item on their own branch; the lead merges by sha into `feature/adjustments`.
- Messages: plain sentence naming the stage; end with the session's attribution lines.
- ONE push, Stage D only, after TOTAL PASS. No PR. Nothing to main. Do not stage scratch files.

## Definition of Done (each box: action + completeness bar)
- [ ] Stage A core Proof passes on a throwaway DB, and both isolation tests and both guard mutation tests pass; review PASS.
- [ ] EVERY listed ON rule (B1 list) has a passing 1-record / 0-record test; T-14 evaluated with its tests and review PASS.
- [ ] ALL 14 trade approaches change the paper legs in a passing test; A-11 debit guard and order-sequence tests pass.
- [ ] Bell counts open adjustment records; toast and click tested.
- [ ] #657 and #658 wording shipped with tests; migration 0044 tested on a throwaway DB.
- [ ] Second adjustment, all 4 exits + settlement, and all 4 outcomes have passing tests.
- [ ] One `prepush.py --full` TOTAL PASS on the pushed sha; `feature/adjustments` pushed once.
- [ ] Every parked stage has an issue and a PARKED line; no stage is silently skipped.
- [ ] Handover + PROGRESS final entry with DONE / PENDING / BLOCKED / PARKED / NEXT; lock released; trees removed.

## Guardrails
- No real order and no Kite call in scenario mode; real order routes stay refused there.
- The owner's real strategies (e.g. 82) are never read by a scenario worker; proofs run on a throwaway DB only.
- No new dependency; no change to live-mode behaviour beyond the marker filter (live lister = `scenario_id IS NULL`).
- No synthetic numbers in reports: every claim has a command and its result line.
- No edit of kit files; no question to the owner during the run (park it in `docs/process/owner-questions-<date>.md`).

## Final report
Per stage: what shipped + commit shas; skipped (already covered); parked with issue numbers; review verdicts; the gate
result line; the push line; DONE / PENDING / BLOCKED / PARKED / NEXT; learnings to fold back (proposed only).
Also: (a) every new user-facing sentence added with a "pending owner read" pin, listed with its text, so the owner can
read them in one place; (b) strategy 82's stop lines before and after the Stage D dev upgrade (§0.4.3); (c) the open
issues this contract left out on purpose (#627 item 3, #636, #644, #647, #624, ADR-028 phone channels), one line each.

## Authorization trail
| Fork | Decision | Why |
|---|---|---|
| What "end to end" covers | Full trade loop | owner, question tool 2026-11-05 |
| Proof | Full paper loop on test data, no live day | owner |
| Rules | Existing approved playbook, ON rules only | owner |
| Alerts | In-app only (ADR-028 channels later) | owner |
| Plan + delivery plan | Approved | owner, question tool |
| Scenario-mode paper orders, marker, frame table, T-14 formula, bell reuse | as in design decisions | technical calls (orchestrator) + plan review (11 findings accepted) |
