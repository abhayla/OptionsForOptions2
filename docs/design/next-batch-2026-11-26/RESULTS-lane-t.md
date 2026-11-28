STATUS 23:25 IST LINK TEST: T: reply works (the send_message tool is refused with elevated_session_untrusted_device, so this line is the reply). Your items: alembic-free test fix DONE (5342dcb2c); CI frontend job DONE (5342dcb2c: 1956 Playwright tests vs 282, 75 fail twice, timeout 25 -> 40); flaky feed-control DONE and pushed d8cb91df1 (the fakeredis stand-in drops a ~30 KB XRANGE reply under load; read in pages; 12 of 12 green under load, was 5 of 8 red; TOTAL PASS 1046.4s); test_exit_door no_deadlock (before_claim, before_place): both PASS on origin build a1d704225 (paper_alerts exists; no migration on any origin branch touches it; CI runs the file, no marker hides it: the server job is -m "not full_chain" and these have none), I cannot reproduce: send me Lane R1's head commit; W-07 and W-35: not started, waiting for the commit you name after wave 1. Also closed: I-204 (5 passed on the build), I-168 (green on B3's branch ecf8e8f99). Nothing unpushed except this line; no check running.

# RESULTS: Lane T (test-only gaps and tooling)

Spec basis: ADR-016 to ADR-019; ADR-330 (45) to (72); completion plan 2026-11-28 section 1, rows I-184, I-126, I-204, I-168, I-170, I-176.

Set-up note (not a test change): the cloud container's database `ofo_test` had no schema, so every DB test failed with
`relation "public.catalogue_contracts" does not exist` (9 of 10 in the I-184 file, 4 of 13 in the I-126 file). Fixed by
`python scripts/orchestrator/db_run.py . python -m alembic -c backend/ofo_app/alembic.ini upgrade head` once. Every count
below is after that step, with `OFO_TEST_DB_PER_FILE=1` and the proxy variables unset.

## Items

| Item | Real case (from the plan) | Before | After | Commit |
|---|---|---|---|---|
| I-184 | "Three stale xfail strict markers in tests_app/test_slow_price_source_live_day.py" | grep of `xfail|strict` on the build head: nothing | 10 passed (file alone) | none needed (already clean) |
| I-126 | "Two plan-watch tests read the real clock and fail Friday after 15:00" | pins 8ed916db, cdce22ce are ancestors of the build | `tests_app/test_plan_watch.py` 13 passed; the two pinned tests are `test_a_hanging_market_read_is_cut_at_the_budget_and_answers_not_live` and `test_a_quote_answering_after_the_market_was_cut_is_not_asked` (they call `_pin_server_clock`) | none needed |
| I-204 | "Three FE2 DB tests fail on the merged build (F-39)" | build e2da71f50: 3 failed, 2 passed (`real_position_exit_refused`) | fix branch origin/fix/r3-leftovers-1128 (951aa698c, worktree, removed after): 5 passed. Build re-run after wave 0 (a1d704225, worktree, removed after): 5 passed. CLOSED | none (fix is a5259db50, now on the build) |
| I-168 | "Pool-not-held plan-watch tests fail on the unmodified build; test_d36 assumes a fresh database" | first pass (under load, DB behind head): `test_pool_not_held_across_market_wait.py` 3 failed | alone on the r3 build with a database at head: `test_pool_not_held_across_market_wait.py` 5 passed, `test_d36_adjustment_counts.py` 6 passed. On origin/fix/r3-backend-b3-1128 (ecf8e8f99, with I-48 cut 2; worktree, removed after): `test_pool_not_held_across_market_wait.py` 5 passed, `test_d36_adjustment_counts.py` 6 passed. CLOSED on both heads; B3's branch is not in the build yet, so no re-run on the build | none (no test change needed) |
| CI-1 (coordinator, front of queue) | CI pull 881, job domain-tests, commit a1d70422: `tests/test_alert_kinds.py::test_the_migration_copies_the_table` ModuleNotFoundError: No module named 'alembic' | clean venv (pyyaml, jsonschema, pytest, mypy only): 1 failed, 12 passed | same venv: 13 passed; mutation (an extra answer in the 0054 literal) makes it fail, so the guard still runs; ruff clean | see git log |
| I-170 | "27 DB tests in 12 files fail on a clean run" | 18 files, 28 tests failed (511 files run one by one, `OFO_TEST_DB_PER_FILE=1`, while the pre-push check used the machine) | the same 18 files alone, database at head 0062: 0 failed, 249 passed | none (no test change needed) |
| I-176 | "11 of 29 failing tests never named" | all 28 failures named below (`-rf`) | 0 unnamed, 0 failing | none |

## Closing evidence

| Item | Claim | Evidence (command run this turn, result) |
|---|---|---|
| I-184 | no xfail/strict marker | `git grep -n -E "xfail|strict" origin/integration/weekend-r3-1129 -- tests_app/test_slow_price_source_live_day.py` prints nothing (exit 1); pytest on the file: `10 passed` |
| I-126 | clock pins on the build, both tests green | `git merge-base --is-ancestor 8ed916db origin/integration/weekend-r3-1129` and the same for cdce22ce: both true; `tests_app/test_plan_watch.py`: `13 passed` (run on Saturday 28 Nov 18:5x IST; the pin makes the result day-independent, see `CLOCK_PIN` in the file). Not proven by a command: a run on a real Friday after 15:00 |
| I-110 | issues 854 to 880 filed (27) | `gh issue list` is refused here (GraphQL blocked); REST instead: `gh api -X GET repos/abhayla/optionsforoptions2/issues -f state=all -f per_page=100 -f page=1..3`, non-PR numbers between 854 and 880: 27, first 854, last 880 |
| I-109 | AX-01 to AX-14 are in the plan | `git show origin/docs/test-plan-weekend-1127:docs/process/test-plan-weekend-2026-11-28.md \| grep -o -E "AX-[0-9]+" \| sort -u` lists AX-01 to AX-14 (14 ids); AX-14 row at line 246 and section 14 intake table at lines 1681 to 1690 (AX-08 to AX-12 appear as one range row "not built") |
| I-96 | Alerts Active and History rows are in the plan | same file: `grep -n -i alerts` finds rows W-13 (line 199, History "Closed by system"), W-17 (line 203, Active on a slow connection) and SW-8 (line 255, Alerts Active, History, Records block). The slow-link half is "not proven by a command" (the plan itself says the real link time is proven only by the PC) |

## Same class search (CI-1)

`grep -rln "alembic" tests/ | xargs grep -ln "exec_module\|import_module\|from alembic\|import alembic"` hits: test_prepush.py (105 passed), test_door_names_private.py (301 passed), test_history_not_shown.py (56 passed), test_alert_writers_one_caller.py (13 passed), test_alert_kinds.py (fixed). All run in /tmp/ci-like (only pyyaml, jsonschema, pytest, mypy). Wider search for tests naming `alembic/versions`: 8 more files, 129 passed, 1 skipped in the same environment. No other test needs a fix. The fix reads KINDS and ANSWERS by `ast.literal_eval` of the module-level assignments; no importorskip.

## CI-2: the "frontend" job of app-tests.yml cancelled at 25 minutes (pull 881, commit a1d70422, run 46155059897)

Measured from the job's own step times (gh api actions runs and jobs) and its log, compared with two green runs of the same job:

| Step | cancelled run a1d70422 | green run a0e6fee1 | green run cf31e8d4 |
|---|---|---|---|
| migrations | 1:55 | 0:38 | 0:58 |
| lint and unit tests | 5:22 (398 files, 4265 tests: local count) | 1:48 (222 files, 2605 tests) | 2:48 |
| build to server start | 0:35 | 0:35 | 0:35 |
| Playwright | cancelled after 16:32, 980 of 1956 tests done | 2:45, 282 tests | 3:59, 282 tests |
| whole job | 25:19 (limit 25) | 6:54 | 9:20 |

Findings:
1. **Not a hang, not a watch mode.** The step was still finishing tests (about 60 per minute) when the 25-minute limit cancelled the job.
2. **The Playwright suite grew 7 times.** The 26 Nov screen suite (8 `screen-*.spec.ts` files, from the push-5 tree) is on the round 3 build and not on main (main has 33 files in frontend/e2e, the build 44): `npx playwright test --list` on the build prints `Total: 1956 tests in 34 files`. The job was sized for 282.
3. **75 tests fail on both attempts** (CI retries once; none passed on the retry): screen-alerts 20, screen-live-strategies 20, screen-home 13, screen-builder-legs 7, screen-positions 6, screen-my-strategies 5, positions 2, index-view 1, my-strategies 1. A failing attempt costs about 7.9 s (the 5 s expect timeout plus page work) against 0.69 s for a passing one: the 156 failed attempts used 1226 s of the 1792 s of measured test time (68 percent). Reproduced locally on the build: `CI=1 npx playwright test e2e/screen-alerts.spec.ts` with a preview on 4175: 40 failed attempts-lines, 70 passed, 4.2 min; the first failures read `getByTestId('alerts-empty')` / `alerts-attention` / `alerts-earlier-heading` not found, so the spec's expectations drifted from the Alerts page after 26 Nov (a test-side drift, not a hang).
4. **With every test passing** the same rate gives about 11 to 12 minutes for Playwright, so about 21 minutes for the job on a healthy runner. The cancelled runner was also 2 to 3 times slower in the other steps, so 25 minutes was too thin even then.

Decided: only the frontend job's `timeout-minutes` line in .github/workflows/app-tests.yml, 25 to 40 (the coordinator allowed this line, ci.yml untouched). The raise alone would not make the job green: the 75 failing screen-suite tests must be fixed or re-pinned by the lane that owns frontend/e2e (outside my edit list; screen-alerts first, 20 tests). Measured, not guessed: ~21 min healthy, ~42 min if the failures stay.

Suggested (not done): a `timeout-minutes: 15` on the Playwright step itself so a slow step ends red with its log instead of a cancelled job with none.

## FLAKE-1: tests_app/test_feed_control.py "load-flaky" (coordinator's item)

- **Which test:** `test_no_token_or_fingerprint_is_on_the_bus_or_in_any_log_line`. Alone on a quiet machine: 16 passed in 18.7 s. With six busy-loop processes on 4 CPUs: the file failed in 2 of 3 runs; the one test alone failed in 5 of 8 runs, always at the same line (the `xrange` of the whole ticks and control streams): `redis.exceptions.ConnectionError: Connection closed by server` after `IncompleteReadError: 10365 bytes read on a total of 27972 expected bytes` (other runs 28761 of 30914, 32261 of 32588).
- **Why it depends on load:** with REDIS_URL unset (a lane's machine, the pre-push check) the `redis_url` fixture serves the bus from fakeredis `TcpFakeServer`, a pure-Python server on a non-blocking socket; one reply of about 30 KB is cut part-way when the machine is busy and the client reads slowly. CI uses a real `redis:7` service and is not exposed. Not shared state between tests, not a sleep, not a product timing fault: no product file to name for Lane B1b.
- **Fix (test side):** a helper `_read_whole_stream` reads the stream 10 entries at a time (exclusive `(id` start) so no reply is large; the secret scan over the same entries is unchanged. Checked equal to a single `XRANGE` for 0, 1, 10, 11 and 250 entries on the stand-in.
- **Proof:** same load, the same single test: 12 of 12 passed (before: 5 of 8 failed). Ruff clean.
- **Same class:** other tests that read a whole stream without a count (`test_broker_disconnect`, `test_bus_socket`, `test_feed_process_boundary`, `test_feed_user_isolation`) run 3 times each under the same load: 12 of 12 passed, so they are not changed. Their reads are small; if one of them ever shows the same error, use the same helper.

## For Lane Z3

(New `*_t_1128.py` files: none so far.)

## I-170 / I-176: the named list and causes

22 tests in 15 files: `function public.expire_order_request_keys() does not exist`. The test database sat at migration 0061; my merge of the build brought 0062, so every downgrade-then-upgrade round trip ran `DROP FUNCTION` on a function that was never created. Files (tests): test_migration_0028_paper_orders (1), _0030_paper_settle_zero (1), _0031_adjustment_playbooks (1), _0043_scenario_marker (2), _0044_s06_carry_gap (2), _0045_rule_state_marker (1), _0052_held_entries (1), _0057_history_delete_entries (1), _0059_last_close (1), test_migration_actionable_alerts (1), test_migration_several_standard_playbooks (1), test_order_book_migration (1), test_reconciliation_store (1), test_strategy_closed_status (1), test_strategy_followups (1), test_strategy_planned_entry (1), and test_order_request_key_durable_fd3 (3, the same missing function). A further 3 tests in test_pool_not_held_across_market_wait failed on timing under load and pass alone. Fixed by `alembic upgrade head` on the test database, not by a test edit. Skip-only files (not failures): test_check_failed_fe3_1128 (3), test_execute_replay_api (1), test_index_leg_save (1), test_report_atomic_fe3_1128 (9); the files give "no Redis here" or "the test catalogue holds no INDEX row".

Suggested tooling fix (scripts/ and tests_app/conftest.py are outside this lane's edit list): the per-file clone should fail fast with one line "test database at <rev>, code head <rev>: run alembic upgrade head" instead of 18 files of a misleading SQL error.

## Product causes found

None. No product code was at fault in any run.

## Decided for the owner

- Ran `alembic upgrade head` on the container's own throwaway test database to get a schema; no file, no product code touched.

- Friction row for the coordinator (I1; this lane may not edit docs/process/friction-log.md): "Cloud test database `ofo_test` has no schema at session start: every DB test fails with `relation public.catalogue_contracts does not exist` until `db_run.py . python -m alembic -c backend/ofo_app/alembic.ini upgrade head` is run; a 60 min foreground run of all tests_app was killed at 62 percent by the default background limit. Fix to recommend: cloud_services.sh migrates ofo_test, and the lane brief gives the 7200000 ms limit for a full tests_app run." Status: new.

## Not done

- Coordinator messages (send_message to the parent) are refused: "elevated_session_untrusted_device"; the remedy is an owner card (confirm_repository_trust) that also limits this session to trusted devices for good, so it was not raised unasked. Status goes through this file and the push line.
- Nothing open in items 1 to 6 except re-running I-168 on the build once Lane B3 is merged (green on B3's branch already).

SAFE TO CLOSE: no (items 4 to 6 open)


---

# Earlier file of the same name (26 Nov 2026, screen-suite lane; kept unchanged below, headings demoted one level)

## Lane T: screen-by-screen browser tests (26 Nov 2026)

Branch `test/screen-suite-1126` from `feat/nb-screens-w2-1126` a9bd41a. Tests, helpers and docs only; no product
code, no spec rows, no migration. Owner evidence: comment 7184365037 on PR #722 (26 Nov screen test).

### Status

| Screen | Spec file | Tests (x2 viewports) | Expected-fail (ids) | New findings | Pushed head |
|---|---|---|---|---|---|
| Core proof (Home row 2 > builder) | `frontend/e2e/screen-home.spec.ts` | 1 | 0 | 0 | 57508da |
| Home | `frontend/e2e/screen-home.spec.ts` | 79 | 5 (N-18 x2, NEW-T01, NEW-T02, NEW-T03) | 3 | 7c90919 |
| Coverage guard | `frontend/tests/screen-inventory-guard.test.js` (vitest, runs in `npm run test:run`) | 1 | 0 | 0 | 2796b56 |
| My Strategies | `frontend/e2e/screen-my-strategies.spec.ts` | 100 (LIST-9 mobile only) | 2 (NEW-T10, NEW-T11) | 2 | a6ed1c6 |
| Current positions | `frontend/e2e/screen-positions.spec.ts` | 142 (stable: 568 passed with `--repeat-each 2`) | 6 (NEW-T20, NEW-T21/N-05, NEW-T22/N-04, NEW-T23, NEW-T24, N-01) | 5 | 4d9cbaa |
| Live Strategies, Adjustment opportunities, Adjustments (playbooks, settings, system admin) | `frontend/e2e/screen-live-strategies.spec.ts` (+ `e2e/support/live-card-stub.ts`) | 130 (stable: 520 passed with `--repeat-each 2`; round 2 fixed a race in LINK-11) | 2 (N-14, NEW-T31) | 2 (NEW-T31, NEW-T32 observation) | 433f60c |
| Option Chain | `frontend/e2e/screen-option-chain.spec.ts` | 105 (stable: 630 passed with `--repeat-each 3`) | 3 (NEW-T40, NEW-T41, row 12) | 2 | 247bcfd |
| Strategy Builder part A (legs table, leg door, figures, Drafts Mode edits, Review and add, Exit) | `frontend/e2e/screen-builder-legs.spec.ts` | 90 (stable: 540 passed with `--repeat-each 3`) | 10 (row 12, N-04, N-05, N-07, NEW-T50, NEW-T51, NEW-T52 x3, NEW-T53 phone) | 4 | c32fd04 |
| Strategy Builder part B (Drafts Mode, leave and replace questions, Save / Save As / Rename, saved list, history, drawers, load states) | `frontend/e2e/screen-builder-drafts.spec.ts` | 131 (stable: 786 passed with `--repeat-each 3`) | 12 (row 12 x2, NEW-T60..T68; NEW-T68 phone only) | 9 | 8c6ca7e |
| Alerts (Active, History, Notification settings) and the 15 unbuilt placeholder pages | `frontend/e2e/screen-alerts.spec.ts` | 55 (stable: 330 passed with `--repeat-each 3`) | 1 (N-14) | 2 observations (NEW-T70, NEW-T71) | 3aa98cc |
| Live-socket guard fix (REQ-133 AC-2) | chain spec no longer routes the strategy live socket; `live-card-stub.ts` pushes stamped; guard EXPECTED lists the stub | - | - | - | acbadd2 |
| Socket stand-in guard fix | chain spec records socket hosts with `page.on('websocket')`, no regex route | - | - | - | 4197832 |
| Inventory Covered-by column after the suites | `screen-inventory.md` | - | - | - | a71b1f7 |

Core proof: the row-2 test failed under one mutation (`HomeOverviewPage.vue` row link pinned to row 1: "Expected
/strategy\/builder\?strategy=7$/ Received .../strategy/builder?strategy=12") and passed again after the revert.

How the suite runs: built app on `vite preview` (port 4175, `OFO_API_TARGET=http://127.0.0.1:9`) with `page.route`
stubs, the way the existing `home.spec.ts` runs; `PW_CHROMIUM_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome
npx playwright test e2e/screen-home.spec.ts --trace off` from `frontend/`. The real-backend mode CI uses (Postgres 16,
migrated, 2026-10-08 catalogue seeded, uvicorn 8000-8002, previews 4173-4176) also works in this container.

### Totals

| Measure | Value |
|---|---|
| Routes / pages in the inventory | 55 route entries, 47 pages (15 unbuilt placeholders) |
| Controls in the inventory | 446 |
| Covered before Lane T (9de2c9b) | 279 |
| Covered after Lane T (a71b1f7) | 348 (+69) |
| Not covered after | 98 |
| Spec-silent controls | 30 (question Q9 in `owner-questions-lane-t.md`) |
| New Lane T tests (per viewport; each runs at 390 and 1280 px) | 832 (Home 79, My Strategies 100, Current positions 142, Live and Adjustments 130, Option Chain 105, Builder A 90, Builder B 131, Alerts and placeholders 55) plus the inventory guard (vitest) |
| Expected-fail tests (written to the spec; today's code fails) | see the per-screen table; each proved once to fail for its stated reason |
| New findings | 29 (NEW-T01..T03, T10, T11, T20..T24, T31, T32, T40, T41, T50..T53, T60..T68, T70, T71) |
| Owner findings pinned as tests | row 12, N-01, N-04, N-05, N-07, N-13 (as NEW-T65), N-14, N-18 (R-06) |

Coverage per section, covered/not covered, before to after (unchanged sections omitted): SHARED 26/18 to 36/8; HOME
6/1 to 7/0; PLACE 0/1 to 1/0; MYSTR 13/1 to 14/0; BUILD 107/89 to 143/53; LIVE 4/2 to 6/0; ADJ 36/30 to 47/19; ADJOPP
3/2 to 5/0; CHAIN 18/5 to 23/0. The 98 rows still NONE are listed by id in `screen-inventory.md`; most are the
builder's payoff chart, adjustment drawer, plan editor and target sliders (BUILD), the Adjustments plan-edit form
(ADJ-38..45), the Settings page (SET) and the landing page (LAND), none of which were on this lane's screen list.

"Covered before" (279) was measured by a script plus a read of about 10 hits, so it is generous; each "after" row was
checked against the test body.

### Gate notes (for the next lane)

- Two repo guards run in the prepush preflight and are not in `ci_local.py`: `tests/test_e2e_live_socket_fakes.py`
  (every push on the strategy live socket stamped with `echoSeq`; its `EXPECTED` map lists every file that routes that
  socket) and `tests/test_e2e_socket_standins.py` (every `routeWebSocket` URL a plain string literal). Lane T's second
  and third prepush runs failed on them (an unstamped push in `live-card-stub.ts`; the chain spec's catch-all regex
  route); fixed in acbadd2 and 4197832. Run `pytest tests -m repo_scan` once before prepush when adding e2e socket stubs.
- The push hook checks the checked-out HEAD, so a gated older commit cannot be pushed once HEAD has moved on.

### Findings (product defects; steps, spec, actual)

| Id | Screen | Steps | Expected (spec) | Actual | Test | Screenshot |
|---|---|---|---|---|---|---|
| N-18 (owner R-06) | Home | Open Home with paper totals `+13,410.44` after charges; read the Total P&L tile name | "Total P&L (after charges)" (REQ-109 AC-10, ADR-320 (6)) | "(after charges) (after charges)", no name; same with "(before charges)" | `R-06 / N-18`, `FIG-2` | `frontend/test-results/lane-t/N-18-1280.png`, `N-18-before-1280.png` |
| NEW-T01 | Home | Open Home with no strategies | "Welcome, [Name]" and the 7-day Pro trial status with end date (REQ-008 AC-3) | Neither line; the code defers it to sign-in (row #433, Stage 5) | `STATE-3` | `NEW-T01-1280.png` |
| NEW-T02 | Home | Paper list answers `prices_not_live` with `totals_as_of` 10:00 IST | "Paper P&L paused - prices not live, as of 26 Nov 2026, 10:00:00 IST" (REQ-109 AC-5) | Sentence without the as-of time | `STALE-2` | `NEW-T02-1280.png` |
| NEW-T03 | Home | Paper list answers 500 or paused | Tile keeps the name "Total P&L" with "—" | Name is empty: `pnlFigure` returns `label: ''` and overrides it (same code path as N-18) | `STALE-3` | `NEW-T03-1280.png` |

| NEW-T10 | My Strategies | Rename on any row, type, press Escape | Esc cancels the rename (inventory MYSTR-11; owner R-05 left Escape unverified). Spec text is silent on Escape: question for the coordinator | The rename box stays open | `RENAME-5` | `NEW-T10-1280.png` |
| NEW-T11 | My Strategies | `GET /strategies` answers 200 with an unreadable body (proxy HTML page) | Fail closed: "Could not load your strategies. Nothing was changed." with Retry (ADR-330 S-05, REQ-065) | Read as an empty list: shows "You have no saved strategies yet..." and no Retry | `LOAD-4` | `NEW-T11-1280.png` |

| NEW-T20 | Current positions | `GET /positions` answers 200 `{unexpected:true}`; open Current positions | Unreadable answer shows the failure message, never an empty or blank section (REQ-044 AC-3, ADR-008) | Real section shows no failure message | `REAL-14` | `NEW-T20-1280.png` |
| NEW-T21 (owner N-05) | Current positions | Paper P&L > Exit after a failed re-read (Exit disabled) | A blocked action looks disabled (owner N-05, ADR-328 (4)) | Disabled and enabled Exit have identical computed opacity, colour, background, border | `EXIT-20` | `NEW-T21-1280.png` |
| NEW-T22 (owner N-04) | Current positions | Tick a leg, open Exit, let the re-read fail (dialog closes itself), let prices return | Nothing staged is left when the page closes the dialog (owner N-04) | Tick stays; "Exit (1)" enabled again | `EXIT-21` | `NEW-T22-1280.png` |
| NEW-T23 | Current positions | First `GET /paper/strategies` answers 500 | Paper total shows the same paused reason as the list (ADR-330 (10)) | Dash with no reason line | `TOT-11` | `NEW-T23-1280.png` |
| NEW-T24 | Current positions | `GET /positions` 500, then `GET /broker/status` answers non-JSON | Unreadable status is a failed read, not "not connected" (REQ-015 AC-10; PositionsPage's own rule); AC-10 is ambiguous: question | `data-state=not_connected` | `REAL-13` | `NEW-T24-1280.png` |
| N-01 (owner) | Current positions | Stops: save a refused level, wait for the next good list re-read | The "Not saved:" refusal line stays (owner N-01) | Cleared by the next re-read | `STOP-11` | - |

| N-14 (owner) | Live Strategies | Two Running paper trades both named "Short Iron Condor" | The two cards can be told apart (owner N-14; REQ-134 AC-1 allows shared names, silent on telling cards apart) | Identical headers "Short Iron Condor, NIFTY" on both viewports | `LINK-11` | `N-14-1280.png` |
| NEW-T31 | Adjustment opportunities | Inbox answers 200 with `<html>gateway</html>`; open /positions/adjustment-opportunities | Unread inbox shows the neutral four-part error (REQ-065, REQ-162) | Empty inbox "Showing 0-0 of 0 rows", no error | `OPP-15` | `NEW-T31-1280.png` |
| NEW-T32 (observation) | Adjustment opportunities | A dismissed outcome with a detail | Outcome and detail are separate words | DOM text "You dismissed thisNot relevant" (CSS margin only; a screen reader reads one word) | `OPP-1`, `OPP-5` (match with `\s*`) | - |

| row 12 (owner) | Option Chain / Builder | Builder `?strategy=63` (paper), remove one leg ("1 pending change"), Market link, browser Back | The pending change is still there (owner check 12, ADR-329 (1)) | "0 pending changes": `StrategyBuilderPage.vue:135` runs `builderHold.clear()` whenever the URL has `strategy=`, so Back drops the held edit. The vitest round trip `chain-trip-adr329.test.js` passes only because it returns with `router.push` to a URL without `strategy=` | `ROW-12` | `row-12-after-back-1280.png` |
| NEW-T40 | Option Chain | Open the chain; read the Expiry selector | Dates read "1 Dec (5 days)", never raw ISO (REQ-148 AC-2 names builder legs; applies to the chain? question) | Options "2026-12-01", "2026-12-08", "2026-12-29" | `CHAIN-02 expiry dates...` | `NEW-T40-1280.png` |
| NEW-T41 | Option Chain | Tick 25150 CE, press Buy; read Selected Legs | "NIFTY 1 Dec 25150 CE", as the builder names it (REQ-029 AC-10, REQ-148 AC-2) | "NIFTY 2026-12-01 25150.00 CE", also in the Remove button's accessible name | `CHAIN-NAMES...` | `NEW-T41-1280.png` |

| N-04 (owner) | Builder | Paper trade, stage an Exit, let the book read fail (page closes the Exit list) | Nothing staged remains (owner N-04) | The staged exit stays | `PP-22` | `N-04-1280.png` |
| N-05 (owner) | Builder | Exit staged, book unreadable | Review and add looks and acts blocked (owner N-05, ADR-328 (4)) | Enabled; does nothing when pressed | `PP-20` | `N-05-1280.png` |
| N-07 (owner) | Builder | Paper trade 63: compare the P&L Table tab with Net Positions for one contract | One price for one contract (ADR-008 one engine) | P&L Table 39.15 (outcome LTP) vs Net Positions 41.00 (paper book LTP) | `PP-24` | `N-07-1280.png` |
| NEW-T50 | Builder | Draft of 4 legs, trash on row 2 | Removal is immediate with a short Undo (REQ-030 AC-15) | No Undo (only Clear all has one) | `LT-18` | `NEW-T50-1280.png` |
| NEW-T51 | Builder | Add/Edit > "Pick from Option Chain" in the picker footer | The chain is reachable from the builder (REQ-029 AC-5, REQ-076 AC-10); may be by design (W-195 note): question | Only switches the strike table to the LTP view; URL stays /strategy/builder | `PK-14` | `NEW-T51-1280.png` |
| NEW-T52 | Builder | Draft with SELL 22800 CE; Add/Edit, pick SELL 22800 CE, Done | "Already in this strategy" question answerable by Increase quantity / Keep separate / Cancel (ADR-328 (1), REQ-030 AC-12) | Question renders under the drawer overlay; no button can be clicked; only Escape answers | `ED-5b`, `ED-6`, `ED-7` | `NEW-T52-1280.png` |
| NEW-T53 / NEW-T68 | Builder | Phone 390 px, open Add/Edit, look for "Show Editor >>" | A way back from the full-screen drawer (BUILD-15; spec silent, question) | The 520 px drawer pushes the edge tab to x=520, off screen | `PK-13`, `DR-2`, `DR-3` (mobile only) | `NEW-T53-390.png` |
| NEW-T60 | Builder | Open ?strategy=7, remove a leg, reload | The unsaved change survives a reload (REQ-154 AC-1); conflicts with ADR-329's note: question | Builder empty | `LV-14` | `NEW-T60-1280.png` |
| NEW-T61 | Builder | Rename, empty name, Save | "Give the strategy a name" (REQ-134 AC-1) | "The strategy has no name." (catalogue `strategy_name_empty`) | `SV-21` | - |
| NEW-T62 | Builder | Open Settings | The REQ-138 AC-1 settings list | Only "Show legs as" | `MN-7` | - |
| NEW-T63 | Builder | Settings > Quantity, reload | The choice is kept (REQ-138 AC-2) | Back to Lots; no settings write sent | `MN-8` | - |
| NEW-T64 | Builder | Saved tab, search "zzz" | "No saved strategy matches zzz" (REQ-134 AC-4) | "No saved strategy matches." (`noMatchText` in saveDraft.js unused) | `SL-11` | - |
| NEW-T65 (owner N-13) | Builder | Open ?strategy=7 with a slow read | No "No draft strategy is open" while reading (owner N-13) | Shown for the whole read | `ST-1` | - |
| NEW-T66 | Builder | Open ?strategy=999 (deleted) | Wording that says not found (spec silent on the words: question) | Neutral "The page could not get an answer from the server." blames the connection | `ST-4` | - |
| NEW-T67 | Builder | Saved tab, pencil on a row that is not open | The rename dialog opens (REQ-134 AC-3) | The strategy opens, no dialog: `renameRow` clears `pendingRename` before the async open sets `current.id` | `SL-18` | - |

| N-14 (owner, alerts) | Alerts | Active list with stops from trades 172 and 175, both named "Short Iron Condor" | The two can be told apart (owner N-14, R-07) | Both print "Short Iron Condor", no trade number | `ACT-17` | `NEW-T70-alerts-1280.png` |
| NEW-T70 (observation) | Orders placeholder | Open /orders | Orders is the user's Zerodha orders, import and funds view (REQ-009 AC-5, ADR-160) | Note still reads "Strategy-linked orders only. There is no order-entry form." (nav.js) | `PH-ORD` (pins the part still true) | - |
| NEW-T71 (observation) | Placeholders | Open any placeholder, e.g. /home/important-alerts | Empty state names what is coming (ADR-193 (4)) | Message "This page is a placeholder. It is built in a later work item." is developer wording shown to a trader | `PH x15` | - |

Screenshots are written by the tests to `frontend/test-results/lane-t/` (gitignored; regenerated on each run).

### Coverage guard

`screen-inventory-guard.test.js` rebuilds the inventory from the router and the `.vue` templates and fails, naming
file:line and label, when a route or control has no row in `screen-inventory.json`, or a row's control is gone.
Matching is on source file + kind + testid-or-label, not the positional id. Proof: a temporary `<button>Lane T probe</button>`
in `HomeOverviewPage.vue` made it fail with `HomeOverviewPage.vue:81 button "Lane T probe"`; reverted.

### Not covered yet (Alerts)

- Lane P's full Alerts screens are not on this branch: alert text naming the strategy (N-14 fix), leg-stop alert with the NIFTY value (row 2 / S-20), the "Includes N closed strategies" line (S-15 / Q2-14), Compare through an alert link (R-10), expiry settlement rows (trade 173), R-07.
- A real stop firing (stubbed).

### Not covered yet (Strategy Builder)

- BUILD-18..38 payoff chart, summary and figure widgets, charges, margin; BUILD-39..62 execute, tracking, adjust drawer; BUILD-68..85 adjust compare; BUILD-130..136 ready-made panel contents; BUILD-187..196 scenario and target blocks (partly in existing column-mode, display-format, range-step specs).
- BUILD-93..95 strategy-type confirm; BUILD-101..108 straddle, strangle, quick select, futures, synthetic; BUILD-116/185 reprice prompt; BUILD-156/157 paper toast after Add to Paper; BUILD-91/92 choosing width or lots mode.

### Not covered yet (Option Chain)

- Leave dialog x and overlay close (Escape, Stay, Leave are covered); builder-side leave paths (rows 11, 15) belong to the builder screen.
- Real-backend eligibility path (stubbed; `chain-selection.spec.ts` covers the real outcome route in CI).

### Not covered yet (Live Strategies and Adjustments; 2 rounds used)

- ADJ-36 "Stop at % of margin" switch; ADJ-37..45 plan-edit block (needs `GET/POST /strategies/{id}/adjustment-plan` stubbed); ADJ-53/54 "Earlier values (N)" and its Change; ADJ-31 rail links; ADJ-48 time-of-day input.
- Playbook editor approach checkboxes, day-rule inputs, situations step, stage from/to: rendered, not edited.
- 25 s card give-up timer (D-41).

### Not covered yet (Current positions)

- Live index line in the Stops panel (needs the WebSocket feed); only "Index values unavailable." is tested.
- Real exit dialog: none on this screen (ADR-281); its absence is tested.
- Held-at-my-broker form, Add-to-Paper dialog, Greeks panel with data: not reachable from Positions or not exercised.
- Real-backend round trip (all stubbed).

### Not covered yet (My Strategies)

- Real-API round trip stays in `my-strategies.spec.ts` (needs the live catalogue); this suite is stubbed.
- After-charges tap on a Completed row's net figure (SHARED-09); Builder's Saved-list delete (Builder screen).

### Not covered yet (Home)

- Welcome / trial slot: nothing to click until sign-in exists; only the absent text is asserted (NEW-T01).
- Header toast for a new adjustment opportunity: needs a second header poll; the record count is covered (BELL-4).
- R-06 same-moment sum of the My Strategies rows: not provable against stubs; Home vs Positions headline is covered.
- Hover-open menus (150 ms delay) and arrow-key menu navigation; click, Escape and outside click are covered.
