# Chunk 1 reference-copy builder, part B2 (ADR-178 (2)): four COPY records of rows 2, 4 and 10 (broker reads, margin, capability flags)

Common brief: docs/process/builder-brief.md (Budget hard stop: at 72 calls start nothing new, commit, report).
Size: M, about 12 files, 4 items, backend + frontend
CI: app tests job (your new or changed `tests_app/` files; vars: DATABASE_URL via CI only - run NO database test locally); kit tests job (`tests/` files you change); frontend job (`frontend/tests/` files you add or change).
Expected (orchestrator, before dispatch): 60 min / ~400k.

Core: a newly connected user's positions are read once at connect and then on a fixed period, and no user's reads can come faster than that period, all through the existing per-user rate limiter.
Proof: step 1 is a failing test on the real read path with an injected clock and a fake Kite: connect a session, assert one positions read at connect without opening Execute (today: none until Execute is opened), then advance the clock 45 s and assert the second read, and assert a read asked for 10 s after the last one is answered from the last read (not a new Kite call).

Records (read each JSON in full first: `spec/reference-diffs/RD-0NN.json`, fields `reference_behaviour`, `ours`, `reference_screens`, `req`):
1. RD-014 (REQ-015, row 2, NEW AC NEEDED): positions are read once at connect, then on a fixed period, so a new connection never waits on a manual step.
2. RD-063 (REQ-118, row 10, NEW AC NEEDED): broker reads have a fixed minimum period per user - 30 s for numbers (quotes/margins as the record says), 45 s for positions; a read inside the period is served from the last answer with its read time. Reuse the existing limiter in `backend/ofo/broker/rate_limit.py` and its door; never a second limiter.
3. RD-013 (REQ-015, row 2, NEW AC NEEDED): the settings/profile screen shows the connected Zerodha user id MASKED (say the masking rule you used and why, e.g. first 2 and last 2 characters) and, when the `funds_read` capability is on, Zerodha's own available margin WITH its read time, exactly as read (a Decimal string from the API). Never computed, never a default: margin read failed, empty, not connected, or capability off -> the reason, never 0 (ADR-016; `tests/test_margin_from_zerodha_only.py`).
4. RD-025 (REQ-117, row 4, NEW AC NEEDED): add the capability flags the record names (e.g. brokerage charges, split P&L, holdings, verified P&L) to the closed flag list, each fail-closed as REQ-117 requires (unknown or unset = off), and each wired only where a feature reads it today - a flag with no reader is added with a test that it defaults off, nothing more.

For each NEW AC: add the acceptance criterion to the requirement (ADR-173 / ADR-176: copying is the default and needs no owner question). First check for a similar line with the kit's spec_similar tool (the kit guard may refuse it in this worktree; if so, grep the requirement by hand and say so) and extend or cite a match. The new AC's text must not name the reference product (ADR-176). Add the AC's test to the work item's `tests_required` (W-130 for REQ-015, W-132 for REQ-117, W-138 for REQ-118). When a record is built, set its `status` to `built` and add the commit (do NOT set `verified`). Do NOT regenerate `docs/process/reference-differences.md` or any index.

Spec basis: ADR-176 (2) as amended by ADR-178 (2): COPY records are built once per chunk by one builder with one check. ADR-173 (reference product first). ADR-016 (Zerodha is the authority on positions, orders and margin). ADR-012 (browsers never talk to the market-data vendor). REQ-015, REQ-117, REQ-118 (every AC).
Copy from: none - the reads go through this project's existing Kite read doors (`backend/ofo_app/kite_reads.py`, `backend/ofo_app/kite_http.py`) and limiter; legacy-reuse map rows for these requirements are listed below by copy_from_check.
Reference: screens 012, 022, 216, 331 - copy the behaviours of RD-013, RD-014, RD-025, RD-063. RD-010 and RD-012 (REQ-015) were built in part A (status built, the chunk's one COPY check is pending): do not change them, but your RD-013 profile work sits next to RD-010's login panel - keep both working.
Kite API facts: use the user-level `zerodha-expert` skill (margins endpoint and its fields, positions endpoint, rate limits per endpoint) - never from memory.
Mutation gate: run `python scripts/orchestrator/mutation_gate.py` on every guard you add (the minimum period, the read-at-connect trigger, the margin-as-read rule, each flag's fail-closed default) before reporting; DB-backed mutants: say so per mutant; quote its results file.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-chunk1-copy-b2`, branch `build/seq-chunk1-copy-b2`, made by the orchestrator from the chunk head f5a1059c (frontend packages installed). Commit with `git commit -F <msg> -- <your paths>`, and do NOT push. BINDING: never stop a process by name; stop only PIDs you started. Never call Kite live. The kit guard blocks shell commands naming spec/, tools/, .claude, views, factory or .github: edit those files with Read/Edit and commit them with pathspec globs that avoid the words (e.g. `':(glob)**/reference-diffs/RD-0*.json'`). If a write is refused by `verifier_inflight_gate`, wait 2 minutes, retry once, then keep editing and report the pending commit. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\5db71e90-61e3-4f1b-8a6c-a0ee38c54e11\scratchpad\copy-b2`.

Attack list: (each names its test file)
1. Connect -> one positions read with no Execute visit; +45 s -> second read; +10 s after a read -> served from the last answer with its read time, no Kite call (a new `tests_app/` file with an injected clock and a fake Kite).
2. Two users: one user's reads never delay or consume the other's period (same file).
3. Disconnect or token expiry stops the periodic read; reconnect starts it again with one read at connect (same file).
4. Profile: masked user id; margin exactly the API string with its read time; margin read failed / empty / capability off / not connected -> the reason, never 0 (a `tests_app/` route test + a `frontend/tests/*.test.js`).
5. Each new capability flag: unset or unknown = off; a feature reading it refuses or hides when off (`tests/` capability tests).
6. The rate limiter is the only limiter: grep shows no second throttle (a repo test or a line in your report with the grep).

Standing items: (a) the periodic read is a time-driven job: it reuses the existing limiter's per-user budget, never more than one read per period per user, and a test shows the order path's reads (Execute, return) still run first when the budget is tight; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) the broker's answer states for each read (margins, positions) - answered, absent field, not found, failed (network/5xx), rate-limited (429), token expired, empty - each with what is stored and what the screen shows (never a computed or zero margin, never positions marked fresh from an old read).
Threat model: in scope - a margin figure not from Zerodha, a read storm from many tabs or users, a stale positions answer shown as fresh, a flag that defaults on; out of scope - order placement (unchanged), the login flow (row 2, unchanged).
Findings checked: brief-rule-from-memory, verified-on-a-module-the-product-does-not-call (the periodic read must feed the positions the app's screens actually show: name the route/module), report-time-typed-not-read.
Reviewer checklist: each record's behaviour on the real route and component; new ACs not naming the reference product; margin only as read; one limiter; the order path not starved; fail-closed flags; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/broker tests/test_margin_from_zerodha_only.py; python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests; python -m pytest -q -p no:cacheprovider -c pytest-app.ini <your DB-free tests_app files>; in frontend/: npm run lint, npm run test:run (your files)
Why Opus: margin display (ADR-016 money from Zerodha only), live broker reads under the rate limiter (live-data liveness, REQ-118), capability gating (REQ-117) - all in the safety set.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Legacy map rows (copy_from_check.py)
Rows of the legacy-reuse map that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read
before designing; SKIP -> do not re-survey.

| `market_data/auth_tracking.py` (102) | REFERENCE | token-expiry detection idea | REQ-015 |
| `src/components/settings/KiteSettings.vue` (388), `views/AuthCallbackView.vue` (81) | ADAPT (P4) | no token in URL | REQ-015 |
