# Goal contract GC-ADJ2: adjustment playbooks, plan sheet, opportunities inbox and history, iron condor first (2026-10-31)

Written 2026-10-31 after GC-ADJ1 closed (prepush --full PASS on b5ad5fe5, merged into local `feature/adjustments`
2cc34503) and the owner's approval of the iron condor numbers (ADR-216). Run it with `/goal` in a FRESH session. Scope:
the playbook system for ALL types through one store and code path, with the iron condor as the only shipped
non-Draft playbook; paper strategies first. Suggest-only (ADR-003, ADR-206): no order is ever placed.

Core: a stored playbook's per-stage triggers, evaluated against a tracked strategy, flag exactly the rules the scenario
library expects, and a condition already true at entry does not flag (F-71).
Proof: step 1 - scenario mode ADJ-02 (fires) and ADJ-01 (quiet) on the dev server: the iron condor system playbook,
read from the DB, flags the generator's expected rules with value read and threshold; an F-71-shaped scenario (short
0.35% from spot at entry) flags nothing at entry and flags once spot moves inside the stage's threshold.

## Owner decisions behind this contract (all recorded; the run never re-asks them)

- **Owner rule (2026-10-30): every change stays on `feature/adjustments`. Never open a PR to main, never merge or push
  to main, even when the feature is done. Only the owner's explicit approval allows that.** GC-ADJ2 is the last
  contract before that one PR; the run does not open it.
- ADR-214 (3), (4), (4a)-(4d): playbooks under Strategies > Adjustments ("My playbooks"); one system playbook per type
  plus the user's own; stages, triggers per stage, day-and-date rules, situations, guards; one step-by-step editor;
  inbox under Positions > Adjustment opportunities.
- ADR-216 (owner, 2026-10-31): the iron condor (PB-04) numbers are approved and carry no "Draft" label. Per stage the
  defaults are the mockup screen 4 values in `tests/fixtures/adjust_scenarios/_playbooks.json` (iron condor family)
  with ONE change: T-19 fires below **1x** the adjustment's cost (the fixture says 2). Every other system playbook stays
  "Draft" (REQ-158 AC-2).
- ADR-215 (Exit shows no Greeks after, cannot lead) stands; GC-ADJ1's compare is reused, not rebuilt.
- Requirements: REQ-158 (store), REQ-159 (content), REQ-160 (editor + Test), REQ-161 (plan sheet), REQ-162 (inbox),
  REQ-163 (history), and the part of REQ-112 they stand on (AC-1, AC-2, AC-4, AC-6: one suggestion record with an
  outcome; AC-3 only as "Paper - not sent to Zerodha" / "Acted on" because the run places no order). REQ-045 AC-1,
  AC-3, AC-7, AC-8 (labels, AND/OR, precedence, grouping).
- Test data (owner, 2026-10-30): every proof runs on the scenario library `tests/fixtures/adjust_scenarios/`
  (generator `tests/adjust_scenarios_gen.py`, expected values derived without the engine). Add a scenario through the
  generator when a case is missing; never hand-type numbers.
- Target screens: mockup https://claude.ai/artifact/RwzCxhDod7yVCk6TWrQc9e screen 4 (playbook editor) and its inbox and
  history panels. Look and words follow the mockup; numbers come only from the engine (ADR-008).

## §0.1 Where the run works

- Run tree: `~/.claude/tools/wt-new.ps1 -Repo D:\Abhay\Ventures\OptionsForOptions2 -Name gcadj2-run -Branch
  build/gcadj2 -Base feature/adjustments -Purpose "GC-ADJ2 run" -TtlHours 72`. `feature/adjustments` must contain
  ADR-216 (commit on `build/gcadj2-docs`, merged locally before the run). Never work in the main checkout.
- Builder sub-worktrees `wt-new.ps1 -Name gcadj2-<item> -Base build/gcadj2`, merged locally into `build/gcadj2`.
  `frontend`: `npm ci` (link_guard refuses a junction into main; GC-ADJ1 setup note).
- Lock: `.run-active.lock` with the session token at the run tree root; removed on any stop.
- Memory (measured 2026-10-31): prepush --full needs ~6 GB free; it was killed 3 times at 3.3-3.7 GB and passed at
  7.9 GB after a restart. Before the close step, check free memory; under 6 GB, stop builders and dev servers first.

## §0.2 Preflight (never redo finished work)

- Read the Status column, "Found during the run", "Parked", and `git log --oneline build/gcadj2` for `GC-ADJ2 step N`
  commits; a DONE step with its commit is re-verified from its proof and skipped.
- Read before any code: ADR-214, ADR-215, ADR-216, ADR-003, ADR-008, ADR-206, ADR-207; REQ-158..163, REQ-112,
  REQ-045, REQ-109; `spec/findings.md` F-71, F-74; `knowledge/findings/INDEX.md`; `docs/process/runbook.md`;
  `.claude/kit/builder-brief.md`; catalogue `docs/research/adjustments-catalogue-2026-10-30.md` Parts 3, 4, 6, 9b,
  9c; `_playbooks.json` (stages, triggers, families, guards, day_rules, situations, conventions); code
  `backend/ofo/adjustment/{detection,registry,approaches,compare}.py`, `backend/ofo_app/routes/tracking.py` (l.61
  near-level threshold, l.107 platform_detection), `backend/ofo/tracking/`, `frontend/src/lib/tracking.js` (GC-TP
  replaced "Start tracking" with the builder's paper action, ADR-207 (1)), `frontend/src/router/nav.js:32`
  (the inbox nav entry exists, no page), the last migration `backend/ofo_app/alembic/versions/0030_paper_settle_zero.py`.
- GC-ADJ1 lesson (row 23): a brief that touches `backend/ofo_app` imports carries
  `tests_app/test_order_closure_all_routes.py` in its Tests line.

## §0.3 Progress log

Each step ends with one line here: `step N DONE <sha> <proof line>` or `PARKED (#issue)`.

- step 0 DONE bc8baafc (2026-10-31 10:5x): loose grep `playbook|adjustment_plan|suggestion|opportunit|REQ-112` over backend,
  frontend/src, tests, tests_app: NO playbook store, plan table, suggestion record or inbox page exists. Hits are text
  only: `detection.py` (fixed 0.5% platform rule, kept for strategies with no playbook type), `routes/tracking.py`
  l.107 `platform_detection`, `lib/tracking.js:40` label, `nav.js:32` inbox key (no page), `errors/explanations.py`
  ADJUSTMENT_OPPORTUNITY label, generator `playbooks()` + `tests/test_adjust_scenarios.py` `recompute_fired` (the
  engine-free reference the evaluator must match). Reuse: those two; retire: nothing.

## Rules for the run

- Prove the core first: step 1's proof must pass before steps 2-7 start. A failing core STOPS the run (report, park).
- Close: `python scripts/orchestrator/prepush.py --repo <run tree> --full` must PASS, then `build/gcadj2` merges
  `--no-ff` into local `feature/adjustments`. No push, no PR, never `gh pr merge`.
- The migration (step 1) is Tier A: fresh Opus reviewer, mutation tests on every guard (unique name per type, one
  active per type, a system playbook cannot be saved in place), upgrade AND downgrade run on ofo_dev only (never
  ofo_test; the DB host serves production), one file at a time.
- Money and every P&L / booked P&L / charges / premium-left figure comes from the one engine (ADR-008); step 6 gets the
  `options-math-review` checklist and an Opus reviewer (REQ-163 risk: high).
- Every build brief carries: Core, Proof, Budget, Report: evidence-table, Spec quote, Findings checked, Sensibull line
  (none for adjustments, ADR-214 source), every answer state of each data read (stated, absent, not found, failed,
  empty, ambiguous) and what the screen shows for each, and the builder-brief standing items.
- Wording: ADR-003; "Your rule was triggered" / "Adjustment opportunity detected"; "You dismissed this", never "missed";
  no "best". The wording CI check must pass.
- At most 2 fix rounds per item, then park (`parked` issue, tracker line) and move on.
- Owner away: never ask; decide spec-conformant points and record them here; anything needing the owner goes to
  `docs/process/owner-questions-<date>.md` with a recommendation. Night guard 22:00-08:00 applies.
- Browser checks in the owner's visible Chrome only (Claude-in-Chrome), one tab, closed after; never click inside a
  live order panel; no orders.

## Running the app

- As GC-ADJ1 "Running the app": ports 8765 / 5174 checked first; stop only recorded PIDs (by literal PID); API via
  `scripts/orchestrator/dev_run.py` on ofo_dev; Vite `OFO_API_TARGET=http://127.0.0.1:8765 npx vite --port 5174
  --strictPort`. Scenario mode `OFO_SCENARIO=<ADJ-id>` (dev and test only) serves the scenario's chain, spot and clock.
  A live REST spot needs `LIVE_MARKET` registered (F-76 note). Live checks are optional, never a blocker.

## Design decisions (pre-made; the run does not pause on these)

- **Store (REQ-158).** Tables `adjustment_playbooks` (id, user_ref or NULL for system, strategy_type, name, is_system,
  status `draft`/`approved`, body JSONB, version, created/updated) and `adjustment_playbook_active` (user_ref,
  strategy_type, playbook_id; unique per user+type). Unique (user_ref, strategy_type, lower(name)). The body holds
  stages, triggers per stage, day rules, situations, guards, approaches on/off: data, not code (REQ-158 AC-7). System
  playbooks are seeded by the migration from one checked-in JSON derived from `_playbooks.json` (12 types per
  REQ-158 AC-1; iron condor `approved` with the ADR-216 values, the rest `draft`). No row for a user = system default
  active. Deleting the active one makes the system playbook active and the answer says so (AC-4).
- **Precedence (REQ-158 AC-5, REQ-045 AC-7).** A strategy's plan is a COPY of the playbook body taken when the plan is
  accepted (`strategy_adjustment_plans`: strategy_id, playbook_id it came from, body, accepted_at). Editing or deleting
  the playbook never touches it. A strategy with no plan reads its type's active playbook.
- **Evaluation (REQ-159, F-71 class fix).** One pure function `evaluate(plan_body, strategy_state, clock) -> [Flag |
  NotChecked]` in `backend/ofo/adjustment/playbook_eval.py`: picks the stage from days left (weekly or monthly
  stages), reads each ON trigger's value for that stage, compares exactly (Decimal, inclusive as `detection.py` l.13),
  combines AND/OR rules (REQ-159 AC-3), and returns per rule: strategy, value read, threshold, stage. A trigger whose
  data is missing returns NotChecked with its reason, never passed (REQ-160 AC-3). F-71: a rule whose condition
  already held at the moment tracking started is recorded "Already true when tracking started" and does not open an
  opportunity until it has stopped holding and holds again (the class: any distance trigger on a shape whose short
  sits inside the threshold by design). `detection.py`'s fixed 0.5% stays only for a strategy with no playbook type
  (REQ-161 AC-4 generic triggers).
- **Open conventions (catalogue / `_playbooks.json` "conventions"), technical calls made here:** T-14 "loss from a 1%
  move" = the engine's P&L change at spot +1% and -1% at today's IV and time, the larger loss, as % of the Zerodha-
  stated margin; T-19 "premium still left" = sum over open short legs of (mid x quantity) minus the sum over open long
  legs, compared with the adjustment's own charges (GC-ADJ1 "This adjustment" figure); "% of premium paid" (long
  options, PB-08) = current value / debit paid - 1, Draft playbooks only; "tighten every trigger by X%" = every trigger fires
  sooner: a distance threshold ("spot within N% / N points") multiplied by (1 + X/100), a loss, delta or profit
  threshold by (1 - X/100), for the rest of that session.
  Each written into REQ-159's section text in step 2 and the scenario expectations regenerated.
- **Suggestion record (REQ-112 part).** Table `adjustment_suggestions` (id, strategy_id, rule id or `platform`, the
  flag's value read + threshold, shown_at, outcome `open`/`dismissed`/`acted_on`/`lapsed`, timeline JSONB append-only).
  "Acted on" = the user opened the compare and pressed "Open in builder and prepare basket" (GC-ADJ1 step 3).
  "Completed"/"Partly completed" exist in the type but are never set by this run (no orders); a paper strategy shows
  "Paper - not sent to Zerodha". "Lapsed" = the condition stopped holding before any action, or the strategy closed.
- **Screens.** Strategies > Adjustments: list of playbooks per type (system + own, active mark, Draft label), editor
  per REQ-160 AC-1 with the plain-words summary beside it, Test per AC-3 (scenario mode gives current strategies).
  Plan sheet: opens from the builder's paper/track action (ADR-207 (1) replaced "Start tracking"), fields per REQ-161
  AC-1, "Use playbook as is", editable later from the strategy page. Inbox page at the existing nav key
  `adjustment-opportunities`. History panel on the strategy page. Phone width: tables scroll in their own container.

## Items

| Step | What | REQ / finding | Proof (scenario data) | Status |
|---|---|---|---|---|
| 0 | Overlap check: loose grep for `playbook`, `adjustment_plan`, `suggestion`, `opportunit`, `REQ-112` over backend, frontend/src, tests, tests_app; list what exists to reuse or retire | - | the grep output in §0.3 | |
| 1 | **CORE**: migration 0031 (playbooks, active, plans, suggestions) + seed + `playbook_eval.py` + F-71 crossing rule; wire the tracking route's detection to the strategy's plan / active playbook | REQ-158 AC-1/2/4/5/7, REQ-159 AC-1/2/3, F-71 | Test per iron condor scenario: flags equal the generator's expected rules (value read, threshold, stage); ADJ-01 quiet; an F-71-shaped scenario (add via the generator) quiet at entry, flags after the move; NotChecked with reason for a missing price; migration up/down on ofo_dev; Tier A check | |
| 2 | Playbook API: list, read, create, duplicate, rename, delete, make active, save as new / save in place; refusals with the exact REQ texts; conventions written into REQ-159 text | REQ-158 AC-3/4/6, REQ-159 AC-4/5/6 | app tests per refusal ("A playbook named X already exists for Iron condor"; system playbook saved in place refused); order-closure test passes | |
| 3 | Editor + plain-words summary + Test | REQ-160 AC-1..4 | Component tests; owner's Chrome in scenario mode ADJ-02: open the iron condor system playbook (no "Draft" label; a strangle playbook shows "Draft"), change T-01 Middle to 0.3, Test lists the flag with value and threshold, unsaved; "Save as new" creates the user's own | |
| 4 | Plan sheet at the paper/track action | REQ-161 AC-1..4 | Chrome, scenario ADJ-02: sheet pre-filled from the active playbook; "Use playbook as is" saves the plan; editing the playbook later leaves the plan unchanged (app test); an unmatched shape says it uses generic triggers | |
| 5 | Suggestion records + inbox | REQ-112 AC-1/2/4/6, REQ-162 AC-1..3 | App tests: a flag opens one record; Dismiss sets "Dismissed" with reason; prepare basket sets "Acted on"; condition ends -> "Lapsed"; grouped flags one outcome each. Chrome: inbox lists ADJ-02's opportunity with label and outcome, links to the compare; empty state text | |
| 6 | Adjustment history + whole-trade totals | REQ-163 AC-1..3, F-74 | Scenario ADJ-13 (booked +962.00): rows and totals equal the generator's engine-free values to the paisa, totals = sum of rows; paper rows say "Paper - not sent to Zerodha"; an unconfirmed adjustment shows "pending" and is not in the totals; Opus review with options-math-review | |
| 7 | Close: prepush --full PASS, merge `build/gcadj2` into local `feature/adjustments` (no push, no PR); handover DONE / PENDING / BLOCKED / PARKED / NEXT; memory note | - | prepush marker + `git log feature/adjustments` showing the merge | |

## Definition of Done

Steps 1-6 DONE with proof lines in §0.3, or PARKED with an issue; F-71 marked fixed in `spec/findings.md` with its
proof and a class file in `knowledge/findings/` (status `guarded`, naming its test); the four conventions written into
REQ-159; `build/gcadj2` merged into local `feature/adjustments` after a passing prepush --full; nothing pushed, nothing
on main; handover written; memory note updated. The run then tells the owner the feature is ready for the one PR to
main and waits for the owner's explicit approval; it does not open it.

## Found during the run

| # | What | Where | Decision |
|---|---|---|---|
| 1 | Step 1 is too big for one builder | step 1 | Technical call: split into 1A store + migration 0031 + seed (Tier A), 1B pure evaluator + F-71 + generator (parallel), 1C wiring + dev-server proof. Shared body shape fixed first in `docs/design/playbook-body-v1.md` (bc8baafc). |
| 2 | F-71 needs memory across checks; the contract's four tables have no home for it | step 1 | Technical call: a fifth table `adjustment_rule_state` (strategy, rule, held_at_entry, seen_clear). Held at entry is computed from the position's entry state (entry spot), not from the first check, so ADJ-02 (far at entry) still flags on its first check. |
| 3 | Branch DB tests would move the shared ofo_test to an unmerged revision (finding branch-migration-tests-move-shared-db) | step 1A | DB tests run only through `db_run_fresh.py` (throwaway database); ofo_dev upgrade/downgrade by the orchestrator. |
| 4 | Paper orders store no index level at entry, so F-71's entry state is unknown live | step 1C | Technical call: in scenario mode the scenario's `position.entry`; live, the first check after tracking starts (rule memory empty) is the entry state. The plan sheet (step 4) accepts the plan at the paper action, so the first check is at entry. |
| 5 | The four open conventions | step 2 (done early) | Written into REQ-159's section text now (docs only): T-14, T-19, % of premium paid, tighten by X%. |
| 6 | 1B round 1: 3 repo guards red (plain-text reasons, money ratios outside the engine, scan mark) | step 1B | Round 2: ratios move into the engine package (ADR-008 by structure, no allow-list widening); reasons become catalogue codes reusing the scenario library's sentences (owner wording review later); scenario folder read as test_adjust_scenarios does. |
| 7 | 1A round 1: the AC-3 duplicate-name sentence fails the wording scan when the user's name holds a word like safe | step 1A | Technical call: the name is the user's own text, slotted as user text (shown verbatim, not judged); the template stays scanned; the AC-3 sentence is unchanged. No spec change. |
| 8 | Regenerated library: ADJ-33, ADJ-37, ADJ-40 are real F-71 cases (22900 short 0.52% from entry spot 23020, inside Early 0.75%); T-01 moves from fired to already true at entry. ADJ-08 T-19 no longer fires at 1x (ratio 2.0236). F-71 scenario is ADJ-42 (ADJ-39 was taken) | step 1B | Expected values regenerated by the generator; recorded for the F-71 finding update. |

## Parked

None yet.

## Next contract (outline): GC-ADJ3 and later

As in the GC-ADJ1 handover table (cost and honesty, more strategy types, triggers T-03..T-19 live, what-if and paper
adjust, time-of-day help, deeper analysis). Owner input before GC-ADJ4: approval of the other system playbooks'
numbers (catalogue Part 9b question 1, every PB except PB-04).
