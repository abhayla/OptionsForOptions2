# Chunk 1 Tier A review fix F2: a user read's 429 retry fits its wait limit; four limiter MINORs; the Execute race; the 0023 downgrade

Common brief: docs/process/builder-brief.md (Budget hard stop: at 72 calls start nothing new, commit, report).
Size: M, about 10 files, 8 items, backend
CI: app tests job (`tests_app/` files you add or change, incl. `tests_app/test_rate_limit_door.py`, `tests_app/test_strategy_versions_app.py`; vars: DATABASE_URL via CI only - run NO database test locally except the one run below); kit tests job (`tests/broker/`, `tests/` files you change).
Expected (orchestrator, before dispatch): 60 min / ~400k.

Core: a user read (Execute's and return's reads included) that gets a 429 is retried up to twice within its 5 s wait limit, so REQ-118 AC-3 and AC-4 both hold; past the limit it is refused busy, never queued without bound.
Proof: step 1 is the review's attack as a failing test on the REAL door: `ofo.broker.kite_http.open_url` with the opener stubbed to answer HTTP 429 once and then 200, user context. Today: 1 send, outcome KiteBusy('wait') (review attack `review-a2/attack4.py` in the session-5 scratchpad). After: 2 sends, the 200 answer returned, total wait under 5 s; with 429 on every send: 3 sends at most, then the read fails per AC-4 and the caller's fail-closed rule applies.
Class: rate-limit-answer-handling - every Kite read through the two doors (`backend/ofo/broker/kite_http.py`, `backend/ofo_app/kite_http.py`) in user and background context; before, user reads never retried (the fixed 10 s cooldown is longer than the 5 s user wait); after, both contexts follow AC-4 within their own wait limit.

Spec basis: REQ-118 AC-3: "a request that would wait longer than its group's limit (default 5 s for user". REQ-118 AC-4: "is retried after the wait Kite indicates". REQ-118 is a TECH row decided by the orchestrator (source: master register MR-095), so the orchestrator decides the reconciliation of AC-3 with AC-4: keep the 5 s user limit and make the post-429 wait come from what Kite states, so the retries fit inside it.
Copy from: none - this project's own limiter and doors.
Reference: screens catalogue 012 - copy nothing; RD-063 is verified (the minimum periods stay as built).
Kite API facts: use the user-level `zerodha-expert` skill for what Kite sends with a 429 (a Retry-After header or not; per-second limits per endpoint group) - never from memory. If Kite states no wait, use the endpoint group's own per-second window from `GROUP_RATES`, and say so. FIRST read why row 10 chose a fixed 10 s cooldown (`git log -S` on the constant, the row 10 briefs `docs/process/builder-sequence-briefs/row-10-*.md`, ADR-160/ADR-162); if a decision fixed it, quote it and keep its intent.
Findings checked: verified-on-a-module-the-product-does-not-call, brief-rule-from-memory.
Exercise each item through the real door and the real route, never only the module.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-chunk1-copy-b2`, branch `build/seq-chunk1-copy-b2`, at the chunk head f7b7ab8f. Commit with `git commit -F <msg> -- <your paths>`, do NOT push; the migration change in its own commit. BINDING: never stop a process by name. Never call Kite live. Another Opus builder (F1) works at the same time in `-chunk1-copy` on `backend/ofo/marketdata/`, `kite_ws.py`, `reconnect_policy.py` and the frontend: do not touch those. ONE local DB run at the end of the touched DB test files through `python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-chunk1-copy-b2 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini -o faulthandler_timeout=60 <files>` (log to a file, tail); if unavailable, say so. If a commit is refused by `verifier_inflight_gate`, wait 2 minutes, retry once, keep editing. Scratch: `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\5db71e90-61e3-4f1b-8a6c-a0ee38c54e11\scratchpad\f2`.

## What to do
1. MAJOR (area 2): the post-429 wait comes from Kite's stated wait (or the group window), and a user read retries up to twice while the total stays within its 5 s limit; a background read keeps its own limit. Both doors share one helper (`rate_limit.py:~59-61, ~244-246`, `kite_http.py:~198-213`, `ofo_app/kite_http.py:~260-274`).
2. MINOR: a KiteBusy refusal where nothing was sent is never stored as the period's answer (`rate_limit.py:~216-220`, `kite_period_reads.py:~72-76`), so a background refusal never shows the user's Positions screen as busy; a user request never waits on a lock held by a queued background read.
3. MINOR: a stored failure is re-raised as a NEW exception each time (store the code, not the object) (`rate_limit.py:~212-213`).
4. MINOR: install the process limiter at app startup from `BrokerSettings.KITE_API_KEY` (`rate_limit.py:~324-326`, `broker_config.py:34`), so a key only in `.env` never makes a stray '-' bucket.
5. MINOR: `kite_flags.py:~364` accepts only YYYY-MM-DD (check the text before `fromisoformat`; '20261022' is refused, every flag off).
6. MINOR (area 3): Execute reads the strategy without a lock (`routes/execute.py:~294`) and locks later in `next_plan_number`; after the lock, re-load the strategy and refuse with an explanation template (one home `backend/ofo/errors/templates.py`, pin in `tests/errors/template_pins.json`) if its revision changed, so a plan is never built from a definition the row no longer holds.
7. MINOR (area 3): migration 0023's downgrade refuses while any `reconciliation_required` flag or plan version link is stored (like 0022's downgrade refuses with versions stored). Own commit.
8. Update `docs/api/openapi.json` only if a response model changes (`python scripts/generate_openapi.py`).

Attack list: (each names its test file)
1. User read, 429 then 200: 2 sends, 200 returned, under 5 s; 429 x3: 3 sends max then failed, margin gate blocks (`tests/broker/` door test + `tests_app/test_rate_limit_door.py`).
2. Background refusal with nothing sent: the user's next Positions read inside the period gets a fresh answer, not busy (`tests_app/test_periodic_positions_read.py`).
3. Stored failure re-raised three times: three distinct exception objects, traceback length constant (`tests/broker/`).
4. Key only in a `.env` file: the /instruments download shares the app's bucket (`tests_app/` test with a temp env file).
5. Flag file dated '20261022': all flags off (`tests/broker/`).
6. A PUT committing between Execute's read and its lock: Execute refuses, nothing sent to Kite, no plan stored (`tests_app/test_strategy_versions_app.py` or the execute route test; a DB test - CI or the one run).
7. 0023 downgrade with a flag or link stored: refused, nothing dropped (migration test; DB).

Standing items: (a) the retry wait is a time-budgeted path: a test shows the order path's reads still get their slots when the budget is tight and a user read never waits past 5 s in total; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) Kite's answer states on a read - 200, 429 with a stated wait, 429 without one, 5xx, timeout, token refused - each with what the door does (retry, refuse busy, fail) and what the caller shows.
Threat model: in scope - an order-path read that fails on a retryable 429, a background read blocking a user's screen, a plan built from a definition the row no longer holds, a downgrade that silently drops safety state; out of scope - order placement retries (never retried, ADR-017), the minimum periods (RD-063, verified).
Mutation gate: run `python scripts/orchestrator/mutation_gate.py` on: user-context retry removed; the 5 s total cap removed; the busy-not-stored rule removed; the revision re-check removed; the downgrade refusal removed (DB-backed mutants: say so per mutant).
Reviewer checklist: one helper for both doors; AC-3 and AC-4 both hold with numbers; order placement never retried; fail closed; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (openapi only if a model changes).

Tests: python -m pytest -q -p no:cacheprovider tests/broker tests/errors/test_template_pins.py; python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests; python -m pytest -q -p no:cacheprovider -c pytest-app.ini <your DB-free tests_app files>
Why Opus: Tier A - the Kite read doors and the rate limiter feed the order path (Execute, return, margin gate), Execute's plan building, and a migration.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
