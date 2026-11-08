# Session handover: GC-ADJ2 (adjustment playbooks, plan sheet, opportunities inbox, history) - 2026-10-31

Contract: `docs/process/goal-contract-GC-ADJ2-2026-10-31.md` (progress log §0.3 and "Found during the run" 1-22 hold
every proof line and decision). Run branch `build/gcadj2` (run tree `D:\Abhay\Ventures\OptionsForOptions2-gcadj2-run`),
merged locally into `feature/adjustments`. **Nothing pushed, no PR, main untouched by this run** (owner rule
2026-10-30: nothing to main without the owner's explicit approval).

## DONE

| Step | What | Proof (see §0.3) |
|---|---|---|
| 1 | Store + migration 0031 (5 tables, DB guards), seed of 12 system playbooks, per-stage evaluator, F-71 crossing rule, check route | fresh DB 8 passed; dev server ADJ-02 flags T-01/T-03/T-09, ADJ-01 none, ADJ-42 already true; Tier A: 6 review gaps fixed, 5/5 mutants killed |
| 2 | Playbook API (list, read, create, duplicate, rename, delete, activate, save as new / in place, stage gap/overlap) | fresh DB 18 passed |
| 3 | Editor (7 steps, plain-words summary, labels from the catalogue) + Test of unsaved values | owner's Chrome: T-01 Middle 0.3 unsaved -> no T-01 flag, T-03/T-09 flag, nothing saved; 12 real bodies x 7 steps render (vitest 21) |
| 4 | Plan sheet at the paper action, plan copy, Plan entry | fresh DB 7 passed; Chrome: prefilled, time exit 14:30, Use playbook as is saved |
| 5 | Suggestion records, inbox page, panel flags, Dismiss / acted-on, ADR-217 | fresh DB 8 + 11 passed; Chrome: 3 flags, grouped inbox row |
| 6 | Adjustment history + whole-trade totals | Opus money review findings fixed, 44-scenario oracle sweep; Chrome totals = ADJ-02 fixture |
| 7 | prepush --full, merge into local feature/adjustments | first run killed by low memory (apps closed, 5.7 -> 7.5 GB free); second run red on 5 guard checks -> one fix round (b0264b7c) + regenerated views; third run TOTAL PASS on 6b2e2546 (18:05); merged into local feature/adjustments a27c373c |

Spec written this run: REQ-159 section "How the open triggers are measured"; ADR-217 + REQ-112 AC-7 (owner decision:
a dismissed flag stays dismissed until the condition clears and holds again); F-71 FIXED in spec/findings.md with the
class file `knowledge/findings/level-trigger-true-at-entry-by-design.json` (guarded).

## PENDING (owner)

1. **Wording review**: about 100 new texts are pinned `pending owner read` in `tests/errors/template_pins.json`
   (trigger reasons, refusals, labels, summary sentences, guard labels, condition lines). Specific ones to read:
   A-13 "Add a lizard: sell a put and a call spread" (the fixture's "no risk on one side" is a promise word; "jade
   lizard" may not appear in code); A-11 has two names ("Re-centre both shorts at the money" kept vs the fixture's
   "Convert to iron butterfly"); "No value in this stage." (the stage name is not slotted); the 12 guard labels.
2. **The one PR to main** of `feature/adjustments` (GC-ADJ1 + GC-ADJ2): the run does not open it; it waits for the
   owner's explicit approval.
3. Approval of the other system playbooks' numbers (every PB except PB-04 stays "Draft") before GC-ADJ4.

## BLOCKED

None.

## PARKED

None. Step 3 needed two rounds beyond the two-round rule (contract findings 16, 22: browser-proof exceptions).

## Known gaps (not defects of the steps' proofs; listed so nobody rediscovers them)

- Live paper orders store no index level at entry: F-71 "held at entry" is judged at the first check after tracking
  starts (contract decision 4).
- The Live Strategies cards show no adjustment alert (only the builder's tracking panel and the inbox do); the mockup
  shows it on the card. Candidate for GC-ADJ3.
- Test lists T-02 with a P&L figure under "Spot crosses a breakeven"; the summary's plan line omits "or 4% of margin".
- Migration 0031 cannot be downgraded once a check has run (rule state is never deleted, by design).
- `build/gcadj2` also contains main's PR #620 docs commits (REQ-164/165), merged by mistake (contract finding 21);
  harmless (already on main).

## NEXT

1. Owner: wording review (one batch), then approve or hold the PR of `feature/adjustments` to main.
2. GC-ADJ3 (outline in the contract): cost and honesty, more strategy types, triggers T-03..T-19 live, what-if and
   paper adjust, the Live Strategies card alert.
3. The multi-user foundation goal runs after GC-ADJ2 (owner, memory note multi-user-foundation-2026-10-31).
