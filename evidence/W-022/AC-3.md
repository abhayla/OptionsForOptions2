---
work_item: W-022
ac: AC-3
result: pass
verified_by: "verifier (opus, fresh context; second check W-022b)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "same runs; mutants M1, M2, M3, M4, M10"
---

AC: AC-3
result: pass
commands: same runs; mutants M1, M2, M3, M4, M10
observed: protective legs precede the sells that depend on them: covered call entered sell-first -> future first; covered put, calendar and diagonal protected; reversed diagonal and genuinely naked shorts flagged naked; strategies with no dependency keep the user's order (a sell may come first), so 'all buys first' is not hard-coded
attack: round 1 failed: futures and calendar protection ignored (covered call sent the short call first; review said naked). W-014 worst-case function confirmed unsuitable as the relation (covered put UNLIMITED from the future's own upside; calendar MultiExpiryError); the short future caps the downside the short put fears

Recorded by the orchestrator from the verifier's returned block.
