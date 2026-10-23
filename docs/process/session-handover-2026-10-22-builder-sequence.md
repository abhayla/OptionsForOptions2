# Session handover 2026-10-22 ~18:10 IST (builder sequence, session 1) - continue with the same /goal prompt

## UPDATE session 6 (06fe7549), 2026-10-24 - START HERE (newest)
"Session-6 scratchpad" = `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\06fe7549-4596-4e85-8261-0804902d0768\scratchpad`
(`chunk2-notes.md` = per-row Measure results and decisions; `chunk2-deferred.md` = items for #532; helpers
`render_brief.py` (make_brief render + open records of every named REQ + map-row append + both checks),
`kitrun.py` (kit checkers from a worktree root), `wtrm-batch.ps1` / `wtnew.ps1` (user-level worktree tools by wrapper)).
Chunk 1 merged before this session (PR #525). Chunk 2 = branch `build/seq-chunk-2`, draft PR #531, sequence worktree
`D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`.
- **DONE (rows close in order):**
  - Row 17 (REQ-006+007 UX levels removed, W-145 in_review until #531): spec A1-A3 (ADRs, vision, invariants,
    registers, 13 REQs, 89 re-pins + 134 amends citations, REQ-035 back to Approved), backend (one column set; outcome
    route ignores a stray `ux_level`, `advanced_details` renamed `leg_quotes`, sent only for a COMPUTED answer), frontend
    (no switch, no `?ux=`, no level in any request). Opus check + fix round 1 + round 2 PASS (`results-row-17.md`).
  - Row 18 (REQ-035 strategy table, W-146 in_review): full-AC Opus check found AC-7's heading pair never reached the
    screen; built (94077a89); round 2 PASS; evidence W-146 AC-1..8.
  - Chunk 2 process item: `scripts/orchestrator/reach_check.py` + baseline (every entry cites #532/#528) + repo test;
    checked twice. It reads only python tests (frontend-only evidence = UNRESOLVED by design) and "reached" = imported,
    not called (row 18's AC-7 is exactly that gap).
  - Chunk-1 conformance check (late): 13 MISS; tracker updated. Reference study for rows 17-24: RD-122..RD-163.
  - Issue #532 = chunk 2's ONE deferred issue (reach-check hits + tooling); add items to its body, never a new issue.
- **IN FLIGHT at writing:** row 19 backend finish round (worktree `-row19`, branch `build/seq-row-19`, brief
  `row19/brief-19fix.md`): 5 guard tests it broke, ruff +8, day stats via a real provider method (not getattr),
  futures LTP from the feed, strikes listed without a spot. Overlap gate OK vs row 18 (a3209a88).
- **NEXT, in order:** row 19 backend check (Opus: kite_frames / kite_provider / feed_health are safety set) -> row 19
  frontend part (picker tabs, multi-select Buy/Sell, depth popup; notes in `chunk2-notes.md`) -> row 20 (take hunks from
  `build/W-126-a1-leg-rows` per the notes; backend shares main.py with row 19 so it starts after row 19 backend lands)
  -> row 21 (after row 20; shares 6 files) -> row 22 (check `ofo.scenario.outcome` is UNREACHED) -> 23 -> 24 -> chunk
  COPY builder for rows 17-24's open records -> chunk Tier A review -> chunk-2 conformance check.
- **Worktrees to remove when #531 merges** (wt-rm refuses before: merged into the chunk branch, not main; use
  `-Discard -MergedSha <merge sha>`): `-row17a2`, `-row17b2`, `-row18`, `-OptionsForOptions2-chunk2-process` (odd name:
  wt-new prefixes the repo name), later `-row19`. An empty locked harness worktree `agent-a59c99e84c09acee8` sits under
  the project's hidden worktrees folder (9d885bda).
- **Process lessons this session:** (1) always run overlap_gate.py before ANY row-ahead dispatch (missed once, new
  finding); (2) a data-feature brief lists the plumbing between decoder and route (provider, feed health), not only the
  endpoints - row 19's narrow list shipped values always null in production; (3) a merge in progress makes the overlap
  gate count the whole chunk diff - resolve and commit first; (4) `test_row_review_log.py` still needs `### Row N` per
  closed row and `### Meta review after row N` every 3rd row (short form is fine); (5) Tier A items stay `in_review`
  until the chunk PR merges (trace_check wants review_status naming the PR); (6) a builder may rename a response field
  beyond its brief - read its report for "beyond the brief" and grep the other side before merging.

## UPDATE session 5 END (5db71e90), 2026-10-23 (older)
"Session-5 scratchpad" = `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\5db71e90-61e3-4f1b-8a6c-a0ee38c54e11\scratchpad`
(attack scripts of every review are there: `review-a1..a3`, `review2-*`, `verify-*`).
Chunk 1 = PR #525. The kit merge gate cannot read a PR of 300+ files (687 here; kit #163), so the owner approved ONE
manual merge (ADR-180, 2026-10-23 ~23:57 IST): CI green on the head + the gate's rules checked by hand, then a plain
merge commit. Check `gh pr view 525 --json state` first: MERGED means start chunk 2 from main.
- **Rows (evidence recorded, ac_fp on every block):**
  - Row 11 W-139 (REQ-114): all 8 pass, `in_review`. AC-7 was re-verdicted FAIL by the chunk Tier A review (market
    closed reached only the Settings card), fixed by F1 + the independent redesign (one market-state path; banner and
    last values labelled stale on every price screen; index never LIVE when closed), re-recorded pass on 1006ca32.
  - Rows 12-14 W-140/W-141/W-142 (REQ-072/032/033): all pass, `in_review`.
  - Row 15 W-143 (REQ-028): AC-2 fail on the app path (#528: modification, adjustment proposal and exit domain types no
    route calls); others pass; stays `todo`.
  - Row 16 W-144 (REQ-038): AC-3 and AC-4 fail end to end (no live plan can activate a proposal; the adjustments row
    closes both, #527); AC-1/2/5 pass; stays `todo`.
- **Reference copy (ADR-178 (2)):** all 16 chunk COPY records verified (parts A, B1, B2; check + findings-only round 2).
  12 NO-SCREEN records deferred to the owner capture list #529. 7 SPEC CHANGE records wait for Q282 (do not block).
- **Chunk Tier A review (one round, three areas read in parallel because the chunk is ~5,400 product lines):** round 1
  FAIL in all three (area 1 market closed shown live; area 2 a user read never retried a 429; area 3 an evidence verdict
  on an unreachable path). Fixes F1 (feed) and F2 (limiter MINORs, migration 0023 downgrade refusal); ADR-179 (a user
  read after a 429 is refused busy unless Kite states a wait that fits 5 s; F-60's 10 s cooldown) amends REQ-118 AC-4.
  Round 2 (findings-only): areas 2+3 PASS; area 1 MAJOR left (index LIVE on a closed market) -> independent redesign (ADR-106 rule 5) -> check FAIL (last value hidden) -> fix -> re-check PASS on 1006ca32.
- **CI fixes 3-5:** openapi/VersionOut/template pins/golden bytes; the 18 database-drop guard tests run in CI again
  (+ repo test `tests/test_dependency_skips_have_a_ci_home.py`); apt reads the Ubuntu archive directly before Playwright
  installs (reviewed fix 2 after fix 1 failed; repo test `tests/test_app_workflow_apt_direct.py`); 116 spec pins.
- **Deferred issues filed:** #526 (chunk MINORs), #527 (row 16 latent + Execute race + adopted units: fix BEFORE the
  adjustments row), #528 (row 15 AC-2), #529 (owner capture list), #530 (calendar special sessions/muhurat: fix before
  a live deploy that spans one; Diwali 2026-11-08).
- **Findings:** new transcript-usage-counted-per-line, test-skipped-in-its-only-ci-job, ci-apt-mirror-stall (all
  guarded); verified-on-a-module-the-product-does-not-call 4th occurrence (still unguarded: its automated check is chunk
  2's one process item); brief-rule-from-memory 15th (a Kite fact written without its F-id).
- **NEXT, in order:**
  1. Read CI on the head (`gh pr checks 525`); red -> fix from `gh run view <id> --log-failed`, tail only.
  2. If PR #525 is still open: re-check ADR-180's four facts on its head (CI green; 1006ca32 an ancestor; main not
     ahead; files after 1006ca32 docs/spec/evidence only) and merge it with a plain merge commit (ADR-180 covers #525
     only). Then remove the merged worktrees (below).
  3. Chunk 2: keep every PR under 300 files (finding pr-exceeds-merge-gate-file-limit) - land rows in PRs by area,
     each through `merge.py`, until kit #163 is fixed.
  4. Chunk 2 starts with its one process item: the automated check for verified-on-a-module-the-product-does-not-call
     (per Verified/in_review requirement, the modules its evidence tests import must be imported by a route/app module).
  5. Before release: Connect Zerodha panel text (`frontend/src/lib/connectHelp.js`) gets the ADR-175 NSE ad-code check
     (owner business item at the release brief); #530 before any live deploy across a special session.
- **Worktrees to remove** (merged into the chunk branch; remove with wt-rm.ps1 by hand - the kit guard refuses any
  command naming the `.claude` folder it lives in): `-ci-fix`, `-process`, `-builder-next`, `-builder-next-12`,
  `-row-16`, `-chunk1-copy`, `-chunk1-copy-b2` (the last two have frontend node_modules: count packages in the main
  checkout before and after, run-discipline F4).
- **Process lessons this session:** (1) the kit guard blocks any command whose TEXT names `.claude`, `spec`, `views`,
  `tools/`, `.github` - run kit checks from the main checkout through the read-only wrappers in the session-5 scratchpad
  (`kit_checks.py`, `dupes_summary.py`) and commit with pathspec globs that avoid the words; PowerShell does not expand
  `tests/test_*.py` (use the Bash tool for the guard suite). (2) One CI red hides the next: run `kit_checks.py` + guard
  + repo_scan before every push. (3) Briefs written from memory were wrong three times (manual units, clearing the flag,
  Kite's 429 wait): quote the ADR/REQ text and cite the F-id for every vendor fact. (4) Per-row checks passed modules
  users never reach, twice in one review: every check brief now asks "which screen/route shows this, and did you
  exercise it there?" per AC. (5) Builders stop at 80% budget with gates unrun: the orchestrator runs repo_scan,
  kit checks, the full frontend suite and the register check itself before merging - cheaper than another round.
  (6) A hand-edited evidence file must keep the footer "Recorded by the orchestrator from the verifier's returned
  block." verbatim (tests/test_spec_integrity.py); a docs-only commit still gets the guard suite before the push - one
  skipped run cost a red CI on the merge attempt. (7) One running verifier freezes git writes in every worktree: merge
  and commit builders' finished work BEFORE dispatching a checker.

## UPDATE session 4 END (7a0c81e3), 2026-10-23 (older)
Handed over at the context limit (measure_process: avg 226k/turn), with 0 rows closed. "Session-4 scratchpad" below =
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\7a0c81e3-1fa0-4c0c-ab2b-6ae5a07ae075\scratchpad`.
Rows 15-16 start-check results: `builder-sequence-briefs/results-rows-15-16.md`. Chunk head f23f0818 is pushed,
and draft PR #525 CI is running on it.
- **DONE:**
  - Draft chunk PR #525 opened (step 1).
  - Row 11 round 2 PASS: 5/5 checks, 3 mutants killed (`verify-row-11-r2.md`). Combined evidence JSON for AC-1..AC-8
    is written but not recorded: session-4 scratchpad `ev-W-139.json` (round 1 was extracted from session b9b5cb32's
    agent output, `r11-round1.json`).
  - Row 12 round 2 PASS, with one MINOR: the `except SpotRefused` safety net was removed (`verify-row-12-r2.md`
    result in this block).
  - CI fix 1 (5d5534d0) and CI fix 2 (6097acf8): row 11's 14 database failures, the asyncpg collection error, the
    bundle self-test, the template pin, Windows-only brief paths (new helper `scripts/hooks/brief_path.py`), the
    bus-socket race and the e2e reconnect text.
  - Copy part A: RD-010, RD-012, RD-045 and RD-048 built (REQ-015 AC-10/AC-11), all set to `built`, no check yet.
  - Row 16 (REQ-038) built: migration 0022 `strategy_versions`, store/route/return path, `POST
    /strategies/{id}/versions/{n}/confirm`. Its attack-6 test fixes (b5855c17) have NOT run on a database yet.
  - Process: `make_brief.py` and `row_actuals.py` (f441b87d). Not reviewed; the actuals token column is unproven on
    real transcripts.
  - Kit harvest issue #162 (guard false positives) filed. Stray worktree removed (step 8).
  - Findings bumped: `verified-on-a-module-the-product-does-not-call` (REQ-038 reset from Verified to Approved),
    `verifier-guard-watches-every-worktree` (5th), and `domain-test-imports-app-package` (now unguarded).
- **NEXT, in order:**
  1. Read CI on f23f0818: `gh pr checks 525`, and for a red job `gh run view <id> --log-failed`, tail only. Red
     means CI fix 3, findings only.
  2. With NO builder writing (the verifier write guard blocks every worktree), dispatch three checks:
     - Row 16: Opus, full check (Tier A migration). Mutants are ready in the session-4 scratchpad `row16\mutants.json`.
     - CI fixes 1+2: Opus, findings only, 15/20 (`kite_ws.py`, `scripts/hooks/brief_path.py`).
     - Process tools: Sonnet, 15/20.
  3. Close rows 11 → 12 → 13 in order, once CI is green:
     - Record evidence with `record_evidence.py`, then add the `requirement` and `ac_fp` lines (scratch
       `close_rows.py` shows how; it handles rows 13-14 from `results-rows-12-14.md`).
     - Set W-139/W-140/W-141 to `in_review`.
     - File ONE chunk deferred issue for all MINORs: row 11's two time formats for one banner, its stale comment
       at `feed_health.py:42` and the hyphenated `access-token`; row 12's `SpotRefused` net and its untested
       missing-leg + missing-index case; rows 13-14's surviving mutants `shared_greeks_key_iv` and
       `days_in_year_guard`; row 15's M7/M9; and the brief-path fail-open on a missing file.
     - Three rows closed means hand over.
  4. Row 15: one Sonnet check of REQ-028 AC-2 (not checked; the other 4 ACs pass, results in this block's session
     transcript, summary: AC-1/3/4/5 pass).
  5. Copy part B, after row 11 closes: RD-013 (profile margin as read), RD-014, RD-025, RD-039, RD-046, RD-047,
     RD-057, RD-058, RD-063, RD-068, plus RD-090/095 after row 15 closes. Several already match after row 11
     (RD-046 calendar, RD-068 wording, RD-039/047 the 60 s silence): verify and mark `built` with file:line.
     Then ONE check of all 16 COPY records.
  6. Before release, compliance: the Connect Zerodha panel text (`frontend/src/lib/connectHelp.js`, the
     no-extra-charges line is the builder's own wording) gets the ADR-175 NSE ad-code check against GLOBAL.md's
     compliance text. This is a business item for the owner at the release brief.
  7. Row 16 known limit: the Execute route will not build an adjustment plan while units are held, so a proposed
     version cannot reach `active` in the live app yet. The adjustments row must close this.
  8. The 12 NO-SCREEN records of rows 1-16 are decided per record before chunk 1 closes. The 7 SPEC CHANGE records
     wait for Q282.
- **Worktrees** (wt-new meta, TTL 48h): `-ci-fix`, `-chunk1-copy`, `-row-16`, `-process` (all merged into the
  chunk branch; remove with `wt-rm.ps1` once their checks pass), `-builder-next` and `-builder-next-12` (rows 11/12,
  merged or superseded; remove after the rows close).
- **Process lessons this session:** the verifier write guard froze two builders for about 25 minutes, so run checks
  only when no builder needs to commit. Kit tools (`tools/*.py`) are blocked in a linked worktree outside the main
  folder (kit #113), so rely on CI for factory_lint/trace_check. Commit messages naming a guarded word go through
  a message file.

## UPDATE session 3 END, 2026-10-23 ~14:4x IST (older): implement ADR-178, then rows 11-16
- **Process audit done** (independent, Fable): `docs/process/process-audit-2026-10-23.md`. Owner approved its three
  loosenings (ADR-178, Q283); its technical changes are the orchestrator's (ADR-178 lists them). Read ADR-178 FIRST -
  it overrides the per-row rules of the goal contract, row-review.md and ADR-176 (2) where they differ.
- **Rule 1 for every session from now: keep the orchestrator's context small.** A fresh session about every 3 rows; never
  read logs, transcripts, diffs or the 63-row table into context (tail 20 lines, or ask an agent); scripts write briefs,
  evidence, issues. This session (0c676935) ends here for that reason.
- **NEXT, in order:**
  0. Enforcement of ADR-178 (owner: "nothing get missed, nothing get assumed"; the auditor's minimum set, ~70 min,
     ~10M tokens): `docs/process/adr-178-tracker.md` (12 rows, one counter each) is written. Build: (a) one Sonnet
     builder (Size S, 30 min / 40 calls) adapts the audit's scripts (`measure_sessions.py`, `measure_transcripts.py`,
     `classify_commits.py`, in the session-3 scratchpad `process-audit/`) into `scripts/orchestrator/measure_process.py`
     printing the tracker's counters 1-7 and 10 against their limits; (b) one line in the project SessionStart hook
     printing the tracker's `open` / `missed` rows; (c) a chunk-end conformance brief (Sonnet, 15 min / 25 calls). Run
     the script at EVERY session end and update the tracker's status column from its output (never typed).
  1. Open the chunk-1 PR as a DRAFT now (`build/seq-chunk-1` -> main; body with the Spec-deviation block) so CI runs
     the app DB suites on every push; stop using the tunnel for selections (only a row's own new DB test file locally).
  2. Row 11: merge `build/seq-row-11` (fix 1 at cffc1da8; 5 items done, gate 9/9) into the chunk branch's current head;
     round 2 = FINDINGS-ONLY (ADR-178 (1)): AC-7 wiring + the ADR-177 wording, AC-2's drop test (A10), AC-6's token
     check, the changed files; Opus (live-feed files). The ~10 DB failures seen at 76-86% of two cut runs are
     unclassified: classify them from the draft PR's CI run against fb9a3702's behaviour. Row 11's open COPY records
     go to the chunk-1 copy builder (ADR-178 (2)), not to row 11.
  3. Row 12: verify fix d76cd0e0 (`-builder-next-12`, outcome/service.py = safety set -> Opus, small scope); the stale
     index stays computed with a label (REQ-072 AC-3) - the brief's item 2 was wrong, the builder was right.
  4. Rows 13-14: close from `results-rows-12-14.md` (one deferred issue for both MINORs).
  5. In parallel: rows 15-16 (one shared verifier) and ONE chunk-1 reference-copy builder for the chunk's open COPY
     records (`python scripts/orchestrator/reference_register.py --open REQ-...` per row's REQ; about 23), Sonnet,
     one Sonnet check (Opus only for records touching safety-set files). The `spec_change` records wait for Q282.
  6. The one process exception (ADR-178): a brief generator `make_brief.py <row> <measure.json>` (Sonnet), and a
     script that generates the measured expected-vs-actual table from commit times + transcripts. Nothing else.
  7. File a kit harvest issue: the kit guard blocks read-only commands whose TEXT contains a guarded word (about 9-12
     blocks per session, e.g. a commit message saying "SPEC CHANGE").
  8. Remove the stray worktree `.claude/worktrees/agent-a5043e23c50a0886e` with `wt-rm.ps1` (empty, from a builder run).
  9. Chunk-1 close: the draft PR becomes the real PR, ONE Tier A Opus chunk review, CI green, land.
- **Open for the owner:** Q282 (13 approved-requirement differences, recommendation each, in
  `owner-questions-2026-10-23.md`); Q273 (Redis host, at the first deploy brief).
- **Reporting now (ADR-178 (3)):** a short status per row; the full table, review and trend once per chunk or when a
  row runs >50% over.

## UPDATE session 3, 2026-10-23 14:2x IST - PAUSED BY THE OWNER (older)
- Owner, ~14:20: "pause everything other than the audit. Let audit run and give its recommendation, and based on that
  we will implement everything, including 61 issues that we have found out, plus the requirements".
- Running: the independent process audit (Fable; report in the session-3 scratchpad `process-audit/report.md`).
  Paused: row 11 fix 1 (commits 38b757fe, cffc1da8 on build/seq-row-11; asked to stop and commit any WIP), row 12 fix
  built (d76cd0e0, not verified), rows 13-14 verified, not closed. Register merged (b38b268a, 121 records, page
  57be2e77); deferred #524; the batch of approved-requirement differences = Q282 in owner-questions-2026-10-23.md.
- NEXT: read the audit, present it, implement what the owner approves, then the 61 gaps and the rows.

## UPDATE session 3, 2026-10-23 12:51 IST (clock) - READ THIS FIRST (newest)
- **New binding rules ADR-173..176 (owner, between 12:46 and 13:12 by commit times):** reference product first for every requirement, enforced by
  `check_brief.py` (process item `process-sensibull-line.md`, built bd2a69d4 - label to be renamed `Reference:`);
  every difference is a record in the ADR-176 register (to be built), gated at brief / verify / close; always copy,
  never a bug, approved extras via one batched SPEC CHANGE list; new text never names the reference product.
  ADR-174 (no prices without Zerodha, revisit at the demo), ADR-175 (account-opening link with the PIFS partner code
  + "is it safe" explainer). Rows 1-16 studied: session-3 scratchpad `sensibull-study/rows-01-07.md` (23 gaps),
  `rows-08-14.md` (21), `rows-15-16.md` (17) - to be loaded into the register. A row in flight closes only after its
  records are built or decided.
- Process branch merged into the chunk branch (7d93c1bd). Row 11 verify r1 dispatched 12:46 (b04d47f0); row 12 fix 1
  dispatched 12:46 in `-builder-next-12` (overlap gate OK). Known red: one hook test whose sample brief predates the
  mutation-gate rule - fixed in the Sensibull process item.

## UPDATE session 2 END, 2026-10-23 12:36 IST (clock) - older
- **Closed:** rows 1-5, 7, 9 (REQ-113), 10 (REQ-118, fb9a3702: Done, AC-6 sender deferred #521, MINORs #522). PARKED:
  6 (#517), 8 (#519). Chunk branch `build/seq-chunk-1` head fb9a3702, pushed; no PR until row 16.
- **In flight - four worktrees (ADR-171: four rows in flight, rows close in order, no shared files, ONE db run at a time,
  older first, one agent per worktree):**
  - `OptionsForOptions2-builder-next`, branch `build/seq-row-11` (pushed, b04d47f0, clean): row 11 (REQ-114) BOTH PARTS
    BUILT. Part A 799b16ab (gate 15/15 killed; no DB run yet). Part B b04d47f0 (12:38-12:46: vitest 16/16, lint clean,
    gate 8/8 killed; e2e NOT run - no Chrome; one known CRLF failure in learn.test.js). NEXT: verify row 11 with
    `verify-row-11.md` - fill <HEAD> = b04d47f0 and <B-SHA> = b04d47f0; its DB run uses THIS worktree path in
    fresh_launch.py. Note for row 11's review: part B's mutation launcher (`scratchpad\row11b\vt.py`) swapped mutant
    files INTO the real worktree and restored them (breaks R4 - scratch copies only; the tree was verified clean after,
    `git status` empty) - tell the next frontend builder to copy `frontend/` to scratch and run vitest there.
  - `OptionsForOptions2-builder-next-12`, branch `build/seq-row-12` (clean, at fb9a3702): row 12's one fix
    (`row-12-fix-1.md`, REQ-072 AC-2 wrong reason when the index is missing). Dispatch when row 11's verifier is
    dispatched, after `python scripts/orchestrator/overlap_gate.py <row-11 wt> fb9a3702 <row-12 wt> <plan file>`
    exits 0 (plan: backend/ofo/outcome/service.py, tests/outcome/test_spot_gate_reason.py).
  - Rows 13 (REQ-032) and 14 (REQ-033): FULLY re-checked on fb9a3702 - every AC passes (Opus non-DB: hand computations to
    the paisa; DB part 224 passed). They close right after row 12 (evidence from `results-rows-12-14.md`; the two
    surviving mutants - shared-Greeks key IV (= #519) and days_in_year guard - are MINORs for one deferred issue).
  - `OptionsForOptions2-process`, branch `build/seq-process` 05c3e431: mutation_gate.py fix (proven), kill_by_name_guard
    hook (Tier A r2 PASS WITH MINORS, port-owner kill fixed; MINORs #523). MERGE it into the chunk branch when no agent
    writes in builder-reqs: combine `.claude/project/hooks.json` (the chunk has the night hook, the process branch the
    kill guard - keep both), regenerate settings with `python tools/kit_settings.py <wt>` from the main checkout, then
    `tests/hooks` must pass (2 night-hook wiring tests fail on the process branch alone - expected).
- **Kill guard at user level (Q276): WIRED and LIVE since 2026-10-23 12:42** (run at the owner's instruction; backup
  `settings.json.bak-20261023-124239`; a test `taskkill //IM ...` was BLOCKED). Any name-based kill is now refused in
  every project; stop processes only by the PIDs you recorded.
- **Owner decisions today:** ADR-170 (keep per-user feeds, ask Zerodha at the demo), ADR-171 (four rows in flight, binding
  overlap gate, one agent per worktree, older first), ADR-172 (IV from the bid-ask mid, else LTP), Q276 (kill guard on
  now). Open: Q273 (where Redis runs in production - ask at the first deploy brief).
- **Mechanisms due (Learn-or-block):** finding `report-time-typed-not-read` (3 occurrences): a report/log time stamped
  from `date`, and a repo test refusing a log time later than its commit - build as the next process item.
- **Meta review** due after row 12 closes, before any later build. Then rows 15-16, then the chunk 1 PR.
- **Infra:** the live API on :8765 (run_api_live_wt.py) dies with this session - restart it if a live read is needed;
  the owner's Kite session (logged in ~09:00 today) is stored and valid until 06:00 tomorrow. DB lock:
  `D:\Abhay\scratch\ofo2-builder-sequence\db.lock` (fresh_launch.py takes it; a dead holder is cleared).
- **R17/R19:** no question box 22:00-08:00 or when the owner has not written for ~30 min (owner-questions file);
  every time written is read from `date` or a commit.

## UPDATE session 2, 2026-10-23 09:06 IST (commit 83707b70) - older
- **Closed:** row 8 PARKED #519; row 9 (REQ-113) Done 08:59 (9dcd471c; MINORs #520). Meta review after row 9 applied
  (335485c7). Owner decisions: ADR-170 (keep per-user feeds, ask Zerodha at the demo; F-59), ADR-171 (one row may be
  built ahead, rows close in order, NO shared files between rows in flight, ONE database run at a time, older row
  first, a separate worktree for the row ahead - `check_brief` enforces `Row-ahead: yes` briefs).
- **In flight:** row 10 (REQ-118 rate limits, W-138) builder dispatched ~09:07 from `row-10-REQ-118-rate-limits.md`;
  a process builder (`process-mutation-gate-night-hook.md`: `mutation_gate.py` + the 22:00-08:00 question hook) in
  the same tree on disjoint files - the hook needs a Tier A check (Opus) before it counts.
- **NEXT:** row 10 verify (Tier A); while it runs, build row 11 AHEAD in `OptionsForOptions2-builder-next` (make it
  with wt-new.ps1) only if row 11's Measure file list shares no file with row 10's changes; row 11 (REQ-114 feed
  health) touches row 9's feed files, which are closed, so check only against row 10.
- **Kite:** the owner logged in 2026-10-23 before 09:03 (exact time not recorded) (live API on :8765 via run_api_live_wt.py, ofo_dev, order path
  off); valid until 06:00 tomorrow; read calls only, never a burst that could draw a 429.
- **R17:** no question box 22:00-08:00 IST or when the owner is away - write `owner-questions-<date>.md`.

## UPDATE session 2 (~21:45 IST) - older
- **Row 8 CLOSED as PARKED #519** (commit 1cee0593, pushed): AC-2 pass; AC-1/AC-3 correct in code but 30 of 40 cache-key
  parts have no killing test (MAJOR, final round); AC-4 deferred. Rules R14-R16 added (row-review.md, builder-brief.md).
- **Row 9 (REQ-113) In progress**, split into parts A0 (core: feed process + Redis Streams bus, API restart keeps the
  socket), A1 (bus loss, login/Disconnect control, positions re-read in bus mode), B (per-user sockets, caps, 06:00
  end), C (browser "reconnecting"). Design: independent Opus review ADOPT WITH CHANGES (proposal in session-2 scratch
  `row09-design-proposal.md`); F-58 (stand-in has no pub/sub, Streams work); Q273 (where Redis runs in production - ask at
  the first two-process deploy brief). A0 built 495c0af7; openapi regenerated 117f38dc (row 7 left it stale); A0 verify
  r1 PARTIAL (no code defect; 5 of 22 mutants survived, MAJOR = late-frame test blind to the API clock). Fix round 1
  brief `row-09a0-fix-1.md` dispatched 21:40; verify r2 brief ready `verify-row-09a0-r2.md` (fill <HEAD>). A failed r2
  = PARK row 9 with an issue. Note: production with LIVE_MARKET now requires `bus` mode, which lacks A1's control
  messages - production live is blocked until A1 (no deploy is planned).
- **NEXT:** A0 r2 -> then parts A1, B, C (each its own brief, Measure already done), close row 9, then the META REVIEW
  (due after row 9, before row 10's build), then row 10.
- Tier A verifiers: dispatch as `general-purpose` (the `verifier` type stops at 40 turns; the budget hook refuses 70).

The next session needs ONLY this file, the goal contract, the table and `row-review.md`. No order was ever sent.
Continue at the FIRST ROW NOT CLOSED (row 8 - see "In flight").

## Read first, in order (all on branch `build/seq-chunk-1`, worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`)
1. `docs/process/goal-contract-builder-sequence-2026-10-22.md` - the rules (step 9 = per-row process review).
2. `docs/process/builder-sequence-2026-10-22.md` - the 63-row table (the checklist).
3. `docs/process/row-review.md` - review method, standing rules R1-R13, the effect check, expected-vs-actual table, log.
4. `docs/process/builder-brief.md` - the template every builder brief uses (updated today).
5. `spec/decisions/ADR-168.md`, `ADR-169.md`.

## State
- **Main:** PR #511 merged (plan + step 0). Nothing else merges until chunk 1's PR (after row 16).
- **Chunk 1 branch `build/seq-chunk-1`:** backup-pushed, NO PR. Rows closed: 1 REQ-001, 2 REQ-015, 3 REQ-054, 4 REQ-117,
  5 REQ-053, 7 REQ-049 (Done); 6 REQ-048 PARKED #517. Work items of closed rows are `in_review` (flip to done and drop
  their coverage lines only when the chunk PR merges - coverage drops done items).
- **Deferred MINOR issues:** #512 (row 46), #513 (picked up by row 7), #514 (before order-path use), #515, #516
  (scheduler start-up gap before 08:30: fix before a deploy restarting the API 07:30-08:30 IST and before the row-63 live
  window), #518. Parked: #517 (row 6 AC-5: redesign the credential guard as a reply-field inventory; a FRESH
  independent designer first).
- **Owner decisions today:** ADR-169 (connect by Zerodha login only); strict row order kept; per-row review by the
  orchestrator + meta review every 3rd row; add checks freely, ask before loosening; expected vs actual per row
  (reason when >20% off); learnings also to the kit (`docs/process/delivery-learnings-generic.md`, harvest
  abhayla/Startup-Factory#161); ofo_test reset approved -> done as a throwaway database per run instead.

## In flight at the handover (row 8, REQ-050 shared computation, W-136)
- Build commits 5844a0c3 + d20287f0 (shared_compute.py, outcome service/snapshot, live route, three test files).
- An independent Opus design review decided (technical, recorded): ONE snapshot instant for the whole answer = the
  latest frame time among the quotes read, capped at the clock; expiry/session checks stay on the real clock; drop the
  `_newest` eviction that made IV entries stale on arrival.
- A fix-round builder was dispatched ~18:00 with `docs/process/builder-sequence-briefs/row-08-fix-1.md` (6 items: one
  instant, forward key, two red repo guards, the hanging M4 test, the row-2 stale test in
  `tests_app/test_strategy_live_push.py`, R13 test selection). Its commits land on `build/seq-chunk-1`.
- **UPDATE ~19:45 IST:** fix round 1 committed at 85de202e (pushed). Tier A verify ROUND 1 = PARTIAL (one more round
  allowed). Passes: second reader of one snapshot computes nothing on the real recorded frames; a new frame gives
  fresh IVs equal to an unshared read; no mixed-instant hole; 15:30 check on the real clock; guards fixed in code. AC-4
  deferred (ADR-053). FIX ROUND 2 (fresh builder, `row-08-fix-2.md`, Size M): (1) pass
  `FeedScope(SHARED_COMPUTE, ctx.feed_owner)` into `read_snapshot` in `ofo_app/routes/planned_entry.py:79` and
  `ofo_app/routes/tracking.py:120`; (2) make `test_100_concurrent_first_requests_for_one_key_run_one_computation`
  discriminate (compute blocks on an event set after the threads start: 100 calls without the per-key lock, 1 with -
  verifier probe `scratchpad/verify-08/coalesce_probe.py`); (3) AC-1 Greeks: per-contract Greeks are still per strategy
  (`table/model.py:252`) - share them through a market-wide entry point outside `table/`, or record the narrowing as a
  decision (technical call; get an independent reviewer if unsure); (4) a test where only the spot changes at the same
  instant and the forward recomputes (kills M15); (5) the 3 app files that failed on a dropped DB tunnel
  (`test_db_pool_core_proof`, `test_strategy_shape_matrix`, `test_strategy_store`) run green through the launcher. Then
  verify ROUND 2 (fresh Opus) - the last; a CRITICAL/MAJOR after it = PARK. Row 8 is over its 90 min / 450k estimate.
  Known local failure, not row 8: `tests_app/test_broker_status_route.py::test_core_proof_a_stored_session_reads_connected_and_ending_it_reads_disconnected`
  fails identically on main (clock skew).
- **NEXT for row 8 (older note):** `git -C <worktree> log --oneline -5` to see the fix commits; if the tree is dirty or half-done,
  send a fresh finisher (row-review R5); then the Tier A verifier (Opus) with a `verify-row-08.md` brief (use
  `verify-row-07.md` as the shape); then close per the checklist below. Row 8 expected 90 min / 450k (it is over).
- Uncommitted at the handover: `knowledge/findings/dependent-tests-not-run-stale-later.json` (commit it with row 8's
  close; regenerate the findings index once at the chunk PR).

## The per-row close checklist (every row, in this order - the owner's standing rules)
1. Before dispatch: Measure (Explore, Sonnet) returns ACs, files, items, an attack list (>= 5, each naming its test
   file), the CI job + variables per new test, and whether the core needs real input. Write the brief from
   `builder-brief.md` + the row part with the `Size:` line, `CI:` line, attack list, Spec basis quoted verbatim,
   `Threat model:` on ONE line; run `check_brief.py` (PYTHONUTF8=1) and `copy_from_check.py --append`; write the row's
   EXPECTED time/tokens into the brief and the row-review table BEFORE dispatch.
2. Builder: Sonnet, `git add <paths>` only, hard budget; locally only the row's own NEW DB test file (throwaway
   launcher); the R13 selection runs in CI on the draft chunk PR (ADR-178).
3. Verifier: read-only, every AC, the attack list, known-failing tests named; Opus ONLY when a changed file is in the
   safety set (`builder-brief.md`), else Sonnet. Round 2 = findings + changed files, 15 min / 20 calls (ADR-178 (1)).
   A row-ahead fix of <= 3 files is verified as soon as it is built.
4. Two failed rounds -> PARKED with an issue (row 6 example); a CRITICAL that breaks CI is removed the same hour.
5. Close: `record_evidence_fp.py` (ac_fp from `fps_wt.py` in the worktree), the work item (tests_required naming real
   files), table status, MINORs as one deferred issue (`gh_issue.py app deferred ... --stage <stage>`), findings same
   turn, then MY self-checks: `tests/test_row_review_log.py`, `tests/test_tests_required_exist.py`,
   `coverage.py . --check`, `ruff_ratchet.py`; commit (message via `-F` file), backup push.
6. Review (ADR-178 (3)): the measured numbers come from `measure_process.py` and the expected-vs-actual generator,
   never typed; a prose review entry only for a row >50% over and at each chunk end (then update
   `delivery-learnings-generic.md` and comment #161). MINORs: one deferred issue per CHUNK, not per row.
7. Report to the owner: a SHORT status - what a user sees now, expected vs actual, open issues and questions, the
   evidence table. The whole 63-row table, process review and trend table once per chunk or when a row runs >50% over.
8. Session end: `python scripts/orchestrator/measure_process.py --chunk-start <sha>`; a MISS = a finding the same turn;
   update `adr-178-tracker.md` Status from the output only. A fresh session about every 3 rows.

## Helper scripts (NOT in the repo): `D:\Abhay\scratch\ofo2-builder-sequence\`
- `fresh_launch.py <checkout> <command...>`: DB tests in a throwaway database with the MAIN checkout's .env (use for
  every DB proof; ofo_test is polluted, #497).
- `fps_wt.py <checkout> REQ:AC ...`: AC fingerprints in a worktree.
- `run_api_live_wt.py` (live API :8765, worktree code, ofo_dev, order path off; the owner's Kite session of 2026-10-22
  expires ~06:00 - a new day needs one login, ask once); `run_api_replay.py` (replay API :8771).
- `kit_issue_comment.py <n> <body>`: comment on the kit repo; `record_profile_door.py`; `core_replay.py`, `core_live.py`.

## How the guards bite (save retries)
- Kit guard: no shell command may contain spec/, tools/, .claude, factory, views, .github - commit with `-F <file>`,
  `git add -u` for tracked files, run kit tools bare as `python tools/<x>.py <worktree-path>` from the main checkout,
  read kit files with Read/Grep.
- `gate_before_commit` refuses a commit after a piped step: separate calls.
- The stray agent worktree `agent-a3130708769c0608b` (empty, at main's head) is locked by a dead process; leave it.

## NEXT after row 8
Row 9 (REQ-113 price feed in its own process - it owns the cross-process cache; Measure first), meta review after row
9, rows 10-11, 12-14 (verified: one shared verifier, close one by one), 15-16 (one shared verifier), then chunk 1's PR:
merge main once, fast checks, `regen.py` once, `land.py --reviewed-sha`, Tier A chunk review, CI's full app suite (83
affected files - stale tests may surface there: fix as part of the chunk), then flip rows 1-16's work items to done.
