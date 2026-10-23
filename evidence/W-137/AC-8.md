---
work_item: W-137
ac: AC-8
requirement: REQ-113
ac_fp: "ad66f808d252"
result: pass
verified_by: "independent verifiers (Opus, fresh context; final round on 4b829faf)"
builder: "builders (Sonnet, builder sequence row 9: parts A0, A1, B, C and their fix/finish rounds)"
date: '2026-10-23'
commands: "final round: mutants M07-M09, M14; a real-store probe"
---

AC: AC-8
result: pass
commands: final round: mutants M07-M09, M14; a real-store probe
observed: at expiry the feed closes that user's socket, publishes one ended event, never reconnects (feed_main.py:241-277). MINOR (deferred issue): with the real store the status turns stopped one re-check after the ended event; a DB outage at 06:00 keeps the socket open (read failure returns before the in-memory expiry check)
attack: expiry never reached / ended session reconnects / no ended event / two-query race -> all killed

Recorded by the orchestrator from the verifier's returned block.
