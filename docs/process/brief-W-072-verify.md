# Verifier brief: W-072 contract names, IST times, four-part errors (Tier B)

Core: the real Builder page shows each leg by contract name, every time as `15 Oct 2026, 11:59:59 IST`, and every
catalogue error with four labelled parts - no raw id or ISO time on the page.
Proof: re-run the core e2e yourself; the builder's report is a claim.

Model: sonnet (Tier B verifier).
Budget: 30 min wall-clock, 30 tool calls (batch commands). HARD limit: at call 27 stop and return what you have.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), then the JSON block below.

## Where
- Checkout (read-only, frontend packages installed): the scratchpad folder `v072` named in your dispatch, branch
  `build/W-072-display-format` at 54dbfaa. Diff: `git diff origin/main...HEAD -- frontend`.
- Brief with the reviewer checklist: `docs/process/brief-W-072.md`. Work item `work/W-072.md` (card correction: in
  NOT_CONNECTED / not-live answers a draft-URL leg reads `Contract details not available` - moved to W-073).
- AC: REQ-039 AC-3. Fingerprint: `python tools/ac_fp.py REQ-039 AC-3 --yaml`.

## Spec basis
- REQ-039 AC-3: "Every important non-normal state shows what happened, when, what is blocked and the next action"
- ADR-086: "every leg is named by its contract" and "every time is shown in India time"

## Check (how could it fail?)
1. `npx vitest run` in `frontend/` (all), then `TZ=America/New_York npx vitest run tests/display-format.test.js`.
2. The e2e core spec and the existing Builder specs, with the servers `.github/workflows/app-tests.yml` starts (read it
   for the exact commands, ports 8000/8001 and previews 4173/4174/4175): `npx playwright test e2e/strategy-display-format
   e2e/strategy-states e2e/strategy-live e2e/leg-picker e2e/strategy-table`. Use the main checkout's
   `scripts/orchestrator/db_run.py <checkout> ...` for the API so the test database variables are set. Stop every
   server by PID and confirm the ports are free.
3. For AC-3 on the not-connected, stale, refused and error states: does each still show what happened, WHEN (readable
   IST time where the state has one), what is blocked and the next action? Name any state that lost its time.
4. One attack of your own: e.g. a non-IST browser zone in the e2e, a time with no offset, a leg with a decimal strike.
Never write files in the repo; never write `evidence/`.

## Return
Evidence table, then one JSON block:
```json
[{"ac": "AC-3", "requirement": "REQ-039", "ac_fp": "<from ac_fp.py>", "result": "pass|fail",
  "commands": "...", "observed": "...", "attack": "..."}]
```
Plus defects (file:line, severity).
