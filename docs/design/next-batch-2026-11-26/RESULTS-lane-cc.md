STATUS 23:25 | items 1, 2, 3: built, tests green, review pending | next push 00:30 (push 1) | blocker: message to @parent refused (device trust), this line is the report

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

## Not done

- Item 4 (design document), review of the design, item 5.
- Second-helper mutation review of the tests: running.

SAFE TO CLOSE: not yet.
