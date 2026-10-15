# Verifier brief: W-073 live-push matcher, socket fallback flag, draft label, contract names (Tier A)

Core: a Builder page opened from a draft link with lots `02` and planned entry `042.70` keeps applying live pushes
instead of freezing on the first answer, and a link it cannot canonicalize is refused before any request.
Proof: re-run the tests and the e2e yourself; the builder's report and the reviewer's are claims.

Model: opus (Tier A verifier).
Budget: 35 min wall-clock, 35 tool calls (batch commands). HARD limit: at call 32 stop and return what you have.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), then the JSON block below.

## Where
- Branch `build/W-073-live-push-lows` at the head named in your dispatch; the read-only checkout named there has
  frontend packages installed. Diff: `git diff origin/main...HEAD`.
- Brief + reviewer checklist: `docs/process/brief-W-073.md`; card `work/W-073.md`; issues #234, #221.
- AC: REQ-035 AC-4. Fingerprint: `python tools/ac_fp.py REQ-035 AC-4 --yaml` (main checkout).

## Spec basis
- REQ-035 AC-4: "Entry Price, LTP, Entry Value, Current Value, Unrealized P&L and P&L % update live"
- ADR-020: drafts marked "Draft — Live data not connected"

## Check (how could it fail?)
1. `npx vitest run` (all) in `frontend/`; `npm run lint`; `npm run build`.
2. Domain: `python -m pytest -q -p no:cacheprovider tests/outcome tests/errors`.
3. App, targeted only, through the main checkout's `scripts/orchestrator/db_run.py <checkout> python -m pytest -q -rs
   -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_socket_fallback.py tests_app/test_strategy_live_push.py
   tests_app/test_outcome_route.py tests_app/test_outcome_catalogue.py` (never the full app suite: the test database sits
   on a production host).
4. Playwright `e2e/strategy-states e2e/strategy-live e2e/leg-picker e2e/strategy-display-format` with the servers
   `.github/workflows/app-tests.yml` starts (the builder used `dev_run.py` for the API because `db_run.py` sets only the
   test-database variable; set the placeholder Kite settings from the workflow; previews 4173/4174/4175;
   `PW_CHROMIUM_PATH=D:/ms-playwright/chromium-1223/chrome-win64/chrome.exe` if headless shell 1243 is missing).
   Stop every server by PID and confirm the ports are free.
5. AC-4 live behaviour: with the replay server (OUTCOME_REPLAY=1), do two consecutive pushes both reach the page for a
   draft link with lots `02` / entry `042.70`? Attack: a draft link whose legs differ from the pushed legs by one
   strike or one lot - the push must NOT be applied.
6. One attack of your own on the refusal path (a link with `"lots":"2.0"`) in the browser: four-part error, no request.
Never write in either checkout; never write `evidence/`.

## Return
Evidence table, then one JSON block:
```json
[{"ac": "AC-4", "requirement": "REQ-035", "ac_fp": "<from ac_fp.py>", "result": "pass|fail",
  "commands": "...", "observed": "...", "attack": "..."}]
```
Plus defects (file:line, severity).
