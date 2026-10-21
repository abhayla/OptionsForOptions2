---
work_item: W-116
ac: AC-4
requirement: REQ-029
ac_fp: "0feb6a84cbb3"
result: fail
verified_by: "verifier (opus, fresh context, Tier A; round 1 ff7cf11 FAIL, round 2 6562054, 2026-10-19)"
builder: "builder (W-116, opus, 2 rounds)"
date: '2026-10-19'
commands: "scratch b1.py, b2.py; same pytest command"
---

AC: AC-4
result: fail
commands: scratch b1.py, b2.py; same pytest command
observed: Under 0.1 s ticks for 20 s OI changed at 1, 5, 10, 15, 20 s; bid/ask strings, 0 -> null; min gap between sends 1.0 s. BACKEND PART PROVEN: LTP and bid/ask live, OI at a lower frequency. NOT MET AS WRITTEN: IV is not carried (needs the one engine, ADR-008).
attack: OI starvation under constant LTP ticks: not starved. push+error, refusal+push, re-centre+push in one second: never 2 messages. MINOR deferred: a client sending a bad message every second gets 0 pushes (self-starvation).

Recorded by the orchestrator from the verifier's returned block.
