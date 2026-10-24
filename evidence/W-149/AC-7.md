---
work_item: W-149
ac: AC-7
requirement: REQ-077
ac_fp: "b9c604065573"
result: pass
verified_by: "independent verifiers (Opus part checks 21m/21b/21a/21d with round 2; Sonnet 21c check + round 2; Opus CI-fix check + round 2; Opus row 21 closing check on 9730cda2)"
builder: "builders (Opus: 21m 8a3bf0d2, 21b 8f5dc56e, 21a c851c84d, 21d 6d4ae53f; Sonnet: 21c f1a5e938 + fix 264576bb, CI fix 6bac88cf..ab38cd8d)"
date: '2026-10-24'
commands: "vitest and app runs as above; mutant M6 routes/leg_edit.py:360 makes 'read' re-capture unpriced legs"
---

AC: AC-7
result: pass
commands: vitest and app runs as above; mutant M6 routes/leg_edit.py:360 makes 'read' re-capture unpriced legs
observed: apply_edit 'read' returns (legs, frozenset()) (leg_edit.py:319-320): nothing is captured on reopen. A leg saved without an entry reopens with (None, None, None) and keeps the ADR-085 reprice path. Frontend (21c): opening a draft sends only the read control.
attack: M6 SURVIVED (26 passed): no backend test sends 'read' with an unpriced leg while a live price exists. Code correct by reading; MINOR test gap deferred to #532.

Recorded by the orchestrator from the verifier's returned block.
