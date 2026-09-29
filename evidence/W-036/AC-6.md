---
work_item: W-036
ac: AC-6
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "git worktree add --detach <SCRATCH>/verify/W-036 origin/build/W-036-close-refusal; python -m pytest -q -p no:cacheprovider tests/execution/test_close_refusals.py tests/execution/test_close_slices.py; python -m pytest -q -p no:cacheprovider; git show origin/main:backend/ofo/execution/partial.py executed in memory against both test files; python stdin probes (reasons, scenarios A-D); python -c mutants M1-M3"
---

AC: AC-6
result: pass
commands: git worktree add --detach <SCRATCH>/verify/W-036 origin/build/W-036-close-refusal; python -m pytest -q -p no:cacheprovider tests/execution/test_close_refusals.py tests/execution/test_close_slices.py; python -m pytest -q -p no:cacheprovider; git show origin/main:backend/ofo/execution/partial.py executed in memory against both test files; python stdin probes (reasons, scenarios A-D); python -c mutants M1-M3
observed: 33 passed; 1305 passed in 153.17s; on main code: 11 failed, 22 passed; reasons 'Nothing prepared: NIFTY26O0623000PE: the freeze quantity is below one lot of 65.' / 'Nothing prepared: freeze quantity of NIFTY26O0623000PE must be a positive integer, got 0.'; Complete on a later read prepares and clears the marker; gate-blocked Complete keeps marker, later Retry ready and clears it; Close after refused Close ready; M2 and M3 each killed by 1 targeted test, M1 survived (near-equivalent)
attack: Every Close refusal path (missing LTP, exits in flight, freeze < lot NIFTY/SENSEX, non-whole lots, freeze 0, gate block, stale read mid-prepare): no mark_closing, no held preparation, Complete/Retry usable. Stuck-marker sequence Close -> Complete refused -> Close again -> Complete on fresh read: not stuck. Changed close_slices tests are stronger (prefix + reason + marker None), red on main. Gaps (non-blocking): Complete/Retry slicing refusal still raises ValueError rather than returning a reason (no state change); mutant M1 survives but is near-equivalent; a docstring says +100 s vs asserted +70 s.

Recorded by the orchestrator from the verifier's returned block.
