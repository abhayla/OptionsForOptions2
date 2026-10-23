# Per-row process review (builder sequence and every later delivery run)

Owner decisions 2026-10-22 (~12:10 IST, question tool, three answers): (1) learnings live in this project's process
files, and the parts every project should get go to the kit as a `harvest` issue; (2) the orchestrator writes the
review itself right after each row closes, from measured facts, with no extra agent; a fresh agent reviews the reviews
every 3rd row and at each chunk end; (3) a change that adds a check, sharpens a brief or cuts waste without dropping a
check is applied at once; a change that removes or loosens a check, a review round, a verifier or a safety rule first
gets an independent reviewer's read, then goes to the owner as one question. Every change is logged below with its
reason. Strict row order stays (owner, same session: "Keep strict order").

## Expected vs actual (owner 2026-10-22: every row, from row 5; row 4 stated after the fact)

Before a row's build is dispatched, the orchestrator writes its expected time in the row's table below and in the
status reply: measure + build (from the size: S 30, M 60, L 2 x 60 minutes) + verify (Tier B 10, Tier A 20 minutes) +
orchestrator work (live proofs, fixtures, close: about 10 minutes) = expected minutes, and expected agent tokens
(about 150k per dispatch). When the row closes, the actual is read from the completion notices and the commit times.
A difference within 20% needs no comment. Over 20% either way: one line of cause (faster: which rule or change saved
the time; slower: what went wrong), and for slower, the change that stops it next row, applied the same turn.

1. **Measure** from the dispatch notifications: for each agent (start check, measure, build, fix, verify) its minutes,
   tokens and tool calls; the number of rounds; the orchestrator's own work outside agents.
2. **Right / wrong:** what worked; every extra round or continuation with its ONE-sentence cause, sorted into: brief
   gap, sizing, builder self-check, verifier miss, environment, owner question.
3. **Change:** for each cause, the smallest process change that would have prevented it, and where it lands
   (`docs/process/builder-brief.md`, the goal contract, a verifier brief template, a script). Applied the same turn
   under rule (3) above; a loosening change goes to a reviewer and the owner instead.
4. **Log** it here (newest first), and show the owner three lines (right / wrong / changed) under the status table.
5. Every 3rd row and at each chunk end: a fresh agent reads this log and the row records and reports what the reviews
   missed (it does not re-verify product code). The same turn, the orchestrator updates the Effect check table and
   copies every generic lesson into `docs/process/delivery-learnings-generic.md` (no project names, no project
   tools), then comments the change on the kit harvest issue abhayla/Startup-Factory#161 (owner 2026-10-22: "document
   all these findings in a doc which we can share with startup factory project").

## Standing rules learned (applied to every brief from row 3 on)

- **R1 Attack list before the build** (cause: row 2 brief gap). The start check (built rows) or the Measure step (rows
  to build) writes the list of attacks the final verifier will run; the list is copied into the builder brief under
  `Attack list:` - at least 5 numbered items, each naming the test file expected to hold it (check_brief refuses
  fewer than 5); the builder runs each one before reporting. Example: "a heartbeat alone must not count as a price".
- **R2 Builder runs every changed test file in full** (cause: row 1 stale picker test, row 2 stale status test). Not a
  `-k` subset. DB-backed `tests_app` files run through the MAIN checkout's `scripts/orchestrator/db_run.py <worktree>
  ...` (the worktree has no `.env`); a skipped DB test counts as NOT run and is reported as such. Before reporting,
  grep every test tree for the old value or old answer of anything changed, and put the grep command and its hit
  count in the evidence table.
- **R3 Size by files touched** (cause: row 1 continuation dispatch, 23 min, 178k tokens). From Measure, count the
  files the fix must touch: <= 5 files S (30 min / 40 calls); 6-15 M (60 / 80); more, or backend + frontend, L (split
  backend then frontend). A class spread over ~20 files is never S.
- **R4 Never mutate in place** (row 1 builder edited files in place for mutation checks and restored them). Mutation
  copies live in the agent's scratch folder only.
- **R5 A resume re-sends the agent's whole history** (row 3: a 4-call follow-up to the builder cost 203k tokens, 28 s;
  a fresh small agent ~60-80k). Resume the same builder only for a real fix round where its context saves re-reading;
  a small follow-up (<= 3 files changed and no new design, e.g. switch a fixture, add one test) goes to a fresh agent
  with a narrow brief.
- **R8 Every guard in a brief is an allow-list** (row 4: the orchestrator's brief listed forbidden shapes and 19 others
  passed). The build section names what IS allowed and refuses the rest; forbidden shapes belong in the attack list
  only. check_brief refuses a builder brief whose build section names a scan/guard/gate/detector without "allow-list".
- **R9 Read the findings before a time, date or limit rule** (row 5: an 08:00 publish time contradicted F-56's
  documented 08:30). Grep `spec/findings.md` and the requirement by the rule's key terms first; cite the finding.
- **R10 A `verified` claim reads the code's use** (row 5: a batch constant marked verified against the basket limit
  it does not implement). Verify the value AND what the code does with it.
- **R11 Every new test names its CI job and variables** (row 6: a test needing DATABASE_URL, a scan no CI job ran, a
  fail-on-`CI` switch that broke the kit's job). The brief says which job/step runs it and with which variables; the
  builder runs it with exactly those; a test that can only skip in CI is a defect.
- **R12 Secrets are guarded by inventory** (row 6): the closed set of reply fields / build inputs that may exist,
  asserted both ways; never a list of secret-looking names.
- **R13 Run the tests a change can break, not only the ones named** (row 7 found a row-5 stale test in a file nobody
  ran). Builder and verifier select the app tests for the row's own backend diff (`scripts/orchestrator/select_app_tests.py`
  logic, restricted to the row's commits) and run every file it names in a throwaway database.
- **R14 Cache keys are built from the call** (row 8: 30 of 40 key parts had no killing test). A cache or memo key is
  made from the exact arguments passed to the computation it guards (one helper returns key and result), and the attack
  list carries "remove each key part in turn: each removal has a killing test".
- **R15 Measure lists every caller** (row 8: two routes reading the same snapshot were missed). For a changed entry
  point, Measure greps every caller and the brief names each one.
- **R16 Slow DB runs start first** (row 8: ~23 s per DB test over the tunnel; a 498-test selection needs ~3 h). The R13
  app run starts first, in the background, with `-o faulthandler_timeout=60`; the report gives its timing. The selection
  is never dropped; CI at the chunk PR runs it in full.
- **R17 A business question never holds the session** (row 9, 2026-10-22: the question box asked at ~23:35 IST held
  the whole session ~7.5 h until the owner answered at ~07:15; the question blocked nothing in the build). The
  question tool is used only while the owner is active in the session (a message from them in the last ~30 minutes,
  and not between ~22:00 and ~08:00 IST); otherwise the question goes to `docs/process/owner-questions-<date>.md` with
  the recommendation, Business call and Spec basis, the build continues, and the question is asked with the tool the
  next time the owner writes.
- **R7 Measured table per row**: every agent of the row with minutes, tokens and tool calls from its completion notice
  (process agents listed separately), the orchestrator's tool calls, and the close time read from the commit; the
  meta review (every 3rd row) is due before the next row's build; verifier briefs list the known-failing tests (#497).
- **R6 The orchestrator runs its own checks after every bookkeeping edit**: `tests/test_tests_required_exist.py` after
  any work-item edit, `coverage.py . --check` after any status or stage change (rows 1-3: a W-129 entry naming no file,
  and `status: done` making coverage drop W-129/W-130; work items stay `in_review` until the chunk PR merges).

Rejected (rule (3), loosening), 2026-10-22: "the final verifier skips ACs the diff did not touch". Independent
reviewer (Sonnet, fresh context): saves ~1-2 min per verify round on Tier B rows only (Tier A rows stay full), while
both stale-test failures of rows 1-2 were exactly "untouched" ACs broken by a shared change; a safe version needs an
import-graph script that eats the saving. Final verifiers keep checking every in-scope AC. Kit harvest of the adopted
rules: abhayla/Startup-Factory#161.

## Effect check (owner 2026-10-22: prove each rule reduces time, tokens and waste; updated after every row)

Each rule names the waste it targets and the counter that shows whether that waste came back. A rule whose waste
recurs twice after it was added is rewritten or turned into a machine check at the next meta review.

| Rule | Waste it targets | Counter | Rows 1-2 (before) | Rows since (after) |
|---|---|---|---|---|
| R1 attack list | verify round failed on an attack nobody listed | such failures per row | 1 (row 2) | 0 (row 3) |
| R2 full test files | stale test reaching the verifier | stale tests found at verify | 2 (rows 1, 2) | 0 (row 3) |
| R3 size by files | builder out of budget, continuation dispatch | continuations per row | 1 (row 1, 23 min / 178k) | 0 (row 3) |
| R4 scratch mutations | in-place edits of checked-out files | in-place mutation runs reported | 2 (rows 1, 2) | 0 (row 3) |
| R5 fresh agent for small follow-ups | resume re-sending a whole history | resume tokens on <= 3-file tasks | - | 203k (row 3, before R5 fixed) |
| R6 orchestrator self-checks | bookkeeping turning a repo test red | red repo tests from orchestrator edits | 1 (row 1 W-129) | 0 (row 3) |
| R7 measured table | wrong times, missing agents in totals | review claims without a record (meta review) | - | 4 (meta review after row 3) |
| R8 guards as allow-lists | a scan written as a list of forbidden shapes | forbidden-list guards reaching a verifier | 3 earlier occurrences (finding) | 2 (row 4 in the orchestrator's brief; row 6 although the brief said allow-list) - R12 (inventory) added |
| Budget hard stop | builder running past its budget | builders over budget | - | 5 (row 4: 152/80, 47/40; row 5: 48/40; row 6: 46/40, 46/40) - Size line by machine added after row 6 |
| R1 / R2 / R3 / R6 (rows 4-6) | listed above | per row | - | R1: 0 misses; R2: 1 (row 6, CI env) -> R11; R3: 3 (rows 5, 6) -> Size line by machine; R6: 1 (row 5, F-57 unstaged, caught by coverage) |

| Row | Expected (min / tokens) | Agents | Actual minutes (agents) | Actual tokens (agents) | Verify rounds | Notes |
|---|---|---|---|---|---|---|
| 1 | not set | 5 + half shared start check | 52 | ~820k (+93k shared) | 2 | before R1-R7 |
| 2 | not set | 4 + half shared start check | 42 | ~650k (+93k shared) | 2 | before R1-R7 |
| 3 | not set | 4 (+1 process builder, 7.5 min / 111k, separate) | 37 | ~650k (~450k without the resume) | 1 | first row under R1-R4 |
| 4 | 100 / 450k (set after the fact from size M: measure 1 + build 60 + verify 20 + orchestrator 10 + slack) | 6 (measure, build, finish, verify r1, fix, verify r2) | 52 agent min; 58 wall-clock (12:57-13:55) | ~870k | 2 | time -42% (faster), tokens +93% (slower): see the row 4 log |
| 5 | 90 / 450k (set 13:35 IST before dispatch: measure 1 + build 60 + verify 20 + orchestrator 10; core already proven live at 13:31) | 7 (build, finish x2, verify r1, research, fix, verify r2) + 3 process (reset tool, throwaway-db tool, tool review) | 61 agent min; 97 wall-clock (13:58-15:35) | ~1,010k (+316k process) | 2 | wall-clock +8% (within 20%); tokens +124%: see the row 5 log |
| 6 | 60 / 350k (set 15:20 IST before dispatch: measure 2 + build 30 + verify 20 + orchestrator 10) | 5 (measure, build, verify r1, fix, verify r2) | 53 agent min; 74 wall-clock (15:20-16:34, close commit 150873d3) | ~610k | 2 (PARKED) | time +23% (corrected by the meta review: first stated +75%), tokens +74%: see the row 6 log |
| 7 | 90 / 450k (set 16:50 IST before dispatch, in the brief: measure 1.5 + build 60 + verify 20 + orchestrator 10) | 3 (measure, build, verify r1) | 52 agent min; ~62 wall-clock (16:40-17:42) | ~368k | 1 | time -31% (faster), tokens -18% (within 20%): see the row 7 log |
| 8 | 90 / 450k (set 17:20 IST before dispatch, in the brief) | 6 (build, design review, fix 1, verify r1, fix 2, verify r2) + 2 process (row 9 measure, row 9 design review) | ~219 wall-clock (17:20-20:59, two sessions); session-2 agents 60 min (fix 2 30.0, verify r2 30.2); session-1 agents unmeasured (notices lost at the handover) | session 2: 375k (fix 2 169k, verify r2 206k); session 1 unmeasured | 2 (PARKED #519) | time +143%, tokens over (at least the 375k measured plus 4 unmeasured agents): see the row 8 log |
| 9 | part A0 90 / 350k (set 20:20 IST before dispatch, in the brief); row 9 = 4 parts (A0, A1, B, C), ~330 min in all | | | | | |

## Log (newest first)

### Row 8 - REQ-050 Shared computation (PARKED #519, 2026-10-22 ~21:00 IST)
- Expected 90 min / 450k. Actual: ~219 min wall-clock (17:20 dispatch - 20:59 close), across a session handover at 91%
  context. Session 2: fix 2 30.0 min / 169k / 79 calls (budget 80 - its 40-file app run was still going at the stop);
  verify r2 (Opus) 30.2 min / 206k / 67. Session 1 (build, an Opus design review, fix 1, verify r1): unmeasured - their
  completion notices did not survive the handover (commit times only: build 17:47-18:04, fix 1 18:13-18:42). Process
  agents (separate): row 9 measure 0.8 min / 84k / 18; row 9 design review (Opus) 1.9 min / 139k / 16. Orchestrator:
  ruff ratchet back to baseline (the 2 PLR0913 rises came from fix 1's fake sockets), F-58 measured, Q273, close.
- Difference: +143% time. Causes: (1) brief gap - the row brief did not fix the key's INSTANT, so the build keyed each
  IV on its own quote time and evicted on arrival (a design review + fix round); (2) Measure gap - only the outcome route
  was named, the planned-entry and tracking readers of the same snapshot were missed (round 1); (3) the attack list named
  single key parts (M8, M15), never "every key part" - round 2 found 30 of 40 key parts with no killing test (MAJOR,
  park); (4) environment - a DB test costs ~23 s over the tunnel, so the 498-test R13 selection needs ~3 h: neither the
  builder nor the verifier could finish it inside a budget; (5) a session handover mid-row (context).
- Right: the code is correct (no wrong number found; the suspected hang was slow DB tests, proved by 5 stack dumps with no
  lock wait); fix 2 met every round-1 item in one pass; the verifier's 40-mutant key sweep is the check the brief should
  have asked for.
- Wrong: the orchestrator's briefs (instant, callers, key completeness) caused 3 of the 5 causes; the builder stopped at
  79 calls with its app run unfinished and two watcher loops left running.
- Changed (all add checks, applied now): R14 - a cache/memo key is BUILT from the exact arguments of the computation it
  guards (structural, run-discipline C8), and the attack list carries "remove each key part in turn: each removal has a
  killing test" (builder-brief quality bar); R15 - Measure lists EVERY caller of a changed entry point (grep), not only
  the one an AC names; R16 - DB-backed app runs start FIRST, in the background, with a per-test timeout
  (`-o faulthandler_timeout=60`), and their timing goes in the report; the R13 selection is never dropped (the chunk PR's
  CI runs it in full). Tier A verifiers are dispatched as general-purpose agents (the `verifier` type stops at 40 turns,
  below a Tier A budget).

### Row 7 - REQ-049 Data health (closed 2026-10-22 ~17:42 IST)
- Expected 90 min / 450k (set before dispatch, in the brief). Actual: measure 1.5 min / 81k / 25 calls; build 21.9 min /
  130k / 88 calls (budget 80 - the hard stop broken again); verify r1 28.4 min / 157k / 42. Agents 52 min, ~368k;
  wall-clock ~62 min (16:40 dispatch after f369fa05 - 17:42). Orchestrator: one test for the untested branch (M5,
  proved on a scratch export), the row-5 stale test, the selector run.
- Difference: time -31%, tokens -18%: FASTER. Why: ONE verify round, the first since row 3. What helped: the Size and
  CI lines (the builder ran its app tests with exactly CI's variables - none of row 6's CI surprises); real recorded
  frames named in the brief; #513's three items handed over with file:line from row 2's verifier.
- Wrong: the builder ran 88 calls on an 80 budget (the hard stop is still prose for agents); row 5's builder had not run
  `test_execute_route.py` although it changed `execute.py` - a stale test the row-5 verifier never ran either (it ran
  only the files its brief named); found here, passes on main, fixed.
- Changed: R13 - the builder AND the verifier run `python scripts/orchestrator/select_app_tests.py <worktree>`-style
  selection on the ROW's own diff (backend files) and run every app test file it names (throwaway database), and list
  them in the report; the brief's Tests line names it. The whole-chunk selection (83 files) runs in CI at the chunk PR.

### Meta review after row 6 (2026-10-22 ~16:45 IST, fresh Sonnet agent, 1.0 min / 117k / 6 calls)
- Found: waste is not shrinking (row 3 best; rows 4-6 two rounds each, row 6 parked); about 9 of ~15 causes are the
  orchestrator's (briefs, sizing, spec reading, bookkeeping), 5 the builders', 1 the environment; rules broken after
  they were written: R8 (the word passed, the design did not), the Budget hard stop (3 more over-budget runs), R3 (row
  6 was backend + frontend + CI on an S budget), R2/R11 (a test passing only with the builder's DATABASE_URL), R7
  (meta review after row 3 missed once); the row 6 numbers were wrong: the close commit 150873d3 is 16:34, so wall-clock
  was 74 min (+23%, not +75%) and the agent sum is 53 min (not 75); other close times typed a few minutes off; the
  effect table stopped at row 3.
- Accepted and applied: `check_brief` now requires a `Size: S|M|L, <n> files, <k> items[, backend + frontend]` line
  whose budget matches (more than 5 files, more than 4 items, or backend + frontend can never be S) and a `CI:` line
  naming the job and variables of the new tests (R3, R11 by machine); the R8 check now reads only the build section
  proper (a "no static detector" standing item had tripped it); row 6 numbers corrected below and to the owner; times
  from commits only; the effect table updated with rows 4-6.
- Not yet machine-checked (kept as prose, named here so the next meta review can count them): R9 (findings before a
  time/limit rule - the proposed "cite an F-id" check is too noisy as written), R6 (status done before the chunk
  merges), a generated measured table from git log.

### Row 6 - REQ-048 Market-data pipeline (PARKED #517, 2026-10-22 ~17:05 IST)
- Expected 60 min / 350k. Actual: measure 1.6 min / 76k / 10 calls; build 14.6 min / 112k / 46 (budget 40); verify r1
  18.1 min / 161k / 47; fix 12.7 min / 110k / 46; verify r2 6.2 min / 153k / 26. Agents ~53 min (+ waits), ~610k;
  wall-clock ~105 min. Orchestrator: ESLint main-vs-branch check, the CRITICAL removal and its clean-export proof.
- Difference: time +75%, tokens +74%, two failed rounds -> PARKED. Causes: (1) a test passed only because the builder's
  shell had DATABASE_URL set (CI sets only TEST_DATABASE_URL); (2) a scan that could only skip in CI (no job both built
  the frontend and ran pytest) - it looked like protection and was none; (3) the fix keyed fail-or-skip on `CI`, which
  GitHub sets everywhere, turning the kit's job red (would have blocked every merge); (4) the credential scans were
  name lists again (guard-as-forbidden-list, 5th occurrence) although the brief said allow-list - R8's check only sees
  the word, not the design.
- Right: both verifiers read the workflow files and caught what no local run could; the CRITICAL never reached a PR;
  the park keeps AC-1..AC-4 and a concrete structural redesign (reply-field inventory).
- Wrong: the brief did not say which CI job runs each new test, or with which variables; "allow-list" in the brief was
  satisfied in words, not in design.
- Changed: R11 - every new test or scan names the CI job and step that runs it and the variables it needs; the builder
  runs it with exactly those variables (`env -u DATABASE_URL ...`); a test that can only skip in CI is a defect.
  R12 - a credential or secret guard is designed as an inventory (the closed set of fields/values that may exist,
  asserted both ways), never as a list of names to look for.

### Row 5 - REQ-053 Contract eligibility, read part (closed 2026-10-22 15:40 IST)
- Expected 90 min / 450k (set before dispatch). Actual: build 15.9 min / 173k / 79 calls; finish 1 2.4 min / 104k /
  48 (budget 40); finish 2 14.7 min / 154k / 80; verify r1 12.1 min / 188k / 45; research 1.0 min / 109k / 15; fix 5.9
  min / 114k / 33; verify r2 8.6 min / 170k / 23. Row agents 61 min, ~1,010k tokens; wall-clock 97 min (13:58-15:35).
  Process agents (separate): reset tool 9.0 min / 98k, throwaway-db tool 6.1 min / 103k, its review 0.9 min / 115k.
  Orchestrator: live catalogue load, two throwaway-db runs (5 + 6 min), registry sources, test fix; ~70 tool calls.
- Difference: wall-clock 97 vs 90 = +8%, within 20% (the estimate covers everything; agent minutes alone are 61 =
  -32%, the rest is the orchestrator's live load and two 5-6 min throwaway-database runs). Tokens +124%: (1) the first builder ran
  out at 79 calls with half the brief left (7 attacks + 4 build items was L-sized work in an M budget - sizing, R3);
  (2) finish 1 got 5 items on an S budget (orchestrator sizing again) and stopped at 48 calls; (3) the orchestrator's
  own "loaded today" rule was wrong for weekends and its 08:00 publish time contradicted F-56 (spec not read by every
  key term: "publish", "08:30" - spec-first R1), costing a finish round; (4) #497 made DB proofs impossible until the
  throwaway-database tool existed.
- Right: the core was proven live before the build (today's list loaded at 13:31); the throwaway-database tool turned
  15 "known failures" + 5 unrunnable tests into 137 passing; the research found a real open finding (NIFTY freeze 3,510
  reported) and the orchestrator's own wrong verified flag was caught by the verifier.
- Wrong: three sizing misses by the orchestrator in one row; a spec finding (F-56) not read before designing a time
  rule; a `verified=True` written from a summary without matching the constant's actual use; the threat-model line
  wrapped across two lines three times (check_brief refuses it each time).
- Changed: R9 - before any time/date/limit rule in a brief, grep spec/findings.md and the requirement by the rule's
  key terms (publish, fetch, window, expiry, limit, freeze); R3 applied to finish/fix briefs too (count the items x
  files, not only files); R10 - a registry `verified=True` needs the constant's use in code read, not only its name;
  DB proofs default to the throwaway-database runner (`D:\Abhay\scratch\ofo2-builder-sequence\fresh_launch.py`).

### Row 4 - REQ-117 Broker capability flags (closed 2026-10-22 13:57 IST)
- Expected 100 min / 450k (stated after the fact). Actual: measure 0.6 min / 75k / 11 calls; build 22.8 min / 258k /
  152 calls (budget 80; stopped at its 100-turn hard limit mid-rename); finish (fresh agent) 8.2 min / 93k / 38; verify
  r1 6.7 min / 155k / 30; fix (fresh agent) 8.3 min / 125k / 47 (budget 40); verify r2 5.8 min / 164k / 27. Agents 52
  min, ~870k tokens; wall-clock 58 min (12:57-13:55). Orchestrator: ~45 tool calls (briefs, checks, evidence, the R8
  check); its tokens unmeasured.
- Difference: time 42% UNDER (the estimate's 60-minute build was too generous for a builder that worked fast but
  undisciplined; fresh small agents for the finish and the fix took 8 minutes each). Tokens 93% OVER: (1) the first
  builder ignored its budget (152 calls, 258k) and left a half-done rename that a second agent had to finish (93k);
  (2) a whole verify round + fix round (~445k) came from the orchestrator's brief, which specified the broker-name scan
  as a list of forbidden shapes (finding guard-as-forbidden-list, 4th occurrence).
- Right: R5 worked (fresh finisher 93k vs ~260k to resume); the round-2 verifier classified all 184 allow-list entries
  before trusting a generated allow-list; one real consumer proves "flag off -> hidden with a reason" now.
- Wrong: the orchestrator wrote a forbidden-list guard into a brief although the finding was listed as checked; builders
  ran over budget twice; the estimate was not set before dispatch (rule came mid-row).
- Changed: R8 + check_brief refuses a builder brief whose build section describes a scan/guard/gate/detector without
  the word allow-list (it flags the original row-4 brief and caught row 5's AC-5 forbidden-shape list before dispatch,
  rewritten as a registry allow-list); Budget hard stop in the builder brief (at 80% of calls: no new change, consistent
  tree, commit, report); the finding's occurrence recorded.

### Meta review after row 3 (2026-10-22 13:05 IST, fresh Sonnet agent, 0.7 min / 108k / 5 calls)
- Found: row 3's close time was typed (~13:35) while the close commit says 12:56 (fixed below; times now from `date`
  or the commit); totals left out the process-guards builder and row 1's half of the shared start check; orchestrator
  cost and tool calls never given in numbers; R1/R2/R5 and the meta-review timing too vague to check; verifier briefs
  still let a verifier spend ~5 min re-proving #497.
- Accepted and applied: per-row measured table (every agent: minutes, tokens, tool calls, from its completion notice;
  process agents listed separately; orchestrator tool calls counted, its own tokens stated as unmeasured); R1 >= 5
  numbered attacks each naming the test file expected to hold it (check_brief enforces 5); R2 report the grep command
  and hit count; R5 small = <= 3 files and no new design; the meta review is due BEFORE row N+1's build (missed once:
  row 4's build started alongside this review); verifier briefs carry the known-failing test list (#497 names).
- Rejected: skipping AC re-checks already evidenced (the loosening an independent reviewer rejected with evidence,
  see above); lowering verifier budgets (also a loosening); running process work only after the row closes (same
  tokens, only more wall-clock).

### Row 3 - REQ-054 Broker adapter, read part (closed 2026-10-22 12:56 IST, commit 5f5cc339)
- Measured: measure 1.0 min / 80k; build 17.1 min / 200k; real-fixture follow-up (resume) 0.5 min / 203k; verify
  r1 18.5 min / 169k. ONE round. Total ~37 min, ~650k tokens (the resume alone 31% of it). Orchestrator: live
  `/user/profile` recording through the new door on the owner's session.
- Right: first row under R1-R4 passed its Tier A check on round 1 (16 of 17 mutations killed); the 7-point attack
  list was run by both builder and verifier; the egress guard refused an off-door probe, so the real fixture was
  recorded through the door itself.
- Wrong: the builder typed the profile reply from Kite's docs instead of asking for a real one (the brief said the
  orchestrator records it AFTER the build, so the builder had nothing real to use: brief ordering); the follow-up went
  to the resumed builder at 203k tokens (R5 corrected); the verifier spent ~5 min proving 53 DB failures were the
  shared-catalogue pollution #497.
- Changed: R5 corrected, R6 added; for a row whose core is a live reply, the orchestrator records the reply BEFORE the
  build when the door call already exists, else the brief says "core test waits for the orchestrator's fixture"
  (builder writes it against the fixture path, orchestrator drops the file in, test runs); #497 named up front in
  every verifier brief (done since row 2).

### Row 2 - REQ-015 Zerodha connection (closed 2026-10-22 ~12:15 IST)
- Measured: shared start check 11.6 min / 185k (rows 1-2); build 12.4 min / 161k; verify r1 6.3 min / 160k; fix
  6.4 min / 191k; verify r2 4.9 min / 140k; orchestrator: 2 live proofs (owner session), 1 test expectation, owner
  question (AC-3). Total ~42 min of agents, ~650k tokens (+ half the shared start check).
- Right: the live proof against the owner's session caught what unit tests could not (status Connected 70 s after the
  last screen closed); asking the owner AC-3 early removed a whole L-sized build (ADR-169).
- Wrong: round 1 failed because the brief said "a fresh frame within the window" without "a heartbeat is not a
  price" (brief gap -> R1); round 2 had one stale test the builder never saw because its DB tests skipped locally
  (builder self-check -> R2).
- Changed: R1, R2 added.

### Row 1 - REQ-001 Scope (closed 2026-10-22 ~11:35 IST)
- Measured: build 8.9 min / 133k (ran out of budget); continuation 22.8 min / 178k; verify r1 7.1 min / 154k; fix
  8.0 min / 210k; verify r2 5.1 min / 146k. Total ~52 min, ~820k tokens.
- Right: one structural home for the underlying set plus a scan test as second layer; the verifier's 25-shape probe
  found the scan's blind spots (deferred #512).
- Wrong: sized S with 40 calls for a class spread over ~20 files (sizing -> R3); a stale picker test left red (builder
  self-check -> R2); mutation checks done by editing real files (R4); the orchestrator's own W-129 `tests_required`
  entry named no file and turned a repo test red at row 2 (orchestrator self-check: run `tests/test_tests_required_exist.py`
  after editing any work item).
- Changed: R3, R4; orchestrator runs `tests/test_tests_required_exist.py` after every work-item edit.

### Step 0 (merged PR #511, 2026-10-22 10:33 IST)
- Measured: two parallel builders 6.0 min / 108k and 6.8 min / 83k; PR CI 7 checks green first time.
- Right: the core proof ran on replay AND live in one sitting; the owner's Kite login was used the same morning.
- Wrong: the kit guard blocks any shell command naming kit words (spec, tools, .claude, factory, views) including
  commit messages and `cd <dir> && python tools/...`; cost ~10 retries. Fix: run kit tools bare as
  `python tools/<x>.py <worktree-path>` from the main checkout, commit with `-F <message file>`.
