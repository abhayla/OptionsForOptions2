# Session handover 2026-10-22 ~18:10 IST (builder sequence, session 1) - continue with the same /goal prompt

## UPDATE session 3, 2026-10-23 12:51 IST (clock) - READ THIS FIRST (newest)
- **New binding rules ADR-173..176 (owner 12:48-13:45):** reference product first for every requirement, enforced by
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
2. Builder: Sonnet, `git add <paths>` only, hard budget, throwaway-database runner for DB tests, R13 test selection.
3. Verifier: fresh Opus (Tier A) / Sonnet (Tier B), read-only, every AC, the attack list, known-failing tests named.
4. Two failed rounds -> PARKED with an issue (row 6 example); a CRITICAL that breaks CI is removed the same hour.
5. Close: `record_evidence_fp.py` (ac_fp from `fps_wt.py` in the worktree), the work item (tests_required naming real
   files), table status, MINORs as one deferred issue (`gh_issue.py app deferred ... --stage <stage>`), findings same
   turn, then MY self-checks: `tests/test_row_review_log.py`, `tests/test_tests_required_exist.py`,
   `coverage.py . --check`, `ruff_ratchet.py`; commit (message via `-F` file), backup push.
6. Review: the row's log entry (expected vs actual from commit times, causes of every extra round, what changed); apply
   changes the same turn; meta review (fresh Sonnet) every 3rd row before the next build (next due after row 9);
   at each meta review update `delivery-learnings-generic.md` and comment #161 (`kit_issue_comment.py`).
7. Report to the owner: what changed for a user, expected vs actual with reasons, THE WHOLE 63-ROW TABLE (never a
   subset), open questions, the trend table, the evidence table.

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
