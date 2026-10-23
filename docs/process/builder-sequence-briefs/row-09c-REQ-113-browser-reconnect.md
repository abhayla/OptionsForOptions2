# Row 9 part C: REQ-113 (W-137) - the browser shows "reconnecting", resumes within 10 s, never shows an old price as live

Common brief: docs/process/builder-brief.md (Budget hard stop: at 32 calls start nothing new, leave the tree
consistent, commit, report; scratch-copy mutations; fix lint as you go).
Size: M, 8 files, 3 items
CI: app job `frontend` (vitest: `frontend/src/composables/__tests__/` or the existing socket test files next to
`useStrategyLive.js`; vars: none) and app job `e2e` (Playwright `frontend/e2e/feed-reconnect.spec.ts` against `vite
preview` + the API, as `app-tests.yml` starts them; vars: those of the e2e job, unchanged). Locally: `npm run lint`,
`npm run format:check`, `npm run test:run` in `frontend/`; the e2e file with `npx playwright test e2e/feed-reconnect.spec.ts`
only if the API and preview servers are up - otherwise say "e2e not run locally" (CI runs it).
Expected (orchestrator, before dispatch): build 60 min / ~150k; verify (Tier A, Opus) 20 min / ~170k; ~90 min / ~330k.

Core: when the live socket drops, every live screen stops calling its prices live at once and says it is reconnecting;
when the server is back it resumes within 10 s.
Proof: step 1 is `frontend/e2e/feed-reconnect.spec.ts` failing first: with `page.routeWebSocket` (already used by
`e2e/strategy-live.spec.ts` and `e2e/support/quiet-live.ts`) the Strategy Builder gets one live push, then the socket is
closed by the fake server and refused for 5 s, then accepted again: during the gap the screen shows "reconnecting" and no
price cell is marked live; a fresh push arrives and shows within 10 s of the server accepting again.

Spec basis: REQ-113 AC-2: "Browser websockets reconnect to the new API and resume within 10 s, showing "reconnecting"
meanwhile and never an old price as live (ADR-015)." ADR-015 (no stale data shown as live). Sensibull study: no screen
for a lost price connection (`D:\Abhay\Ventures\competitors\sensibull\2026-10-21\INDEX.md`, searched the words reconnect,
disconnect, offline and stale), so this rests on the requirement, not on Sensibull.
Copy from: `frontend/src/composables/useStrategyLive.js` is already ADAPTED from algochanakya `useWebSocket.js`
(legacy-reuse row 142); extend it, never copy it.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head 50b095d6. PART A1 IS
BUILT IN THE SAME TREE AT THE SAME TIME (backend and tests_app only; orchestrator decision 22:50 to save ~90 min): touch
ONLY `frontend/` files; commit ONLY your own paths with `git commit -F <msg> -- <your paths>` (a bare `git commit` would
take A1's staged files); never `git stash`, `git checkout --`, `git reset` or `git restore`; ignore A1's files in
`git status`. Do NOT push. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row09c`.

## What to build (orchestrator decisions, technical, recorded)
1. Reconnect timing in the ONE socket helper (`useStrategyLive.js` `createLiveSocket` / `backoffDelay`, which
   `useChainLive.js` and `useIndexLive.js` already import - check `useIndexLive.js:38` uses it too, else make it): a
   fast phase of attempts 1 s apart for the first 30 s after a drop (an API deploy restarts in seconds), then the
   existing doubling to the 30 s cap; the give-up limit counts only the slow phase. Every caller keeps one helper (no copy).
2. One shared status word for every live screen: after a screen has been live, `connecting` / `down` read as
   `reconnecting`; the text lives once in `frontend/src/lib/sharedStateText.js` (`RECONNECTING_TEXT`, the word
   "reconnecting" per AC-2) and each live screen (`StrategyBuilderPage.vue`, `LiveStrategyCard.vue`, the chain via
   `useChainLive.js`, the index strip via `useIndexLive.js`, `ExecuteStrategyPage.vue`) shows it with a test id
   `live-reconnecting`.
3. Never an old price as live: the moment the socket drops, the screen's live marker (the existing `data-live` and any
   "Live" badge) leaves `live` - no grace period - and returns to `live` only on a NEW push (a push received after the
   drop). Callers (R15): every user of `useStrategyLive`, `useChainLive`, `useIndexLive` (grep) named in your report.

Attack list: (each names its test file)
1. Drop -> within the same tick no element says live; "reconnecting" shown (`frontend/e2e/feed-reconnect.spec.ts`).
2. Server back after 5 s -> a fresh push on screen within 10 s of accept (`frontend/e2e/feed-reconnect.spec.ts`).
3. A push queued before the drop and delivered late is not shown as live (vitest, the socket helper's test file).
4. Fast phase then slow phase: the delays are exactly 1 s x 30 then 2, 4, 8 ... 30 s; give-up only after the slow-phase
   limit (vitest, fake timers).
5. The chain and index screens show the same "reconnecting" text from the one constant (vitest per composable).
6. `stop()` (page left) never shows "reconnecting" and never reconnects (vitest).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes (vitest and Playwright are installed by the existing frontend and e2e steps); (c) n/a: no static detector; (d) the server socket's answer states - an outcome push, a non-answer message, a malformed message, close, refused connect, accept-then-silence: each listed in the socket helper's vitest file with what the screen shows (live only on an answer push; everything else not live).
Threat model: in scope - an old price shown as live during or after a reconnect, a screen that gives up during an API deploy, a reconnect storm hammering the server; out of scope - server-side feed health (parts A0/A1/B).
Findings checked: wall-clock-assertion-flakes-under-load, dependent-tests-not-run-stale-later
Reviewer checklist: one socket helper, no copies; fake timers in vitest (no real waits); the e2e uses routeWebSocket,
no sleeps longer than the timing under test; every live screen named; text from one constant; old e2e and unit tests
that asserted the old 1-2-4 s delays updated (grep `backoffDelay`, `MAX_ATTEMPTS` in `frontend/`); no new duplicated
literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
