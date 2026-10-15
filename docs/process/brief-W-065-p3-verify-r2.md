# Verifier brief: W-065 phase 3 round 2 (fresh context), Tier A, AC-4

Core: when this page's own socket is down, the screen never shows numbers as live, whoever else holds the contracts.
Proof: re-run the two-holder attack and the round's tests yourself; do not trust the builder's report.

Model: opus. Why Opus: Tier A re-verification after a FAIL; adversarial judgement of a new request flag that changes
the REST outcome contract.
Budget: 45 min wall-clock, 32 tool calls (verifier maxTurns 40; batch commands).
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), then the JSON block below.

## Where
- Worktree `D:\Abhay\Ventures\OptionsForOptions2-W-065v`, branch `build/W-065-frontend` at 26b3df4 (round 2 = commits
  after f5f6681; main merged in). Read-only: edit nothing, commit nothing; logs and scratch scripts under `%TEMP%`.
- Round 1 brief (all its checks still apply): `docs/process/brief-W-065-p3-verify.md`. Round 1 result: FAIL - with a
  second socket on the same legs, the REST fallback after this page's socket dropped answered COMPUTED, unlabelled.
  The round 1 attack script:
  `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\4b112add-c2b9-4a08-b5d6-b3bbac8c47e6\scratchpad\attack_two_holders.py`
- Round 2 fix brief: `docs/process/brief-W-065-p3-r2.md` (OutcomeRequest `fallback` flag; the page sends it after a
  drop; no flicker; a push for other legs is dropped).
- AC: REQ-035 AC-4, `ac_fp` faa18f01993e.

## Spec basis
- ADR-077: "When a strategy's live connection to the platform drops (the browser's own socket closes) and the screen
  falls back, it shows REQ-049 AC-5's message"
- REQ-049 AC-4: "Screens show when data is stale or unavailable instead of presenting old numbers as live."
- ADR-068 (2): "the screen falls back to a REST refresh when the socket is down, labelled as not live"
- REQ-035 AC-4: "Entry Price, LTP, Entry Value, Current Value, Unrealized P&L and P&L % update live"

## Attack (how could round 2 still fail?)
1. The round 1 attack, adapted to send `fallback: true` as the page now does: not-live with AC-5's exact text and the
   newest price time, no numbers.
2. When does the page clear the flag? Find any path where the page shows numbers from a `fallback: false` answer
   while its own socket is down or off (reconnect timing, a leg edit during the outage, MAX_ATTEMPTS reached, page
   reload, navigation away and back).
3. The leg-match rule for pushes: can a legitimate push for the current strategy be dropped (e.g. legs equal but in a
   different order, a decimal written differently such as "42.7" vs "42.70")? A dropped legitimate push freezes the
   live screen.
4. The flag is part of the public outcome API: any other caller (the leg picker, the planned-entry route, the live
   push itself) that now sends or misreads it; the OpenAPI drift test is green on the regenerated files.
5. Round 1's LOW items: are they fixed or still present (late push of the previous strategy; flicker).

## Commands
As in round 1's brief: the app tests through `db_run.py` (targeted files: `tests_app/test_strategy_live_push.py`,
`tests_app/test_outcome_route.py`, `tests_app/test_openapi_drift.py`), `npx vitest run`, and Playwright
`e2e/strategy-live.spec.ts` on the replay (placeholder `KITE_*`/`BROKER_TOKEN_KEY` from app-tests.yml lines 80-84;
`PW_CHROMIUM_PATH` for the local Chromium). Stop every server by PID.

## Return
Evidence table, then exactly one JSON block:
```json
[{"ac": "AC-4", "requirement": "REQ-035", "ac_fp": "faa18f01993e", "result": "pass|fail",
  "commands": "...", "observed": "...", "attack": "..."}]
```
Plus defects (file:line, severity), if any.
