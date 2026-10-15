# Builder brief: W-077 `Checked at`, names with no provider, strict IST parsing, index-only filter (Tier B)

Core: an outcome answer in each of the four non-normal states (unpriced, not connected, error, refused) carries the
server's answer time, and the Builder page shows `Checked at 16 Oct 2026, 09:20:05 IST` for an answer stamped
2026-10-16T03:50:05Z.
Proof: step 1 is `tests_app/test_outcome_checked_at.py` driving the REAL outcome route into each state and asserting
the time field is present and timezone-aware. Write it FIRST, red on current main.

Tier: B (display + one route field; no money, no order path). Model: sonnet (builder routing).
Budget: 50 min wall-clock, 60 tool calls. HARD limit: at call 56 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - fixes to this project's own W-065/W-072/W-073 code; no legacy row covers the Builder page.

Read first: `docs/process/builder-brief.md`, `work/W-077.md`, `spec/decisions/ADR-088.md`, `spec/decisions/ADR-086.md`,
issues `gh issue view 245`, `gh issue view 249`, `gh issue view 244`, `gh issue view 213`, `CLAUDE.md`.

## Spec basis
- REQ-039 AC-3: "Every important non-normal state shows what happened, when, what is blocked and the next action"
- ADR-088: "The four non-normal Builder states with no time today - unpriced, not connected, error, refused - each show"
  (followed in the ADR by `Checked at <time>`, the time being the moment the server produced that answer)
- ADR-088: "For not connected it is the time of the last connection attempt."
- ADR-086: "every time is shown in India time as" (format `15 Oct 2026, 11:59:59 IST`, whatever the browser's zone)
- ADR-086: "every leg is named by its contract"

## What to build
1. #245 API: every outcome answer (REST and socket) carries one answer-time field, timezone-aware ISO, set by the
   server when it produced that answer; use the app's existing clock seam (find how routes get the current time; the repo guard
   `tests/test_no_wall_clock_asserts.py` forbids asserting on the wall clock - inject the clock in tests). For not
   connected it is the moment of the last connection attempt the server made (if the server holds no attempt, the
   answer time, and say which in the report). Add it to the OpenAPI output (`scripts/generate_openapi.py`) if the
   repo keeps a checked-in schema.
2. #245 page: `frontend/src/pages/StrategyBuilderPage.vue` (~178-215) shows `Checked at <istTime(answer time)>` in
   each of the four states; the stale state is unchanged. Use `istTime` from `frontend/src/lib/displayFormat.js`.
3. #249: in `backend/ofo_app/routes/outcome.py` (~270, `ctx is None`) the no-provider path names each leg from the
   stored catalogue (the same contract fields the computed path returns: instrument, strike, expiry, type) using the
   catalogue store the app already has - one lookup by the leg's contract identity; an unknown contract keeps `None`
   (the page's fixed wording stays). Test both a known and an unknown contract.
4. #244: rewrite `istTime` parsing as one regex (date, time, optional fraction of any length, `Z` or `+hh:mm`) with a
   calendar check (2026-02-30 gives `Time not available`), trimming first; no `Date.parse` on the input string. Add the
   three missing tests (SaveDraftBar compact save-error, saved-draft `updated_at` line, adv-symbol / lot-size lines).
5. #213: `tests_app/test_broker_instruments.py` real-file test keeps expiry-None rows only when
   `r.contract.is_index()`.

## Reviewer checklist (write first; each must turn red when mutated)
- Remove the time from one state's answer -> a red test per state (4 states).
- Browser clock used instead of the answer time -> red (mock `Date.now` to a different time; the shown time must not
  move).
- `istTime('2026-02-30T06:29:59Z')` gives `Time not available`; a padded `' 2026-10-15T06:29:59Z '` gives the right
  time; `...59.362869+05:30` gives `15 Oct 2026, 11:59:59 IST`.
- No-provider leg named for a known contract; unknown contract keeps the fixed wording (never an id).
- #213: a non-index row with no expiry fails the filter.

## Rules
- Targeted tests only: `tests_app` -> `test_outcome_checked_at.py`, `test_outcome_route.py`, `test_outcome_catalogue.py`,
  `test_broker_instruments.py` via `python scripts/orchestrator/db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini <files>`;
  domain `python -m pytest -q -p no:cacheprovider tests/outcome tests/errors`; frontend `npm run lint`,
  `npm run test:run`, `npm run build`; Playwright only `strategy-states` and any spec you change, with servers started
  through `scripts/orchestrator/dev_run.py` as `app-tests.yml` does (set
  `PW_CHROMIUM_PATH=D:/ms-playwright/chromium-1223/chrome-win64/chrome.exe`), stopped by PID. Then your worktree's own
  `scripts/orchestrator/atool.py <worktree> W-077 --no-tests`.
- Do not touch `backend/ofo/charges/`, `backend/ofo/instruments/` freeze code, `backend/ofo/execution/` (parallel
  items), migrations, kit files, `spec/`, `views/`, `knowledge/findings/INDEX.md`. Never write `evidence/`.
- Commit and push `build/W-077-builder-checked-at`. Do not open a PR.
