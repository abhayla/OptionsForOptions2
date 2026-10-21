# W-115 round 2 (last allowed round): one place owns whether an index answer is live - the composable, used by the index page and the Home strip

Common brief: docs/process/builder-brief.md
Core: after ITS OWN socket drops, neither the index page nor the Home strip shows any index number until a NEW live answer arrives, because both read their shown values from ONE state machine in `useIndexLive.js`.
Proof: the same four drop tests run against BOTH the page and the strip (a shared test table): LIVE push 25150.00 -> drop -> fallback rejects / answers NOT_CONNECTED / hangs -> no 25150.00 anywhere; a read sent before a drop resolving later is ignored; a new push after the drop shows the number again.
Budget: 35 min wall-clock, 45 tool calls
Report: evidence-table
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Tier: B (frontend only), structural fix for a repeated class (run-discipline B8: prefer a structural guarantee).

## Findings (Tier B verifier on a219c3b)
1. MAJOR - `frontend/src/components/layout/IndexStrip.vue` `onDown` never clears the last LIVE answer (no
   `notLiveAfterDrop`, no drop counter): after a drop with a failed, hung or late fallback read the strip shows the old
   number as live - the class W-114 round 2 fixed only inside `IndexViewPage.vue`. REQ-049 AC-4: "Screens show when data
   is stale or unavailable instead of presenting old numbers as live." Third sample of the class (W-113 reconnect MINOR,
   W-114 MAJOR, this).
2. MINOR - `read()`, `shownValue`, `NAMES`, `Index values unavailable.` and `Not available` are copied from
   `IndexViewPage.vue`.

## Change (class level)
Move the answer state machine OUT of `IndexViewPage.vue` INTO `frontend/src/composables/useIndexLive.js`: first-paint
read, drop counter (ignore any read sent before the latest drop), clear-on-drop (keep only each index's last time),
fallback read, and one exported `shownValue(row)` / `rowsForDisplay` that returns a number ONLY from a LIVE answer
received after the latest drop. The composable returns reactive display rows; `IndexViewPage.vue` and `IndexStrip.vue`
both render those rows and hold NO answer state of their own. The two labels and the name map live in one module and are
imported by both. Keep W-114's 11 page tests green unchanged (they test behaviour, not structure); move tests only if
they referenced removed internals.

## Tests
`frontend/tests/index-live-state.test.js`: the Proof's four cases run as one table over BOTH components (mount page,
mount strip). Mutations: delete clear-on-drop in the composable -> both components' cases red; delete the drop counter
-> the late-read case red for both. Run `npm run lint`, `npx vitest run tests/index-live-state.test.js
tests/index-view.test.js tests/home.test.js`, `npm run build`.

## Isolation
Work ONLY in `D:\Abhay\Ventures\OptionsForOptions2-gc5s-w115` (branch `build/W-115-home`, HEAD a219c3b). Never run git or
npm in `D:\Abhay\Ventures\OptionsForOptions2`; no database, no server, no Playwright run; no backend change. A verifier may
be running in another worktree: if a git command is refused by the verifier in-flight gate, wait and retry (never delete
its snapshot). Commit, push; no PR. No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not
rise; targeted tests only; no regenerated files in the PR.
