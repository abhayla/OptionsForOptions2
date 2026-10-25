# Row review: lessons that still change behaviour, and the per-item log

Since ADR-189 (2026-10-26) this file follows the kit deliver skill's step 10: after each item, record minutes, rounds
and the cause of each extra round, and apply the fix that removes the cause the same turn. No per-row table, no meta
review every third row, no tracker. The full history to row 30 (the 62 KB file of 2026-10-22..25, R1-R19, effect
checks and the row log) is in git: `git show 6f08cdb4:docs/process/row-review.md`.

Lesson ids keep their old numbers (R1 -> L1) because scripts cite them. L7 (the measured per-row table) is retired.

## Lessons

- **L1 Attack list before the build** (row 2). The brief carries `Attack list:` with at least 5 numbered attacks, each
  naming the test file expected to hold it (check_brief refuses fewer); the builder runs each before reporting.
- **L2 Run every changed test file in full**, never a `-k` subset (rows 1-2: stale tests). DB `tests_app` files run
  through the main checkout's `db_run.py <worktree>`; a skipped DB test is NOT run. Grep every test tree for the old
  value of anything changed and report the grep and its hit count.
- **L3 Size by files touched** (row 1). <= 5 files S (30 min / 40 calls); 6-15 M (60 / 80); more, or backend +
  frontend, L: split. A class spread over ~20 files is never S.
- **L4 Never mutate in place** (row 1). Mutation copies live in the agent's scratch folder only.
- **L5 A resume re-sends the agent's whole history** (row 3: a 4-call follow-up cost 203k tokens). Resume a builder
  only for a real fix round; a small follow-up goes to a fresh agent with a narrow brief.
- **L6 The orchestrator runs its own checks after every bookkeeping edit**: `tests/test_tests_required_exist.py`
  after a work-item edit, `coverage.py . --check` after a status or stage change, `tests/orchestrator` at a row close.
- **L8 Every guard in a brief is an allow-list** (row 4: 19 shapes passed a forbidden-list). The build section names
  what IS allowed; forbidden shapes go in the attack list only.
- **L9 Read the findings before a time, date or limit rule** (row 5: 08:00 vs F-56's 08:30).
- **L10 A `verified` claim reads the code's use** (row 5): the value AND what the code does with it.
- **L11 Every new test names its CI job and variables** (row 6); a test that can only skip in CI is a defect.
- **L12 Secrets are guarded by inventory** (row 6): the closed set of fields that may exist, asserted both ways.
- **L13 Run the tests a change can break** (row 7): `select_app_tests.py` on the row's own diff.
- **L14 Cache keys are built from the call** (row 8: 30 of 40 key parts had no killing test).
- **L15 Measure lists every caller** of a changed entry point (row 8 missed two routes).
- **L16 Slow DB runs start first**, in the background, with `-o faulthandler_timeout=60` (~23 s per DB test).
- **L17 A business question never holds the session** (row 9: one question held the session ~7.5 h overnight). The
  question tool only while the owner is active and not 22:00-08:00 IST (`question_night_guard.py`); otherwise
  `docs/process/owner-questions-<date>.md` with the recommendation, and the build continues.
- **L18 Mutation results go to a file as they run** (row 9: results lost when the run was killed); quote the file.
- **L19 Every time written is read, never typed** (2026-10-23: nine typed times, up to 34 min in the future). Use
  `date` in the same step or a commit time; unknown is "not recorded".

## Per-item log (deliver step 10, newest first)

Format: `### <row/W-id> - <title> (<date>)` then one line each: `minutes: <wall-clock>`, `rounds: <n>`,
`extra rounds: <cause, one sentence each, or none>`, `fix applied: <what changed in a brief, rule, test or tool, and
where; or none>`.
