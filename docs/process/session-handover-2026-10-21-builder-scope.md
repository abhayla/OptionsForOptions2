# Session handover 2026-10-21 (builder scope, run 1)

Contract: `docs/process/goal-contract-builder-scope-2026-10-21.md` (plan `scope-plan-builder-first-2026-10-21.md`,
ADR-165). Next session: run the same /goal prompt; this file is the state. No order was sent.

## DONE (evidence in the PR bodies)
- Step 0: PR #494 merged 21:15 IST - ADR-165, plan rev 4, contract; REQ-073 AC-6 (order path off); ADR-165 pinned in
  REQ-045/REQ-073; 36 in-scope Draft/Specified requirements set to Approved (REQ-024, 047, 050, 076-087, 089-091,
  103-119, 133; REQ-103 read part only).
- Step 1: 12 order-path PRs labelled `parked` with the ADR-165 reason, branches kept: #478 #470 #463 #456 #455 #454
  #453 #421 #420 #418 #394 #459. #450 (CI split) merged. #424 Tier B review PASS WITH MINORS on 5889145.
- Owner decision ADR-166 ("Start tracking" is the label; REQ-109 AC-1 reworded) - on this docs branch.

## IN FLIGHT (at the time of writing)
- W-121 order path off (REQ-073 AC-6): Tier A verifier PASS WITH MINORS on ff7be0a; evidence recorded; PR #496 landing.
  Deferred #495 (route scan reads direct imports only; fix = check inside the order modules, run-discipline C8).
- W-122 Start tracking + Q253 detection (Step 2 core): backend built, core proof green on the replay (paper P&L +195.00
  = -390 + 130 + 780 - 325; detection at threshold 0.6: short strike 22,400 vs index 22,533.25, 133.25 points, 0.59%);
  part 2 (frontend, guard mutations) running; branch build/W-122-track-detect. Its migration is 0019 and collides with
  #419's 0019: renumber W-122 after #419/#451 land. W-122 links REQ-109 only (one link per work item); REQ-045's
  detection ACs need a W-123 linking the same tests.
- Held-PR lander (scratchpad `land_held2.sh`): 424 474 417 448 419 451 452 393 465 457 466, one at a time; on RE-REVIEW
  NEEDED it compares the PR's own +/- lines at the reviewed sha and the head (`samelines.py`) and retries with the
  head only when they are identical. #451/#452 had a red `api` job (ruff PLR0913 108 -> 109, expected to clear once
  #419's ruff fix is on main).

## BLOCKED on owner inputs (named)
- REQ-105 delayed prices: a delayed-price source + written permission (ADR-155) - built switched off only.
- REQ-108 events and FII/DII: data source, licence and cost (ADR-156 (3)).
- REQ-071: the 7 unclear video values (metric_registry.json rows 12, 13, 19, 20, 21, 22, 30).
- Notifier: the OFO2 project block and key on the shared gateway (lane D1).
- Step 2 live window and the final live window: the owner's Kite login on a market day.

## NEXT
1. Live core proof (Step 2) on the next market day with the owner's Kite login: build a NIFTY iron condor, Start
   tracking, one detection from the live feed with the threshold lowered, numbers checked by hand.
2. Then four lanes from the drafted cluster briefs (scratchpad `lane-briefs/`, 24 briefs, all `check_brief` clean;
   copy them into `docs/process/` with this batch): A1-A5, B1-B6, C1-C8, D1-D5. Merge order: A3 and B4 first.

## Lessons (to register)
- `regen.py` does not rebuild `spec/requirements/INDEX.md`; a status change then fails CI's index check (cost one CI
  round on #494). Fix: add `build_spec_index.py` to regen.py.
- A `changes: refines ADR-X` relation fans out a pin to every requirement citing ADR-X (86 pins for ADR-165); use
  `applies` when the decision does not change the cited decision's text.
- TaskStop on a background bash loop leaves its child loop running; kill by PID and re-check `ps`.
