---
work_item: W-021
ac: AC-3
requirement: REQ-060
ac_fp: "47d71bdf3eb3"
result: fail
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builders (W-021, W-037, W-085; live path W-095, W-096)"
date: '2026-10-17'
commands: "same pytest run; read backend/ofo_app/routes/execution_return.py:286-330; grep record_report and audit in backend/ofo_app"
---

AC: AC-3
result: fail
commands: same pytest run; read backend/ofo_app/routes/execution_return.py:286-330; grep record_report and audit in backend/ofo_app
observed: The domain Mismatch carries time, broker state, platform state, difference and next action, validated on construction. The live _answer() only returns per-contract units, a catalogue id and read_at; it writes no mismatch record (order_audit records external orders and the broker book only; resolution.record_report is never called from ofo_app); no next-action text, no difference field.
attack: checked whether the live route persists a mismatch record: it does not; the reply is lost after the screen renders. Domain: a Mismatch with a non-int unit or a naive datetime is refused

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
