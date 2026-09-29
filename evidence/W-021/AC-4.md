---
work_item: W-021
ac: AC-4
result: pass
verified_by: "verifier (opus, fresh context; rounds W-021 to W-021g)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/reconciliation/test_external_change.py; attack scripts"
---

AC: AC-4
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/reconciliation/test_external_change.py; attack scripts
observed: external change -> EXTERNAL_MODIFICATION, EXTERNAL_BROKER_CHANGE_DETECTED, flag set; record_report is two-phase: a refused run (later strategy refuses, first strategy refuses, full outcome log, bad payload, bad run id) writes nothing and can be retried, the retry audits exactly once
attack: round 1 left strategy A flagged with 0 audit events; round 2 validated payloads in phase 2 only; both fixed and tested. Hardening note: phase 1 checks storability, not unit type, under a constructor bypass

Recorded by the orchestrator from the verifier's returned block.
