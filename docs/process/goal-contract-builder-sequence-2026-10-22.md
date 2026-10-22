# Goal contract: Builder sequence (63 rows, one at a time, top to bottom)

Owner-approved order and rules: ADR-168 (2026-10-22). Status table and row order: `builder-sequence-2026-10-22.md`
(the checklist). Reviewed 2026-10-22 by an independent architect (round 1 REVISE, round 2 PASS WITH FIXES, all fixes
applied) and a delivery-efficiency engineer (measured CI/PR history; changes 1-10 applied). Replaces the builder part
of `goal-contract-builder-scope-2026-10-21.md` (its lanes A and B, steps 3-4). The rest of the ADR-165 scope
(adjustments incl. REQ-037, alerts, daily Zerodha check, Zerodha import) waits for a later contract written at row 63.
This contract overrides `docs/process/builder-brief.md` where they differ (e.g. builders work in the sequence worktree
on the chunk branch, not a fresh branch from origin/main).

**Core:** a user picks NIFTY legs with live prices, edits them, sees the engine's numbers and payoff, and saves the
strategy with a name (rows 1-29). **Proof:** before row 1, re-run the existing core chain end to end on the recorded
replay (build a NIFTY iron condor -> outcome -> save -> reload) and read the numbers back against a hand calculation;
live window 1 (after chunk 3) repeats it with the owner's Kite login.

## Goal (met only when ALL hold)

1. Every row is `Done`, `Done (live check pending)` proven by row 63, `Done (switched off: <hold>)`,
   `Done (AC-x deferred: <where>)` for the ACs listed under "Deferred acceptance criteria" in the table file,
   `Superseded`, or `PARKED (#issue)` after two failed rounds. `Waiting on owner (<question>)` counts only when the
   question was asked with the question tool (or filed in the owner-questions file) and the owner has had at least
   one session to answer it. No other end state.
2. Each row closed only after an independent verifier (a fresh agent that did not build it) checked every in-scope
   acceptance criterion; evidence files written by the orchestrator (`record_evidence.py`); `trace_check.py` passes.
   Old evidence is never trusted on its own (example: evidence/W-075/AC-7.md proved the with-charges basis that
   ADR-167 reversed, and its fingerprint did not change).
3. Every chunk merged on main through `merge.py --reviewed-sha`; CI green on main after the last merge.
4. Live windows held with the owner's Kite login on a market day: after chunk 3, after chunk 7, and at row 63.

## Step 0 (one small Tier B PR, before row 1)

- Fix the two flaky end-to-end tests that turned main red 4 of 43 pushes (`create-strategy.spec.ts:31` 5 s timeout,
  `strategy-live.spec.ts:136` "AC-4 two holders"), each under the defect-fix contract (RCA, class, failing run first,
  proof).
- Replace the response-door exact model COUNT with a checked-in sorted list of model names asserted exactly (stricter,
  and a line merge no longer needs a hand recount; the count changed 33 times since 10-15).
- Allocate all 63 W-ids (one requirement each) and their `coverage-stages.yaml` lines in one commit, so rows never
  edit that file again (it changed in 56 of the last 100 PRs).
- Step 0 runs on branch `docs/builder-feature-reqs` (pushed 2026-10-22; it carries ADR-168, REQ-134..140, the
  sequence table and this contract), so the plan and the step-0 fixes land as ONE PR.

## How a row is worked (strictly one row at a time)

Row N+1's BUILD never starts before row N is closed. While row N's verifier runs, the session prepares row N+1 only:
READ, MEASURE, write its builder brief, run `check_brief.py` + `copy_from_check.py`, fill its W-file.

1. **Read** the requirement in full (every AC), the decisions it cites, the Sensibull study screens
   (`D:\Abhay\Ventures\competitors\sensibull\2026-10-21\INDEX.md`; screenshots never enter this repo), the
   legacy-reuse map rows (`copy_from_check.py`), and the findings registry (`knowledge/findings/`).
2. **Measure** (rows still to build): a read-only `Explore` agent on Sonnet returns each AC as built / partly /
   missing with file:line, on main AND on the in-flight work: branch `build/W-126-a1-leg-rows` (rows 20 REQ-076,
   30 REQ-078), branch `build/W-127-b2-payoff` (rows 26 REQ-081, 36 REQ-083, 37 REQ-084), PR #509 branch
   `build/W-124-a3-chain` (rows 33-35 REQ-029/030/031, 45 REQ-087). **Reuse rule:** take only the files and hunks for
   the current row into the chunk branch (`git checkout <branch> -- <path>` or a hand-applied hunk), never a
   whole-branch merge that pulls a later row's code in early. Earlier reviews do not carry over; the chunk review
   covers them. Close PR #509 with a comment pointing at this contract once its rows are taken (never merged as is).
3. **Rows whose starting state is built or verified:** skip Measure; do not bypass the row. Dispatch the verifier on
   the full AC list; its failing ACs are the Measure result and go to step 4. **Adjacent built/verified rows share one
   verifier dispatch** (tier = the group's highest), returning one evidence block per row per AC: groups 1-2, 12-14,
   15-16, 48-49, 55-56. They still close one by one in order with the table printed each time; if row k fails, the
   rows after k in the group are re-verified after k's fix.
4. **Build** the missing ACs: the row is sized S / M / L from Measure. One builder agent in the sequence worktree on
   the chunk branch (Sonnet; Opus only with a `Why Opus:` line). Budget: S 30 min / 40 calls, M 60 / 80; an L row is
   ALWAYS split backend then frontend, each part 60 / 80. Brief = `docs/process/builder-brief.md` + the row part
   (REQ/AC text quoted, `check_brief.py` and `copy_from_check.py` pass, Sensibull screens, `Report: evidence-table`,
   the reviewer checklist, standing items C4 a-d, its own scratchpad subfolder). Tests: only the changed files'
   tests and the row's new tests, plus `ruff_ratchet.py`; no full suite.
5. **Verify** with a fresh read-only general-purpose agent on every in-scope AC: Sonnet for Tier B rows, Opus for
   Tier A rows (never Haiku). Replay-provable ACs must pass now; live-only ACs become `live check pending`
   (ADR-168 (2)).
6. **Close:** edit the row's Status in the table, commit on the chunk branch, push the chunk branch to origin as a
   backup (no PR yet: workflows run only on pull requests and on main, so this triggers no CI), then PRINT THE WHOLE
   TABLE on screen, followed by the "Open questions" list (owner: "after each requirement is completed ... show the
   whole table with the updated status").
7. **Blocked on a business question: never stop and never wait** (owner 2026-10-22, ADR-168 (6)). Ask it (one
   question, `Business call:` + `Spec basis:`; owner away -> the dated owner-questions file), set
   `Waiting on owner (<question>)`, and move on automatically: first finish every AC of that row that does not need
   the answer, then go to the next row that does not depend on the waiting one (its `depends_on` and the table
   order), skipping further down if needed. When the answer comes, write it into the spec the same turn and work the
   waiting row next, before any new row.
8. **Two failed verify or review rounds** -> `PARKED (#issue)` with the evidence; print the table; next row.

## Chunks (the only PR / full-CI / chunk-review points)

| Chunk | Rows | After it |
|---|---|---|
| 1 | 1-16 prerequisites (broker reads, instrument list, feed, data health, engine, save) | PR, CI, Tier A review |
| 2 | 17-24 UX levels removed + builder core screen | PR, CI, Tier A review |
| 3 | 25-29 margin, money summary, housekeeping, history, save with name | PR, CI, Tier A review; LIVE WINDOW 1 |
| 4 | 30-35 Shift/Width/Hedge, warnings, definitions, option chain | PR, CI, Tier A review |
| 5 | 36-42 charts, what-if, tables, manual P&L, settings, header, market context | PR, CI, Tier A review |
| 6 | 43-52 notes, share, chain options, BANKNIFTY/FINNIFTY, Create Strategy screen | PR, CI, Tier A review (row 46) |
| 7 | 53-54 tracking | PR, CI, Tier A review; LIVE WINDOW 2 |
| 8 | 55-63 held items (switched off) + close-out | PR, CI, review; final live window (row 63) |

- **Nothing else merges to main during a chunk** (the freeze holds): only the chunk PR. This removes the conflicts the
  parallel lanes caused.
- A chunk over ~1,000 Tier A product lines is split into stacked PRs at a row boundary; a migration rides as its own
  PR inside the chunk. Main is merged into the chunk branch once, before its gate.
- Before opening the chunk PR: the fast checks in CLAUDE.md "Commands", `ruff_ratchet.py`, the guard tests +
  `pytest -m repo_scan tests`, the chunk's changed files' tests, `pr_close_check.py`, `regen.py` once. Full suites
  and DB tests run in CI only. Red CI: read the failed log, fix, push once.
- One review per chunk PR (tier = its highest-risk row), at most 2 rounds. **A review finding reopens the row it
  names** (status back to `In progress`, table printed), and that round counts toward that row's two rounds. All rows
  reopened by one review round are re-verified together in ONE verifier dispatch after the fix (each row's full AC
  list).
- Docs (table, work items, evidence, findings, handover) ride in the chunk PR.

## Row 17: UX levels removed, spec first

Before any code: REQ-006 and REQ-007 are already `Superseded` (ADR-168). Rewrite every level-dependent rule to the
one-level rule of ADR-168 (5), in the same chunk PR: the ADR texts ADR-004 (Q21, Q31, Q32), ADR-007 (Q36, Q38, Q45),
ADR-008 (presentation by level), ADR-056 (5), ADR-068 (3), and the requirements REQ-012, 024, 029, 030, 034, 035,
036, 041, 063, 068, 069, 076, 080, 083, 084, 087, 096 (grep "Guided|Standard|Advanced|UX level|level" again first;
REQ-011 is already done). In the same change add `amends ADR-007; amends ADR-008; amends ADR-056; amends ADR-068` to
ADR-168's `changes:` and re-pin every requirement `spec_dupes.py` then names (about 44, each re-read for level
wording). Then remove the level switch and every level branch in the code, with tests.

## Rules

- **No order is ever sent; Execute stays off** (ADR-165, REQ-073 AC-6). Read-only Zerodha calls are in scope.
- **Spec first:** anything a requirement does not say is decided (technical, recorded in the PR body) or asked
  (business). Every owner answer is written into the spec the same turn. Row 58 needs REQ-016 approved first: ask
  the owner when row 57 closes.
- **Status on screen:** the whole table plus open questions after every row closes, and whenever the owner asks.
- **Pace:** estimated ~62-98 agent-hours, about 8-12 sessions, ~13 PRs including step 0, ~150 CI runs (efficiency
  review 2026-10-22; estimates). After chunk 1, report measured hours per row against this, as information.
- **Sessions:** a session that ends before the goal writes `session-handover-<date>-builder-sequence.md` (DONE /
  PENDING / BLOCKED / PARKED / NEXT, open questions, the chunk branch and its last pushed commit) and a memory
  pointer; the next session runs the same prompt and continues at the first row not closed.
- **Worktree:** ONE worktree for the whole sequence, `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs` (created
  2026-10-22 for this plan, TTL = until row 63), with a new branch per chunk
  from main after the previous chunk merges; removed at row 63 with tracked-file AND installed-package counts of the
  main checkout before and after.

## Stops (the only reasons to call the owner)

A live window is due (Kite login on a market day; ask, and keep building later rows meanwhile); every remaining row
waits on an owner answer; a Tier A CRITICAL survives two rounds with no redesign path; spend or a production deploy.
An open question alone is never a stop.
