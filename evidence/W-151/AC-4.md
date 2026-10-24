---
work_item: W-151
ac: AC-4
requirement: REQ-119
ac_fp: "b98a43c14777"
result: pass
verified_by: "independent verifiers (Opus 23a check, round 2, redesign check; Opus 23b check, round 2)"
builder: "builders (Opus: 23a 3d57accf/e724981b + orchestrator lint 8ca82154, Sonnet fix 220923e9, Opus independent redesign c2e921bd; Sonnet: 23b 00b8ecba, fix f7445753)"
date: '2026-10-24'
commands: "same vitest run; probe P1, P4, P5, P6a, P6b, P7, P8 (verify-23b-r2)"
---

AC: AC-4
result: pass
commands: same vitest run; probe P1, P4, P5, P6a, P6b, P7, P8 (verify-23b-r2)
observed: While the newest outcome or leg-edit request has no applied reply, the numbers are marked updating and Execute is disabled ('Waiting for the latest numbers...'); numbers are drawn only when they match the legs and choice on screen (drawable = matchesLegs + matchesChoice for the REST reply, the leg-edit embedded outcome and the live push); a custom range is re-asked after an edit.
attack: round-1 MAJOR (at-expiry numbers under Estimated Now with Execute enabled) fixed: P1 newer request survives, stale numbers dropped, re-asked; no re-ask loop (P7). MINOR deferred: matchesChoice compares a typed range '22000' with the server's '22000.00' as text, so live pushes for a custom range are dropped (#532).

Recorded by the orchestrator from the verifier's returned block.
