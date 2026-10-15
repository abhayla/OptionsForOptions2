# Goal contract 2026-10-15: close Stage 4a, then 4b and 4c, to the core gate

Core: live Kite prices -> engine -> saved strategy -> screen, then one real basket order -> Zerodha confirmation ->
reconcile -> one rule firing with an alert.
Proof: the W-065 live push on the owner's real Kite session (first run 2026-10-15 11:43 IST: 59 pushes, minimum gap
1.011 s, LTP and P&L moving; the strict health check counted the pre-first-tick push, see the evidence), then each
stage gate below on real data.

Owner-approved 2026-10-15 (plan rev 2 after an independent Opus review). Master plan: `master-plan-2026-10-07.md`
(its rules, gates and stage order stay in force: "No stage starts before the previous stage's gate has passed").

## Goal
The master-plan core gate (core-invariants section 4) passes with evidence; REQ-065 is either Verified or named as
an open exception under ADR-074. Then the ADR-060 demo-ready milestone is next.

## Phases (one session per phase; each ends with a DONE / PENDING / BLOCKED / PARKED / NEXT handover)
| Phase | Done-test |
|---|---|
| 1. Stage 4a close-out | W-065 core proof recorded and verified; W-066 (#172) merged and verified, or parked; #200 one round (pass: REQ-065 Verified; fail: parked, ADR-074); #199, #89, #110, #204 merged and verified, or parked; the four live gate checks recorded (D8 formula on live inputs, draft reload, screenshots, real REST captures); the token-expiry probe recorded; the 4a gate review written |
| 2. Stage 4b | 4b questions numbered and decided (user-visible ones by the owner); basket, margin check, safeguards, failed legs built through deliver (Tier A) on real captures; the real order placed by the owner; confirmation, reconcile, existing positions and W-017 built and verified on the real responses; the 4b gate passed |
| 3. Stage 4c | 4c questions decided; monitoring statuses, alert + prepared orders, in-app alerts built and verified; Notifier onboarded after the release record and the owner's typed go; a real rule fires on live data and the WhatsApp alert is delivered (terminal status read); the core gate passed |

## The only stops (owner touchpoints)
1. One Kite login per working day that needs live data, in a PRIVATE browser window (the normal window holds
   another Kite account's session and gets "The user is not enabled for the app").
2. The 4b questions that change what a user sees, one at a time.
3. The real order (the owner places our basket on Kite and exits it).
4. The typed go for the Notifier change on the shared production host.

Nothing else stops the run: green CI, rebases, merge conflicts, issues, briefs, dispatches, worktrees and the next
approved item are not stops.

## Owner away
No interactive questions. A choice the spec already settles is decided and recorded like an owner answer (a decision
row plus a log line). Anything needing the owner goes to `docs/process/owner-questions-<date>.md` with a
recommendation, and the run continues with other items.

## Park rule
Two failed rounds on an item, a real-world proof overdue by 2 working days, or an outside blocker: open a `parked`
issue with the evidence and what is left, note it in the handover, move on. A parked item never blocks the others.

## Delivery rules (unchanged from the master plan and CLAUDE.md)
- Every brief: Core/Proof, `Budget:` (Tier B 30 min/60 calls, Tier A 60 min/80 calls for builders, which stop at
  80% of their turn limit), `Copy from:`, a verbatim Spec basis checked by `check_brief.py`, the reviewer checklist,
  `Report: evidence-table`, and a model on every dispatch (Opus with a `Why Opus:` line).
- Builder, then an independent verifier (Opus for Tier A), then evidence by the orchestrator, then a PR with the
  Spec-deviation block, then `merge_when_green.py`.
- The test database lives on a production host: targeted test files only; full suites in CI.
- Generated files only in batched docs PRs; CI's checks run locally before every push.
- No recurring timer inside a session.
