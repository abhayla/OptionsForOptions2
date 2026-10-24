---
work_item: W-151
ac: AC-3
requirement: REQ-119
ac_fp: "df9567468d7f"
result: pass
verified_by: "independent verifiers (Opus 23a check, round 2, redesign check; Opus 23b check, round 2)"
builder: "builders (Opus: 23a 3d57accf/e724981b + orchestrator lint 8ca82154, Sonnet fix 220923e9, Opus independent redesign c2e921bd; Sonnet: 23b 00b8ecba, fix f7445753)"
date: '2026-10-24'
commands: "same vitest run; probe P2/P3; execute-screen 'cancelled prepare' test"
---

AC: AC-3
result: pass
commands: same vitest run; probe P2/P3; execute-screen 'cancelled prepare' test
observed: The older in-flight request of the same kind is aborted (AbortController signal through api.js); an aborted request rejects as superseded and shows no error; only a real failure of the newest request shows its error.
attack: mutant 'cancel shown as an error' (api and Execute page) killed; an aborted prepare leaves no execute-error.

Recorded by the orchestrator from the verifier's returned block.
