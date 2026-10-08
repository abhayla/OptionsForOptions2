---
work_item: W-059
ac: AC-4
requirement: REQ-048
ac_fp: "2a005452c53f"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-10-08'
commands: "python tools/ac_fp.py REQ-048 AC-4 --yaml; python -m pytest -q -p no:cacheprovider tests/marketdata/test_fanout_replay.py; python ../atk.py (scratchpad script: 999 normal subscribers plus one never-draining subscriber with max_queue=50, real fixture)"
---

AC: AC-4
result: pass
commands: python tools/ac_fp.py REQ-048 AC-4 --yaml; python -m pytest -q -p no:cacheprovider tests/marketdata/test_fanout_replay.py; python ../atk.py (scratchpad script: 999 normal subscribers plus one never-draining subscriber with max_queue=50, real fixture)
observed: vendor_subscribe 1091 ticks 7301; dead queue 50 dropped 7251 lagging True; others full True (all 999 others got 7,301 quotes); KeyError ok 1000. The repo test also shows 1000 inboxes identical, 7,301 ticks each, and that the last unsubscribe releases the vendor subscription.
attack: Added a subscriber that never drains. Its queue stopped at its cap (50), the 7,251 drops were counted, the lagging flag was set, the producer never blocked, and the other 999 subscribers got every tick in order. A raising listener is counted and skipped, and the repo test covers that. The 'never drains' case itself is not covered by the repo's own tests; it was proven with the verifier's script.

Recorded by the orchestrator from the verifier's returned block.
Recorded 2026-10-08 at PR #131 head c75e776. Review: Tier B diff review, 1 round, MAJOR findings fixed (see AC-2.md).
