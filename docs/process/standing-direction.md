# Standing direction (owner-approved 2026-11-10 13:07 IST)

In force for every session on this project until the owner changes it in his own explicit words. A session's own
judgement, a handover note or an older goal contract does not change it. Reasoning, evidence and the full cards
(D-01 to D-12): the review page https://claude.ai/artifact/H4LhEbLVt372vUork193pc (private to the owner; read with
the Artifact tool). This file is enough to follow the direction without the page.

Why it exists: a review on 2026-11-10 (main 5a8f5683) found about ten days of work spent on depth for one strategy
type while the journey a user needs was missing three steps: only the owner can log in, the app runs on one PC, and
real order placing is on hold (ADR-281).

## The goal

A person who is not the owner opens a link, logs in, builds an iron condor, and sees it through to a real order with
the broker. Until that is true the product is not ready to show Zerodha (ADR-060).

## The order

| Step | What | Card | Finished when |
|---|---|---|---|
| 1 | Finish the open iron condor run GC-ICGUIDE (live tasks g35, g36 on 11 Nov; g37 on 17 Nov; g38). Then the freeze below is on. | D-01 | Every row of that run is DONE or PARKED in its handover. |
| 2 | Write the demo-ready checklist: every item of finding F-31 plus the screens ADR-060 names; status, proof and owner per item. | D-02 | The owner has approved the list. |
| 3 | Fix the four first-user failures: #627 (worker reads margin so T-16 is checked; heartbeat alert when the worker stops), #686 (calendar for 2027), #680 (daily instrument refresh with no forced override), #682 (one database connection per request). | D-03 | One live market day where the worker log shows T-16 checked on every open strategy, the counter named; a 2027 date reads open in a test; three days of refresh with no manual force. |
| 4 | Make the whole journey work for iron condor: a host and a deploy path (Q273), a real signed-in user in place of the constant owner, real order placing at 1 lot. Host: the Hostinger Linux VPS with Redis there (ADR-288). The second person signs in with their own app login and works on paper; the one real order is on the owner's account, placed by the owner (ADR-289). | D-05, D-06 | The goal sentence above is true; every leg of one real iron condor is submitted, executed and reconciled with 0 mismatches. |
| Side test | Beside step 3 or 4: a short strangle (2 legs, no wings) on paper and scenario data. A test, not a build. | D-04 | A written answer: does "other strategies are minor changes" hold, and how big is the repair. Stop and report after 3 working days of session time, finished or not. |
| 5 | Only after step 4: add strategy types one at a time. | not written | The owner picks the order when step 4 is done. |

Clean-up allowed beside any step: D-07 (one triage pass on open issues), D-08 (one true status record), D-09 (land
the faster test database, re-measure CI), D-10 (fewer decision rows; parameters live in data), D-11 (clean working
tree, worktrees inside their limit). D-12 (structural debts) waits until step 4 is done.

## Core and depth

- **Core** is the journey: log in, build, place with the broker, watch, adjust, close. Work that makes a missing step
  of the journey exist is core.
- **Depth** is making one existing step richer: one more adjustment approach, one more trigger, another wording
  round, more guide content. Depth on iron condor is frozen.

## Rules for every session

1. **Name the step first.** Before starting work, state which step above it belongs to; a goal contract names its
   step in its first lines. Work that belongs to no step is not started: say so, and name the step it waits for.
2. **Iron condor freeze.** Allowed: a real defect in what is already built, and anything a step above needs. Not
   allowed: a new approach, trigger, wording round, guide content or iron-condor decision row.
3. **No second strategy type is built before step 4 is done.** The side test is the only exception and stays on
   paper.
4. **An owner request outside this order** is neither refused nor quietly done. Ask one question: change of
   direction, or a one-off exception? Record the answer here.
5. **Only the owner's explicit words change this direction.** When he does, update this file and the review page in
   the same turn, and add a line to the change log below.
6. **A step is finished only on its proof:** a real run or a named counter, never "it ran".
7. **The side test starts with its core proof:** on a 2-leg short strangle, the tested-side roll returns trades
   instead of the refusal `adjust_needs_two_spreads` (`backend/ofo/adjustment/approaches.py`, `_condor`). Nothing
   else in the test is built until that holds.

## Still needs the owner

Approving the direction did not approve these (status 2026-11-11: the checklist is approved, ADR-287; the host is
decided, ADR-288; one real order is approved, ADR-289): the content of the checklist (step 2); the host and any spend
(step 4); reopening the Zerodha ticket and questions Q258 to Q261 (step 4); any real order (ADR-281 stays in force
until the owner lifts it, and the owner presses Execute); closing or merging any issue in the triage (D-07).

## Change log

- 2026-11-10 13:07 IST: approved by the owner as written by the 2026-11-10 review.
- 2026-11-11 (owner, question tool): step 2 done, the checklist approved as written (ADR-287). Step 4 made exact, not changed in order: host = Hostinger Linux VPS with Redis there (ADR-288); the second person works on paper with their own app login, and ONE real 1-lot iron condor is placed on the owner's account by the owner, lifting ADR-281 for that order only (ADR-289).
- 2026-11-11 evening (owner, chat + question tool): no real order through the app; ADR-289 part (2) withdrawn, ADR-281 stays for everything. Goal now: any user logs in, builds an iron condor or types in one already held at any broker, and the app tracks it against that user's adjustment settings and suggests adjustments until the exit; tracking runs while at least one strategy is open (ADR-290). Zerodha read-in is a later extra. The goal sentence and step 4 above are read with ADR-290 until this file is rewritten.
- 2026-11-11 evening (owner, question tool, "Approve 1-11 as listed"): step 4 is the 11-item tracking-journey list, built in this order: (3) per-user live prices proven first, then (1) sign-up and log-in, (2) each user's own Kite app, (8) no user sees another's data, then (4) a held condor typed in by hand, (5) the watcher tracks every user's open strategies and stops when none is open, (6) settlement at expiry, then (7) hosting on the VPS (deploy = owner approval), then (9) hide order placing, (10) triage and fix the defects that make suggestions wrong, (11) watcher restart and the #680 proof. Contract: `goal-contract-GC-TRACK1-2026-11-12.md`.
- 2026-11-12 ~00:1x IST (owner, chat): current work serves ONE user, the owner's own Kite account (ADR-291); any Kite connection needs the person's own Kite Connect app with the data API. Sign-up, other users, per-user Kite apps and hosting wait until the owner starts multi-user. GC-TRACK1 rewritten to that scope.
