# W-118 round 2 (last allowed round): a change of underlying or expiry clears the old answer at once; reuse the socket client

Common brief: docs/process/builder-brief.md
Core: no number from one (underlying, expiry) choice is ever shown under another choice: changing either clears the shown answer and the followed request at once, and any read or push for the old choice is ignored.
Proof: the verifier's scratch case as a red test first - NIFTY answer shown (spot 24510.00, LTP 111.11), switch to SENSEX with a slow and with a failing catalogue -> neither 24510.00 nor 111.11 appears, a late NIFTY push (222.22) is ignored, and the catalogue error is not shown beside old rows; then green.
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Tier: B fix round (display). Findings checked: last-live-answer-kept-after-drop (this is the same class: an old answer survives a change of choice)

## Findings (verifier, f6aa87e)
1. CRITICAL - `watch(underlying)` runs `loadExpiries`, which blanks `expiry`; `watch(expiry)` skips the empty value, so
   `follow()` never clears the answer: NIFTY spot and LTPs stay under the SENSEX label, a late NIFTY push still applies,
   and with a failing SENSEX catalogue the NIFTY rows show beside the expiries-could-not-be-read line. Fix: the
   underlying change itself stops following, clears the shown answer and bumps the choice counter BEFORE loading
   expiries; every answer carries the (underlying, expiry) it was requested for and is dropped unless it matches the
   current choice.
2. MAJOR - `createChainSocket` in `useChainLive.js` copies `createLiveSocket` (only `MAX_ATTEMPTS` / `backoffDelay`
   imported). Fix: use `createLiveSocket` from `frontend/src/composables/useStrategyLive.js` with its `url` / `onPush` /
   `onMessage` / `onDown` parameters (it already accepts any URL; if its `isOutcome` check blocks chain answers, add ONE
   optional `isAnswer` parameter defaulting to today's check and keep every existing `strategy-live.test.js` test green).
3. MINOR - add the `/api/market/chain/live` WebSocket proxy entry to `frontend/vite.config.js` the way W-114 did for
   `/api/market/indices/live` (W-114's entry is not on this branch: add only the chain line; W-114's rides in #430).
4. MINOR - a REST-only LIVE first paint shows the not-connected label while the socket is still connecting: show the
   waiting state instead.
5. MINOR - `routes.js` typo `=SECTIONS`: fix if it is a real typo (read the file first).

## Tests
Add to `frontend/tests/option-chain.test.js`: the Proof (slow and failing catalogue); a late push for the old expiry
after an expiry change ignored; first-paint label. Mutation: remove the clear-on-underlying-change -> the Proof red.
Run `npm run lint`, `npx vitest run tests/option-chain.test.js tests/strategy-live.test.js`, `npm run build`.

## Isolation
Work ONLY in `D:\Abhay\Ventures\OptionsForOptions2-gc5s-w118` (branch `build/W-118-chain-screen`). Never run git or npm
in `D:\Abhay\Ventures\OptionsForOptions2`; no database, no server, no Playwright; no backend change. Commit, push; no PR.
No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no
regenerated files in the PR.
