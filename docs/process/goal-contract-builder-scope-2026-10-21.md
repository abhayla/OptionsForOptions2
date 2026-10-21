# Goal contract: Builder scope (strategy builder, tracking, adjustment suggestions)

Owner-approved 2026-10-21 (plan rev 4). Plan with every requirement per step: `scope-plan-builder-first-2026-10-21.md`.
Decision: ADR-165. This contract replaces the old goal chain (GC-3F / GC-6): their open rows are either in this
contract or parked by Step 1.

**Core:** a built strategy is tracked and the live feed drives one adjustment detection on it with the right numbers.
**Proof:** Step 2 below, on real live data, numbers checked by hand.

## Goal (met only when ALL hold)

1. Every row below is CLOSED with an independent verifier's evidence file per acceptance criterion, or PARKED with an
   issue (after two failed rounds), or BLOCKED on a named owner input. No other state exists.
2. Every product change is merged on main through `merge.py --reviewed-sha`; CI green on main after the last merge.
3. Both live windows passed with the owner's Kite login (Step 2 and the final live window).
4. `tracker_check.py` agrees with GitHub; the final handover lists DONE / PARKED / BLOCKED / NEXT.

## Rows (the checklist; one row = one requirement's acceptance criteria in scope)

| Step | Rows | Lane | Owner needed |
|---|---|---|---|
| 1 Clean up and switch off orders | Execute off on the server + test; land #448 #466 #457 #393 #465 #450 #474 #417 #424; park the order PRs; in-scope Draft/Specified REQs set to Approved (owner approved 2026-10-21) | main | No |
| 2 Prove the core live | REQ-109 AC-1/2 + one Q253 detection, replay first, then live | main | Kite login, market day |
| 3 Live data the builder needs | plan Step 3 list | C | No (replay) |
| 4 The builder, complete | plan Step 4 list, held items switched off live | A, B | No (replay) |
| 5 Tracking and Zerodha import | land #419 #451 #452; plan Step 5 list | C | No (replay) |
| 6 Adjustment engine | plan Step 6 list; platform-view suggestions off live until Q211 | D | The 7 unclear video values (REQ-071) |
| 7 Alerts and daily check | plan Step 7 list | D | No |
| Final live window | every AC that needs live data, in one market-day window | main | Kite login, market day |
| 8 Adjustment playbooks | BLOCKED until the owner sends the specifics | - | Specifics |

## Rules

- **Work:** four lanes (A builder interaction, B summary and charts, C data + tracking + import, D adjustments +
  alerts) after Step 2; one Sonnet builder per lane in its own worktree; one PR per feature cluster (about 12-16 in
  all); the session integrates and merges.
- **Every brief:** `docs/process/builder-brief.md` + the item part: the REQ/AC text quoted (`check_brief.py` passes),
  `Copy from:` rows, the Sensibull study screens it follows (`D:\Abhay\Ventures\competitors\sensibull\2026-10-21\
  INDEX.md` screen numbers; screenshots never enter this repo), `Budget:`, `Report: evidence-table`.
- **Tests and CI:** changed files' tests while building; full suites once per PR in CI; red CI = read the failed log,
  fix, push once.
- **Review:** one review per PR; Tier A (fresh Opus) only for money maths, the live feed and detection numbers;
  Tier B (Sonnet) for the rest; at most 2 rounds, then park. One verifier dispatch per PR returns every AC block.
- **No guessing:** anything the spec does not say is decided and written down (technical) or asked (business) before
  it is built. Owner away: business questions go to `owner-questions-<date>.md` and the run continues.
- **No order is ever sent.** No step re-enables Execute.
- **Sessions:** a session that ends before the goal is met writes `session-handover-<date>-builder-scope.md` (DONE /
  PENDING / BLOCKED / PARKED / NEXT, open lanes and their branches) and a memory pointer; the next session runs the
  same prompt and continues from the open rows. Docs (tracker, handover, findings, evidence) go in one docs PR per
  lane, not per item.
- **Pace check:** after the first full lane-day, report agent-hours used vs the 70-110 h estimate, as information.

## Stops (the only reasons to stop and call the owner)

A live window is due (needs the Kite login); an owner input row is reached and nothing else is runnable; a Tier A
CRITICAL survives two rounds and no redesign path exists; spend or a production deploy would be needed.
