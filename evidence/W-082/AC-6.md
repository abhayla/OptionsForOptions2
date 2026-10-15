---
work_item: W-082
ac: AC-6
requirement: REQ-033
ac_fp: "042fb6fff274"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (sonnet, worktree agent)"
date: '2026-10-16'
commands: "python tools/ac_fp.py REQ-033 AC-6 --yaml; git diff --stat origin/main...origin/build/W-082-be-labels; python -m pytest -q -p no:cacheprovider tests/scenario|tests/table|tests/outcome|tests/engine (each separately, scratch worktree at b818294); python probe082.py (branch and origin/main); python mut082.py"
---

AC: AC-6
result: pass
commands: as in the frontmatter
observed: 31/54/54/676 passed; 10 brief cases + 4 extra labelled as hand-derived (zero-cost bull put -> Lower 22400; long/short call and put unchanged; iron condor 22909/23491 unchanged; zero-cost bull call -> Lower 22200; zero-cost bear put -> Upper 22400; credit-0 iron fly -> Lower = Upper = 23000; debit-0 reverse fly -> Lower 23000); breakeven values identical to origin/main in all 14; main mislabels zero-cost bull put, credit-0 iron fly and zero-cost short straddle, the branch is correct.
attack: extra shapes (zero-cost short straddle, zero-cost bear call, non-terminating BE 23116.67, zero-cost long straddle) correct; 5 of 6 in-memory mutants killed, the survivor is equivalent; no breakeven drift. Defects (non-blocking): ADR-089 wording ambiguous when profit lies on both sides with no loss (clarified in this PR: Lower BE, as the code does); no CI test for the short-straddle except-level path or a rounded single breakeven.

Recorded by the orchestrator from the verifier's returned block.
