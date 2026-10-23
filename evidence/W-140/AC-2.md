---
work_item: W-140
ac: AC-2
requirement: REQ-072
ac_fp: "d0a6b6685613"
result: pass
verified_by: "independent verifiers (Opus, fresh context; start check on f9a8d780, DB part Sonnet on fb9a3702, round 2 on fix d76cd0e0)"
builder: "builders (earlier work items; builder sequence row 12 fix 1, Sonnet)"
date: '2026-10-23'
commands: "start check found PARTIAL (MINOR): a missing index quote with the feed live was refused with the forward reason; fix 1 d76cd0e0 (row-12-fix-1.md); round 2 (Opus, fresh, verify-row-12-r2.md) PASS"
---

AC: AC-2
result: pass
commands: start check found PARTIAL (MINOR): a missing index quote with the feed live was refused with the forward reason; fix 1 d76cd0e0 (row-12-fix-1.md); round 2 (Opus, fresh, verify-row-12-r2.md) PASS
observed: stale spot (+90 s, +3 h) labelled 'stale since 09:20 IST'; unavailable after a disconnect refused; after fix 1 the spot gate answers before the forward errors in outcome/service.py, so a missing index quote is refused with the index reason. Round 2 MINOR: the except SpotRefused safety net was removed, and the missing-leg + missing-index case is untested (chunk deferred issue)
attack: round 1: missing index quote with a live feed; round 2: findings-only re-check of fix 1

Recorded by the orchestrator from the verifier's returned block.
