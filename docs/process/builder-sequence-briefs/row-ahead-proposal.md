# Proposal: build row N+1 while row N is being verified ("one row ahead")

Owner, 2026-10-23 ~08:50 IST: "why can't you start working on the next row while you're testing this row? ... I want
to revisit that rule to fasten the process ... one or two developers can start working on the next row."

## Today's rule
ADR-168 + goal contract "How a row is worked": "Row N+1's BUILD never starts before row N is closed. While row N's
verifier runs, the session prepares row N+1 only: READ, MEASURE, write its builder brief". Owner 2026-10-22: "Keep
strict order".

## Measured cost of the rule (rows 4-9, row-review.md)
- A verify round takes 15-40 min (row 8 r2 30 min, row 9 A0 r1 15, r2 31, A1+C 20, final ~35). A row has 1-2 verify
  rounds plus 0-2 follow-ups. During each verify round no builder runs.
- Example, row 9: builds 22+45+9+27+20+13 min; verifies 15+31+20+35 min = ~100 min of verify with no build running.
- Expected saving: the next row's build (30-60 min) runs inside the current row's verify time (20-40 min per round):
  ~20-35% less wall-clock per row; total tokens unchanged (same work, earlier).

## Proposed rule (replaces "Row N+1's BUILD never starts before row N is closed")
1. **One row ahead, never two.** When row N's code is committed and its verifier is dispatched, row N+1's build may
   start. Row N+2 never starts before row N closes.
2. **Rows still CLOSE in order.** Row N+1 is verified and closed only after row N is closed (or parked). The table,
   evidence, reviews and the per-row report stay in row order.
3. **Separate worktree and branch.** Row N+1 is built in a second worktree `OptionsForOptions2-builder-next` on branch
   `build/seq-row-<N+1>` made from the chunk branch head; the verifier of row N keeps a FIXED commit in the main
   sequence worktree (no commits land there while it runs). When row N closes, row N+1's branch is rebased onto the
   chunk branch, its changed files' tests re-run, then its verifier starts.
4. **Builders: one per row-ahead,** two only when row N+1 is an L row split backend + frontend (the two parts touch
   disjoint folders and commit with `git commit -- <own paths>`, as rows 9 A1 + C did on 2026-10-22).
5. **Dependency guard.** If row N+1 depends on row N (`depends_on`) it builds on row N's unverified code. If row N's
   fix round changes a file row N+1 also changed, or row N is PARKED, row N+1's builder re-runs its tests after the
   rebase and the verifier's brief names the overlap. If row N parks for a design reason row N+1 builds on, row N+1
   waits (status `Waiting on row N`) - the build is kept, not thrown away.
6. **Database load.** At most two throwaway-database runs at once (a verifier's and a builder's); a DB test costs ~23 s
   over the tunnel, so each run is slower - the builder runs only its own changed DB files (R13 on its own diff).
7. **Unchanged:** fresh independent verifier per row; two failed rounds = PARKED; meta review every 3rd row before the
   next build (it pauses the row-ahead build that would cross it); the per-row close checklist and report; chunk PR
   points; no order sent.

## Costs and risks (honest)
- Rework: when row N's fix touches the same files as row N+1 (e.g. row 9 feed files vs row 11 REQ-114 feed health),
  row N+1 repeats its tests or part of its build. Mitigation: rule 5; pick the overlap from Measure's file list.
- Orchestrator load: twice the events to track; context fills faster -> more session handovers.
- DB tunnel: two runs at once, each slower (rule 6).
- A row-N verifier misses less? No change - it still works on a fixed commit.
- Not a saving when row N+1 needs an owner answer or a live window (it waits anyway).

## What changes in the files (after approval)
- New decision ADR-171 "amends ADR-168": rules 1-7 above, with the owner's words.
- Goal contract `goal-contract-builder-sequence-2026-10-22.md`: "How a row is worked" step text + the worktree rule
  (a second worktree with TTL, removed at the chunk end per the worktree lifecycle rule).
- `row-review.md`: an effect-check row for the new rule (counter: wall-clock per row, rework minutes from overlap).
- The /goal prompt text: "strictly one row at a time, top to bottom" -> "rows close strictly in order, top to bottom;
  the next row may be built while the current row is verified (ADR-171)". The owner re-sets /goal with that text.

## First use
Row 10 (REQ-118 rate limits, brief already written and checked) starts in the second worktree as soon as the owner
approves, while row 9's final verify finishes. Row 10 depends on REQ-113 (row 9) but touches the REST doors, not the
feed files - low overlap.
