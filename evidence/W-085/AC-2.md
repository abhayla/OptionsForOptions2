---
work_item: W-085
ac: AC-2
requirement: REQ-060
ac_fp: "d4b747da20aa"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (sonnet, worktree agent)"
date: '2026-10-16'
commands: "pytest tests/reconciliation; pytest tests/strategy; probe085b/r3.py; probe085b/blk.py; probe085/cases.py (scratch worktree at 43470d2)"
---

AC: AC-2
result: pass
commands: as in the frontmatter (verified at 43470d2; the merge with main renumbered the two new templates to 219/220 and the full domain suite passed, 4221)
observed: 145/437 passed; calendar awaiting + standalone overlap -> AWAITING_SETTLEMENT not blocking, blocked ids []; settles at 118.85 once a price arrives, P&L 2290.00 equals the hand check (233.35 - 118.85) x 20; QUANTITY / MISSING / EXTERNAL / SIDE mismatches still block; a failing timeline store leaves the record unchanged and a retry settles.
attack: the round-2 failing overlap case is now a note; Zerodha keeping the standalone quantity, a non-awaiting second holder, and an external change all still block. Observations carried to #279: settlement must run before reconciliation after the close; an expired standalone stays an awaiting note forever; two mismatch labels.

Recorded by the orchestrator from the verifier's returned block.
