---
work_item: W-083
ac: AC-1
requirement: REQ-061
ac_fp: "70db9d6d4a46"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (sonnet, worktree agent)"
date: '2026-10-16'
commands: "python -m pytest -q -p no:cacheprovider tests/reconciliation; python <scratchpad>/probe083/probe.py <scratchpad>/v083"
---

AC: AC-1
result: pass
commands: as in the frontmatter (verified at 6a0e2c7; round 3 at a27357a only moved the position parser to a neutral module, full domain suite 4190 passed)
observed: 157 passed; three groups NIFTY:2026-09-29 (1), NIFTY:2026-10-06 (4, resembling an Iron Condor), SENSEX:2026-10-01 (1); the in-strategy leg excluded; unresolved=[]. Rows built to Kite's documented position shape (no real position on the owner's account - unproven on real data, ADR-084).
attack: NRML+MIS rows of one contract -> two legs kept (round-1 CRITICAL fixed); quantity 0 / average 0 dropped before parsing; strategy 1 lot vs Zerodha 2 lots and an opposite side -> differs_from_strategy; unknown product / contract -> unresolved. Minor (#275): a second row with the same (contract, product) is silently dropped.

Recorded by the orchestrator from the verifier's returned block.
