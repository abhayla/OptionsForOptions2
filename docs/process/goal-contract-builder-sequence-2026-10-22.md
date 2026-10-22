# Goal contract: Builder sequence (63 rows, one at a time, top to bottom)

Owner-approved order and rules: ADR-168 (2026-10-22). Status table and row order: `builder-sequence-2026-10-22.md`
(the checklist; rev 2 after the independent architect review). Replaces the builder part of
`goal-contract-builder-scope-2026-10-21.md` (its lanes A and B, steps 3-4). The rest of the ADR-165 scope
(adjustments incl. REQ-037, alerts, daily Zerodha check, Zerodha import) waits for a later contract written at row 63.

**Core:** a user picks NIFTY legs with live prices, edits them, sees the engine's numbers and payoff, and saves the
strategy with a name (rows 1-29). **Proof:** before row 1, re-run the existing core chain end to end on the recorded
replay (build a NIFTY iron condor -> outcome -> save -> reload) and read the numbers back against a hand calculation;
live window 1 (after chunk 3) repeats it with the owner's Kite login.

## Goal (met only when ALL hold)

1. Every row is `Done`, `Done (live check pending)` proven by row 63, `Done (switched off: <hold>)`,
   `Done (AC-x deferred: <where>)` for the ACs listed under "Deferred acceptance criteria" in the table file,
   `Superseded`, `Waiting on owner (<question>)` with the question asked, or `PARKED (#issue)` after two failed
   rounds. No other end state.
2. Each row closed only after an independent verifier (a fresh agent that did not build it) checked every in-scope
   acceptance criterion; evidence files written by the orchestrator (`record_evidence.py`); `trace_check.py` passes.
3. Every chunk merged on main through `merge.py --reviewed-sha`; CI green on main after the last merge.
4. Live windows held with the owner's Kite login on a market day: after chunk 3, after chunk 7, and at row 63.

## How a row is worked (strictly one row at a time)

Row N+1's BUILD never starts before row N is closed. While row N's verifier runs, the session may do row N+1's READ
and MEASURE steps only.

1. **Read** the requirement in full (every AC), the decisions it cites, the Sensibull study screens
   (`D:\Abhay\Ventures\competitors\sensibull\2026-10-21\INDEX.md`; screenshots never enter this repo), the
   legacy-reuse map rows (`copy_from_check.py`), and the findings registry (`knowledge/findings/`).
2. **Measure** what exists, AC by AC (built / partly / missing, with file:line), on main AND on the in-flight work:
   branch `build/W-126-a1-leg-rows` (rows 19, 29), branch `build/W-127-b2-payoff` (rows 25, 35, 36), PR #509 branch
   `build/W-124-a3-chain` (rows 32-34, 45). **Reuse rule:** take only the files and hunks for the current row into the
   chunk branch (cherry-pick by file, `git checkout <branch> -- <path>` or a hand-applied hunk), never a whole-branch
   merge that pulls a later row's code in early. Their earlier reviews do not carry over; the chunk review covers them.
   Close PR #509 with a comment pointing at this contract once its rows are taken (it is never merged as is).
3. **Work item:** the orchestrator allocates one W-id per row (`work/W-###.md`, one requirement, `tests_required`
   covering its in-scope ACs). Builders never allocate W-ids.
4. **Already built or verified:** do not bypass. Dispatch the verifier on the AC list; passing ACs get evidence; a
   failing AC goes to step 5.
5. **Build** the missing ACs: one builder agent (Sonnet; Opus only with a `Why Opus:` line) in the chunk worktree,
   brief from `docs/process/builder-brief.md` + the row part (REQ/AC text quoted, `check_brief.py` and
   `copy_from_check.py` pass, Sensibull screens, `Budget:`, `Report: evidence-table`, the reviewer checklist and the
   standing items C4 a-d). A large row is split backend first, then frontend. Tests: only the changed files' tests and
   the row's new tests, plus `ruff_ratchet.py`; no full suite.
6. **Verify** with a fresh read-only general-purpose agent on every in-scope AC; replay-provable ACs must pass now;
   live-only ACs become `live check pending` (ADR-168 (2)).
7. **Close:** edit the row's Status in the table, commit on the chunk branch, push the chunk branch to origin as a
   backup (no PR yet: workflows run only on pull requests and on main, so this triggers no CI), then PRINT THE WHOLE
   TABLE on screen (owner: "after each requirement is completed ... show the whole table with the updated status").
8. **Blocked on a business question:** ask it (one question, `Business call:` + `Spec basis:`; owner away -> the
   dated owner-questions file), set `Waiting on owner (<question>)`, print the table, and continue with the next row
   ONLY if that row does not depend on the waiting one (its `depends_on` and the table order); otherwise stop and wait.
   When the answer comes, the waiting row is worked first, before any new row.
9. **Two failed verify or review rounds** -> `PARKED (#issue)` with the evidence; print the table; next row.

## Chunks (the only PR / full-CI / chunk-review points)

| Chunk | Rows | After it |
|---|---|---|
| 1 | 1-16 prerequisites (broker reads, instrument list, feed, data health, engine, save) | PR, CI, Tier A review |
| 2 | 17-24 UX levels removed + builder core screen | PR, CI, Tier A review |
| 3 | 25-29 margin, money summary, housekeeping, history, save with name | PR, CI, Tier A review; LIVE WINDOW 1 |
| 4 | 30-35 Shift/Width/Hedge, warnings, definitions, option chain | PR, CI, Tier A review |
| 5 | 36-42 charts, what-if, tables, manual P&L, settings, header, market context | PR, CI, Tier A review |
| 6a | 43-46 notes, share, chain options, BANKNIFTY/FINNIFTY | PR, CI, review |
| 6b | 47-52 Create Strategy screen | PR, CI, Tier B review |
| 7 | 53-54 tracking | PR, CI, Tier A review; LIVE WINDOW 2 |
| 8 | 55-63 held items (switched off) + close-out | PR, CI, review; final live window (row 63) |

- A chunk over ~1,000 Tier A product lines is split into stacked PRs at a row boundary; a migration rides as its own
  PR inside the chunk. Main is merged into the chunk branch once, before its gate.
- Before opening the chunk PR: the fast checks in CLAUDE.md "Commands", `ruff_ratchet.py`, the guard tests +
  `pytest -m repo_scan tests`, the chunk's changed files' tests, `pr_close_check.py`, `regen.py` once. Full suites
  and DB tests run in CI only. Red CI: read the failed log, fix, push once.
- One review per chunk PR (tier = its highest-risk row), at most 2 rounds. **A review finding reopens the row it
  names** (status back to `In progress`, table printed), and that review round counts toward that row's two rounds.
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
- **Status on screen:** the whole table after every row closes, and whenever the owner asks.
- **Pace:** estimated 80-120 agent-hours, about 10-15 sessions (architect review 2026-10-22: ~18 built/verified rows
  at 30-45 min each, ~44 rows to build at 1.5-2.5 h each, plus 9 chunk reviews and 3 live windows). After the first
  chunk, report the measured hours per row against this, as information.
- **Sessions:** a session that ends before the goal writes `session-handover-<date>-builder-sequence.md` (DONE /
  PENDING / BLOCKED / PARKED / NEXT, the chunk branch and its last pushed commit) and a memory pointer; the next
  session runs the same prompt and continues at the first row not closed.
- **Worktrees:** one chunk worktree `OptionsForOptions2-seq-chunk<N>`, removed after its PR merges (count tracked
  files and installed packages in the main checkout before and after).

## Stops (the only reasons to call the owner)

A live window is due (Kite login on a market day); a business question blocks the next row and no later row is
independent of it; a Tier A CRITICAL survives two rounds with no redesign path; spend or a production deploy.
