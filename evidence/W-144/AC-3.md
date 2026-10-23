---
work_item: W-144
ac: AC-3
requirement: REQ-038
ac_fp: "fefda3f93eb2"
result: fail
verified_by: "independent verifiers (Opus, fresh context; round 1 on d99b2097, round 2 on 735ba1a6; DB part CI #525 on f5a1059c)"
builder: "builders (Opus, builder sequence row 16: build, fix 1)"
date: '2026-10-23'
commands: "round 1 (Opus) on d99b2097 (time-only plan match, MAJOR); fix 1; round 2 (Opus) on 735ba1a6: version link fixed; DB part CI #525"
---

AC: AC-3
result: fail
commands: round 1 (Opus) on d99b2097 (time-only plan match, MAJOR); fix 1; round 2 (Opus) on 735ba1a6: version link fixed; DB part CI #525
observed: activation needs a confirmed pending version and a reconciled return of a plan whose strategy_version equals it (strategy_store.py:495-497); the database CHECK requires active rows confirmed and reconciled. Not proven end to end: Execute builds plans only from the ACTIVE version (execute.py:294, :400) and refuses an ENTRY while units are held (execute.py:338-346), so no live plan can activate a proposal; the adjustments row closes this. Latent MINORs #527
attack: a reconciled plan built from version 1 never activates confirmed version 2 (core test); unconfirmed proposal never judged

Recorded by the orchestrator from the verifier's returned block.
