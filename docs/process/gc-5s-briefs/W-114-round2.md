# W-114 round 2 (last allowed round): the index page never keeps an old number after its socket drops

Common brief: docs/process/builder-brief.md
Core: once the page's own socket is down, no index value from an earlier LIVE answer is shown until a NEW live answer arrives, whatever the fallback read returns or fails with.
Proof: a Vitest where a LIVE push showed 25150.00, the socket drops and `GET /api/market/indices?fallback=true` rejects: neither panel shows 25150.00 and each shows its not-live state.
Budget: 25 min wall-clock, 35 tool calls
Report: evidence-table
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Tier: A fix round (frontend file only). Findings checked: liveness-from-shared-subscribers, live-subscription-lost-on-release-reacquire

## Findings (Tier A verifier, dbc4d84)
1. MAJOR - `frontend/src/pages/IndexViewPage.vue` 34-39 / 59-62: `onDown` sets `failed=true` but keeps `answer` = the
   last LIVE push; `shownValue` checks only `answer.state`, so after a drop with a failing fallback both panels keep the
   old number with its `as of` time and no health word, under an `unavailable` banner. REQ-072 AC-2: "a stale or missing
   index value is shown as such and is never used silently in a calculation." REQ-049 AC-4: "Screens show when data is
   stale or unavailable instead of presenting old numbers as live." Fix: a socket drop clears the shown values at once
   (keep only each index's last time for the not-live line); a value shows only from a LIVE answer received AFTER the
   latest drop.
2. MINOR - first-paint race: the first REST read (not a fallback read) can resolve after `onDown`'s NOT_CONNECTED answer
   and replace it with a LIVE snapshot. Fix: any answer whose request was sent before the latest drop is ignored.
3. Accepted, no change: a LIVE answer may carry a value with health unavailable/unhealthy; it is shown with its health
   word.

## Tests (add to frontend/tests/index-view.test.js)
(a) the Proof; (b) drop, then the fallback answers NOT_CONNECTED -> no number; (c) the race: first-paint read held back,
drop happens, then the held read resolves LIVE -> still not live; (d) after a drop a NEW socket push LIVE -> the number
shows again. Mutations: revert fix 1 -> (a) red; revert fix 2 -> (c) red. Name them. Original attack list:
D:\Abhay\Ventures\OptionsForOptions2-gc5s-docs\docs\process\gc-5s-briefs\W-114-builder.md.
Run: `npm run lint`, `npx vitest run tests/index-view.test.js`, `npm run build`.

## Isolation
Work ONLY in `D:\Abhay\Ventures\OptionsForOptions2-gc5s-w114` (branch `build/W-114-index-view`, HEAD dbc4d84). Never run
git or npm in `D:\Abhay\Ventures\OptionsForOptions2`; no database, no server, no Playwright run; no backend change.
Commit, push; no PR. No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted
tests only; no regenerated files in the PR.
