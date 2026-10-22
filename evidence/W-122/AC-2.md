---
work_item: W-122
ac: AC-2
requirement: REQ-109
ac_fp: "2d24e1ab96e6"
result: pass
verified_by: "independent Tier A verifier round 3 (Opus, fresh context)"
builder: "builder (Opus, agent worktrees a5bfdcb6 then fresh redesign a3203dd4)"
date: '2026-10-22'
commands: "verifier scratch test_a_reuse, test_b, test_c, test_e; mutation run; verified sha 21642978dc196a79ccd95fc8f7bfbb53d2453a58"
---

AC: AC-2
result: pass
commands: verifier scratch test_a_reuse, test_b, test_c, test_e; mutation run; verified sha 21642978dc196a79ccd95fc8f7bfbb53d2453a58
observed: the reused token gives PAUSED token_reassigned with paper_pnl null and leg 0 current_price null (never 45.15 or +195.00); after an edit the view is still LIVE at 195.00 (= -390 + 130 + 780 - 325) with quantities 65 x4
attack: round-1 edit case, round-2 reuse case, removing the same-holder check

Recorded by the orchestrator from the verifier's returned block.
