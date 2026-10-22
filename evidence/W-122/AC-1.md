---
work_item: W-122
ac: AC-1
requirement: REQ-109
ac_fp: "29fbf1f96e69"
result: pass
verified_by: "independent Tier A verifier round 3 (Opus, fresh context)"
builder: "builder (Opus, agent worktrees a5bfdcb6 then fresh redesign a3203dd4)"
date: '2026-10-22'
commands: "db_run pytest tests_app/test_strategy_tracking.py test_strategy_tracking_imports.py test_strategy_tracking_allowlist_chain.py + verifier scratch cases (a)-(e); verified sha 21642978dc196a79ccd95fc8f7bfbb53d2453a58"
---

AC: AC-1
result: pass
commands: db_run pytest tests_app/test_strategy_tracking.py test_strategy_tracking_imports.py test_strategy_tracking_allowlist_chain.py + verifier scratch cases (a)-(e); verified sha 21642978dc196a79ccd95fc8f7bfbb53d2453a58
observed: all 36 branch tests passed; a Start with a retired, delisted or reused-token leg returns 409 tracking_contract_not_live and writes 0 rows; strategy_tracking/_legs counts 0/0 after the runs
attack: reused token, retired, delisted, delisted-then-relisted, contract with no broker row (fails closed as contract_missing); same-holder mutation goes red. Rounds: 1 REVISE (view read the saved strategy), 2 REVISE (reused token priced), 3 PASS WITH MINORS after an independent redesign.

Recorded by the orchestrator from the verifier's returned block.
