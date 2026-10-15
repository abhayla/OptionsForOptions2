# Builder brief: W-073 live-push matcher, socket fallback flag, draft label dash (Tier A)

Core: a Builder page opened from a draft URL with lots `2` (a string) and planned entry `042.70` keeps applying live
pushes instead of freezing on the first answer.
Proof: step 1 is `frontend/tests/live-push-match.test.js` on the REAL matcher: URL legs (lots `"2"`, entry `042.70`)
against the server's echoed legs (lots `2`, entry `42.70`) must match. Write it FIRST, red on current main.

Tier: A (the matcher decides whether numbers on screen are live; W-065 was Tier A). Model: sonnet.
Budget: 40 min wall-clock, 50 tool calls. This is a HARD limit: count your calls; at call 47 commit what you have,
push, and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - fixes to this project's own W-065 code; no legacy row covers the live-push matcher.

## Spec basis
- REQ-035 AC-4: "Entry Price, LTP, Entry Value, Current Value, Unrealized P&L and P&L % update live"
- ADR-020: drafts marked "Draft — Live data not connected"
- ADR-077 (the not-live answer follows the browser's own socket; `fallback` is the REST refresh's flag, see the field
  description at `backend/ofo_app/routes/outcome.py:67-70`).
- ADR-008: money is never handled as a float in the browser.

## Start
- Branch `build/W-073-live-push-lows` from current main (W-072 is merged; it changed the same page).
- Read: issue #234 and #221 (`gh issue view 234`, `gh issue view 221`), `frontend/src/pages/StrategyBuilderPage.vue`
  (`matchesLegs`, ~line 101), `frontend/src/composables/useStrategyLive.js` (or wherever the socket client lives),
  `backend/ofo_app/routes/outcome.py`, `backend/ofo_app/live_push.py` (~line 87), `backend/ofo/errors/explanations.py`
  (template `outcome_not_connected`), `tests/errors/template_pins.json`, `frontend/src/lib/legPicker.js`
  (`NOT_CONNECTED_LABEL`).

## What to build
1. #234 item 1: compare normalized values in the matcher - lots as an integer; a money string by its canonical
   decimal TEXT (strip leading zeros of the whole part, pad/strip the fraction to the API's form) with string
   operations only, never `parseFloat`/`Number` on money. Put the canonicalizer in one function with its own tests.
2. #234 item 2: the outcome socket refuses an incoming message that carries a `fallback` key, with the catalogue's
   input error (the same way the socket refuses any other invalid message today - find that path and reuse it).
   REST keeps accepting `fallback` unchanged. Test: `tests_app/test_outcome_socket_fallback.py` (one file, run
   targeted against ofo_test through `scripts/orchestrator/db_run.py` only if it needs the database at all - prefer
   the app's no-database test style used by `tests_app/test_outcome_route.py`).
3. #234 item 3: unit tests that a leg edit during an outage, and after MAX_ATTEMPTS, sends `fallback: true`.
4. #221: the label becomes exactly `Draft — Live data not connected` (U+2014 long dash) in the template
   `outcome_not_connected`, its pin in `tests/errors/template_pins.json`, `NOT_CONNECTED_LABEL`, and every test and
   e2e spec that asserts the old text (grep the whole repo for `Draft - Live data not connected`; docstrings too).
   Do NOT edit `docs/reference/`, `evidence/` or `spec/`.
5. ADR-086 item 1 (contract names): `not_connected()` and `not_live()` in `backend/ofo/outcome/service.py:155-171`
   build every leg with `None` for symbol, instrument, strike and expiry, so the Builder shows "Contract details not
   available" for a draft-URL leg in those states. Fill those fields the way the COMPUTED path does (find where it
   gets them - the catalogue/snapshot - and reuse that one lookup; no new source). A contract the catalogue does not
   know keeps `None` (the page's fixed wording stays). Test both states with a known and an unknown contract; then the
   `strategy-live.spec.ts` assertion of "Contract details not available" for a known contract must change to the name.

## Reviewer checklist (write these first; each must turn a test red when mutated)
- Mutations: compare raw values again (item 1 test red); canonicalize through `Number()` (a test with entry
  `0.10` vs `.1`-style input or a 2-decimal edge must catch float use - add a grep-style unit assert that the
  canonicalizer source has no `parseFloat`/`Number(`); accept `fallback` on the socket (item 2 red); drop
  `fallback: true` after MAX_ATTEMPTS (item 3 red); a hyphen anywhere in the label (item 4 pins red).
- A matcher that matches TOO much is worse than one that freezes: a test where lots `2` vs `3`, or entry `42.70` vs
  `42.75`, must NOT match.
- Fail closed: an unparseable lots or entry in the URL never matches (the page then keeps its own REST state, labelled
  as now).

## Rules
- Targeted tests only. `tests_app`: only `test_outcome_socket_fallback.py`, `test_outcome_route.py`,
  `test_outcome_catalogue.py` (the label tests). Domain: `python -m pytest -q -p no:cacheprovider tests/errors
  tests/outcome`. Frontend: `npm run lint`, `npm run test:run`, `npm run build`; Playwright only `strategy-states`,
  `leg-picker` and any spec you change, against servers you start as `app-tests.yml` does; stop them by PID.
- No migration, kit or `spec/` change. Never write `evidence/`. Never mark anything verified.
- Commit and push `build/W-073-live-push-lows`. Do not open a PR.
