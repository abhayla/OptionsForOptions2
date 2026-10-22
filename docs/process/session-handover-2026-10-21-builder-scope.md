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

## STATE at 2026-10-22 ~07:00 IST (update of the run-1 notes below)
- Step 1 DONE: W-121 order path off merged (#496; REQ-073 AC-6 evidence pass); every held PR landed (#424 #474 #417
  #448 #419 #451 #452 #393 #465 #457 #466 #450) or parked (12); W-111 re-opened and merged (#498).
- Step 2 BUILT, live proof PENDING: W-122/W-123 merged (#504, CI 7/7 green) after three Tier A rounds (edit rewrote
  P&L -> reused token priced -> independent redesign PASS WITH MINORS on 21642978); evidence: W-122 REQ-109 AC-1, AC-2
  pass; W-123 REQ-045 AC-2 pass. ofo_dev upgraded to 0021. Live runbook: run the Step 2 checklist below at market open
  with the owner's Kite login. Threshold is a test-only dependency: the live proof uses a short strike within 0.5% of
  the index at the DEFAULT threshold, plus a negative strategy 2% away.
- Main was red 00:00-05:56 IST (create-strategy e2e race: the click came before the templates reply) -> fixed #503,
  main green on 1d54e1a8 and on #504.
- In flight: #500 class fix (stored contract priced by a reused token, app-wide through tracked_contracts.resolve),
  branch fix/500-reused-token, round 2 running (29 DB tests red in round 1, unproven).
- Docs: #501 merged (ADR-166, Sensibull-first + copy-first rules in CLAUDE.md and the contract, copy_from_check.py,
  24 lane briefs under docs/process/builder-scope-briefs/, findings, tracker).

## Step 2 live checklist (no order is ever sent; the order path is off on the server)
1. API on 127.0.0.1:8765 against ofo_dev with LIVE_MARKET=1 (dev_run.py); `/health` 200; `GET /features` -> off.
2. Owner: private window -> `http://127.0.0.1:8765/broker/zerodha/login` -> lands on `/broker/connected`.
3. After 09:20: NIFTY spot from the index route; iron condor on the nearest weekly expiry with short CE at the listed
   strike nearest spot + 0.3%, short PE spot - 1.5%, wings 200 out, 1 lot; save; Start tracking; GET the view twice,
   2 minutes apart; a second condor with shorts 2% away (must show NO detection).
4. Hand check: P&L = sum(side x qty x (current - entry)) to the paisa; distance % = |index - strike| / index x 100;
   two leg prices vs Kite's REST quote in the same minute (more than one tick apart while LIVE = STOP); positions
   before = after.
5. PASS -> record the evidence rows and start the four lanes; FAIL -> Steps 3-7 wait for the fix.

## BLOCKED on owner inputs (named)
- REQ-105 delayed prices: a delayed-price source + written permission (ADR-155) - built switched off only.
- REQ-108 events and FII/DII: data source, licence and cost (ADR-156 (3)).
- REQ-071: the 7 unclear video values (metric_registry.json rows 12, 13, 19, 20, 21, 22, 30).
- Notifier: the OFO2 project block and key on the shared gateway (lane D1).
- Step 2 live window and the final live window: the owner's Kite login on a market day.

## NEXT
1. Step 2 live window (checklist above) with the owner's Kite login.
2. Then four lanes from `docs/process/builder-scope-briefs/` (24 briefs, check_brief + copy_from_check clean):
   A1-A5, B1-B6, C1-C8, D1-D5. Merge order: A3 and B4 first; content PRs before guard/scan PRs (lesson below).
3. Land #500 when its round passes Tier A review.

## Landing log (held PRs, `land_held2.sh` + `samelines.py`)
Merged tonight: #450 CI split, #424 Windows pytest, #474 link guard, #417 tracker check, #448 DB pool budget, #419
stored mismatch store, #393 My Strategies, #466 Option Chain selection. Each RE-REVIEW NEEDED was cleared only when the
PR's own +/- lines were identical at the reviewed sha and the head (`samelines.py`: SAME).
Fix rounds needed after landing into a moved main (all caught by CI or the merge gate, none by review):
- #451: 0020 called 0019's old `_table_block` signature (#419's ruff fix changed it) -> fix 922927b, narrow Tier A
  PASS (SQL byte-identical, re-hashed independently).
- #496 W-121: #393's My Strategies offered Execute -> fix ef9f14eb (one `useOrderPath()` helper + Vitest scan),
  narrow Tier B PASS WITH MINORS (named-route links and .js files not scanned; added to #495).
- #465: its history scan flagged `alerts-history` (Alerts > History page) and the "not currently available" statement
  -> fix round running (exact allow-list entries).
- #457: the money-outside-engine scan flags guided.js arithmetic; the empty-state Create Strategy button routes to
  `orders` -> fix round running.
- W-122: Tier A verifier REVISE - MAJOR: the tracking view read legs from the current saved strategy, so an edit after
  Start tracking rewrote paper P&L (65 -> 130 units: 195.00 -> 390.00); fix round running. Over-claimed ACs removed:
  REQ-109 AC-3 (paper refusal not built), REQ-045 AC-1 (user-rule half is Step 6).

## Lessons (to register)
- Landing a batch of PRs reviewed against an older main: a PR that ADDS a guard or scan meets content another PR adds
  (3 times tonight: W-121 vs #393, #465 vs #393/W-089, #457 vs the money scan; plus #451 vs #419's helper change).
  Land content PRs first and guard/scan PRs last, and re-run each guard PR's scans on the merged main before the gate.
- Dispatching a builder while a `verifier`-type agent runs: every git write is blocked (known lesson 2026-10-19,
  repeated tonight with the #465 fixer, ~15 min lost). Never overlap a verifier with a builder that must commit.
- `regen.py` does not rebuild `spec/requirements/INDEX.md`; a status change then fails CI's index check (cost one CI
  round on #494). Fix: add `build_spec_index.py` to regen.py.
- A `changes: refines ADR-X` relation fans out a pin to every requirement citing ADR-X (86 pins for ADR-165); use
  `applies` when the decision does not change the cited decision's text.
- TaskStop on a background bash loop leaves its child loop running; kill by PID and re-check `ps`.
