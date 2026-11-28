# Lessons to checks

The rule of the loop: **a lesson is not learned until a check enforces it.** Every row without a check is debt.
A fault of one day becomes a lesson, the lesson becomes a check, and the check gets a test that fails when the check
is removed. The checks live in `lane_watch.py` (flags), `check_brief.py` (brief rules), the tests under
`tests/orchestrator/test_lane_watch_*.py`, and `scripts/orchestrator/prepush.py` (gate). A flag counts as a check
only when it fires on the real case; a count shown in a report is not a check.

Lessons 1 to 13 are in `SKILL.md` and `coordination-lessons-2026-11-28.md`. Lessons 14 to 20 are NOT on this base (commit 020792820 is not on origin yet); only their titles come from the brief.
For rows 14, 15 and 19 the mistake is one of the faults named in the brief. For rows 16, 17, 18 and 20 the mistake
column is an inference from the title, marked (inferred); the owner lane must replace it with the lesson's own case. Row 21 is new: it comes from the hold
that the coordinator placed at the lane and not at the build.

| # | Lesson | The mistake of 28 Nov it came from | Check that enforces it | Proposed check if not enforced |
|---|--------|------------------------------------|------------------------|--------------------------------|
| 1 | Finish line before fan-out; report leads with burn-down | "passed in cloud" stood at 123 for four runs while the list grew 203 to 210 | NOT ENFORCED YET (`lane_watch` prints an ITEMS count only) | `lane_watch` keeps the last count in the state file and prints open, proven since, net, added; a report with no burn-down line is a finding |
| 2 | A lane closing is not work done | a lane's ETA was read as the ETA of its items; hand-over gaps 26 and 7 minutes | NOT ENFORCED YET (flag CLOSING WITHOUT SAFE TO CLOSE only checks the closing line) | `lane_watch` reads "Not done" and "For the owner lane" from a closing lane's results file and counts them as open items with no owner lane |
| 3 | Batches: two pushes per lane, one check per push, no override | one push per item cost 16.9 check-minutes per item; the first push due at 75 minutes was missed unnoticed | `lane_watch` OVERDUE (first_push_due, next_push_due); `prepush.py` has no override; tests `test_lane_watch_overdue_f1b_*`, `test_lane_watch_overdue_r1_*` | none |
| 4 | Not one push at the very end | money-path proof landed 03:20 instead of 01:45; R1's 22:30 push missed | `lane_watch` OVERDUE (next_push_due); test `test_lane_watch_overdue_r1_missed_2230_push` | none |
| 5 | The build lane merges in waves, one combined check per wave | one branch per check cost 5.8 hours for 14 merges; wave 1 at 22:45 | `lane_watch` WAVE PAST DUE (due, ci not green); test `test_lane_watch_wave_one_at_2245_*` | none |
| 6 | Check in the background; reviews alongside; the one code path | five reviews of the browser lock each found one more hole | NOT ENFORCED YET | a brief rule: two review rounds on one area end with a "one code path" line in RESULTS; `check_brief` cannot see rounds, so the coordinator state counts rounds per area and flags the third |
| 7 | Split by files that do not overlap; one owner per shared file | one lane blocked at a merge conflict outside its files; the build lane met 6 document and script conflicts | `lane_watch` FILE OVERLAP and OUTSIDE OWNS; test `test_lane_watch_file_overlap_and_outside_owns_six_conflicts` | none |
| 8a | Signals: read the last event or commit before calling a lane stalled | a 24-minute check looked like a stall | `lane_watch` SILENT uses commit times and prints minutes since last commit; tests `test_lane_watch_silent_*`, `test_lane_watch_not_silent_*` | none |
| 8b | Signals: an accepted build commit goes to the plan lane, the PC and the test lane in the same step | a plan lane sat idle 50 minutes | NOT ENFORCED YET | state `waves[].told` list of lane names; `lane_watch` flags a wave commit not yet told to the plan lane after 10 minutes |
| 9 | Device trust: say at session start that lane events cannot be read | after approval the coordinator could not read lane events; planned around transcripts | NOT ENFORCED YET (needs the host) | first cycle of the procedure sends one test message to each lane and writes the result in the state file; a lane with no answer is INSTRUCTION NOT ACKNOWLEDGED after 30 minutes |
| 10 | Quote facts from the source file | issue 876 passed as 14 triggers; the PC said 13; three lanes built the wrong shape | NOT ENFORCED YET | `check_brief` rule: a line with a count or an issue number in the Queue must carry a `Source:` path |
| 11 | CI and the age of main | main 11 days old, about 1,700 commits behind; 15 minutes wasted per push | NOT ENFORCED YET | `lane_watch` prints `git rev-list --count <build>..origin/main` and the age of main's head; a flag over 100 commits or 3 days |
| 12 | One line to the owner per new lane | lanes multiplied while the proven count stood still | NOT ENFORCED YET | lane field `why_new` in the state file; `lane_watch` flags a working lane without it |
| 13 | One draft pull request for the build; CI after every wave; a freeze needs a green CI run | the plan nearly dropped CI and pull requests | `lane_watch` WAVE PAST DUE needs `ci` green; a freeze is a commitment (COMMITMENT PAST DUE); test `test_lane_watch_wave_one_at_2245_*` | a flag when a wave's `commit` is not the build head (CI ran on an old commit) |
| 14 | Message delivery only at turn end | instructions queued 17:37 to 19:44 reached RA2 as one batch at 21:42 | `lane_watch` INSTRUCTION NOT ACKNOWLEDGED (30 minutes); test `test_lane_watch_instruction_not_acknowledged_ra2_deaf_four_hours` | none |
| 15 | Migration numbering collisions | RA2, B2 and R1 each numbered a migration 0063 on parent 0062 | `lane_watch` MIGRATION COLLISION (same number, same down_revision); test `test_lane_watch_migration_three_lanes_0063`; exit code 1 | the coordinator hands out migration numbers in the brief (a `Migration number:` line checked by `check_brief`) so a collision never starts |
| 16 | Cloud speed proofs need the link delay | (inferred) a speed proof in the cloud passed where the PC link to the database was slow | NOT ENFORCED YET | `check_brief` rule: a brief that names a speed or latency proof must carry a `Link delay:` line (ms to the database) |
| 17 | Run the whole browser suite before a wave; set the last wave by CI time | (inferred) a wave went to CI with a partial browser run | NOT ENFORCED YET | wave field `browser_suite` (pass or fail, commit); `lane_watch` flags a wave whose browser suite is not on the wave commit; last wave due = CI minutes before the freeze |
| 18 | Two proof columns (cloud, PC) in every result row | (inferred) cloud-proven rows were read as proven on the PC | NOT ENFORCED YET | a RESULTS check (in `lane_watch`): a lane's results file with a proof table lacks the two headings `cloud` and `PC` |
| 19 | Commit times, not lane clocks | F3's STATUS said 23:20 at 22:40; a lane in a 24-minute check looked silent | `lane_watch` takes every time from commit times and its own clock; flag STATUS CLOCK AHEAD; test `test_lane_watch_silent_f3_status_clock_is_not_a_heartbeat` | none |
| 20 | An independent reviewer before the owner sees a plan | (inferred) plans reached the owner with holes a second reader found | NOT ENFORCED YET | state list `plans` [{name, reviewed_by, reviewed_at}]; `lane_watch` flags a plan sent to the owner without a reviewer |
| 21 | A hold is placed at the build and in the state file, not only at the lane | RA2 was held at the lane with F3's as-of; the build merged the held commit | `lane_watch` HOLD VIOLATED (`git merge-base --is-ancestor`); exit code 1; tests `test_lane_watch_hold_ra2_with_f3_as_of_*`, `test_lane_watch_hold_not_newer_than_*` | none |

## Debt count

- Rows with a check that fires on the real case: **10** (3, 4, 5, 7, 8a, 13, 14, 15, 19, 21).
- Rows with no check (debt): **12** (1, 2, 6, 8b, 9, 10, 11, 12, 16, 17, 18, 20).
- 22 rows in all. Next to build, cheapest first: row 11 (one `git rev-list` count), row 12 (one state field), row 10 and
  16 (two `check_brief` rules, to be added by the owner lane because `check_brief.py` is not edited here).
