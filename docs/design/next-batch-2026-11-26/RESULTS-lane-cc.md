STATUS 00:10 | push 1 on origin (acef70796, TOTAL PASS 835.9s jobs 4); design built; push 2 (design + this file) next | next push 00:40 | blocker: send_message to @parent refused (device trust); coordinator's 23:35 order read: no new tasks, close after push 2

# Lane CC results: the coordinator's core

Branch `feat/coordinator-core-1128`, cut from `origin/fix/ic-live-test-1123` (a0e6fee1). No product code touched.

## Items

| # | Item | State |
|---|------|-------|
| 1 | `state.example.json` and schema (docstring of `lane_watch.py`) | built |
| 2 | `lane_watch.py` and tests | built, 26 tests green |
| 3 | `LESSONS-TO-CHECKS.md` | built: 22 rows, 10 enforced, 12 debt |
| 4 | design document | built, 163 lines, Sonnet review folded in |
| 5 | last message to coordinator | not started |

## Core proof (migration collision)

Test `test_lane_watch_migration_three_lanes_0063`. Order of work: the code was written before the tests (a departure
from "tests first"), so the red run is a mutation run: the two collision conditions (same number, same down_revision)
replaced by `if False:` in `lane_watch.py`. Result: 2 of 4 migration tests failed
(`test_lane_watch_migration_three_lanes_0063`, `test_lane_watch_migration_lane_collides_with_build`); with the code
restored it passed.

Output on a temporary repository with three branches adding 0063 on parent 0062 (exit code 1):

```
ACT NOW: 6   (watch time 28 Nov 22:40 IST)
 1. MIGRATION COLLISION: feat/ra2 adds 0063_basket_facts_spot_at and feat/b2 adds 0063_order_attempts: same revision number 0063, same down_revision 0062_base (two heads); `alembic upgrade head` fails after both merge; renumber the later one
 2. MIGRATION COLLISION: feat/ra2 adds 0063_basket_facts_spot_at and feat/r1 adds 0063_position_tags: ... (same text)
 3. MIGRATION COLLISION: feat/b2 adds 0063_order_attempts and feat/r1 adds 0063_position_tags: ... (same text)
 4-6. OUTSIDE OWNS: RA2, B2, R1 each changed their migration file, which the demo lanes did not list in owns
```

One run on this repository with `state.example.json` (`--now 2026-11-28T22:40+05:30 --no-fetch`; the 28 Nov lane
branches are not on this origin, so each is a finding, not a crash). Exit 0:

```
ACT NOW: 10
 1. FINDING: build branch integration/weekend-r3-1129 not found on origin
 2-6. OVERDUE: RA2, B2, R1 (push due 22:30), F1b (22:32), F3 (21:00): no branch on origin
 7. CLOSING WITHOUT SAFE TO CLOSE: TG2
 8. FINDING: hold on feat/ra2-basket-facts-1128 cannot be checked: build branch not reachable
 9. INSTRUCTION NOT ACKNOWLEDGED: R1: sent 21:50, 50 min
 10. CONDITION NOT MET: F3 as-of commit on origin
```

## First real run (coordinator's request: filled state file against the real origin)

State file: `docs/process/coordinator-state-2026-11-28.json` (tracked; added at the coordinator's message,
outside the original May-edit list). Built from the coordinator's message and the handover on the fix branch.
Lane `owns` are by area only (the briefs with exact file lists are not in git); session ids of B1b, F1b, W3 are
"unknown". `next_push_due` is 01:30 Sun for a lane with a commit at or after 22:30, else 22:30 Sat. Run: `lane_watch.py
--repo . --state docs/process/coordinator-state-2026-11-28.json --now 2026-11-28T23:40:00+05:30 --no-fetch` (origin
fetched at about 23:29 IST), exit 1. First 37 lines, cut to 190 characters:

```
ACT NOW: 34   (watch time 28 Nov 23:40 IST)
 1. OVERDUE: B3: push due 22:30, now 23:40 (70 min late); last commit 21:44
 2. SILENT: B3: no commit for 115 min (last 21:44); STATUS text is not a heartbeat
 3. OVERDUE: F2: push due 22:30, now 23:40 (70 min late); last commit 21:46
 4. SILENT: F2: no commit for 113 min (last 21:46); STATUS text is not a heartbeat
 5. OVERDUE: F3: push due 22:30, now 23:40 (70 min late); last commit 21:48
 6. SILENT: F3: no commit for 111 min (last 21:48); STATUS text is not a heartbeat
 7. OVERDUE: W2: push due 22:30, now 23:40 (70 min late); last commit 21:33
 8. SILENT: W2: no commit for 126 min (last 21:33); STATUS text is not a heartbeat
 9. OVERDUE: W3: push due 22:30, now 23:40 (70 min late); no branch test/r3-plan-walk-3-1128 on origin
 10. OVERDUE: Z3: push due 22:45, now 23:40 (55 min late); last commit 18:56
 11. SILENT: Z3: no commit for 283 min (last 18:56); STATUS text is not a heartbeat
 12. OVERDUE: X2: push due 22:30, now 23:40 (70 min late); last commit 20:15
 13. SILENT: X2: no commit for 204 min (last 20:15); STATUS text is not a heartbeat
 14. OVERDUE: R2: push due 22:30, now 23:40 (70 min late); last commit 19:52
 15. SILENT: R2: no commit for 227 min (last 19:52); STATUS text is not a heartbeat
 16. MIGRATION COLLISION: fix/r3-backend-b2-1128 adds 0063_basket_facts_spot_at and feat/real-same-screens-be-1128 adds 0063_position_tags: same revision number 0063, same down_revision 0062
 17. MIGRATION COLLISION: fix/r3-backend-b1b-1128 adds 0063_basket_facts_spot_at and feat/real-same-screens-be-1128 adds 0063_position_tags: same revision number 0063, same down_revision 006
 18. FILE OVERLAP: B2 and B1b both changed 3 file(s) not owned by both: docs/api/openapi.json, docs/design/next-batch-2026-11-26/RESULTS-lane-ra2.md, requirements-dev.txt
 19. FILE OVERLAP: B2 and F3 both changed 4 file(s) not owned by both: backend/ofo_app/routes/paper.py, docs/design/next-batch-2026-11-26/RESULTS-lane-ra2.md, docs/process/friction-log.md, t
 20. FILE OVERLAP: B2 and R1 both changed 1 file(s) not owned by both: docs/api/openapi.json
 21. FILE OVERLAP: B1b and F3 both changed 3 file(s) not owned by both: backend/ofo_app/routes/paper.py, docs/design/next-batch-2026-11-26/RESULTS-lane-ra2.md, tests_app/test_stored_close_pa
 22. FILE OVERLAP: B1b and R1 both changed 1 file(s) not owned by both: docs/api/openapi.json
 23. FILE OVERLAP: F1b and F2 both changed 2 file(s) not owned by both: docs/design/next-batch-2026-11-26/RESULTS-lane-fj2.md, docs/design/next-batch-2026-11-26/screen-inventory.json
 24. FILE OVERLAP: F3 and R1 both changed 1 file(s) not owned by both: backend/ofo_app/routes/paper.py
 25. OUTSIDE OWNS: B2 changed 4 file(s) outside its owns: docs/api/openapi.json, docs/design/next-batch-2026-11-26/RESULTS-lane-ra2.md, docs/process/friction-log.md, requirements-dev.txt
 26. OUTSIDE OWNS: B1b changed 3 file(s) outside its owns: docs/api/openapi.json, docs/design/next-batch-2026-11-26/RESULTS-lane-ra2.md, requirements-dev.txt
 27. OUTSIDE OWNS: F1b changed 3 file(s) outside its owns: docs/design/next-batch-2026-11-26/RESULTS-lane-fj2.md, docs/design/next-batch-2026-11-26/screen-inventory.json, docs/design/next-ba
 28. OUTSIDE OWNS: F2 changed 2 file(s) outside its owns: docs/design/next-batch-2026-11-26/RESULTS-lane-fj2.md, docs/design/next-batch-2026-11-26/screen-inventory.json
 29. OUTSIDE OWNS: F3 changed 4 file(s) outside its owns: backend/ofo_app/routes/paper.py, docs/design/next-batch-2026-11-26/RESULTS-lane-ra2.md, docs/process/friction-log.md, tests_app/test
 30. OUTSIDE OWNS: T changed 1 file(s) outside its owns: .github/workflows/app-tests.yml
 31. OUTSIDE OWNS: W2 changed 54 file(s) outside its owns: tests_browser/r2_plan_walk_1128/b4a.js, tests_browser/r2_plan_walk_1128/b4b.js, tests_browser/r2_plan_walk_1128/b4c.js, tests_brows
 32. OUTSIDE OWNS: R1 changed 1 file(s) outside its owns: docs/api/openapi.json
 33. OUTSIDE OWNS: R2 changed 1 file(s) outside its owns: tests/broker_name_allowlist.py
 34. WAVE PAST DUE: wave wave 1 was due 22:45; commit none, ci none
LANES
 B2 (working) head 9220b5cdf | 54 min since last commit
```

What it found that is real (the first run also exposed three faults of the watch itself, fixed: file checks were
measured against the fix branch instead of the build (672 files of noise); a lane that merges the build into its branch
looked like held work; the STATUS check only compared with now): R1's `0063_position_tags` collides with RA2's
`0063_basket_facts_spot_at` (already inside B2 and B1b) on the same parent 0062 (R1 must renumber); wave 1 (22:45) has
no new build commit (build head a1d70422 still 18:56 IST); B3, F2, F3, W2, X2, R2 and Z3 have no commit since 21:44,
21:46, 21:48, 21:33, 20:15, 19:52 and 18:56; W3 has no branch; F3's STATUS says 23:20 in a commit made at 21:48 (a lane
clock 92 minutes ahead; B1b 56, R2 53, F2 39 minutes). Limits: OVERDUE judges "push met" by a commit at or after the due
time, so a lane that pushed batch 1 at 21:44 is shown overdue until the coordinator moves its `next_push_due`; the
hold on `fix/r3-leftovers-2-1128` cannot tell a merge through B1b from a direct one (shown HELD now; a later VIOLATED
needs a human look); commit times come from the lane machine's clock.

## Decided for the owner

- A push is "met" by a commit newer than `started_at` (first push) or newer than `next_push_due`. The coordinator moves
  `next_push_due` forward when it sees a push; the script cannot tell a push that was early.
- Only COMMITMENT PAST DUE, HOLD VIOLATED and MIGRATION COLLISION give exit 1 (as ordered). OVERDUE, SILENT, wave and file
  flags give exit 0 but are listed under ACT NOW.
- `lane_watch.py` refuses any git command not on a read allow-list (it raises); the only write-like command is `fetch`,
  and `--no-fetch` removes it.
- A migration file that two lanes both "add" with the same content (both cut from one commit) is one migration, not a
  collision.
- Lanes 14 to 20 are not on this base. For lessons 16, 17, 18 and 20 the mistake column is marked (inferred).

## Question for the owner

None.

## New test files

- `tests/orchestrator/test_lane_watch_flags.py` (26 tests, one per flag, each named after its 28 Nov case; plus
  `test_lane_watch_makes_no_network_write_and_changes_no_file`)

## For the owner lane

- Message to `@parent` is refused (`elevated_session_untrusted_device`). Fix: owner approves device trust for this session.
- `check_brief.py` proposals (rules for `Source:`, `Link delay:`, `Migration number:`) go into the design document.

## Review of the design (Sonnet helper, own context): 10 findings, folded in

Added to the action table: FETCH FAILED, STATUS CLOCK AHEAD, STATE INCOMPLETE, wider FINDING. Exit codes written
exactly (1 includes an unreadable state file, 2 = bad `--now`). First-cycle field-by-field rule for the state file, and
a `list_sessions` comparison. New flag STATE INCOMPLETE in the watch, with a test. "Runs on its own" reworded: the
watch is automatic, the actions are the coordinator's. Merges, reverts and checks go to the build lane (the coordinator
runs no tests). `send_later` named as the wake-up (no recurring timer). Push rule written: set `next_push_due` before
the next watch run. Lessons 16, 17, 18, 20 are not to be copied into SKILL.md until the real case is supplied. Row 13
recounted as partial. Not done from the review: a count of the debt rows by the watch, a `faults_open` state field.

## Review of the tests (second helper, 78 mutants, one at a time in a detached worktree)

Every one of the seven 28 Nov cases has a test that fails when its check is removed. Surviving mutants that mattered
were closed with 9 new tests: CONDITION NOT MET (met, not yet due), WAVE not yet due, first push with a commit older than
`started_at`, FILE OVERLAP when both lanes own the file, owns patterns (`/**/`, trailing `/`), CLOSING for a `closed`
lane, instruction between 30 and 300 minutes, STATUS ahead at the 10 minute boundary and across midnight, hold with the
build unreachable. Still surviving and accepted: the same-blob `pa == pb` half, the duplicate-pair dedupe, closed lanes
in the migration check, `.py` filter, FETCH FAILED flag, the two hold-UNKNOWN paths for `not_newer_than`.
Equivalent mutants: the `watch()` default arguments.

## Found, not assigned (owner's order of 23:35: recorded, not fixed, not handed on)

All from the first real run (23:40 IST view of origin); the coordinator has them in the run output above.
- R1 (`feat/real-same-screens-be-1128`): `0063_position_tags` has the same number and parent (0062) as RA2's
  `0063_basket_facts_spot_at`, which B2 and B1b already carry. Two alembic heads when both merge. Evidence: MIGRATION
  COLLISION lines 16 and 17 of the run.
- Build `integration/weekend-r3-1129`: head a1d70422 (18:56 IST); wave 1 (22:45) has no new commit. Evidence: WAVE PAST DUE
  and Z3 SILENT 283 minutes.
- No commit for more than 90 minutes at 23:40: B3 (21:44), F2 (21:46), F3 (21:48), W2 (21:33), X2 (20:15), R2 (19:52).
  Their STATUS lines may report pushes the origin does not show.
- W3 (`test/r3-plan-walk-3-1128`) has no branch on origin.
- Lane clocks ahead of their own commit: F3 92 minutes, B1b 56, R2 53, F2 39, F1b 27, W2 22. STATUS times of these lanes are
  not to be trusted.

## Gate

| Push | Head | Result |
|---|---|---|
| 1 | acef70796 | `TOTAL PASS 835.9s (steps sum 2110.4s, jobs 4)`; the first attempt stopped at "TOOLS MISSING" (pinned ruff 0.15.12, requirements, `npm ci` were not installed: installed, then re-run) |

## Not done

- Item 4 (design document), review of the design, item 5.
- Mutation review of the tests (second helper, 78 mutants): see the section below.

SAFE TO CLOSE: not yet.
