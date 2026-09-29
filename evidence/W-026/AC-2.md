---
work_item: W-026
ac: AC-2
result: pass
verified_by: "verifier (opus, fresh context; round 3 W-026c against the independent review's bar)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "own public-name walk over 79 ofo modules; public attacks (direct Preparation, submit_confirmed with a raw Order, wrong choice, copy.copy with changed orders); mutants M5, M6, M8, M10"
---

AC: AC-2
result: pass
commands: own public-name walk over 79 ofo modules; public attacks (direct Preparation, submit_confirmed with a raw Order, wrong choice, copy.copy with changed orders); mutants M5, M6, M8, M10
observed: no public name aliases the sink, request, transport or mint; only submit_confirmed reaches the sink; every public attack refused with 0 transport calls; the round-1 naked 325 sell and the round-2 public mint_capability route no longer exist
attack: rounds 1-2 sent a naked 325 SELL, a sell for a non-existent strategy and a BANKNIFTY buy through public names. Round 3 designed after an independent review; judged against the agreed bar R1 (no public route except submit_confirmed), R2 (the sink derives every broker field), R3 (private-name reach-arounds out of scope, documented)

Recorded by the orchestrator from the verifier's returned block.
