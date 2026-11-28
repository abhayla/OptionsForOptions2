# Coordinator system: design (28 Nov 2026)

Owner's order, 28 Nov 23:15 IST: a written plan is not enough. The coordination must be a system with a feedback
loop. It learns from its mistakes and runs the lanes on its own. The coordinator runs the work and never decides
product questions for the owner. Built now: a small core (`lane_watch.py`, the state file, the lessons table). Designed
now, built after Monday's live test: the rest.

## 1. The four parts

1. **The state file.** One JSON file, `docs/process/.run/coordinator-state.json`, outside git. Schema and a real
   example: `.claude/skills/lanes/state.example.json`. It holds lanes, holds, conditions, waves, build, commitments,
   instructions, and the path of the plan items. It is the one file the coordinator must keep. A fresh session reads it
   first, so a coordinator can be replaced without losing the run.
2. **The rules.** `SKILL.md` (standing rules, coordinator section, lessons) and `coordination-lessons-*.md`.
3. **The automatic checks.** `lane_watch.py` (read-only, from git data and its own IST clock) and `check_brief.py`
   (brief shape). Tests for each flag are in `tests/orchestrator/test_lane_watch_flags.py`.
4. **The loop that turns each fault into a check.** Every fault gets one row in a fault ledger
   (`docs/process/coordinator-fault-ledger.md`, to be created by the owner lane):

   | fault (date, case) | cause | lesson number | check | test of the check |
   |---|---|---|---|---|

   A fault is closed only when the last two cells are filled. `LESSONS-TO-CHECKS.md` is the view of this ledger by
   lesson. Its bottom line counts the debt: rows with no check. The count must fall every week.

## 2. The coordinator's cycle (a fresh session can follow this from the skill alone)

Run it at every report from a lane or the test machine, and at least every 30 minutes.

1. **Start.** Read `CLAUDE.md`, `standing-direction.md`, `SKILL.md` (coordinator section) and the newest hand-over.
   Run `TZ=Asia/Kolkata date`. If `coordinator-state.json` is missing, build it from `state.example.json` and the
   list of lane sessions; say so in the first report.
2. **Read state.** Open the state file. Check each lane's branch head on origin, not its message.
3. **Run the watch:**
   `python .claude/skills/lanes/lane_watch.py --repo . --state docs/process/.run/coordinator-state.json`
   Read the line `ACT NOW: n`. Exit 1 means a hold is violated, a migration collides or a commitment is past due.
4. **Act on each flag** by this fixed table. Do the action, then write it into the state file.

   | Flag | Action |
   |------|--------|
   | HOLD VIOLATED | Stop the next merge at once. Revert the held commit on the build by a merge of the state before it (never a rebase or force-push). Tell the build lane and the held lane. |
   | MIGRATION COLLISION | Pick the lane that merges later. Send it: "renumber to 00NN, parent 00MM". Record the numbers in the state file so the next lane is told its number in the brief. |
   | COMMITMENT PAST DUE | First line of the next report to the owner. Name what is missing and the new time. |
   | OVERDUE (no branch) | Read the lane's last message. If none: send "push your first commit now". If a check is running (a check takes about 24 minutes), move `next_push_due` by 30 minutes and say why in `context_note`. |
   | OVERDUE (branch exists) | Same, and ask for the push of what is committed. |
   | SILENT | Send one line asking for the push. After 30 more minutes with no commit and no ack: start a successor lane from the last pushed head (section 4). |
   | INSTRUCTION NOT ACKNOWLEDGED | Re-send once in one short message. A lane hears only at the end of its turn (lesson 14). If still silent after 30 minutes treat as SILENT. |
   | CLOSING WITHOUT SAFE TO CLOSE | Ask the lane for the line. Count its "Not done" and "For the owner lane" items as open. |
   | FILE OVERLAP | Name the single owner of each file. Send the other lane the exact change to hand over, or tell it to drop the edit. |
   | OUTSIDE OWNS | Same. If the file is correct, widen `owns` and record why. |
   | WAVE PAST DUE | Merge the heads that are ready, start the combined check, set a new wave time. Never skip the check. |
   | CONDITION NOT MET | Find the lane that owes it; treat as OVERDUE for that lane. |
   | FINDING | A branch or commit named in the state file is not on origin. Fix the state file or the lane. |
5. **Report.** Burn-down first (open, proven since last report, net, added). Then bad news. Then one line per push:
   `head <sha> | gate <result> | re-test <what>`. Times in IST. The owner reads on a phone: no repeats.
6. **Write back.** Update the state file (new heads, `next_push_due`, acknowledged instructions, wave commits and CI).
   Commit lessons or checks the same turn (section 5).

## 3. What the coordinator may do without the owner, and what it must stop for

May do: start, replace and close lanes; assign items; place and lift holds; merge lane heads into the build; update the
plan and the state file; add lessons and checks; choose the spec-conformant side of a technical question and record it
under "Decided for the owner".

Must stop for the owner: what the product does (screens, rules, wording); a clash between two of the owner's rules
(write it as a question with a recommendation); real orders or any broker order endpoint; merging into main or marking
the build pull request ready; anything outside the repository (money, accounts, keys, other people).

## 4. Briefs, reports, holds, successors

- **Briefs:** copy `brief-template.md`, run `check_brief.py`. Each brief names the migration number the lane may use
  (proposed rule, section 8), its `owns` list (copied into the state file), `first_push_due` and the batch times.
- **Reports:** a lane sends one line to the coordinator at start, each push, when blocked, at 55 percent of context.
  The coordinator cannot read lane events (lesson 9), so the branch on origin is the report: the STATUS line and the
  commit time. The script never trusts the STATUS time.
- **Holds:** placed in two places in the same step: the build lane is told (and does not merge the commit), and a row
  goes in `holds` of the state file. The script checks the build with `git merge-base --is-ancestor`; a hold that was
  only sent as a message to the lane is a fault (28 Nov: RA2 and F3's as-of).
- **Successors:** a lane that is SILENT or at 55 percent of context gets a fresh lane from its last pushed head. The
  brief carries the old lane's hand-over list as its queue. Start the successor before the old lane stops. The state
  file shows both until the old one is `closed`.

## 5. How the owner sees it

Burn-down first: open, proven since the last report, net, added. Then bad news (every flag still open and its action).
Then good news. One block, short sentences, IST. One line per new lane saying what it finishes that a running lane
cannot (lesson 12). A question to the owner stands alone in its message.

## 6. How we know it improves

Measure each week, from the state file history and the ledger:

| Measure | Source | Direction |
|---|---|---|
| Faults repeated (same lesson twice) | fault ledger | zero |
| Minutes a lane sits unassigned or unheard | OVERDUE, SILENT, INSTRUCTION flags (minutes at first sight and at clear) | falling |
| Checks per item (full checks / items proven) | gate log | falling; target below 7 minutes per item |
| Proven-on-build per hour | items with proof on the build head / hours | rising |
| Debt rows in `LESSONS-TO-CHECKS.md` | the table | falling |

## 7. A kit feature for other projects (harvest proposal, text only)

This session cannot file issues in `abhayla/Startup-Factory`. Text for the owner lane to file as a `harvest` issue:

> Title: harvest: coordinator watch (read-only lane watch, state file, lessons-to-checks table).
> What: `lane_watch.py` reads a JSON state file and git refs and prints actions: overdue pushes (commit times, never
> lane clocks), silent lanes, holds violated at the build, migration number and parent collisions, file overlap against
> declared ownership, unacknowledged instructions, past-due waves and commitments. Exit 1 on the three that cost
> work. Standard library and git only. Why for the kit: any project that runs parallel agent sessions meets the same
> faults. Parts that are project-specific: the migrations directory (a state field) and the lane names.
> Proof: 25 tests on throwaway repositories, one per fault of 28 Nov.

## 8. Not automated, and why

- **Sending and reading lane messages.** Needs the host (device trust, lesson 9). The watch can only tell the coordinator
  whom to message. A future host feature: a message log with delivery time, so INSTRUCTION NOT ACKNOWLEDGED can be set
  by the host and not by hand.
- **Judging a product question.** Always the owner's.
- **Reading a lane's reasoning.** Only branch and commit are read.
- **The fault ledger entry.** Written by the coordinator; a check can only count rows with an empty last cell.

## 9. Proposed changes to `check_brief.py` and `SKILL.md` (not edited here)

`check_brief.py`:
1. Require a `Migration number:` line when the brief's May-edit list names a path under an alembic versions folder.
2. Require `Source:` on a Queue line that gives a count or an issue number (lesson 10).
3. Require `Link delay:` when the brief names a speed, latency or "ms" proof (lesson 16).
4. Require `Owns:` globs in a form `lane_watch.py` can copy (`May edit:` lines already are; accept them as the source).

`SKILL.md`:
1. Add a section "Coordinator cycle" that is section 2 above (procedure and flag table), and the line "run
   `lane_watch.py` at every report".
2. Add lessons 14 to 21 as they stand in `LESSONS-TO-CHECKS.md`.
3. Add to "Closing a lane": the hand-over list is counted as open items in the same cycle.
4. Add: a hold is placed at the build and in the state file, in the same step.

## 10. Order of building after Monday's live test

1. Rows 11, 12 of the lessons table (age of main, `why_new`): small additions to `lane_watch.py`.
2. `check_brief.py` rules 1 to 3 (owner lane).
3. Fault ledger file and its debt count.
4. Burn-down memory (state file keeps last counts; the report line is built by the script).
5. Host feature: delivery log for messages.
