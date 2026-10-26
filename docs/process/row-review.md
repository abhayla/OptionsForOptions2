# Row review: lessons that still change behaviour, and the per-item log

Since ADR-189 (2026-10-26) this file follows the kit deliver skill's step 10: after each item, record minutes, rounds
and the cause of each extra round, and apply the fix that removes the cause the same turn. No per-row table, no meta
review every third row, no tracker. The full history to row 30 (the 62 KB file of 2026-10-22..25, R1-R19, effect
checks and the row log) is in git: `git show 6f08cdb4:docs/process/row-review.md`.

Lesson ids keep their old numbers (R1 -> L1) because scripts cite them. L7 (the measured per-row table) is retired.

## Lessons

- **L1 Attack list before the build** (row 2). The brief carries `Attack list:` with at least 5 numbered attacks, each
  naming the test file expected to hold it (check_brief refuses fewer); the builder runs each before reporting.
- **L2 Run every changed test file in full**, never a `-k` subset (rows 1-2: stale tests). DB `tests_app` files run
  through the main checkout's `db_run.py <worktree>`; a skipped DB test is NOT run. Grep every test tree for the old
  value of anything changed and report the grep and its hit count.
- **L3 Size by files touched** (row 1). <= 5 files S (30 min / 40 calls); 6-15 M (60 / 80); more, or backend +
  frontend, L: split. A class spread over ~20 files is never S.
- **L4 Never mutate in place** (row 1). Mutation copies live in the agent's scratch folder only.
- **L5 A resume re-sends the agent's whole history** (row 3: a 4-call follow-up cost 203k tokens). Resume a builder
  only for a real fix round; a small follow-up goes to a fresh agent with a narrow brief.
- **L6 The orchestrator runs its own checks after every bookkeeping edit**: `tests/test_tests_required_exist.py`
  after a work-item edit, `coverage.py . --check` after a status or stage change, `tests/orchestrator` at a row close.
- **L8 Every guard in a brief is an allow-list** (row 4: 19 shapes passed a forbidden-list). The build section names
  what IS allowed; forbidden shapes go in the attack list only.
- **L9 Read the findings before a time, date or limit rule** (row 5: 08:00 vs F-56's 08:30).
- **L10 A `verified` claim reads the code's use** (row 5): the value AND what the code does with it.
- **L11 Every new test names its CI job and variables** (row 6); a test that can only skip in CI is a defect.
- **L12 Secrets are guarded by inventory** (row 6): the closed set of fields that may exist, asserted both ways.
- **L13 Run the tests a change can break** (row 7): `select_app_tests.py` on the row's own diff.
- **L14 Cache keys are built from the call** (row 8: 30 of 40 key parts had no killing test).
- **L15 Measure lists every caller** of a changed entry point (row 8 missed two routes).
- **L16 Slow DB runs start first**, in the background, with `-o faulthandler_timeout=60` (~23 s per DB test).
- **L17 A business question never holds the session** (row 9: one question held the session ~7.5 h overnight). The
  question tool only while the owner is active (at 22:00-08:00 IST: a typed message in the last 10 minutes, read from
  the transcript by `question_night_guard.py`, fail closed); otherwise
  `docs/process/owner-questions-<date>.md` with the recommendation, and the build continues.
- **L18 Mutation results go to a file as they run** (row 9: results lost when the run was killed); quote the file.
- **L19 Every time written is read, never typed** (2026-10-23: nine typed times, up to 34 min in the future). Use
  `date` in the same step or a commit time; unknown is "not recorded".

## Per-item log (deliver step 10, newest first)

Format: `### <row/W-id> - <title> (<date>)` then one line each: `minutes: <wall-clock>`, `rounds: <n>`,
`extra rounds: <cause, one sentence each, or none>`, `fix applied: <what changed in a brief, rule, test or tool, and
where; or none>`.

### W-153 row 25 - REQ-055 margin check, read part (2026-10-26) - ADR-191 (3) measured row 1 of 3
- minutes: ~253 (11:01 session start -> 15:14 IST merge of #574); core proof live at 11:10 (owner login 11:07): SELL NIFTY26N0322650CE + BUY NIFTY26N0322850CE x65 -> CHECKED, needed 35711.37, available 61324.90, no order
- rounds: 2 Opus (round 1 MAJOR, round 2 one MINOR shipped to the chunk 3 deferred issue); 1 fix dispatch
- extra rounds: round 1 - our ADR-094 figure (Zerodha final.total 6409 + BUY top-up = 13474.50 on the recorded reply) was labelled "Zerodha says" in three texts; the measure (and the orchestrator) accepted "AC-3 met by showing only Zerodha's figure" without reading the labels against the figure's source
- step 2a: FIRED (backend/ofo_app/routes/outcome.py); the draft PR's App tests went red twice before the checker started (ruff ratchet: in-function imports + long lines; the second committed schema docs/api/outcome.openapi.json not regenerated) - the checker never reviewed a red head, as designed; a third red (5 Execute-gate tests asserting the old sentence) was caught by ci_local before the push
- fix applied: builder-brief.md names the second schema file and how it is built; builder-brief.md "check your ADDED lines" (finding local-lint-ratchet-counts-below-ci); dispatch prompts now name the ratchet and the guard Tests: line as their own finish steps; finding own-figure-labelled-as-broker-figure; measure briefs: an AC that names WHOSE figure is shown is checked by reading every label against the figure's source

### W-154 row 26 - REQ-081 money summary, parts b and f (2026-10-26) - ADR-191 (3) measured row 2 of 3
- minutes: ~300 for b + f (measure 11:08; 26b built 11:57; merged #576 ~16:00, #577 ~16:35 IST); 26c separate above
- rounds: 26b 2 Opus (round 1: 3 MAJOR), 26f 2 Sonnet (round 1 PASS, round 2 for the follow-up after 26b's fix); fix dispatches: 26b 1 (+2 resumes), 26f 1
- extra rounds: 26b round 1 - ratios shown from figures without charges when charges cannot be priced (AC-4), no exercise-STT line (ADR-167 (4)), 3 surviving mutants; my fix brief then added a MINOR ("items sum to the total") that contradicted ADR-082's rounded-up total - reverted in the same round; 26b's first build also left 4 repo-guard failures (money outside the engine, one-home constant, write allowlist, reflection) because the builder ran only targeted files before its call limit
- step 2a: FIRED (routes/outcome.py); one CI red before the checker (E501, local ratchet counts below CI); the 26f part did not fire (frontend only)
- fix applied: dispatch prompts name the guard Tests: line and the ratchet as their own finish steps; a fix brief's MINOR is checked against the ADR text before it is folded in (here ADR-082 line 39); builder-brief "check your ADDED lines"; deferred structural items in #537 F4

### W-154 row 26 part c - ADR-167 curves before charges (2026-10-26)
- minutes: ~77 (measure dispatched ~11:20 -> 12:37 IST merge of #575); found by the row 26 measure, not planned (finding accepted-decision-without-owning-row)
- rounds: 1 Opus (PASS, 1 MINOR fixed in row 25) + a delta round 2 on a lint-only commit (PASS)
- extra rounds: the delta round only because the orchestrator's lint fix landed after the review (ratchet E501 rose on 5 added lines)
- step 2a: did not fire (no trigger path)
- fix applied: the kit ci_local default mode cannot run tests above ~8 KB of selected paths on Windows (Startup-Factory #180, finding local-gate-step-argv-over-8k-windows) - used --full

### W-159 row 31 - REQ-085 Builder warnings and "How this trade works" (2026-10-25/26) - PARKED #558
- minutes: ~330 working (measure 14:00-14:40; owner question ADR-185 ~14:20-14:50; blocked by the overlap gate until #552 merged ~15:10Z; 31b build x2 - the first lost to a session restart - fix round, two Opus rounds; 31f build + Sonnet check); parked 2026-10-26 ~02:30 IST unmerged (PR #557 draft, branch build/c4-row-31f pushed)
- rounds: 2 Opus rounds (backend), 1 Sonnet round (frontend, PASS)
- extra rounds: round 1 - reverse calendar not covered the way Execute sees it, liquidity settings untested, unsigned decay text; round 2 - the same Builder/Execute class for FUTURES (expiry ignored for futures in warnings.py) -> ADR-189 park; one brief error (the orchestrator wrote "covered call -> none", contradicting ADR-185's lone-future case)
- fix applied: shared `expiry_covers` in execution/sequence.py used by both screens; the parked issue names the futures fix and the three tests that kill the surviving mutants; checker briefs now ask "does Builder == Execute for every leg kind (options AND futures)"

### W-158 row 30 - REQ-078 Shift / Width / Hedge (2026-10-25)
- minutes: ~454 (13:33-21:07 IST, merge of #554 at 15:37Z); code merged (#552 backend, #554 frontend); PARTIAL until AC-1's live half (50 edits, p95 <= 1,000 ms on the dev server, owner's live session)
- rounds: 2 Opus rounds + an independent redesign (backend), 1 Sonnet round (frontend)
- extra rounds: round 1 - the orchestrator's brief said Width always moves both sides (AC-4's last step was missed) and the route tests faked the eligibility check; round 2 - a STALE index quote kept its price and counted as live (ADR-015); 5 owner questions (~89 min waiting, one held ~70 min of ready work); CI red once - a new slot type not pinned, and the app-test selector does not pick the slot-pin test
- fix applied: ADR-186 (1)-(5) written; one shared `priced(quote)` rule in backend/ofo/marketdata/quote.py; ADR-188 builder handover checklist (docs/process/builder-brief.md: new-file prettier only, selection/slot/template pins, OpenAPI); dispatch before asking; the selector gap -> chunk 4 deferred issue

### W-160 row 32 - REQ-136 Figure definitions and the projections note (2026-10-25)
- minutes: ~128 (13:25-15:33 IST); merged #547; PARTIAL - net premium, charges, funds needed (row 26), breakeven on the target date (row 37), expected-move bands (row 38) get their info mark in the row that renders them
- rounds: 1 Sonnet round (0 MAJOR, 5 MINOR; two wording MINORs fixed by the orchestrator)
- extra rounds: none; one gate red on formatting (builder skipped the gate) and one red from a flaky test under load
- fix applied: builder handover checklist (ADR-188); measure briefs check each AC item against what renders today

### Chunk 4 session A process (2026-10-25, measured)
- measure_process.py fix merged (#549) then retired by ADR-189 the same night; its measured values for chunk 3 session A (a43256ae): context 363k/turn over 627 turns (limit < 250k), 3 rows closed, 0 table prints, 7 Opus dispatches without a safety-set file, round-2 checkers 8/9/15/17/36 min, 4 local DB runs vs 3 rows, row-10 worst 52 min; this session (c097bcc4): 415k/turn over 413 turns
- the independent audit (docs/process/process-audit-2026-10-25.md, ADR-188): about half of row 30's time was waiting; the overlap gate's generated-file refusals fixed (#553)
