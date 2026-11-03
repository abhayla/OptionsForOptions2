---
work_item: W-203
requirement: REQ-156
ac: AC-3
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "dee8afd46ca3"
commands: "python -m pytest -q -p no:cacheprovider tests/adjustment/test_approach_compare.py; cd frontend && npx vitest run tests/adjust-compare.test.js"
---
leaders() (compare.py:201) skips cells without a rank, names every tied column, returns () when none can lead; tests cover ties, dash/no-rank cells, Unlimited max loss cannot lead, and exit 'No position left after exit' with no rank in the Greeks rows. Frontend isLeader also requires unavailable_reason null.

Recorded by the orchestrator from the verifier's returned block.
