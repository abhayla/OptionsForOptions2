---
work_item: W-042
ac: AC-2
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "git worktree add --detach <SCRATCH>\\verify\\W-042 origin/build/W-042-catalogue-guard; python -m pytest -q -p no:cacheprovider tests/instruments; python -m pytest -q -p no:cacheprovider; python - (probe against tests/fixtures/instruments/instruments_slice.csv)"
---

AC: AC-2
result: pass
commands: git worktree add --detach <SCRATCH>\verify\W-042 origin/build/W-042-catalogue-guard; python -m pytest -q -p no:cacheprovider tests/instruments; python -m pytest -q -p no:cacheprovider; python - (probe against tests/fixtures/instruments/instruments_slice.csv)
observed: tests/instruments 32 passed; full suite 1351 passed. drop live row: REFUSE naming the contract; 75% NIFTY truncation: REFUSE (121 dropped); roll-off of 277 contracts expiring 09-29 at 09-30 00:00 and 00:30 IST: ACCEPT (newly_unlisted=277, none deleted); expiry==as_of IST date at 10:00 and 23:59 IST: REFUSE; 18:29Z 09-29: REFUSE; 18:30Z: ACCEPT; naive as_of: ValueError timezone-aware; None expiry dropped: REFUSE; force=True: ACCEPT; refused update leaves state unchanged (1085/1085)
attack: Boundary and timezone (IST vs UTC date, 23:59 IST, 18:29Z vs 18:30Z, 00:30 IST), naive/missing as_of, no-expiry contract, empty list, 75% truncation, force override, state unchanged after refusal: all per Q244. Residual: force has no caller restriction, log or reason (only tests use it today); two execution tests use force=True but still assert CONTRACT_NOT_LISTED so are not weakened; no unit test for exactly 18:29Z (probe only).

Recorded by the orchestrator from the verifier's returned block.
