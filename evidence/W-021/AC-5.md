---
work_item: W-021
ac: AC-5
requirement: REQ-060
ac_fp: "3618bbeb3d81"
result: fail
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builders (W-021, W-037, W-085; live path W-095, W-096)"
date: '2026-10-17'
commands: "same pytest run; scratch attack.py, ev.py; grep backend/ofo_app for adopt_broker, mark_requires_attention, standalone"
---

AC: AC-5
result: fail
commands: same pytest run; scratch attack.py, ev.py; grep backend/ofo_app for adopt_broker, mark_requires_attention, standalone
observed: Domain refuses an empty reason, a blank actor and an adopt on an older report; adopt writes RECONCILIATION_RECORDED and clears the flag. Live app: no route calls any resolution function (0 call sites), so a product user cannot reconcile manually at all.
attack: empty reason, whitespace actor and an older report are all refused by the domain; no app path offers manual reconciliation

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
