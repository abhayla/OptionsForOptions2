# Chunk 1 Tier A review: independent redesign (ADR-106 rule 5) - the index answer is never LIVE on a closed market; Retry-After capped

Common brief: docs/process/builder-brief.md (Budget hard stop: at 72 calls start nothing new, commit, report).
Size: M, about 6 files, 2 items, backend + frontend
CI: app tests job (`tests_app/` files you add or change; vars: DATABASE_URL via CI only - run NO database test locally); kit tests job (`tests/` files you change); frontend job (`frontend/tests/` files you add or change).
Expected (orchestrator, before dispatch): 30 min / ~200k.

Core: on a closed market the index answer's state is never LIVE, so no screen anywhere says index values are live while the market is closed, and every index screen shows the one market-closed banner.
Proof: step 1 is a failing test on the REAL index answer (`backend/ofo_app/index_push.py` with the real KiteProvider and the recorded frame, clock Saturday 2026-10-24 10:00 IST, heartbeats): today the answer reads `state: "LIVE"` with `market_closed: true` (round-2 review attack `review2-a1/r2a.py` in the session-5 scratchpad prints `idx.state=LIVE idx.closed=True`); after the fix the state is not LIVE, and Wednesday 2026-10-21 10:00 still reads LIVE.
Class: live-wording-on-a-closed-market - every answer field and screen text that says live: before, the index answer (`index_push.py:~93`) sets LIVE without reading the market state, so `IndexStrip.vue:~14` says "Index values are live." beside the closed banner on the Market Context page, and `IndexViewPage.vue` has no banner and uses its live "as of" wording; after, one place derives the index state from the one market-state function (`market_closed_for`, `backend/ofo/marketdata/feed_health.py`) and the screens follow the answer.

Why a redesign: round 1 of the chunk review found the market-closed state shown as live; fix F1 made one market-state function and covered quotes, outcome and chain, but the round-2 review (Opus, fresh) found this index-level leak. ADR-106 rule 5: a MAJOR left after round 2 on Tier A code gets an independent redesign (you did not write F1), not a third round by the same builder.
Spec basis: REQ-114 AC-7: "Outside market hours (ADR-119 calendar) silence is expected: the health check marks data market closed". ADR-177 (one market-closed wording). ADR-015 (no stale data shown as live). ADR-179 (Retry-After rule for user and background reads).
Copy from: none - this project's own index answer and market-state function.
Reference: screens catalogue 012, catalogue 200 - copy nothing new. RD-065 and RD-066 (REQ-114) are SPEC CHANGE records waiting for the owner (Q282), not built here.
Findings checked: verified-on-a-module-the-product-does-not-call, guard-as-forbidden-list, brief-rule-from-memory.
Test the SCREENS (Market Context page, index strip, Underlying/index view page), not only the answer.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-chunk1-copy`, branch `build/seq-chunk1-copy`, at the chunk head (frontend packages installed). Commit with `git commit -F <msg> -- <your paths>`, do NOT push. BINDING: never stop a process by name; stop only PIDs you started. Never call Kite live. If a commit is refused by `verifier_inflight_gate`, wait 2 minutes, retry once, keep editing. Scratch: `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\5db71e90-61e3-4f1b-8a6c-a0ee38c54e11\scratchpad\redesign`.

## What to do
1. MAJOR: derive the index answer's state from `market_closed_for` in ONE place in `backend/ofo_app/index_push.py`, so a closed market never yields LIVE (use the existing not-live state word the answer already has for stale data, or the existing closed value if one exists - read the answer's type first; never invent a word the frontend does not handle). The index strip (`frontend/src/components/layout/IndexStrip.vue`) then says nothing live when closed; `frontend/src/pages/IndexViewPage.vue` mounts the existing `MarketClosedBanner` (the ADR-177 text from `frontend/src/lib/sharedStateText.js`, one home) and drops its live as-of wording when the answer says market closed. Check every other reader of the index state (grep `state ===` / `isLive` in frontend/src) follows the answer.
2. MINOR (round-2 review, outside its list): a Kite `Retry-After` header is accepted up to 99999 s (`backend/ofo/broker/rate_limit.py`, the `_RETRY_AFTER` read), so one header could block an endpoint group for 27 hours. Orchestrator's technical decision: honour a stated wait up to 60 s; a larger or unparsable value is clamped to 60 s and logged by value (never the token); F-60's 10 s cooldown when no wait is stated is unchanged (ADR-179).

Attack list: (each names its test file)
1. Saturday 10:00 IST with heartbeats: index answer not LIVE; Wednesday 10:00: LIVE; holiday 2026-10-20: not LIVE; a date past the calendar: not LIVE (a `tests_app/` DB-free test on the real index answer).
2. Market Context page and index strip on a closed market: the banner, and no "Index values are live." text (a `frontend/tests/` test on the real components).
3. Underlying/index view page on a closed market: the banner, no live "as of" wording; open market: unchanged (`frontend/tests/`).
4. Retry-After 2 -> 2 s; 99999 -> 60 s and a log line; "abc" -> 60 s; no header -> the 10 s cooldown (`tests/broker/`).
5. Every frontend reader of the index state (grep) follows the answer: a closed answer never renders a live word on any screen (`frontend/tests/`, one test over each reader).

Standing items: (a) n/a: no time-budgeted job changes (the Retry-After cap only shortens a wait); (b) n/a: no CI step changes; (c) n/a: no static detector; (d) the market-state answers - open, closed (weekend, holiday, after hours), unknown date - each with the index state and what each index screen shows.
Threat model: in scope - any index field or screen that says live on a closed market, one bad Retry-After header blocking an endpoint group for hours; out of scope - the calendar data (special sessions are #530), quotes/outcome/chain (fixed in F1, verified).
Mutation gate: run `python scripts/orchestrator/mutation_gate.py` on: the market-state check removed from the index state; the 60 s clamp removed; frontend mutants (banner removed from IndexViewPage, the closed branch removed from IndexStrip) by hand on a copy of `frontend/` in your scratch folder; record killed/survived.
Reviewer checklist: the index state derived in one place from the one market-state function; every index screen follows the answer; ADR-177 text from its one home; the Retry-After clamp logged; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (except docs/api/openapi.json if a response model changes).

Tests: python -m pytest -q -p no:cacheprovider tests/marketdata tests/broker; python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests; python -m pytest -q -p no:cacheprovider -c pytest-app.ini <your DB-free tests_app files>; in frontend/: npm run lint, npx vitest run <your files>
Why Opus: Tier A - live-data liveness on every index screen (ADR-015) and the broker rate limiter that feeds the order path; an independent redesign after round 2.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
