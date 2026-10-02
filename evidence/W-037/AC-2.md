---
work_item: W-037
ac: AC-2
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/reconciliation; python -m pytest -q -p no:cacheprovider; own python stdin scripts (random equivalence vs git show origin/main compare.py; AST compare of compare_reference.py; 6 source mutants via pytest.main; sys.setprofile call counts 100/200 and wall time 800; builder scaling test against origin/main code)"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/reconciliation; python -m pytest -q -p no:cacheprovider; own python stdin scripts (random equivalence vs git show origin/main compare.py; AST compare of compare_reference.py; 6 source mutants via pytest.main; sys.setprofile call counts 100/200 and wall time 800; builder scaling test against origin/main code)
observed: 103 passed; 1307 passed; equal on 2212 reports + 788 identical refusals, all 9 kinds, 438 multi-holder mismatches; 9/9 reference functions AST-identical to origin/main; mutants killed 3/4/1/12/5/5; call ratio 1.985/1.997 new vs 3.537/3.604 old; wall800 30ms/24ms new vs 491ms/402ms old; scaling test red on origin/main (2 failed)
attack: moved leg with two candidate holders, held leg with multiple unheld candidates, FUT expiry moves, contracts shared by up to 5 holders (Q224), exited/proposal-only/never-active strategies, standalone on held contracts, pairing/holders/others/share mutants: all identical to origin/main or caught

Recorded by the orchestrator from the verifier's returned block.
