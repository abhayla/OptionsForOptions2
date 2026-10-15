# Verifier brief: W-077 "Checked at" on the four non-normal Builder states (Tier B)

Core: each of the four non-normal states (unpriced, not connected, error, refused) shows `Checked at <server answer
time, IST>`; the time comes from the server's answer, never the browser clock.
Proof: re-run the tests yourself; the builder's report and the reviewer's PASS are claims.

Model: sonnet (Tier B verifier).
Budget: 30 min wall-clock, 30 tool calls (batch commands). HARD: at call 27 stop and return what you have.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), then the JSON block below.

## Where
- Make your own read-only checkout in the scratchpad (never a sibling folder of the repo, never under the repo):
  `git -C D:/Abhay/Ventures/OptionsForOptions2 worktree add <scratchpad>/v077 origin/build/W-077-builder-checked-at`
  (detached), then `npm ci` in `<scratchpad>/v077/frontend` (log to a file). Remove it at the end from the MAIN checkout:
  `git -C D:/Abhay/Ventures/OptionsForOptions2 worktree remove --force <scratchpad>/v077` only after confirming it has no
  links/junctions, then `git worktree prune`.
- Brief + checklist: `docs/process/brief-W-077.md`; card `work/W-077.md`; ADR-088; issues #245, #249, #244, #213.
- AC: REQ-039 AC-3. Fingerprint (main checkout): `python tools/ac_fp.py REQ-039 AC-3 --yaml` -> currently `d7a390072d2b`.

## Spec basis
- REQ-039 AC-3: "Every important non-normal state shows what happened, when, what is blocked and the next action"
- ADR-088: "For not connected it is the time of the last connection attempt."

## Check (how could it fail?)
1. In `v077/frontend`: `npx vitest run`, `npm run lint`, `npm run build`.
2. Domain in `v077`: `python -m pytest -q -p no:cacheprovider tests/outcome tests/errors`.
3. App, targeted only: `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py <scratchpad>/v077 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_checked_at.py tests_app/test_outcome_route.py tests_app/test_outcome_no_provider_names.py tests_app/test_broker_instruments.py`
   (never the full app suite; the test DB host also serves production). A lock-timeout error is environmental: re-run
   once, then report it as such.
4. Attack: in a test of your own (scratch only, not committed), give an answer with `answered_at` = 2026-10-16T03:50:05Z
   while the browser clock says another time - the page must show `16 Oct 2026, 09:20:05 IST`. And: remove
   `answered_at` from one state's answer - does a test go red?
5. Honesty check: not connected shows the answer time (the server holds no attempt record). Is that stated somewhere a
   reader sees (card/report)? It is acceptable only if stated; say pass/fail on AC-3 accordingly, with the reason.
Never write in the main checkout; never write `evidence/`.

## Return
Evidence table, then one JSON block:
```json
[{"ac": "AC-3", "requirement": "REQ-039", "ac_fp": "<from ac_fp.py>", "result": "pass|fail",
  "commands": "...", "observed": "...", "attack": "..."}]
```
Plus defects (file:line, severity).
