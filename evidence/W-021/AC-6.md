---
work_item: W-021
ac: AC-6
requirement: REQ-060
ac_fp: "4117fa996556"
result: fail
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builders (W-021, W-037, W-085; live path W-095, W-096)"
date: '2026-10-17'
commands: "same pytest run; scratch attack.py; read backend/ofo/execution/safety.py:382-385, backend/ofo_app/routes/execute.py:475-486, backend/ofo_app/execute_plan.py:233-243"
---

AC: AC-6
result: fail
commands: same pytest run; scratch attack.py; read backend/ofo/execution/safety.py:382-385, backend/ofo_app/routes/execute.py:475-486, backend/ofo_app/execute_plan.py:233-243
observed: Domain: after a mismatch an agreeing run leaves the gate blocked until a recorded adopt (Q222). Live Execute blocks a shortfall, the opposite side, a flat broker and an unreadable reply, but keeps no block: once positions agree again it executes with no recorded resolution (breaks Q222); it compares only this strategy's units, not other strategies' units on the same contract.
attack: A and B each SELL 75 of one CE, the user buys 75 back in Kite (broker -75): strategy_blocked A False, B False, both may execute (Q224: every holder blocks); a mismatch followed by an agreeing read unblocks with nothing recorded

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
