---
work_item: W-133
ac: AC-3
requirement: REQ-053
ac_fp: "3881e2d63aea"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 2 on 11e5546f)"
builder: "builder (Sonnet, builder sequence row 5: build, finish 1, finish 2, fix round 1)"
date: '2026-10-22'
commands: "rounds 1-2; same run; verifier sched_attack.py; orchestrator live run 2026-10-22 13:31 IST: python -m ofo_app.catalogue_load on ofo_dev (added=4 seen=4974)"
---

AC: AC-3
result: pass
commands: rounds 1-2; same run; verifier sched_attack.py; orchestrator live run 2026-10-22 13:31 IST: python -m ofo_app.catalogue_load on ofo_dev (added=4 seen=4974)
observed: READ part (the before-execution repeat is order-path scope): the add-time check, the picker offer, the pre-execution registry and execute.py _list_health judge the list on the database clock as current from 08:30 IST of the most recent weekday session (F-56); a list loaded before that is unconfirmed (gate_contract_unconfirmed); a Friday load stays current over the weekend; the catalogue reloads at start-up and hourly 08:35-15:45 IST on weekdays through the guarded loader (F-33's intraday additions), the parse off the event loop, a hung fetch ends at its socket timeout
attack: round 1: tests judged 'tomorrow' and failed on Fridays/Saturdays (fixed: next weekday, Mon-Sun parametrized); 08:29:59.999 stale, 08:30:00 current. MINOR deferred #516: a restart at 08:16-08:29 delays the first current load to ~09:30 (fails safe: unconfirmed, never stale-as-current)

Recorded by the orchestrator from the verifier's returned block.
