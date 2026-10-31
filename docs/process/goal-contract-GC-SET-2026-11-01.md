# Goal contract GC-SET: admin Settings (app-wide), per-user adjustment Preferences, admin-edited system playbooks (2026-11-01)

Written 2026-10-31 23:35 IST after the owner's answers Q1-Q6 (ADR-222 (1)-(11)). Run it with `/goal` in a FRESH
session from the run tree named in §0.1. Scope: REQ-167, REQ-168, REQ-169, plus the ADR-221 T-19 cost fix that
REQ-168's "no per-leg cost" depends on. Suggest-only stays (ADR-003): no order is ever placed.

Core: a value read from the settings store at the moment a calculation runs changes that calculation's output, with
no restart, and the user-level value overrides the admin default only for that user.
Proof: step 1 - on a throwaway DB, `pricing.risk_free_rate` 0.065 -> 0.07 changes a Greek or "estimated now" figure
returned by the outcome route for the same strategy and market, and a reset row (the default) returns it; no process
restart between the reads.

## Owner decisions behind this contract (all recorded; the run never re-asks them)

- **Owner rule (2026-10-30, restated 2026-11-01 00:10): "complete everything on the adjustments branch, not on the
  main branch."** Never open a PR to main, never merge or push to main. The PR approval given on 2026-10-31 was
  WITHDRAWN (PR #622 closed unmerged); it does not carry over. Pushing `feature/adjustments` itself is allowed only at
  the close step (§ Step 9), after prepush --full passes, as a backup.
- ADR-222 (read all of it, `spec/decisions/ADR-222.md`):
  (1) no business number typed in code; (2) one admin Settings page, audited, value in force at the time;
  (5) admin Settings = APP-WIDE only; adjustment preferences are PER USER on the Adjustments screen;
  (6) Preferences tab holds values for ALL of a user's strategies; stage numbers stay in playbooks, never both;
  (7) admin "Adjustment defaults" group = starting values; a user who did not change a value follows the admin
  default in force; (8) NO per-leg cost allowance, the Rs 40 COST_PER_LEG is deleted; (9) a change applies at the next
  check to every tracked strategy, saved plans (REQ-161) are not changed, every alert line names the value it used;
  (10) the admin edits SYSTEM playbooks in the same editor as versions; (11) order REQ-167 -> REQ-168 -> REQ-169.
- ADR-221: T-19 compares premium left with the cost of the CHEAPEST approach of the playbook's current stage, priced as
  the Compare's "This adjustment" cost (charges + half spread, `backend/ofo/adjustment/compare.py:220-231`); the flag
  names that approach and cost; no priceable approach -> T-19 not checked, with the reason.
- REQ-167 AC-1..AC-7, REQ-168 AC-1..AC-5, REQ-169 AC-1..AC-4 are the acceptance lists. The value inventory with file
  and line is `docs/design/settings-scan-2026-10-31.md` (24 groups A, time-varying facts B).
- Defaults never change in this run: every setting's default is the value the code has today (scan table "Now"
  column), except the Rs 40 which is deleted. Undo window (F-79, owner question Q-SET-1 still open): defaults 8 s
  (one leg) and 10 s (Clear all), as the code has; REQ-167 AC-7.
- Test data (owner, 2026-10-30): proofs run on the scenario library `tests/fixtures/adjust_scenarios/` (generator
  `tests/adjust_scenarios_gen.py`); add a case through the generator, never hand-typed numbers.
- Every browser proof runs in the owner's visible Chrome (Claude-in-Chrome), never headless, in scenario mode
  (`APP_ENV=development OFO_SCENARIO=<ADJ-id>`); no Kite login is needed.

## §0.1 Where the run works

- Run tree: the EXISTING worktree `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`, branch
  `build/settings` (head at writing: aeb1a550 = WIP of step 1 on top of merge faee3cd4, which carries feature/adjustments
  554035b5). Never work in the main checkout `D:\Abhay\Ventures\OptionsForOptions2` (it is on `main`).
- Before step 1: `git -C <run tree> merge --no-ff feature/adjustments` if `feature/adjustments` has moved past 554035b5
  (docs commits only so far); record the merge sha in §0.3.
- Builder sub-worktrees: `~/.claude/tools/wt-new.ps1 -Repo D:\Abhay\Ventures\OptionsForOptions2 -Name
  OptionsForOptions2-gcset-<item> -Branch build/gcset-<item> -Base build/settings -Purpose "GC-SET <item>"`; merge into
  `build/settings` by the SHA the builder reports (never by a `worktree-agent-*` branch name: memory lesson
  merge-builder-by-sha). frontend: `npm ci` in each tree (no junction into main).
- Lock: `.run-active.lock` with the session token at the run tree root; removed on any stop.
- Memory: prepush --full needs about 6 GB free (killed 3 times at 3.3-3.7 GB on 2026-10-30/31). Before the close step,
  check free memory; under 6 GB, stop builders and dev servers first.
- The DB host also serves production: DB tests ONE FILE PER RUN on a throwaway DB:
  `python scripts/orchestrator/db_run_fresh.py . python -m pytest -c pytest-app.ini tests_app/<file>.py`. Never a full
  DB suite locally, never ofo_test directly. Dev-server proofs use ofo_dev via `scripts/orchestrator/dev_run.py`.

## §0.2 Preflight (never redo finished work)

- Read the Status lines in §0.3, the "Found during the run" table, "Parked", and
  `git -C <run tree> log --oneline feature/adjustments..build/settings` for `GC-SET step N` commits; a DONE step with
  its commit is re-verified from its proof line and skipped.
- WIP already on the branch (commit aeb1a550, written by a stopped builder, compiles, NEVER tested):
  `backend/ofo/settings/registry.json` (one key, `pricing.risk_free_rate`, group Pricing, fraction, default "0.065",
  range 0-0.5), `backend/ofo/settings/__init__.py` (loader + validation: refuses JSON floats, duplicate keys, defaults
  out of range, unknown keys, non-numbers, a percent typed for a fraction with "enter 0.065 for 6.5%"),
  `backend/ofo_app/alembic/versions/0032_app_settings.py` (append-only table app_settings, trigger OF032, unique
  (key, effective_from), app role SELECT+INSERT, allowlist block 24, downgrade refused while rows exist),
  `backend/ofo_app/settings_store.py` (value in force at a time, default when no row, future rows not in force, unknown
  keys ignored, a stored value the registry now refuses raises; history newest first; add with validation, no
  back-dating, audit via the existing admin-change event's action/reason fields). Step 1 TESTS this code first; any
  defect is fixed, not rewritten.
- Read before any code: ADR-222, ADR-221, ADR-082, ADR-008, ADR-003, ADR-214, ADR-216, ADR-217; REQ-167, REQ-168,
  REQ-169, REQ-158, REQ-159, REQ-160, REQ-161; `spec/findings.md` F-77, F-78, F-79;
  `knowledge/findings/INDEX.md` (classes one-money-figure-two-formulas, setting-saved-but-never-applied);
  `docs/process/runbook.md`; `.claude/kit/builder-brief.md`; `docs/design/settings-scan-2026-10-31.md`;
  `docs/design/playbook-body-v1.md`; code `backend/ofo_app/alembic/versions/0012_charge_rates.py` and
  `backend/ofo_app/charge_rates_store.py` (the dated admin-store pattern), `backend/ofo_app/audit_store.py`,
  `backend/ofo_app/playbook_store.py`, `backend/ofo_app/alembic/versions/0031_adjustment_playbooks.py` (guard and
  allowlist conventions), `backend/ofo_app/routes/outcome.py` (`get_market_context`), `backend/ofo_app/live_market.py`
  (l.50 LIVE_RATE, l.103), `backend/ofo_app/adjustment_check.py` (l.56 COST_PER_LEG, l.157-158),
  `backend/ofo/adjustment/compare.py` (l.87-89, l.220-231), `frontend/src/pages/AdjustmentsPage.vue`,
  `frontend/src/router/nav.js`.
- Lessons that bind this run (memory): a brief that changes catalogue wording also runs
  `tests/strategy/test_templates.py` (REQ-028 AC-5: no strategy-shape name in backend code) and
  `python scripts/ruff_ratchet.py` (no rule may rise); a brief touching `backend/ofo_app` imports also runs
  `tests_app/test_order_closure_all_routes.py`; new user-facing texts get pins in `tests/errors/template_pins.json`
  with `"reviewed": "pending owner read"`; `docs/api/openapi.json` is regenerated with `scripts/generate_openapi.py`
  when routes change (drift test `tests_app/test_openapi_drift.py`); generated views via
  `python scripts/orchestrator/regen.py .`; a new ADR/REQ is added to `docs/process/coverage-stages.yaml`.

## §0.3 Progress log

Each step ends with one line here: `step N DONE <sha> <proof line>` or `PARKED (#issue)`. Times are read from the
clock (`date`) in the same step, never typed from memory.

- step 0 DONE (2026-10-31 23:36 IST, no code commit) rows re-found 39 of 39 file:line spots (31 backend, 8 frontend);
  moved lines: none beyond multi-line constants (`scenario/config.py:121` opens the DEFAULT_CONFIGS block,
  `compare.py:87` is MOVES within 87-89, `timeutil.py:27` SESSION_OPEN opens 27-32). feature/adjustments = 554035b5,
  no merge needed. Note: `charges/rates.py:33` STAMP_CAP 0.0001 carries "# real 0.00003" (step 5 to check).
- decision (technical, 23:45): the per-request risk-free rate applies to the live and scenario-mode contexts served by
  `get_market_context`; contexts injected by `dependency_overrides` (unit tests, replay) keep their own rate (test
  data). Scenario fixtures state 0.065 = the default, so no scenario output moves with no row; step 2's browser proof
  (Greeks move on ADJ-02) needs this.
- step 1 dispatched 23:47 (builder, worktree `OptionsForOptions2-gcset-core`, branch build/gcset-core).
- step 7 dispatched 23:55 in parallel (no file overlap with step 1; worktree `OptionsForOptions2-gcset-t19`, branch
  build/gcset-t19).
- step 1 builder done 4d4423fd: core proof `test_settings_rate_wiring.py` 6 passed ("figures changed by the rate:
  dividend_yields, legs, table"), store 19 passed, registry 20 passed, ratchet OK. Gaps: mutants 1/2/4/5 not run,
  order-closure ran pre-final. Builder found: scenario mode installs its own override, so it bypassed the setting.
- decision (technical, 01:0x 11-01): scenario mode ALSO applies the setting (stand-in for live; step 2's proof needs
  it); replay + unit-test overrides keep their own rate. Supersedes the 23:45 line's scenario part. Finisher (Sonnet)
  + Tier A reviewer (fresh Opus) dispatched in parallel.
- step 7 builder done bac262d9: core proof ADJ-02 T-19 = A-29 Rs 92.35 = cheapest Compare cell (old formula Rs 342.00);
  mutants 5/5 killed; check route DB file 8 passed (re-run by me on bac262d9). ADJ-14 no longer fires T-19 (last day,
  every approach trades a bid-0 contract -> not checked). New scenarios ADJ-43 (fires) / ADJ-44 (quiet) - ADJ-30/31
  were taken. My fixes: ruff E501 wrap, history-library count pin 44 -> 46, repo_scan mark on the new test; full pure
  tree first run 4 failed / 8568 passed, names being collected.
- step 1 Tier A review (fresh Opus): REVISE, 1 MAJOR (leg picker strikes/futures priced with the default rate, not
  the setting) + 5 MINOR (back-dated raw insert passed the DB, setting row survived a failed audit, owner TRUNCATE,
  loader accepted duplicate/unknown keys, a wiring test blind to a defaults-only reader). Round 2 (Sonnet) fixed all 6;
  new guard `tests/test_rate_context_guard.py` (no `.rate` read in routes/ except via the one dependency, red-then-green
  self-test). DB guard allows 5 s grace on effective_from (store reads now one statement before insert).
- step 1 DONE d86c18ee (merge of fcd723be) 02:3x IST: re-run by me on fcd723be: `test_settings_store.py` 23 passed;
  `test_settings_rate_wiring.py` 8 passed, "figures changed by the rate: dividend_yields, legs, table";
  `test_scenario_rate_wiring.py` 5 passed (abc6ae54); guard+registry+money 39 passed; ruff ratchet OK. Mutants 1-5
  KILLED (builders' runs). Fail closed = generic 500 (INTERNAL_SYSTEM_002).
- step 7 relocation 7797a12c: T-19 engine tests moved to tests_app (tests/ must not import ofo_app; that import also
  broke `test_safety_checks` caplog in the full run); pure scenario test reads the generator's hand cost. Waiting on
  its Tier A review before merge.
- cross-session: the kit `verifier_inflight_gate` is machine-wide; any session's verifier blocks every session's git
  writes (GC-MU logged class verifier-guard-watches-every-worktree). Handled by waiting for the snapshot folder.
- decision (technical, 02:4x) wiring pattern for steps 3-5: registry.json holds every default (the only place the
  number is written); a pure `ofo/` function takes the value as an explicit parameter (no literal default); the app
  layer reads the settings once per request through `outcome.get_settings_reader` (background loops: at each tick)
  and passes values down; a list value is one scalar key per element and a per-index value one key per index
  (e.g. `scenarios.payoff_steps.1..4`, `scenarios.strangle_picks.nifty.1..4`), so the store stays scalar and each
  change is audited on its own. Steps 2 and 3 dispatched 02:4x (worktrees gcset-page, gcset-batch1 at 8be1e3ca).
- step 7 Tier A review: REVISE, 1 MAJOR (opportunities list draws a stored T-19 record without approach/cost, so
  "alert and Compare show the same figure" fails there) + 4 MINOR. Decisions: wording "cheapest adjustment that could
  be priced now (N could not be priced)" when an approach is unpriceable; one shared "offered now" filter (S-11);
  stronger label assertion. Not changed: generator reuses the engine's `charges_for_orders` (own tests) - documented
  as a shared dependency. Round 2 dispatched ~03:15.
- step 2 built 37d5da55 (re-run by me: `test_settings_route.py` 16 passed, vitest nav-shell + settings-page 28
  passed). Nav: "Settings" is an Account item at `/settings/app-settings` (the `/settings` path is the Account hub);
  REQ-009 AC-8 needs the 11th item (written at merge). Tier B: REVISE, 1 MAJOR (charge rate set `read_on` without
  upper bound: a mistyped future year would lock the append-only table) + MINORs (page sent the browser clock as
  "now"; no fraction hint on Charges). Round 2 dispatched ~03:10.
- step 3 built 8ba4c72b: 23 keys wired (SD horizon, payoff steps + default step, scenario columns per index, what-if
  span, strangle quick picks); silent fallback to defaults removed (functions REQUIRE values); reader guard
  `tests/test_settings_reader_guard.py`. Re-run by me: guard + wiring + registry 45 passed, ratchet OK; builder's DB
  runs: leg_edit 73, ready-made 10, range params 16, live push 40, order closure 13, calc wiring 1. SPLIT OUT as 3b:
  forward quality width / strikes near / minimum strikes (4 production callers + the snapshot compute-cache key need
  the values; did not fit round 2). `frontend/src/lib/readyMade.js` quick picks -> step 4 (frontend via GET
  /api/settings). Tier B review running.

## Found during the run

| # | Finding | Where | What was done |
|---|---|---|---|

## Parked

None yet.

## Steps

| Step | What | Done when (proof) | Review |
|---|---|---|---|
| 0 | Preflight per §0.2; re-grep every scan row (`docs/design/settings-scan-2026-10-31.md` A and B) at its file:line and record moved lines | §0.3 line: rows re-found N of N, moved lines listed | none |
| 1 (core) | Test and finish the WIP store: `tests_app/test_settings_store.py` (row present, no row -> default, future row not in force, unknown key ignored, out-of-range refused, append-only trigger refuses UPDATE/DELETE, downgrade refused with rows); wire `pricing.risk_free_rate` per request in `get_market_context` (`dataclasses.replace` of the context's rate); tests that save run in a rolled-back outer transaction (`join_transaction_mode="create_savepoint"`) | Core proof above passes on a throwaway DB; mutation test (max 5 mutants, scratch copy): removing the trigger or the range check fails a test | Tier A (fresh Opus, adversarial) |
| 2 | Routes `backend/ofo_app/routes/settings.py` (GET groups with value in force, default, effective_from, set_by, history; POST a value with effective time and note) behind ONE dependency `require_admin` (today: the single owner; docstring: becomes the admin role check when sign-in lands, REQ-167 AC-3); Charges group read from `charge_rates_store.rates_in_force` and "Add rate set" via `add_rate_set`; `frontend/src/pages/SettingsPage.vue` + route + nav entry "Settings" | Owner's Chrome, scenario ADJ-02: change risk-free 0.065 -> 0.07, the builder's Greeks move; type 6.5 -> refused "Enter 0.065 for 6.5%"; reset; add a brokerage rate set 20 -> 25 effective now -> the Compare's charges on ADJ-02 rise by the expected paisa (generator value), then add 20 back; audit log shows all four writes | Tier B |
| 3 | Move groups batch 1: Pricing rest (forward quality width, strikes near, min strikes), Scenarios and payoff (scenario columns, strangle quick picks, what-if span, payoff table steps and default, SD horizon) | One test per key: changing it changes the output it feeds; scan rows 4, 6, 16-19 have no literal left | Tier B |
| 4 | Batch 2: Limits (range pick-list cap and step, chain strikes each side, leg-picker widths, lot and history caps; frontend values served by GET /api/settings, the browser keeps no copy), Detection (feed stale, reconnect window), Speeds (live push interval, REQ-166), Data (max delist percent: the env var becomes the setting; freeze file stale after), Billing (trial and referral days), Undo windows (REQ-167 AC-7) | One test per key; scan rows 5, 7-10, 20-24 have no literal left | Tier B |
| 5 | Exchange and broker facts group (scan B: market hours and expiry close, paper settlement window, Kite session expiry, freeze units and batch, Zerodha rate and feed limits, quote limit, tick, stamp and SEBI caps (the migration-0014 DB caps become settings too), contract-list publish time), each with its source in the note; fix the captured-at-start gap: the paper monitor (`paper_monitor.py`, `feed.ctx.rate`) and the live chain socket re-read settings at their next tick | Test per key; a paper monitor test shows a rate change taking effect at the next tick without restart | Tier A (market hours, settlement and caps touch money and order splitting) |
| 6 | REQ-167 AC-6 guard: a test fails when a wired module holds a business literal again, and when a registry key has no reader (fails closed on shapes it cannot resolve) | Red-then-green self-test: re-adding `Decimal("0.065")` in `live_market.py` fails it | Tier B |
| 7 | ADR-221 + ADR-222 (8): one engine function for "this adjustment's cost"; the checker prices the current stage's approaches and T-19 uses the cheapest; `adjust_money.adjustment_cost` and `COST_PER_LEG` deleted; the flag line names the approach and cost | Scenario (new, via the generator) where premium left is below the cheapest cost fires T-19 and one above does not; a test holds the T-19 cost equal to the Compare cell for every scenario with approaches; class `one-money-figure-two-formulas` -> guarded; F-77 marked FIXED | Tier A |
| 8 | REQ-168 Preferences tab: migration `0033_user_adjustment_preferences` (append-only, keyed by user ref, same guard pattern), "Adjustment defaults" registry group (starting values: short delta weekly 0.30 / monthly 0.25, roll distances 200 / 500, iron fly min days 3, reduce divisor 2 from `approach_config.json`; near-level alert 0.5% from `detection.py:32`; gap-at-open until 09:30 from `playbook_eval.py:41`; Compare range +/-6%, 48 steps, moves +/-1% and +/-2% from `compare.py:87-89`); per-user read: user value else admin default in force; a Preferences tab on `AdjustmentsPage.vue` (value, "Your value" or "Default", admin default, change within range, reset to follow default); every read/write keyed by the user through one guard (today the owner) | Owner's Chrome, scenario ADJ-02: alert distance 0.5 -> 1.0 in Preferences makes a short 0.7% away flag at the next check, alert line names 1.0%; reset -> follows the admin default; admin changes the default to 0.6 -> the user who reset follows 0.6; a saved plan is unchanged | Tier A (per-user isolation) |
| 9 | REQ-169: system playbook versions (new table or version rows in the playbook store, append-only); "Edit system playbook" for the admin only, same editor and validation (REQ-160), Test before Save, required reason, audit row; "Restore this version" as a new version; approve a Draft system playbook; users' copies unchanged; strategies tracked on the system playbook get the new version at the next check | Owner's Chrome: admin edits PB-04 stop 50 -> 45 with reason, Test, Save -> version 2; a user copy keeps 50; restore version 1 -> version 3 = 50; approve a Draft playbook -> label gone | Tier A |
| 10 | Close: `python scripts/orchestrator/prepush.py --full` TOTAL PASS on the run head; merge `--no-ff` into LOCAL `feature/adjustments`; push `feature/adjustments` (fast-forward only, the prepush pass marker is for that head); handover `docs/process/session-handover-<date>-gcset.md`; memory note | Pass record for the head sha; `git ls-remote origin feature/adjustments` equals the local head; main unchanged; no PR | none |

## Failure budget and stops

- At most 2 fix rounds per step; a third red of the same class gets an independent reviewer (fresh context, different
  model) and a re-plan, then the owner is told as information; still red -> PARK the step (issue labelled `parked`
  via `scripts/orchestrator/gh_issue.py app ... --stage`, a `PARKED (#N)` line in §0.3) and continue with the next step
  that does not depend on it (steps 3-6 do not depend on each other; 8 depends on 1-2; 9 depends on 1-2 and 8's guard).
- Owner away: never call AskUserQuestion; a spec-conformant choice is decided and recorded (§0.3 decision line); any
  SPEC CHANGE or business fork goes to `docs/process/owner-questions-<date>.md` with a recommendation and the run
  continues. After 22:00 IST the project's night guard blocks question boxes anyway.
- Hard stops: any write to `main`; a PR; a Kite order or login; deleting data or history rows; editing a kit file
  (list in `.claude/kit/GUIDE.md`); changing a default value; a full DB suite on the shared host.
- Every Agent brief carries `Budget:`, `Report: evidence-table`, `Core:`/`Proof:` for new work, the
  `.claude/kit/builder-brief.md` standing items, and `model` (Sonnet for clear briefs, Opus only with a `Why Opus:`
  line for Tier A or fuzzy work).

## Definition of Done (every box, literally)

- [ ] Every scan row in group A (except row 1, deleted, and the test-only values) **reads its value from settings or
      preferences at run time, with no literal left in code**, each proven by a test that changes it and sees the
      output change.
- [ ] Every scan row in group B **is a setting in "Exchange and broker facts" with its source**, each tested.
- [ ] `COST_PER_LEG` and `adjust_money.adjustment_cost` **are deleted**; T-19 uses the cheapest approach's cost
      (ADR-221), proven on two generator scenarios.
- [ ] The Settings page, the Preferences tab and the system playbook editor **each pass their browser proof** in the
      owner's Chrome (steps 2, 8, 9), with screenshots named in §0.3.
- [ ] The REQ-167 AC-6 guard test **fails red on a re-added literal and passes green** (self-test recorded).
- [ ] Findings F-77 and F-78 marked FIXED with proof lines; the two finding classes set to `guarded`, with
      `knowledge/findings/INDEX.md` regenerated and the new text grepped in the index.
- [ ] `prepush.py --full` TOTAL PASS on the final head; merged into LOCAL `feature/adjustments`; `feature/adjustments`
      pushed; main untouched; no PR.
- [ ] Handover written (DONE / PENDING / BLOCKED / PARKED / NEXT) and the memory note updated.

## Final report (the run's last message)

An evidence table (claim | command run + result line) for every DoD box; parked steps with issue numbers; owner
questions written during the run; new user-facing texts pinned "pending owner read" (count); the next contract
(GC-ADJ3, `docs/process/goal-contract-GC-ADJ3-2026-11-01-DRAFT.md`: its step 1 is done by this run's step 7, and its
questions Q-ADJ3-2..5 are still open).

## Known facts the run must not re-discover

- No sign-in exists: the admin and the one user are both the owner today; one guard per kind (admin / user) is the
  choke point that sign-in will replace (REQ-167 AC-3, REQ-168 AC-3).
- The audit store requires READ COMMITTED; the WIP's `correlation_id` format was not checked against the audit
  table's rules - step 1 tests it.
- Rows in app_settings can never be deleted (trigger OF032): a test that commits leaves its row in the shared test DB
  and changes other tests - always roll back.
- Scenario and replay modes keep their own risk-free rate (test data, `scenario_mode.py:273`, `replay_mode.py:28`);
  they are not settings.
- `low_oi_blocked` has no live source (F-78); nothing in this run claims a strike is liquid live.
