# Session handover: kit 1.15.0 + 1.16.0, 2026-10-26 (session 4bd042f3)

Main at b4a3e886 (PR #572). KIT_VERSION 1.16.0. Next session: start from the NEXT section below.

## DONE

- **Kit 1.16.0 in force** (PR #571, merge caed2184; opened by the Factory's cloud session, checked and merged here).
  It fixes the five issues this project reported after kit 1.15.0 (Startup-Factory issues 172 to 176):
  - H2 (172): `python tools/ci_local.py` now RUNS the pull request test step (proven here: step 16, 374 s, passed;
    1.15.0 skipped it and still exited 0). When a needed test step does not run it prints `TESTS NOT RUN` and exits 1.
  - H1 (173): a records-only PR runs the records test set (tests marked `records` + this project's list).
  - H3 (174): CI step `python tools/check_control_bytes.py .` fails on raw control bytes in tracked text files.
  - H5 (175): the merge gate accepts a generated file changed after review when its check passes at the head.
  - H4 (176): `python tools/change_scope.py --base <sha> --triggers` + deliver step 2a (draft PR, heavy CI first).
- **ADR-191 (1)**: `.claude/project/ci-docs-only-tests.txt` lists test_reach_check_real, test_tests_required_exist,
  test_spec_integrity (owner Q3 "Opt in"; amends ADR-187 (5)). PR #570.
- **ADR-191 (2)**: trigger paths in `.claude/project/ci-trigger-paths.txt` (owner Q4 "Draft PR + CI first"): migrations,
  route files and api_models.py (reply models), `*_push.py`, the strategy-socket client. Proven with `--triggers` on
  the three real red rows: row 29 -> 0025 migration, row 27 -> routes/catalogue.py, row 30b -> routes/leg_edit.py;
  a docs-only commit -> nothing. PR #572.
- Also merged this session: kit 1.15.0 (#564, ADR-190: ci_reds.py, measure_tokens --budgets); main-red fix (#565:
  docs-only PR #559 had turned main red via 3 unbaselined reach hits); records (#566: docs/process/ci-reds-2026-10-26.md,
  the cause of each Playwright red); CI red classes (#567: select_app_tests.py reaches backend/ofo modules and
  migrations; e2e import-closure check for '@/'; answer-state reader test); #568 (strategy-socket e2e stand-ins must use
  echoSeq; answer-state readers for 8 fields); #569 (night question guard allows a question when the owner TYPED in the
  last 10 minutes; queued messages dated by their enqueue line; Tier A Opus, 2 rounds).

## PENDING

- **ADR-191 (3)**: measure the next 3 delivered rows (minutes, rounds, the cause of each extra round, deliver step 10,
  in docs/process/row-review.md). After the third row, run
  `python tools/measure_tokens.py --budgets --since <first row date>` and
  `python tools/ci_reds.py --repo abhayla/optionsforoptions2 --workflow app-tests.yml --event pull_request --since <same date>`,
  and compare with rows 27, 29, 30 and 31b (each paid at least one red run after review; rows 28-29 took ~3.6-4.4 h,
  row 30 276 min). No saving is quoted before that (ADR-190 (4)).
- Live proof still owed for ADR-191 (1): the first records-only PR's CI log must show the short records test set, not
  the full suite. #570 and #572 ran the full suite because they changed config files, not only records.
- Still open from this session: a `page.route` stand-in that keeps a route's old behaviour (run 40045667454, leg-edit)
  is caught only by CI Playwright (finding e2e-stand-in-drifts-from-server, unguarded for that half).
- Not from this session, kept: worktrees `OptionsForOptions2-c4r31b` / `-c4r31f` (row 31 parked #558) and four older
  `.claude/worktrees/agent-*` trees.

## NEXT

- The next row from the active plan (docs/process/builder-sequence-2026-10-22.md): **chunk 3 session B, row 25
  (W-153, REQ-055, margin check, read part)**, then row 26 (W-154, REQ-081; also mounts row 32's info marks, #561) and
  the chunk 3 close. Prompt: docs/process/chunk-session-prompts.md.
- **Deliver step 2a (kit 1.16.0, ADR-191 (2))**: a row whose diff touches a trigger path runs
  `python tools/change_scope.py --base origin/main --triggers`. If it prints any path (or `UNKNOWN`), push a DRAFT PR
  first and start the checker only after that head's App tests run is green. Row 25 and row 26 will likely touch
  route files, so expect this step.
- Before a push: `python tools/ci_local.py` now runs the test step (~6 min); read the TOTAL line, and treat
  `TESTS NOT RUN` as red.
