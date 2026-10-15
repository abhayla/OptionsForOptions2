# Fix brief: W-065 phase 3 round 2 - the fallback is not-live because THIS browser's socket dropped (Tier A)

Core: when this page's own socket is down, the screen never shows numbers as live, whoever else holds the contracts.
Proof: step 1 is a failing test that reproduces the verifier's attack - a second socket holds the same legs, this
page's socket drops, the REST fallback must come back as REQ-049 AC-5's not-live answer (today: COMPUTED with a
table and no label). The orchestrator re-ran the attack on f5f6681: `ATTACK two holders, mine dropped -> REST state:
COMPUTED | status_label: None | output_label: None | table present: True | leg0 ltp: 30.05`.

Class: every REST outcome request made as the fallback of a dropped strategy socket while any other socket subscribes
to all of that strategy's inputs (a second tab, another user on the same strikes); today 100% of those show unlabelled
numbers, after the fix 0. The single-holder drop already shows AC-5 (keep it).
RCA: `routes/outcome.py` `get_streaming` decides "not live" by `fanout.subscriber_count(...) > 0` on the shared
fan-out, but ADR-077 ties the not-live answer to "the browser's own socket closes"; the page (`StrategyBuilderPage.vue`
`onDown: () => load()` -> `applyOutcome`) trusts that answer and writes no label of its own.

Model: sonnet. Tier: A (fix round: half the tier budget).
Budget: 30 min wall-clock, 40 tool calls. Commit after each step; at budget stop after a commit and report done / not
done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words, with the six fix items
(RCA, Class, failing test first, class-level fix, retest + the attack re-run, detection change).
Copy from: none - a fix inside W-065's own code.

## Spec basis
- ADR-077: "When a strategy's live connection to the platform drops (the browser's own socket closes) and the screen
  falls back, it shows REQ-049 AC-5's message"
- ADR-077: "No stale price outlives a subscription (unchanged); only its time is kept."
- REQ-049 AC-4: "Screens show when data is stale or unavailable instead of presenting old numbers as live."
- ADR-068 (2): "the screen falls back to a REST refresh when the socket is down, labelled as not live"
- ADR-068 consequence: "the screen does no P&L maths (ADR-008)"

## Where
Worktree `D:\Abhay\Ventures\OptionsForOptions2-W-065v`, branch `build/W-065-frontend` at f5f6681 (main merged in).
The verifier's attack script (reuse it as the basis of the failing test):
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\4b112add-c2b9-4a08-b5d6-b3bbac8c47e6\scratchpad\attack_two_holders.py`.

## What to fix (structural, at the decision point)
1. **Fallback flag on the request.** `OutcomeRequest` gains an optional boolean (e.g. `fallback`, default false). When
   true and a market context exists (live or the test replay), `outcome_response` answers `not_live(...)` - REQ-049
   AC-5's message with the newest price time kept per ADR-077; a strategy that never received a price keeps ADR-020's
   draft label. No numbers shown as live, no advanced details. Default false keeps today's behaviour for every other
   caller. Regenerate the committed OpenAPI file if one exists (`scripts/generate_openapi.py`; the #212 drift test).
2. **The page sends `fallback: true` on every load triggered by `onDown`** and while its live status is `down` or
   `off`; a normal load (first open, a leg edit while the socket is live) sends false.
3. **No flicker:** while the page already shows the not-live message, a fallback reload keeps that message on screen
   (does not switch to the loading state); after MAX_ATTEMPTS the last not-live answer stays.
4. **Late push of the previous strategy:** a push is applied only when it belongs to the strategy currently on screen
   (e.g. compare its legs' instrument ids, actions, lots and planned entries with the page's legs); otherwise drop it.

## Reviewer checklist (write the tests first; each must turn red when its fix is mutated)
- App test (`tests_app/test_strategy_live_push.py`): two holders, one drops, REST with `fallback: true` -> state is
  the not-live answer with AC-5's exact text and the newest price time, no table numbers; same request without the
  flag -> unchanged (COMPUTED). Mutation: ignore the flag -> red.
- Vitest (`frontend/tests/strategy-live.test.js`): onDown -> the request body carries `fallback: true`; a normal load
  carries false; a push whose legs differ from the current legs is not applied; the not-live message stays during a
  fallback reload (no 'loading' between).
- Playwright `frontend/e2e/strategy-live.spec.ts`: add the two-holder case on the replay (a second socket opened from
  the test holds the same legs, then this page's socket is killed): the AC-5 message shows and no live numbers.
  1280 and 390.
- Standing items: fail closed - an answer the page cannot parse shows the catalogue error, never old numbers; list
  every fallback answer state (COMPUTED, NOT_CONNECTED/not-live with time, draft label, REFUSED, network down) and
  what the page shows for each.
- Detection change: the two-holder e2e is the new guard; say so in the report.

## Rules
- Database is ofo_test on a production host (tunnel 127.0.0.1:5432): targeted test files only. Run from
  `D:\Abhay\Ventures\OptionsForOptions2`:
  `python scripts/orchestrator/db_run.py D:\Abhay\Ventures\OptionsForOptions2-W-065v python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_live_push.py`
  Frontend in the worktree's `frontend/`: `npm run lint`, `npx vitest run`, `npm run build`. Playwright: only
  `e2e/strategy-live.spec.ts` on the replay, servers started as `.github/workflows/app-tests.yml` lines 226-257 do (the
  replay API needs the CI placeholder `KITE_*` / `BROKER_TOKEN_KEY` values from lines 80-84; the locally installed
  Chromium via `PW_CHROMIUM_PATH` if the pinned one is missing). Stop every server by PID.
- Domain suite if you touch `backend/ofo/`: `python -m pytest -q -p no:cacheprovider tests/outcome`.
- No kit, `spec/`, or `evidence/` edits; never mark anything verified. Commit and push `build/W-065-frontend`. No PR.
