# Goal contract GC-TPD: fix the GC-TP deferred findings that need no live market (2026-10-29, evening)

Written 2026-10-29 20:51 IST at the end of GC-TP session 2. Owner decision (question tool, ~20:49): "Fix them tonight
(Recommended)" for R-33, R-34, R-8, R-22, R-37, R-30, R-17, R-9, R-12, R-36; then "Create a Goal contract to fix them
now" and "Do not work on the fixes without goal contract". R-32 (rupee-sign style app-wide) is NOT in this contract: it
needs owner wording. This contract is a DELTA on GC-TP (`docs/process/goal-contract-GC-TP-2026-10-29.md`, same run
tree); it never edits GC-TP's Items rows, only the Found table's "Fix commit" / "Re-test" cells of the ten findings it
closes. The live contract GC-TPL (30 Oct 09:15) is separate and untouched.

**Core:** each finding is a sample of a class; each is closed by a class-level fix with a failing test first on the real
function and real data (the defect-fix contract), merged into `build/gctp`, with the run tree's full suites green after.
**Proof:** step 1 is R-37's read-only data check on ofo_dev's REAL migrated paper orders (no write), the one item whose
fix depends on what the real data holds.

## GC-TPD HANDOVER (written 2026-10-29 21:54 IST)

- DONE (10/10): R-37 (check, 0 real violations), R-22 (store refuses opposite-side open/add), R-17 (checker tolerance), R-9 (no store defect: quotes are the UserText slot by design; 0 of 66 stored names quoted), R-33, R-34, R-8 (already fixed in GC-TP 4a; test added), R-30, R-12 (test cleanup; 10/10), R-36 (hook built, not wired). All on local `build/gctp`, nothing pushed, no upstream.
- NOT MET: full vitest 1617/1618 - `vendor-host-lint.test.js` timed out under load (F-2, pre-existing, passes alone).
- PARKED: none. Deferred (C4): F-2, F-3 (`test_both_curves` pre-existing red), R-9 screen-strip check.
- OWNER STEP (R-36): to switch the hook on, add to the user-level Claude settings under `hooks.PostToolUse`:
  `{"matcher": "Write|Edit", "hooks": [{"type": "command", "command": "f=\"$HOME/.claude/hooks/clock-stamp-guard.py\"; [ -f \"$f\" ] || exit 0; python \"$f\""}]}`
- NEXT: 30 Oct 09:15 owner runs /goal on GC-TPL (live). AFTER GC-TPL: run Part 2 of this file (owner decision before 22:20: leftovers go into GC-TPD Part 2). Worktrees gctp-def1 / gctp-def2 stay until land (wt-rm refuses unpushed work).

## §0.1 Where the run works (worktree isolation)

- Run tree `D:\Abhay\Ventures\OptionsForOptions2-gctp-run`, branch `build/gctp` (local only, NO upstream). Head at writing:
  6c8ae28f.
- Two builder worktrees ALREADY EXIST (created 20:50 by `wt-new.ps1`, TTL 24 h), both based on `build/gctp` 6c8ae28f,
  both empty of changes:
  - `D:\Abhay\Ventures\OptionsForOptions2-gctp-def1`, branch `build/gctp-def1`, `frontend\node_modules` installed (npm ci).
  - `D:\Abhay\Ventures\OptionsForOptions2-gctp-def2`, branch `build/gctp-def2`, no frontend install (backend / checker /
    data only).
  If either is missing, create it with `~/.claude/tools/wt-new.ps1 -Repo D:\Abhay\Ventures\OptionsForOptions2 -Name
  gctp-defN -Branch build/gctp-defN -Base build/gctp -Purpose "GC-TPD" -TtlHours 24` and `npm ci` in def1's `frontend`.
- Never work in the main checkout. Never `git stash` in a worktree (hook refuses). Never remove a worktree (wt-rm.ps1
  refuses until work is on origin/main - owed at land).
- Lock: write `.run-active.lock` (session token + time from the clock) at the run tree root; remove it on any stop.

## §0.2 Preflight (idempotency: never redo finished work)

- `git -C D:\Abhay\Ventures\OptionsForOptions2-gctp-run log --oneline build/gctp` and look for `GC-TPD R-nn` commits: an
  item with such a commit merged into `build/gctp` AND a DONE status below is verified (re-read its proof) and skipped;
  record every skip in the progress log.
- Read before any code: this file; GC-TP's "Found during the run" rows for the ten R-ids; `.claude/kit/builder-brief.md`;
  `docs/process/runbook.md` (test commands); `spec/decisions/ADR-207.md`, `ADR-209.md`, `ADR-210.md`, `ADR-211.md`;
  `spec/requirements/REQ-152.md` (number format), `REQ-084.md`, `REQ-109.md`, `REQ-144.md`.

## §0.3 Progress log

- The Status column of the Items table and the "Found during the run" table in THIS file are the live log, updated in
  the same commit as each item's merge. A crash leaves them current.

## Rules for the run (kept from GC-TP; all still binding)

- **No push, PR, draft PR, GitHub Actions, `ci_local.py`, `prepush.py`, `land.py`, `merge.py`.** Local commits only:
  `GC-TPD R-nn: ...` in the builder worktree, merged with `git merge --no-ff` into `build/gctp` in the run tree.
- **Nothing lost on a crash:** builders commit after each item passes; the session merges each finished builder branch at
  once; no uncommitted change at the end of a turn longer than a few minutes.
- **Paper only.** No code path may call a Zerodha order, GTT, basket or alert-trigger endpoint; never touch an order panel.
- **Money:** every rupee / percent / level shown comes from the server in exact Decimal (ADR-008); the browser formats only.
- **User wording:** no new user-visible sentence. Every text must be an existing pinned template or a text already approved
  in ADR-209 / ADR-210 / ADR-211 / a REQ. If an item truly needs a new sentence, PARK that item (Parked table) - the owner
  is not asked during this run.
- **Sensibull first:** for any screen choice grep `D:\Abhay\Ventures\competitors\sensibull\2026-10-21` (catalogue-raw.md,
  bundle-findings.md, screenshots) and cite the screen; never copy an image into this public repo.
- **Privacy:** never write the owner's funds, client id, name or email into a repo file.
- **Tests:** builders run only touched test files (+ ruff on touched Python, `npx eslint --max-warnings 0` on touched
  frontend files), output to a log, tail only. DB tests ONE file per run through
  `python D:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\db_run_fresh.py TREE python -m pytest -c pytest-app.ini tests_app/FILE.py -q`
  (TREE = the worktree path, FILE = the test file; the PostgreSQL host also serves production: targeted files only). A new
  reply model is added to `tests_app/test_response_door.py` APP_MODELS and that file is run (two builders missed this in
  GC-TP). A new template is pinned in `tests/errors/template_pins.json`. A new slot type is pinned in
  `tests_app/test_identifier_and_slots.py`.
- **Red first:** every fix writes its failing test first and the builder report pastes the red line. A report without a
  red line is sent back once (round 2), then the item is PARKED.
- **Defect-fix contract per item:** RCA (one sentence), Class (data filter, size before/after), failing test, class fix,
  ONE real-data proof, detection change or `No detection change: reason` - written into the item's Found-table row.
- **Rounds:** at most 2 per item, then PARK with evidence and continue.
- **Times** written into any file are read from the clock in the same step (`date +%H:%M`); a guessed time is a defect (R-36).
- **Commits:** the repo hooks refuse `;`-chained, piped or multi-line-python steps before a `git commit`: run each check as
  its own call, then `git add ... && git commit ...`.
- **Verifier write-guard:** while any reviewer/verifier tool call runs, git writes are refused. Do not run a reviewer while
  merges are pending; if a git step is refused, retry on the next call (never delete a snapshot file).
- **Agent dispatch:** every brief carries `Core:`/`Proof:`, `Budget: 60 min wall-clock, 80 tool calls` (agent type
  `builder`, maxTurns 100; never `builder-b` with 80), `Report: evidence-table`, `Sensibull:`, `Size:`, `Reference:`, `CI:`,
  `Guard tests:`, `Attack list:` (5 items), an explicit `model` (`sonnet`; `opus` only with a `Why Opus:` line), and passes
  `python scripts/orchestrator/check_brief.py BRIEF` (exit 0) before dispatch.

## Items

Builder split (no shared file between the two builders): **def1** = R-33, R-34, R-8, R-30, R-12 (screens and reply
text); **def2** = R-37, R-22, R-17, R-9 (data, store, checker). **R-36** is done by the session itself (user-level hook,
outside the repo). def1 and def2 run in parallel; R-36 runs while they build.

| Step | Item | Builder | Decision (pre-made) | Proof | Status |
|---|---|---|---|---|---|
| 1 | R-37 CORE: migrated exit dated before its open | def2 | 0028 is already applied on ofo_dev: NEVER edit 0028. Write `scripts/checks/paper_orders_order_check.py` (read-only SQL via `scripts/orchestrator/dev_run.py`): for every (strategy, contract) in `paper_orders`, an `exit`/`settle`/`stop` row whose placed_at is earlier than the first `open`/`add` row of that contract is a violation; print the count and the rows. Add a pure test with a fixture of both shapes. If the REAL count is 0: the class is guarded by this check (record it); if > 0: STOP the item, record the rows, PARK (repair needs an owner call: it would change booked P&L) | real run on ofo_dev: the count and the strategy ids; the test red on the bad fixture, green on the good | DONE (63d7811e, merged 9412900b): real run on ofo_dev `violations: 0` over 72 orders / 21 strategies / 54 (strategy, contract) pairs -> class covered by `scripts/checks/paper_orders_order_check.py`. Builder wrote the test after the script (no red); session supplied red by mutation on a scratch copy: `<` -> `<=` mutant `1 failed, 3 passed`, empty-result mutant `1 failed, 3 passed`, unmutated `4 passed`. Known gap: a closing row with NO open row at all is not flagged |
| 2 | R-22 opposite-side `open`/`add` stored under the wrong label | def2 | Structural guarantee in `backend/ofo_app/paper_store.py` (the only writer): an `open` or `add` order whose side would reduce or flip the existing net position of that contract is refused, the same way an exit above the open quantity is refused today (reuse that existing refusal path and its existing pinned template; no new sentence). Test: long 65 held, POST `open` SELL 100 -> refused, nothing stored; long 65 held, `add` BUY 65 -> stored | DB test file red then green; `test_paper_routes.py` and `test_paper_order_door.py` still green | DONE (58dcb24f): red `test_paper_store.py` 4 failed, 11 passed; green 15 passed; `test_paper_routes.py` 29 passed, `test_paper_order_door.py` 14 passed (builder tree). Re-run on merged build/gctp: paper_store 15 passed, paper_routes 29 passed. Same EXIT_EXCEEDS_OPEN error and template, no new sentence |
| 3 | R-17 checker per-leg theta tolerance | def2 | In `scripts/checks/ui_data_check.py` `check_target`: the per-leg Greek tolerance grows with the gap between the reply's valuation instant and the checker's (the leg's own theta x the gap in years, plus the current 0.001) instead of the fixed 0.001; keep the total-Greek tolerance as is. The checker still imports nothing from `backend`. Test: the real 63 reply that showed leg2 theta -1218.2047 vs -1218.2059 matches; a 1.0 change to one leg's theta is still a mismatch | `tests/test_ui_data_check_target.py` red then green; the four checker test files pass | DONE (b730eb32): red old checker `test_ui_data_check_target.py` 2 failed, 6 passed; green four `tests/test_ui_data_check*.py` 167 passed. No real -1218.2047 / -1218.2059 fixture existed: the test builds that shape from `outcome-target.json` with a 40 s gap; zero gap = old 0.001 exactly |
| 4 | R-9 strategy names stored with literal quote marks | def2 | Find where names are stored (`backend/ofo_app` strategy save path; grep for `json.dumps(name` and quote-wrapping). If the quotes come from a pre-GC-TP save path, fix the class going forward (store the plain name; one test) and write a re-runnable read-only REPORT script listing affected rows - do NOT rewrite real names in ofo_dev (a data repair is Tier A and needs a backup + owner OK: PARK the repair part with the list). If the cause is inside GC-TP code, fix it and its test | the cause file:line; test red/green; the affected-row count from ofo_dev (read-only) | DONE, no store defect (8a98c187): ofo_dev `quoted names: 0` of 66 stored names (report `scripts/checks/strategy_name_quotes_report.py`, 2 tests passed). Cause of the quotes: `backend/ofo/strategy/stored_form.py:613` renders the name through template `strategy_name_shown` whose `{name}` is a `UserText` slot (`backend/ofo/errors/explanations.py:1089`), quoted on purpose (REQ-134 AC-1, ADR-003 Q226). No repair to park. Screens strip at read (AlertsPage does); other screens not checked tonight |
| 5 | R-33 target breakevens printed without grouping | def1 | Server: the target reply carries `breakevens_display` built with the existing index-level formatter (the one paper cards use for "22,618"); `TargetBlock.vue` shows that text, never the raw value. Test on a real target reply fixture: raw "22578.12" -> grouped text | route test + vitest red then green | DONE (8f520a32, merged 56f33969): red `test_outcome_target.py` 3 failed / `target-block.test.js` 1 failed; green 18 passed / 21 passed. One shared server function `breakevens_display(levels, spot)` in `backend/ofo/outcome/serialize.py` |
| 6 | R-34 Drafts Mode Breakeven lost its move-from-spot % | def1 | `GET /paper/strategies/{id}` (and the list) carry `breakevens_display` in the SAME shape as the outcome summary's `breakevens_display` ("22,618 (−1.4%)"), built by the same server function the outcome route uses, from the book's breakevens and the snapshot spot; absent spot -> plain grouped level. `StrategyBuilderPage.vue` in Drafts Mode uses it | route test + vitest (`builder-drafts-exit.test.js` "Breakeven in Drafts Mode") red then green | DONE (a38c9853): red vitest `builder-drafts-exit` + `paper-card-figures-r19b` 2 failed; green 26 passed; DB `test_paper_list_figures.py` 11 passed. The book already sent `breakevens_text`: renamed to `breakevens_display`, built by the same function. GAP: no Python red line (the DB run started before the rename, finished green after it) |
| 7 | R-8 Alerts page shows "Strategy 64", not the name | def1 | `GET /paper/alerts` rows carry `strategy_name` (plain, no quote marks: if R-9 parks its repair, strip one pair of surrounding quotes at read); `AlertsPage.vue` and the header bell list show it; absent -> the existing "Strategy N" text | route test + vitest red then green | DONE, no code change needed (92ebf9ef guard test only): `GET /paper/alerts` already carried `strategy_name` since GC-TP step 4a (`routes/paper.py:702`) and `AlertsPage.vue:38` already shows it with the quote strip and the Strategy N fallback; no red possible; new vitest case for absent / null / empty name, `paper-list-4b.test.js` 25 passed. The header bell is an icon with a count, no list |
| 8 | R-30 PaperConfirmDialog price not coerced | def1 | `PaperConfirmDialog.vue`: coerce `price` with `String()` like `lots` before `.trim()`; test with a numeric price (no throw, same refusal rules for 0 / negative / off-tick) | vitest red then green | DONE (f090789f): red `paper-add.test.js` `TypeError: r.price.trim is not a function`; green 25 passed (0, -5, 101.03 refused) |
| 9 | R-12 flaky `live-strategies.test.js` "13 strategies, one card loading at a time" | def1 | Find the timing cause (fake timers vs real promises, an unawaited flush); fix the TEST's waiting, not product code, unless the product has a real race (then fix it with a test). Done = the file passes 10 runs in a row (`npx vitest run tests/live-strategies.test.js` ten times, all green) | 10/10 green log | DONE (f31393b0): cause shown by a forced 2.5 s delay before mount: `FakeSocket.all` length 2 not 1 (pages left mounted by earlier tests keep reconnecting); test now unmounts every page; 10 runs -> 10 x `Tests 30 passed (30)`. Test-only change |
| 10 | R-36 a guessed time written into a file | session | User-level PostToolUse hook `~/.claude/hooks/clock-stamp-guard.py` (Write/Edit): finds `HH:MM IST` / `~HH:MM` stamps next to today's date in the written text; if any is more than 5 minutes AHEAD of the system clock, print a WARNING naming the stamp and the clock (non-blocking, exit 0, fail-open on any error); a test file `clock-stamp-guard.test.py` beside it (future stamp warns, earlier stamp does not, unreadable input exits 0). Wiring the hook into the user-level Claude configuration is the owner's step (owner-only by the global rules): the run does NOT wire it and ends with the exact configuration entry for the owner to add | test file passes; the hook run on a sample text with a stamp 10 min ahead prints the warning | DONE 20:59: red `13 failed` (test run against an absent hook path); green `0 failed` (13 cases: 4 warn, 7 quiet, 2 fail-open); real-clock proof: clock 20:59, sample "Written 2026-10-29 21:09 IST" -> `WARNING clock-stamp-guard: ... 21:09 IST ... clock reads 20:59`, exit 0. NOT wired (owner step; entry in the handover) |
| 11 | Merge, full suites, handover | session | Merge def2 then def1 into `build/gctp` (`git merge --no-ff`), resolve conflicts keeping both sides' intent; then ONCE: `FULL_SUITE_BUDGET=600 npx vitest run --maxWorkers=2` in `frontend` and `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan -q`; then the DB files the items touched, one at a time. Update GC-TP's Found rows (Fix commit + Re-test cells) for each closed R-id; write a "GC-TPD HANDOVER" block at the top of this file; remove the lock | suite tail lines; `git rev-parse @{u}` on build/gctp still "no upstream" | DONE 21:54: def1 merged 56f33969, def2 merged 9412900b (no conflicts). Repo guard set ONCE: `959 passed, 1 skipped, 737 deselected`. Frontend vitest ONCE: `Test Files 1 failed | 110 passed (111)`, `Tests 1 failed | 1617 passed (1618)`: the one failure is `vendor-host-lint.test.js` > flags kite.trade, `Test timed out in 5000ms` under load (file untouched since W-055; alone `12 passed`) - NOT a pass, see F-2. DB files one at a time on build/gctp: test_paper_store 15, test_paper_routes 29, test_paper_order_door 14, test_outcome_target 18, test_paper_list_figures 11, test_response_door 214 passed. `git rev-parse build/gctp@{u}` -> `fatal: no upstream configured` |

## Definition of Done

- [x] Each of the ten items (steps 1-10) has Status DONE with its red line, its green line and its proof recorded in this
      file, OR Status PARKED with evidence and what is left in the Parked table. Every item is one or the other; none is
      left "in progress".
- [x] Every DONE item is merged into `build/gctp` and GC-TP's Found-table row for that R-id carries the fix commit and the
      re-test line.
- [ ] (NOT MET: vitest 1 timeout, F-2; guard set passed) After the last merge, the full frontend vitest and the repo guard set each ran ONCE on `build/gctp` and passed (a
      skipped test counts as not run and is named).
- [x] No push, no PR, no CI (`git rev-parse @{u}` on `build/gctp` reports no upstream).
- [x] The GC-TPD HANDOVER block is written and committed, listing DONE / PARKED / the R-36 configuration entry for the owner.

## Guardrails

- No new dependencies. No design reinvention: every fix reuses the existing formatter / template / store path named above.
- No data written to ofo_dev in this contract (R-37 and R-9 are read-only on real data).
- No edit to GC-TPL, to GC-TP's Items rows, to kit files (`.claude/kit/*`, `.claude/rules/kit/*`), or to the user-level
  Claude configuration.
- Stop the whole run (PARK everything left, write the handover) by 23:30 IST: the owner's live goal starts 09:15.

## Found during the run

| F | Step | What failed (seen) | Class / RCA | Fix commit | Re-test |
|---|---|---|---|---|---|
| F-1 | 10 | R-36: a time written from memory, ahead of the clock (3 times on 10-29) | RCA: nothing checks a written stamp against the clock; Class: every HH:MM IST / ~HH:MM stamp on a today's-date line written by Write/Edit; detection: `~/.claude/hooks/clock-stamp-guard.py` (non-blocking warning) | outside the repo (user-level hook) | `clock-stamp-guard.test.py` 0 failed |
| F-2 | 11 | full vitest: `vendor-host-lint.test.js` first test timed out at 5000 ms under the full run (25.8 s); alone 12 passed | timing class like R-12 (cold ESLint load under 2 workers); pre-existing, file untouched tonight. Deferred (C4) | - | - |
| F-3 | 11 | `tests/outcome/test_both_curves.py::test_flag_off_replies_are_byte_identical_to_the_recorded_ones` fails | pre-existing: fails on def2's tree whose outcome code equals base 6c8ae28f (`1 failed`); not in the guard set. Deferred (C4) | - | - |
| F-4 | 6, 1 | R-34 has no Python red line (DB run straddled the rename); R-37 test written after its script | red-first missed twice by builders; R-37 red supplied by mutation (2 mutants each `1 failed`); R-34 JS red exists. No detection change: check_brief already demands red lines; the session check caught both | - | - |

## Parked

| Row / item | Why (evidence) | What is left |
|---|---|---|
| (none parked) | all ten items DONE | R-9 follow-up: check every screen that shows `strategy_name_shown` strips the API's quote marks (AlertsPage does; others not checked) - deferred (C4) |

## Part 2: the GC-TP leftovers (added 2026-10-29 22:21 IST; owner decision by question tool, answered before 22:20 by the clock read right after it: "Part 2 inside GC-TPD")

Part 1 above (steps 1-11) is DONE and stays as recorded. Part 2 is a separate scope with its own Definition of Done.
**When:** it starts only AFTER GC-TPL (30 Oct live) has finished, because R-27 changes slider / target code that GC-TPL step
L2 tests live, and R-25 needs the NIFTY 3 Nov expiry close. All Part 1 rules (worktrees, no push, red first, 2 rounds then
park, no new sentence, Sensibull first, clock stamps) apply unchanged. At the start of Part 2, each item's decision below is
re-read against GC-TPL's findings and the spec (`views/spec-digest.md` + grep by the item's terms) before any brief.

| Step | Item | Decision (pre-made where the spec allows) | Proof | Status |
|---|---|---|---|---|
| P2-1 | R-25 settle price = Kite day-candle close, proven for SENSEX only (F-72) | Proof only, no code first: after 15:45 on 3 Nov, compare the Kite day-candle close with the NSE official close for every NIFTY 3 Nov contract the paper book holds; equal -> record a finding and close; any difference -> record the rows, PARK (changing the settle source is an owner call) | the per-contract comparison table with both closes | Not started (needs 3 Nov 15:45) |
| P2-2 | R-23 an expiry whose close is unreadable before 18:00 settles next day; a conditional exit on that strategy cannot fire meanwhile (calendars) | Tier A (settlement / money). Step 1 = read the settlement and conditional-exit sections of the spec; if the spec decides what a stop on an expired-but-unsettled leg does, build to it; if silent, PARK with an owner question (what a user sees and when money is booked is a business call) | red DB test on a two-expiry book with the near close unreadable, then green | Not started |
| P2-3 | R-27 for 250 ms after a slider move the old pick's figures sit beside the new slider position | Check Sensibull's target slider (screens 020 / 090) first; then mark the old figures as pending (existing styling, no new sentence) until the new pick's reply lands; a stale reply never overwrites a newer pick. Re-read GC-TPL's R-26 result first: if R-26's fix already covers this, close it with a test | vitest red then green | Not started |
| P2-4 | R-13 Drafts Mode writes the `extremes_reason` words in the browser | The book reply sends the text from an existing pinned server template, the browser shows it; if no approved template fits, PARK and add it to the wording question below | route test + vitest red then green | Not started |
| P2-5 | R-35 after hours the what-if of strategies 48 / 56 says "Estimated Now needs live prices" (no last close today) | Classify from GC-TPL's live observation: works live -> a data-availability finding (record in `knowledge/findings/`, no code); still fails live -> a defect, fix the class with a red test | GC-TPL's live line for 48 / 56, then the finding or the red/green test | Not started (needs GC-TPL result) |
| P2-6 | Wording batch: R-15 (reused stale-price sentence), R-20 (nine reason codes show a dash), R-16 / R-32 (rupee-sign style) | Not built in Part 2: ONE owner question at Part 2 start covering all three, each with a recommended text and its Spec basis; answers go into the spec as decision rows, then a follow-up item builds them | the owner's answer recorded as decision rows | Not started |

### Part 2 Definition of Done

- [ ] P2-1..P2-5 each DONE with red/green lines and proof, or PARKED with evidence and what is left.
- [ ] P2-6 asked as one question; every answer written into the spec as a decision row.
- [ ] Every DONE item merged into `build/gctp` (or its successor branch) with the touched DB files and the repo guard set green; GC-TP's Found row for that R-id carries the fix commit and re-test line.
- [ ] A "GC-TPD PART 2 HANDOVER" block written and committed.

