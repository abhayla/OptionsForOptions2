---
work_item: W-151
ac: AC-2
requirement: REQ-119
ac_fp: "85c6a00bd255"
result: pass
verified_by: "independent verifiers (Opus 23a check, round 2, redesign check; Opus 23b check, round 2)"
builder: "builders (Opus: 23a 3d57accf/e724981b + orchestrator lint 8ca82154, Sonnet fix 220923e9, Opus independent redesign c2e921bd; Sonnet: 23b 00b8ecba, fix f7445753)"
date: '2026-10-24'
commands: "same vitest run on f7445753; mutant accept-ignores-seq (8 failed); probe P1/P8"
---

AC: AC-2
result: pass
commands: same vitest run on f7445753; mutant accept-ignores-seq (8 failed); probe P1/P8
observed: Request 1 then 2, answered 2 first then 1: the screen keeps reply 2; the older reply is dropped and logged at debug level; a reply for old legs or another choice is dropped and the numbers re-asked (outcome:3).
attack: a leg-edit reply landing before a newer outcome request no longer cancels it (aborted=false); a transport that ignores aborts still has the late reply dropped by seq.

Recorded by the orchestrator from the verifier's returned block.
