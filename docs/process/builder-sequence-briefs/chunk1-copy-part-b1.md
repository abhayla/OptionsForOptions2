# Chunk 1 reference-copy builder, part B1 (ADR-178 (2)): eight COPY records of rows 9, 11 and 15

Common brief: docs/process/builder-brief.md (Budget hard stop: at 72 calls start nothing new, commit, report).
Size: M, about 10 files, 8 items, frontend + catalogue data + spec records
CI: frontend job (`frontend/tests/` files you add or change); kit tests job (`tests/` files you change, `tests/strategy/` for the catalogue); app tests job (only if you change a `tests_app/` file; vars: DATABASE_URL via CI only - run NO database test locally).
Expected (orchestrator, before dispatch): 60 min / ~350k.

Core: a browser tab that loses the live socket keeps retrying forever with a random spread on each wait, and 20 new ready-made shapes match as data with no engine code.
Proof: step 1 is a failing vitest on the real live-socket client: after 40 failed attempts it still schedules attempt 41 at the 30 s cap, and two clients started together never pick the same wait (spread up to 1 s). Today it gives up after 40 and waits a flat 1 s.

Records (read each JSON in full first: `spec/reference-diffs/RD-0NN.json`, fields `reference_behaviour`, `ours`, `reference_screens`, `req`, `ac`):
A. Verify-and-mark (row 11 built these; set `status: built` with the file:line that shows it, change no code unless it does NOT match): RD-039 (REQ-114 AC-1: 15 s check, 60 s silence, 30 s back-off cap), RD-046 (REQ-114 AC-7: dated holiday calendar, ADR-119), RD-047 (REQ-114 AC-1: silence on the whole connection over 60 s), RD-068 (REQ-114 AC-7: one market-closed wording, ADR-177). If one does not match, build it and say so.
B. RD-057 (REQ-113, row 9, NEW AC NEEDED): the browser reconnect wait gets a random spread of up to 1 s.
C. RD-058 (REQ-113, row 9, NEW AC NEEDED): the browser never gives up on the live socket; after the back-off reaches its cap it keeps retrying at the cap. While retrying, the screen keeps its reconnecting state (REQ-114 AC-5 wording helper, `reconnectingText`), never a silent stale answer.
D. RD-090 (REQ-028 AC-3, row 15): add the 20 missing ready-made shapes to `backend/ofo/strategy/catalogue.yaml` AS DATA (no engine or matching code). Leg composition: take each from the reference study, screens 010, 100 and 134 (`D:\Abhay\Ventures\competitors\sensibull\2026-10-21\INDEX.md`; private, outside this repo - never copy its screenshots or text into the repo). Where the study does not show a shape's legs, use the standard textbook composition and say which shapes. Every name and description passes the ADR-003 wording check (decision support, never advice: no words such as best, safe, guaranteed or you should). A shape that overlaps an existing template is refused by the loader (REQ-028 AC-3); resolve it by keeping one, and list it.
E. RD-095 (row 15): template names as users read them (examples from the record: Short Straddle, Long Iron Condor, Bull Butterfly). Rename display names only where the wording check passes; keep the template ids stable (stored strategies and tests reference ids). List each rename.

For each record whose `ours` field starts NEW AC NEEDED: add the acceptance criterion to the requirement (ADR-173 / ADR-176: copying is the default and needs no owner question). First check for a similar line with the kit's spec_similar tool (the kit guard may refuse it in this worktree; if so, grep REQ-113 by hand and say so) and extend or cite a match. The new AC's text must not name the reference product (ADR-176). Add the AC's test to the work item's `tests_required` (W-137 for REQ-113, W-143 for REQ-028, W-139 for REQ-114). When a record is built, set its `status` to `built` and add the commit (do NOT set `verified`). Do NOT regenerate `docs/process/reference-differences.md` or any index.

Spec basis: ADR-176 (2) as amended by ADR-178 (2): COPY records are built once per chunk by one builder with one check. ADR-173 (reference product first). ADR-003 (wording is decision support, never advice). REQ-028 AC-3: "Named strategies (e.g. Bull Put Spread, Bear Call Spread, Iron Condor, Iron Fly, Calendar Spread, Straddle,". REQ-113, REQ-114 (every AC).
Copy from: none - catalogue data and the browser reconnect timing; legacy-reuse map rows for these requirements are listed below by copy_from_check.
Reference: screens 010, 012, 100, 134, 200 - copy the behaviours of RD-039, RD-046, RD-047, RD-057, RD-058, RD-068, RD-090, RD-095. Not built here: RD-065 and RD-066 (REQ-114), RD-096 (REQ-028) and RD-035 (REQ-053, named by a legacy map row below) - all four are `spec_change` records that wait for the owner's batched answer (Q282). Note RD-065 is the SERVER socket's jitter (REQ-114 AC-3, stays as approved); RD-057 here is the BROWSER's reconnect spread (REQ-113) - do not change the server's.
Mutation gate: run `python scripts/orchestrator/mutation_gate.py` on the reconnect guards you add (the spread, the never-give-up loop, the cap) before reporting; frontend mutants run on a copy of `frontend/` in your scratch folder; quote its results file.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-chunk1-copy`, branch `build/seq-chunk1-copy`, already merged with the chunk head f5a1059c. Commit with `git commit -F <msg> -- <your paths>`, and do NOT push. BINDING: never stop a process by name; stop only PIDs you started. The kit guard blocks shell commands naming spec/, tools/, .claude, views, factory or .github: edit those files with Read/Edit, and commit them with pathspec globs that avoid the words (e.g. `':(glob)**/reference-diffs/RD-0*.json'`, `':(glob)**/requirements/REQ-113.md'`). If a write is refused by `verifier_inflight_gate`, wait 2 minutes, retry once, then keep editing and report the pending commit. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\5db71e90-61e3-4f1b-8a6c-a0ee38c54e11\scratchpad\copy-b1`.

Attack list: (each names its test file)
1. 41st reconnect attempt is scheduled at the cap; two clients started together get different waits; a wait never exceeds cap + 1 s (a new or changed `frontend/tests/*.test.js` on the real client).
2. While retrying, the screen shows the reconnecting text from the one helper (`frontend/tests/feed-reconnect.test.js` or a new test).
3. Each of the 20 shapes matches its own template when built from its legs, and none matches two (`tests/strategy/` - a new test file over the catalogue).
4. The loader still refuses a duplicate shape; a renamed template keeps its id (`tests/strategy/`).
5. Every new name and description passes the ADR-003 wording check (the existing wording guard test, or a new one over the catalogue).
6. RD-039/046/047/068: one line each, file:line of the code that matches (no test unless you changed code).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) the live socket's answer states for the client - connected, closed by server, network error, never opened, server sends a close code - each with what the client does next (retry at what wait) and what the screen shows.
Findings checked: brief-rule-from-memory, verified-on-a-module-the-product-does-not-call (the reconnect change must be on the client the live screens actually use: grep which module opens the socket on the strategy and positions pages).
Reviewer checklist: each record's behaviour on the real component or the real catalogue; new ACs not naming the reference product; template ids unchanged; no engine code changed for templates; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/strategy; python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests; in frontend/: npm run lint, npm run test:run (your files)
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Legacy map rows (copy_from_check.py)
Rows of the legacy-reuse map that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read
before designing; SKIP -> do not re-survey.

| `app/constants/trading.py` (158), `strategy_types.py` (421), `enums.py` (375), `websocket.py` (65), `brokers.py` (29) | REFERENCE | hardcoded lot sizes conflict with REQ-053; strategy-type names/categories useful | REQ-028 |
| `scripts/seed_strategies.py` (1312), `app/models/strategy_templates.py` (75) | REFERENCE | row 7; our W-005/W-047 library exists: fill only missing templates; `example_spot` Float (`:62`) | REQ-028 |
