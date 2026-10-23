# Row 11 part B (frontend): REQ-114 AC-5 "Reconnecting - prices as of <time>" (W-139)

Row-ahead: yes (ADR-171: built after part 11a in the row-ahead worktree, while row 10 is verified or closing)
Overlap: none (checked against row 10 REQ-118's files - backend and tests only; row 10 touches no frontend file; the
orchestrator re-runs `overlap_gate.py` before dispatch and at your report)

Common brief: docs/process/builder-brief.md (Budget hard stop: at 32 calls start nothing new, commit, report). Before
reporting, run `python scripts/orchestrator/mutation_gate.py` on a mutants file for this part's guards (the text
helper, the server-time source, the live-only-on-fresh-push rule) with the vitest command as each mutant's test, and
quote its results file (R18).
Size: S, 4 files, 3 items
CI: app job `frontend` (`npm run lint`, `npm run test:run`: `frontend/tests/strategy-live.test.js`,
`frontend/tests/feed-reconnect.test.js`; vars: none); app job `e2e` (`frontend/e2e/feed-reconnect.spec.ts`; the e2e
job's existing variables). Locally only `npm run lint` and `npm run test:run` (and the e2e with `PW_CHROMIUM_PATH` set
to an installed Chrome if available); no database.
Expected (orchestrator, before dispatch): build 30 min / ~110k; verify with row 11 part A.

Core: a screen that has just reconnected and has no fresh price yet says "Reconnecting - prices as of <time>" with the
time of its last price, and switches to live on the first fresh push.
Proof: step 1 is a vitest in `frontend/tests/feed-reconnect.test.js` failing first: live -> drop -> reconnect with no
new push -> the text reads exactly "Reconnecting - prices as of 11:02:10" (the last push's time, IST) and no price is
marked live; then one fresh push -> live, the text gone.

Spec basis: REQ-114 AC-5: "A browser that has just reconnected and has no fresh tick yet shows "Reconnecting - prices
as of <time>" rather than an error, and switches to live on the first fresh tick". REQ-113 AC-2 (built at row 9: the
"reconnecting" state, one constant in `sharedStateText.js`). ADR-015 (never an old price as live).
Copy from: none - extends row 9's `useReconnecting` and `RECONNECTING_TEXT` (`frontend/src/lib/sharedStateText.js:7`).

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-next`, branch `build/seq-row-11` (after part 11a's commits).
Work, test and commit ONLY there. The frontend packages: the orchestrator links or installs `frontend/node_modules` in
this worktree before dispatch (check `frontend/node_modules/vitest/package.json` exists; if not, STOP and report).
Commit with `git commit -F <msg> -- <your paths>`; do NOT push. Scratch:
`...\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row11b`.

## What to build
1. The text: `RECONNECTING_TEXT` becomes the exact REQ-114 AC-5 form "Reconnecting - prices as of <time>", built by
   ONE helper from the time of the screen's last price (the push's own server time, shown in IST HH:MM:SS, never the
   browser's clock); before any price has arrived, the row 9 text without a time.
2. Every live screen that shows the reconnecting state (row 9 list: StrategyBuilderPage, LiveStrategyCard,
   ExecuteStrategyPage, OptionChainPage, IndexViewPage, IndexStrip - grep `live-reconnecting`) shows the new text from
   the helper; none builds its own string.
3. Update every test and e2e line that asserted the row 9 text (grep `RECONNECTING_TEXT`, "Live prices are
   reconnecting" in `frontend/`).

Attack list: (each names its test file)
1. Reconnect with no fresh push -> exact text with the last push's time; nothing live (`frontend/tests/feed-reconnect.test.js`).
2. The first fresh push -> live, the text gone (same file).
3. The time is the push's server time in IST, not the browser clock (a browser clock 5 h off changes nothing) (same file).
4. No price ever arrived -> the text without a time (same file).
5. Every live screen uses the one helper (`frontend/tests/strategy-live.test.js` and the per-screen tests).
6. The e2e reconnect test still passes with the new text (`frontend/e2e/feed-reconnect.spec.ts`).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) the server socket's answer states (an outcome push, non-answer, malformed, close, refused, accept-then-silence) are listed in `feed-reconnect.test.js` from row 9 - extend each with what the text shows.
Threat model: in scope - an old price shown live, a time from the browser clock, a screen building its own text; out of scope - the server-side health rules (part 11a).
Findings checked: wall-clock-assertion-flakes-under-load
Reviewer checklist: one helper and one text home; server time in IST; fake timers; every old-text assertion updated;
no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no
regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
