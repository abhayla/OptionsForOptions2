# Chunk 1 reference-copy builder, part A (ADR-178 (2)): five COPY records of closed rows 2 and 7

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, commit, report).
Size: M, about 12 files, 5 items, backend + frontend
CI: frontend job (`frontend/tests/` files you add or change); kit tests job (`tests/` files you change); app tests job (any `tests_app/` file you change; vars: DATABASE_URL via CI only - run NO database test locally).
Expected (orchestrator, before dispatch): 60 min / ~350k.

Core: the five copied behaviours are visible on the real screens, and each one is pinned by a test on the real
component or route.
Proof: step 1 is a failing vitest for RD-012 on the real builder page component. With no broker connected, the Trade
action renders disabled with its reason text before any click. Today it is enabled and prompts only on use.

Records (read each JSON in full first: `spec/reference-diffs/RD-0NN.json`, fields `reference_behaviour`,
`reference_label`, `ours`, `reference_screens`):
1. RD-010 (REQ-015, row 2): login panel with the is-it-safe explainer, the account-opening link and the no-extra-charges
   line. The wording and the partner link are decided by ADR-175. Read it, and use its link exactly. No hand-typed URL:
   the link has one home module.
2. RD-012 (REQ-015, row 2): the Trade action is shown disabled with a reason when no broker is connected.
3. RD-013 (REQ-015, row 2): the profile shows the connected broker user id (masked as ADR-175 or the record says) and the
   available margin AS READ from Zerodha. Never compute margin (CLAUDE.md hard rule: Zerodha is the authority on
   margin; `tests/test_margin_from_zerodha_only.py`). Money stays a Decimal string from the API.
4. RD-045 (REQ-049, row 7): a data-health state is explained in one sentence with its reason, not a bare word.
5. RD-048 (REQ-049 AC-4, row 7): a missing value carries a short reason in place (tooltip or inline), not only at page
   level.

For each record whose `ours` says "NEW AC NEEDED": add the acceptance criterion to the requirement (ADR-173 / ADR-176:
copying is the default and needs no owner question). First run `tools/spec_similar.py` on the new AC text and extend
or cite a match. The new AC's text must not name the reference product (ADR-176). Add the AC's test to the work item's
`tests_required` (W-130 for REQ-015, W-135 for REQ-049). When a record is built, set its `status` to `built` and add the
commit (do NOT set `verified`: the checker's result does that). Do NOT regenerate `docs/process/reference-differences.md`
or any index (generated files stay out, CI's stale check is handled at chunk close).

Spec basis: ADR-176 (2) as amended by ADR-178 (2): COPY records are built once per chunk by one builder with one
check. ADR-173 (reference product first). ADR-175 (account-opening link with the partner code, and the is-it-safe
explainer). ADR-003 (wording is decision support, never advice). REQ-015, REQ-049 (every AC).
Copy from: none - frontend wording and status display; legacy-reuse map rows for REQ-015 / REQ-049 are checked by copy_from_check below.
Reference: screens 180, 246, 216, 245, 051 - copy the five behaviours of RD-010, RD-012, RD-013, RD-045, RD-048. Other open records of REQ-015 (RD-014) and REQ-049 are not in this part (RD-014 is part B); RD-014 waits for part B.
Mutation gate: run `python scripts/orchestrator/mutation_gate.py` on every guard you add (the disabled-Trade condition, the margin-as-read rule, each reason mapping) before reporting; quote its results file.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-chunk1-copy`, branch `build/seq-chunk1-copy`, made by the
orchestrator from the chunk head. Commit with `git commit -F <msg> -- <your paths>`, and do NOT push. BINDING: never
stop a process by name; stop only PIDs you started. Frontend mutants: copy `frontend/` to your scratch folder and run
vitest THERE. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\7a0c81e3-1fa0-4c0c-ab2b-6ae5a07ae075\scratchpad\copy-a`.

Attack list: (each names its test file)
1. No broker connected: Trade disabled with its reason before any click; connected: enabled (a new or changed `frontend/tests/*.test.js`).
2. Profile with a connected session: masked user id and margin exactly as the API string returns it; API margin read failing: the reason, never 0 (frontend test + the route's test).
3. Login panel shows the explainer, the link from its one home module, and the no-extra-charges line; the link is not retyped anywhere (a repo grep test or the existing one-home test).
4. Each health state (stale, delayed, unhealthy, unavailable) renders its sentence with the reason (frontend test).
5. A missing value shows its reason in place, per reason code (frontend test).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) the margin
read's answer states - stated, absent, failed, empty, not connected - each with what the profile shows (never a computed
or zero margin).
Threat model: in scope - a margin figure not from Zerodha, a retyped partner link, advice wording; out of scope - the
login flow itself (row 2, unchanged).
Findings checked: brief-rule-from-memory, report-time-typed-not-read
Reviewer checklist: each record's behaviour on the real component; new ACs not naming the reference product; margin only
as read; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only;
no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Legacy map rows (copy_from_check.py)
Rows of the legacy-reuse map that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read
before designing; SKIP -> do not re-survey.

| `app/utils/market_hours.py` (138) | ADAPT | add holiday calendar and BSE hours; its hard-coded 2026 holiday list is wrong (F-54): never copy it, use the dated NSE data file (ADR-119) | REQ-049 |
| `services/brokers/market_data/ticker/models.py` (84) | ADAPT | row 1; fix float serialization `:61-69` | REQ-049 |
| `market_data/auth_tracking.py` (102) | REFERENCE | token-expiry detection idea | REQ-015 |
| `tests/factories/ticks.py` (220), `tests/backend/brokers/` (normalized tick, health monitor, pool, token policy, iv solver, kite ticker) | ADAPT | Decimal; with the ticker copy | REQ-049 |
| `src/services/priceService.js` (251) | ADAPT (P3b) | polling fallback only; change math from the backend | REQ-049 |
| `src/components/common/MarketStatusBanner.vue`, `DataSourceBadge.vue` | ADAPT (P3b) | data-health indicator | REQ-049 |
| `src/components/settings/KiteSettings.vue` (388), `views/AuthCallbackView.vue` (81) | ADAPT (P4) | no token in URL | REQ-015 |
