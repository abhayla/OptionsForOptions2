# Session handover, 28 Nov 2026 evening (coordinator)

- DONE: round 2 build 829ff65f handed to the PC; plan version 6b; the cloud-first rule.
- PENDING: the 72 workable items, in batches and waves (two pushes per lane, one combined check per wave).
- BLOCKED: nothing.
- PARKED: the real-same-screens change (ADR-330 (73)) joins the build only when proven.
- NEXT: sweeps every half hour; PC round 2 at 21:00 IST Saturday; freeze 10:00 IST Sunday.

The master plan follows unchanged (copied from the git-ignored `docs/process/.run/MASTER-PLAN-2026-11-28.md` so a new session can read it).

---

# MASTER PLAN, weekend of 28 to 30 Nov 2026 (coordinator = release manager). READ THIS FIRST after any restart, summary or new session, and at every sweep.
Saved 28 Nov 19:14 IST. Owner approved it at about 18:40 IST. Update this file whenever the plan changes; never let chat be the only copy.

## Goal and finish line
- All 72 workable items fixed, merged into the round 3 build (integration/weekend-r3-1129) and proven in the cloud. Only items that truly need the live market wait for Monday 30 Nov 09:15 IST.
- Classes: MUST 30 (stop, exit, order, P&L, missing alerts, misleading text), SHOULD 17, LATER 25, OWNER 4. Item lists: finish-line-2026-11-28.md; item-to-lane table: completion-plan-2026-11-28.md; measured review: plan-review-2026-11-28.md.
- Committed times (padded): MUST merged and browser-proven by 04:00 Sun; all 72 by 07:00 Sun; build freeze 10:00 Sun; PC round 3 at 12:00 Sun; P0-only fixes 16:00 to 19:00 Sun; no pull or migration Monday morning.
- Every report to the owner starts with the burn-down: MUST open / proven since last report / net; then all items open / proven / added.

## How the work runs (owner approved)
- Targeted tests per item, local commits; TWO pushes per lane: batch 1 = MUST items on origin by 22:30 IST Sat; batch 2 = the rest by 01:30 IST Sun. One full pre-push check per push (23.6 min median, about 30 percent fail once). Never a bypass, never a skipped test.
- Build lane Z3 merges in waves, one combined check each: wave 0 at 19:00 Sat (RA 951aa698c, FJ 4aeb42652, FJ2 68a46dd62), wave 1 at 22:45, wave 2 at 01:45 Sun, final 08:00 Sun, freeze 10:00, then one Opus review and the pull order.
- Walkers prove each fix in a cloud browser as soon as it is pushed; the PC runs PC ONLY checks plus a sample of at most ten (plan version 6b on docs/test-plan-weekend-1127).
- Lanes report by message at every push, when blocked, at 55 percent of context (then start a successor on the pushed head). The coordinator cannot read lane events since the owner approved device trust; messages and origin are the only signals. The PC session speaks only through PR 722 comments.
- A new finding goes on the list with its class and is counted as "added". A new lane needs one line of justification to the owner.
- Reviews (Opus) on money paths only, two rounds at most; when reviews keep finding holes, move the guarantee to one server code path.
- Standing limits: PR 722 never merged, never marked ready; paper only, never a broker order endpoint; no artifact link in the repo; a clash between two of the owner's rules is asked, not decided; clock from `TZ=Asia/Kolkata date` every time.

## Open holds and decisions
- HOLD: RA2's commit 77315690e stays out of the build until RA2 states that a stored close keeps a non-live price state (option a) or proves with named tests that nothing live follows (option b).
- HOLD: feat/real-same-screens-be-1128 and -fe-1128 join the build only when proven (database test with worker as a separate process, browser walk, Opus review) by Sun 10:00; otherwise Monday runs on the 27 Nov rule (ADR-330 (64)) and the change lands after the live test.
- Owner decision 28 Nov 18:55: "Paper and real trades are same now... no difference other than a tag"; Exit on a real position: same screens, nothing sent, stored with the real tag and the line "Not sent to Zerodha. Place it in Kite."; ADR-281 hold stays; ADR-330 (64) withdrawn. Decision row being written on fix/ic-live-test-1123 as the next ADR-330 point (confirm it is pushed). Design: design-real-same-screens-2026-11-28.md. Its four follow-up questions have fail-closed interims.
- Server-side block against a second order after an unknown outcome: Lane B2, top of batch 1 (the browser lock could not be made complete in five reviews).
- Owner questions still open (lanes built the fail-closed side): armed rows on a real position (now covered by the 18:55 decision), Execute-page lock on a repeat press, table total versus booked P&L switch, paused-badge wording, Cancel after Exit all with nothing staged, held position recorded by hand (ADR-292 (4)), unsent prepared order form reading as real, rupee and percent stop wording, about 30 new sentences to read.
- After Monday: the merge into main (main is 11 days old, about 1,700 commits behind; 3 hours to 2 days), which also removes about 15 minutes of waste per check.

# Live lanes after the 18:40 IST replan (28 Nov). Coordinator cannot read lane events; lanes report by message.
| Lane | Session | Branch | Owns |
| B1 = RA2 | session_01QaT8YK2edaCm2CbTjXXNuT | fix/r3-leftovers-2-1128 | worker, monitor, alerts, routes/paper.py, paper P&L. HOLD 77315690e out of build until stored-close state corrected |
| B2 | session_01QaT8YG7nc63xpT4Wha4YZf | fix/r3-backend-b2-1128 | other routes, stores, request key, server unknown-outcome block (top), Execute door |
| B3 | session_01QaT8YHcJsYhiQ9MTSpCUp3 | fix/r3-backend-b3-1128 | plan-watch speed, outcome wording |
| F1 = FJ2 | session_01QaT8YGWMBDftMQxLas7F94 | fix/r3-frontend-2-1128 | Exit dialog, locks, builder page |
| F2 | session_01QaT8YHowsRYRpSxJJrcCLJ | fix/r3-frontend-f2-1128 | plan screens, Execute page |
| F3 | session_01QaT8YFYnFG8sqbkiPDAuBc | fix/r3-frontend-f3-1128 | Positions, Home, list pages |
| T | session_01QaT8YGrRAPFNpXkAat7khm | test/r3-tests-t-1128 | test-only and tooling; then third walker |
| W1 = TG2 | session_01QaT8YJkdxuCuLg82y5eG6A | test/r3-plan-walk-2-1128 | cloud walk of the plan |
| W2 | session_01QaT8YHvwJDJkiBcmcrVHUY | test/r3-proof-w2-1128 | cloud proof of each merged fix |
| Z3 | session_01QaT8YGJntZzKU9jAqYfTot | integration/weekend-r3-1129 | build; waves: 0 now, 22:45, 01:45 Sun, 08:00 Sun; freeze 10:00 Sun |
| X2 | session_01QaT8YJFCQRTmhBxycpERGg | docs/test-plan-weekend-1127 | PC lists |
| R1 | session_01QaT8YGXMT6KVQFLLEe5sRx | feat/real-same-screens-be-1128 | real = paper backend (owner decision 18:55; merged only on coordinator's word, proven by Sun 10:00 or after Monday) |
| R2 | session_01QaT8YKyMiG1dUJvqqhkykR | feat/real-same-screens-fe-1128 | real = paper frontend |
| PC | session_01QaT8YGvTk8cS2G7qtuoCeb | - | round 2 at 21:00 on 829ff65f, plan v6b; PR 722 comments only |
Closed, safe to archive: RA, FJ, TG, Z2, FD5, FE4 and earlier.
Batches: batch 1 (MUST) on origin by 22:30 IST; batch 2 by 01:30 Sun. Files: completion-plan-2026-11-28.md, plan-review-2026-11-28.md, finish-line-2026-11-28.md, design-real-same-screens-2026-11-28.md, WORKING-RULES-1128.md.
Owner decision 18:55: real = paper except the tag; same screens, nothing sent; ADR-330 (64) withdrawn; row being written by the lessons helper on the fix branch.

## Working rules sent to every lane
Working rules from 28 Nov 19:00 IST (owner approved; they replace "one push per item" in older briefs):
1. Per item: failing test first, the fix, that item's targeted tests green, one local commit. No full pre-push check per item.
2. Exactly two pushes per lane. BATCH 1 = your MUST items (stop, exit, order and money paths first), due on origin by 22:30 IST Saturday. BATCH 2 = everything else, due by 01:30 IST Sunday. A lane may commit locally as often as it likes; one check covers all commits of the pushed head.
3. Before each push: `git fetch origin && git merge --no-edit origin/integration/weekend-r3-1129` (the round 3 build; on a conflict keep both intents, on a stop, exit, order or money path take the stricter, fail-closed side and name it), the pre-check list, then the full check once: `python scripts/orchestrator/prepush.py --jobs N` in the background with a 7200000 ms limit, N = 4 only if `nproc` is 4 or more and `free -g` shows 6 GB or more free, else 2. Never an override, never a skipped test. Read only the failing stage's log on a red run.
4. While the check runs, do not change that tree. Build the next item in a second worktree (`git worktree add ../wt-next -b <your-branch>-next`, purpose written in RESULTS, removed with plain `git worktree remove` when merged back, never --force). If unsure, wait for the check instead.
5. The Opus review of a batch's money-path diff runs while the check runs. A finding that can cost money is fixed before the push; every other finding goes into the next batch. Two review rounds at most, then list what is open.
6. One line to the coordinator by send_message (session_id "@parent") at: start, each push (commit, items done, the TOTAL PASS line), when blocked, when a question needs an answer, and at 55 percent of your context with the hand-over list. The coordinator cannot read your events.
7. A new defect you find outside your items: one line to the coordinator with file and evidence; do not start it.
8. Paper only, never a broker order endpoint; money exact Decimal; never wait for the owner: build the spec-conformant, fail-closed side and record it under "Decided for the owner"; a clash between two of his rules is written under "Question for the owner", not decided.
