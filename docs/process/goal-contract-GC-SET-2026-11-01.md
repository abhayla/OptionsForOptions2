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
- step 3 DONE 66f8738f (merge of 8ba4c72b). Tier B: no MAJOR; MINORs carried (round budget used): cross-field admin
  value surfaced as a user 422, `checked_choice` skipped on one branch, two store reads per request -> step 4a; guard
  gaps (aliases, module-level calls, reassignment) -> step 6.
- step 2 DONE 1fbda68b (merge of 29ab23a7): round 2 fixed the future `read_on` lock (store refuses a date after today
  IST), page sends no "now", fraction hint, brokerage cap Rs 1000 (input sanity, changes no figure). Re-run by me on
  the merged head: `test_settings_route.py` 24 passed, openapi drift 1 passed, pins+guards 108 passed, ratchet OK.
  REQ-009 AC-8 updated (d2d7235d). MY MISS: I merged without the full pure tree; the Rs 1000 cap broke
  `test_charges_in_sentences.py` (5000 brokerage); fixed 889d37bf. From now on: full pure tree on the merged head
  before the next merge. Browser proof for step 2 pending (needs the dev server, heavy slot).
- step 7 round 2 (6887e46c, 97303cff) + two older defects found on the check path (F-80 clock-time line, F-81 stage
  name with a space -> 500; class reply-type-refuses-real-value-shape, c9a295a6). Stage-name fix dispatched.
- steps 4a, 4b, 3b: every Sonnet batch builder hit its budget at about half (measured: 4a, 4b, 3b, 3 round 1).
  Round 2 sent to 4a and 4b; 3b committed by me 0bcf7a42 (core: 17 passed, cache-key test; guards 76 passed), Tier C
  finisher runs its DB files. Briefs from step 5 on: one group per builder.
- step 7 DONE db19f061 (merge of e78a65c5) ~04:10: stage name as catalogue text (F-81, 845f49db); real-data proof
  re-run by me: `test_adjustment_opportunities.py` 12 passed (ADJ-43 check 200: T-10b clock line + T-19 line naming
  A-28 and its cost; the list line equals the check), `test_adjustment_check.py` 8 passed, order closure 13 passed.
  Cause of the "T-19 not checked" red: the test had no charge rates (conftest default = none -> rightly not checked);
  the test now seeds the scenario library's rates. Pin conflict resolved as the union (828 pins, pin test 63 passed);
  openapi regenerated, drift 1 passed. S-11 filter wired for T-19 + generator, NOT in the Compare (the approaches route
  reads no playbook) -> recorded open.
- MISS (mine, second of the class "merged without the full pure tree"): full `tests` run on the merged head showed 8
  repo-guard failures from steps 1-3/7 (producer inventory, door names x2, history-not-shown on SettingsPage, repo_scan
  marks, underlying-tables scanner). Rule from now: a merge into build/settings needs a full pure `tests` pass on the
  candidate head first. Guard fixer dispatched (worktree gcset-guards at db19f061).
- step 4b 40b5accc (2 rounds): wired chain strikes each side (server + browser store `settingsValues.js`), Undo one
  leg 8 s, Undo Clear all 10 s (3 timers), history days 15; DB runs all green (price history 29, settings route 24,
  drift 1, leg picker 51, order closure 13). NOT wired, keys removed: range caps/step, leg-picker widths, multiplier/
  lot caps, strangle distances in readyMade.js -> item 4c. Decision for 4c: the server's own answer carries the
  choices it offers (leg-picker widths in the strikes answer, quick-pick distances in the ready-made answer), the
  browser shows what the server sent; range caps + lot caps via the settings store loaded in test setup.
- step 4a b66780c5 (2 rounds): live push / chain / index push interval, billing trial/referral days, freeze stale
  days, max delist percent (env var removed) wired; carried fixes a/b/c green (`test_settings_speeds_wiring.py` 10).
  NOT wired: feed stale/reconnect windows -> item 4d. Literal default 10 for delist left in two direct-call paths ->
  step 6's guard must catch it.
- integration DONE 4c029a29 (~04:50; build/settings fast-forwarded): 3b + 4a + 4b + guard fixes (99fc26dd: 9 repo
  guards incl. a selection pin, settings write routes classified in scenario mode - start in scenario mode had been
  refused since step 2 - and `history` -> `earlier_values`). Gate run by me on the candidate head 3c4b9233: full pure
  `tests` 8618 passed / 2 failed (forward.py getattr; settings count maths not on the non-money allow-list) -> fixed,
  affected files re-run 322 passed, ratchet OK (3728); DB: adjustment_check 8, scenario_mode 60, settings_route 24,
  settings_speeds_wiring 10, order closure 13 - all passed. The last small edits were NOT covered by a full-tree run
  (affected files only) - the close step's prepush --full covers them.
- dispatched ~04:55: step 8 backend (Opus, Tier A, from 3c4b9233, migration 0033), 4c (server-carried choices +
  range/lot caps), 5a (timing facts + paper monitor re-read per tick, Opus Tier A). Every brief now ends with a full
  pure `tests` run before the last commit. Still to dispatch: 4d (feed health windows), 5b (order/limit facts incl.
  migration-0014 caps), step 6 (AC-6 guard), step 8 UI, step 9, browser proofs 2/8/9, close.
- integration 2 (worktree gcset-int2, head 85fd0fa8, ~06:30) = 4c 5f3ca38e + 4e 524bc7b5 (incl. 5a c5210d3e) + step 8
  bc8869af + 5a-2 02071c13. Merge decisions: registry rebuilt as a keyed union each time (65 keys, no key differed);
  5a and step 8 had each built an HHMM time check -> ONE kept (5a's `time_of`, check, template, pin), step 8's copy
  removed, `hhmm_text` now calls `time_of`; 5a's "every time setting is a broker fact" test narrowed (gap-at-open is
  an adjustment default). Bug found by 5a-2: refusing ANY non-time setting answered 500 (the refusal eagerly built a
  time example) -> slots built only for a time key, regression test.
- step 8 backend: mutants a-e all KILLED by me on a scratch copy (guard removed 2 failed; user ref dropped 3; fallback
  to registry 1; reset as DELETE 1 (refused by the DB); trigger removed 3). Round 2: approaches route test had no DB
  (64 x 500) -> conftest default preferences reader; real-path tests marked `real_preferences`.
- 5a: wired paper settlement window + paper monitor / strategy / chain sockets re-read settings per tick; time unit
  HHMM. 5a-2: contract-list publish time, Kite session expiry (app computes expiry from started_at + setting; the DB
  trigger on broker_sessions still stamps 06:00 and that column is no longer judged -> a literal left in a migration,
  for step 6's guard / follow-up). NOT wired yet: market hours + expiry close (~14 modules incl. time-to-expiry
  maths) - the largest remaining item of group B.
- 4c: leg-picker widths + quick-pick distances carried in the strikes answer; range caps via the settings store.
  4e: one shared `check_lots` (outcome, live push, leg edit), schema keeps a type sanity bound; browser caps from the
  settings store. Open: 2 chain-page vitest files fail (mocks do not answer /settings) - the gate's vitest run checks.
- ~06:45 the integration-2 gate (9 DB files + full vitest) was KILLED by Claude Code for critically low memory (GC-MU
  builders run on the same PC). Claude Code's rule: restart only when the owner asks -> Q-GCSET-1 parked in
  `owner-questions-2026-11-01.md` (night guard blocks question boxes). Done before the kill on 85fd0fa8: full pure
  `tests` 8640 passed / 0 failed; drift x2; DB approaches route 64, check 8, opportunities 12. The run continued with
  light items only, one builder at a time, no DB suites in parallel.
- step 6 3ae95d06 (merged into int2): `tests/test_settings_literal_guard.py` (reader + literal checks, fails closed,
  self-tests; red on a re-added `LIVE_RATE = Decimal("0.065")` naming the file and line). KNOWN_LEFTOVERS listed and
  re-checked: unused `ofo/range/pick_lists.py`, delist default 10 in catalogue direct calls, 06:00 in the broker
  session trigger (migration 0007), market hours in `timeutil.py`, feed windows in `feed_health.py`.
- E501 rise from 5a-2 wrapped (ad01dee8). step 8 UI 3781782c (Preferences tab; re-run by me: vitest 36 passed).
- step 9 backend 4eec3818 (merged into int2): migration 0034 append-only versions, admin-only routes reusing the user
  editor's validation, Test before Save = the existing Test route, restore/approve as new versions, the checker reads
  the current version through one `playbook_store._current`. Builder's DB runs: new file 23, playbook store 40,
  adjustment check 8, scenario mode 60, drift 1. Mutants by me on a fresh scratch copy: guard removed KILLED (2
  failed), checker reads version 1 KILLED (2), restore without a new version KILLED (2); trigger first branch off =
  23 passed - EQUIVALENT (the same trigger's next check still refuses UPDATE/DELETE with OF034); the owner test checks
  the code, not which rule fired (noted, not chased). Editor buttons (Edit / Restore / Approve) = step 9 UI, next.
- BATCH 2 LANDED f2510f25 (10:02 IST from the commit time, merge of int2 48f15858): 4c, 4e, 5a, 5a-2, step 6, step 8 (backend + Preferences
  tab 3781782c), step 9 (backend + editor UI e87fdeab). Gate, run by me on the int2 head (owner: "Restart the gate",
  then "GC-MU finishes, then GC-SET"; the reaper killed 4 runs/waits before): DB one file at a time - user prefs 18,
  scenario mode 60, settings route 25, speeds 10, paper settlement 28 (one tunnel drop, re-run), chain live 83, leg
  edit 74, outcome 25, system playbooks 23, playbook store 40, playbook routes 18, check 8, opportunities 12, order
  closure 13 (after pinning the system_playbooks -> playbook_store edges, 33), approaches 64 (earlier run); full pure
  tree in chunks: 1804+2323+3599+860+64 passed after 2 fixes (step 9 used private names `_refused/_load/_dump` ->
  public `refused/load_body/dump_body`; system playbook test on the selection pin); full vitest 751+1077 passed after
  3 fixes (2 chain-page mocks did not answer GET /settings - from 4b; `settingsValues.js` added to the named-uses list
  with a reason per line). Heavy slot released before the merge; owner rule (same morning): GC-MU has priority on the PC. Leftovers 8fc06cbc (dead range/pick_lists.py deleted, max_delist_percent required; 2 KNOWN_LEFTOVERS rows closed; tests_app call sites compile-checked only - DB run in the batch 3 gate). 4d dispatched 10:1x (pure tests only).

- step 2 browser proof, Greeks check (2026-11-01 14:11 IST, new session): dev API PID 20988 + vite 5173 on ADJ-02,
  stored rate 0.07 in force (GET /api/settings: value 0.07, effective 08:12:11Z, set_by owner). Fresh page load shows
  Delta 0.45 / Theta 15.99 / IV 13.10% as at 0.065. NOT a defect (F-82): in-process outcome at 0.065 vs 0.07 moves
  `dividend_yields` 9 Nov -0.0000115 -> 0.0050063 and per-unit Theta 15.988 -> 15.987 only; the parity forward absorbs
  the rate into q (ADR-063). Live server proof: reset to default 14:12 -> q -0.0000115; 0.07 set again 14:14 -> q
  0.0050063 (3 of 3 fresh requests, no restart); reset 14:15 -> q -0.0000115 (4 rows kept, none deleted). An earlier
  0.0048023 page capture did not reproduce (unexplained, noted in F-82). No code change. Screenshot
  `C:\Users\itsab\AppData\Local\Temp\claude-chrome-screenshots-0Oemv3\screenshot-1793522547938-3.jpg` (reset row).

- step 2 browser proof, Compare (14:2x-14:4x IST): defect found and fixed (F-83, class
  one-shot-feed-loses-quote-on-shared-unsubscribe, guarded): scenario mode dropped every contract's price after a
  builder socket released (fan-out unsubscribed under the scenario; one-shot frame never re-sent). Fix in
  `scenario_mode.overrides` (scenario hold on the fan-out); new test red "82 of 82 scenario contracts lost their price"
  -> green, `test_scenario_mode.py` 61 passed (db_run_fresh), ruff ratchet OK. DB tunnel dropped once at ~14:32 and was
  back (ssh PID 18168, not started by this session) before the run.

## Found during the run

| # | Finding | Where | What was done |
|---|---|---|---|

## Parked

- Owner decision 2026-11-01 ~08:05 IST (chat: "Go with your recommended option A"): this run finishes the gate, step 9
  UI, 4d feed-health windows, the guard's leftovers, the three browser proofs, F-77/F-78 marking and the close; it
  PARKS to a follow-up contract (issue at close, label `parked`):
  - market hours and expiry close (`ofo/timeutil.py`, about 14 modules incl. time-to-expiry in the pricing maths;
    Tier A);
  - step 5b, order and limit facts: freeze units and batch, Zerodha rate and feed limits, quote limit, tick, stamp
    and SEBI caps incl. the migration-0014 DB caps (Tier A).
  The DoD box "Every scan row in group B is a setting" stays OPEN and is reported as parked; 4 of the group B facts
  (paper settlement window, contract-list publish time, Kite session expiry, plus the per-tick rate re-read) are done.

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
