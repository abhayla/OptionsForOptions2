---
work_item: W-137
ac: AC-9
requirement: REQ-113
ac_fp: "06e8d3ce223c"
result: pass
verified_by: "independent verifiers (Opus, fresh context; final round on 4b829faf)"
builder: "builders (Sonnet, builder sequence row 9: parts A0, A1, B, C and their fix/finish rounds)"
date: '2026-10-23'
commands: "final round: DB run; mutants M01, M15; 5 re-runs of the flaky test (5 of 5 pass), fixed by the orchestrator (wait for the server's close count)"
---

AC: AC-9
result: pass
commands: final round: DB run; mutants M01, M15; 5 re-runs of the flaky test (5 of 5 pass), fixed by the orchestrator (wait for the server's close count)
observed: one task per user; reconcile catches errors per user (feed_main.py:219-223); killing A's Kite server leaves B flowing; an exception in A's frame handling leaves B untouched
attack: per-user catch removed or halt raising -> killed; raising start/stop for A during reconcile -> killed (finish 2)

Recorded by the orchestrator from the verifier's returned block.
