# Independent delivery-process audit: OptionsForOptions2 builder sequence (rows 1-14)

Auditor: Fable 5.1, fresh context, read-only. Date: 2026-10-23 (measured ~14:20-15:15 IST by the clock).
Scope: the 2026-10-22/23 builder-sequence process (CLAUDE.md "Fast delivery", goal contract, row-review R1-R19,
check_brief + mutation_gate + overlap_gate + reference_register, ADR-106/107/168/171/173/176).
Everything below is measured (source given) or marked **estimate** / **unmeasured**.
Scripts and raw outputs sit next to this file: measure_transcripts.py -> transcripts.json / summary.txt;
measure_sessions.py -> sessions.txt; classify_commits.py -> commits.txt; git-log-sorted.log; git-numstat.log.

---

## 0. The three findings that matter most

1. **The process measures the wrong token number, by about 100x.** The row-review "tokens" column (e.g. "A0 build
   22.2 min / 289k") is the agent's FINAL CONTEXT SIZE, not the tokens it processed. The same agent's transcript shows
   31.8M cache-read tokens + 1.0M cache-write + 220k output (summary.txt, 10-22 21:01, 118 tool calls, avg 269k
   context per call). Every tool call re-reads the whole context, so cost = calls x context size, and none of the 19
   process rules targets that product. Explainer: *cache read* = the model re-reading text it already saw, billed at
   roughly a tenth of fresh input, but 100-300k of it on every single tool call.
2. **The orchestrator is the biggest single consumer and was never measured** ("its tokens unmeasured" in every row log).
   Two orchestrator sessions on 10-22/23 (sessions.txt): cdc8b776 9.9 h, 1,196 turns, **639M** context tokens read,
   940 tool calls, 67 agent dispatches; b9b5cb32 18.6 h, 1,223 turns, **667M**, 941 tool calls, 55 dispatches.
   Average context per turn **534k-546k** (2.5x a normal window, for 18 hours). The 15 fully recorded agents of the
   same two days read 290M in total. On an Opus-class price the orchestrator alone is roughly 4-5x all its agents
   combined (**estimate**: price ratio applied to measured counts).
3. **Most second rounds were not product defects.** Of the 9 rows that took two verify rounds (1, 2, 4, 5, 6, 8, 9-A0,
   10, 11) the row logs attribute the extra round to: the orchestrator's own brief (rows 2, 4, 5, 8), the builder leaving
   tests/mutants unfinished (rows 1, 9, 10), CI-environment surprises (rows 6, 8). Real product defects the verifiers
   found across 14 rows: heartbeat-counts-as-price (row 2, Tier A, worth its round), per-feed eviction making IVs stale
   (row 8), a wrong refusal reason (row 12, MINOR), a market-closed wording MAJOR (row 11 AC-7 - wording). Row 8 was
   PARKED with "the code is correct (no wrong number found)" because 30 of 40 cache-key parts lacked a killing test.
   The process pays Tier A prices to find paperwork gaps.

---

## 1. Where the wall-clock and tokens go (measured)

### 1.1 Rows closed, wall-clock per row (row-review.md lines 136-147; commit times)

| Row | Expected min | Actual wall-clock | Agent-sum min | Rounds | Main cause of overrun (row log) |
|---|---|---|---|---|---|
| 1 | - | 52 | 52 | 2 | sizing (S for 20 files), stale test |
| 2 | - | 42 | 42 | 2 | brief gap (heartbeat), stale DB test |
| 3 | - | 37 | 37 | 1 | resume cost 203k ctx |
| 4 | 100 | 58 | 52 | 2 | brief wrote a forbidden-list guard |
| 5 | 90 | 97 | 61 | 2 | 3 sizing misses, finding F-56 not read |
| 6 | 60 | 74 | 53 | 2 PARKED | CI env var, scan that could only skip |
| 7 | 90 | 62 | 52 | 1 | - |
| 8 | 90 | 219 | >60 (4 agents unmeasured) | 2 PARKED | brief (instant), missed callers, 40-mutant sweep, DB tunnel |
| 9 | 330 | 718 (460 idle) | ~300 | 4 | 4 follow-ups for unfinished mutants; overnight question box |
| 10 | 90 | 180 | 172 | 2 | two finishers, a name-kill destroyed a run, 3 x 20-min DB runs, CI reds from row 9 |
| 11 | - | in flight (built 12:30-12:39, verify 12:45-13:29 PARTIAL, fix brief 13:29) | - | 2 | AC-7 wording MAJOR |
| 12-14 | - | pre-built; verified passing 10-23 (shared Opus + Sonnet DB verifier) | 25 + ? | 1 | one MINOR -> row 12 fix (131 lines, 2 files) |

Throughput: 10-22 closed rows 1-5, 7 (6 and 8 parked) between 10:33 and 21:01; 10-23 closed rows 9 and 10 by 12:10,
then **no product row closed from 12:10 to the audit start (~14:20)**: that window went to ADR-173..177, the reference
register tool + its Tier A verify + 6 MINORs (#524), the kill-by-name hook (build, fix 1, fix 2, two Tier A checks,
#523), the register load (Opus, 276 calls, 818k OUTPUT tokens, 39.6M context: the costliest single agent in the sample,
doing data entry) and check_brief changes (commits.txt 10-23 12:07-13:35: 0 product-closing commits).

### 1.2 Commits 10-22..10-23 (commits.txt; 98 unique commits, all branches)

| Category | Commits | Lines added |
|---|---|---|
| product (backend, frontend, tests, tests_app) | 33 | 10,410 (incl. ~2,000 test lines) |
| docs/close (briefs, evidence, work items, handover, row-review, register records) | 44 | 6,752 |
| process-tool (orchestrator scripts, hooks, their tests) | 13 | 3,851 |
| decision records | 3 | 394 |
| merges/empty | 5 | - |

10-23 alone: 14 product commits vs 47 non-product. Docs + process lines equal product lines (10.6k vs 10.4k). ADR-106's
own baseline measured "49% docs/process vs 15% product" BEFORE the fast-delivery rules; the ratio has not moved.

### 1.3 Agent tokens (15 fully recorded transcripts, 10-22 09:43 .. 10-23 13:46; summary.txt)

| | n | context tokens read | output tokens | agent-minutes | avg context per call |
|---|---|---|---|---|---|
| Sonnet (builders, finishers, process builders) | 8 | 162M | 991k | 757 (one 513-min idle A1 builder) | 74-269k |
| Opus (verifiers, design review, register load) | 7 | 129M | 1,183k | 186 | 98-283k |

- Opus agents are 7 of 15 by count but at the ~5x price ratio about **80% of the agent spend** (**estimate**). Opus
  verifiers run at 247-283k context per call for 49-85 calls each (10-24M read per verify).
- First-turn prelude (fixed text every agent starts with): **47k** for Sonnet builders, **91k** for Opus agents. CLAUDE.md
  17.3 KB, common builder brief 13 KB, row brief 5.5-9.8 KB, verifier brief 2.8-4.8 KB, global user rules ~20 KB more.
  The prelude is paid on every call: the register loader alone paid 276 x 91k = 25M of its 39.6M.
- The completion notices under-report by ~100x (finding 1); "~150k per dispatch" is a context-size budget, not cost.

### 1.4 Orchestrator sessions (sessions.txt)

| Session | Hours | Turns | Context read | Tool calls | Dispatches | Question tool | 63-row table prints | Largest messages |
|---|---|---|---|---|---|---|---|---|
| cdc8b776 (10-22 10:00) | 9.9 | 1,196 | 639M | 940 (Bash 336, Edit 210, Write 155, PowerShell 78) | 67 | 7 | 6 | 10.5k, 9.8k, 9.5k chars |
| b9b5cb32 (10-22 18:08 -> 10-23 12:44) | 18.6 | 1,223 | 667M | 941 (Bash 378, Edit 174, Write 136, PowerShell 77) | 55 | 4 | 2 | 10.2k, 9.5k chars |
| 0c676935 (10-23 12:44, current) | 1.6 | 394 | 99M | 281 | 19 | 14 | 0 | 3.8k |

- 1,880 orchestrator tool calls for 8 closed + 2 parked rows = **~190 orchestrator turns per row** at ~540k context each.
  Edit + Write = 675 calls: briefs, evidence, handover, row-review and the table are hand-typed one edit at a time by the
  most expensive model in the system.
- The 63-row table (10k chars, ~3k tokens) was printed 8 times; each print sits in every later turn's context
  (~3k x ~500 remaining turns = ~1.5M tokens per print, **estimate**).
- Guard friction: ~9 kit-guard blocks + ~8 check_brief refusals reported this session; in this audit's own ~30 calls the
  kit guard blocked 4 read-only or scratch-only commands. Each block = a wasted 540k turn + a rewrite turn:
  ~17 x 2 x 540k = ~18M/session (**estimate**).

### 1.5 Stage breakdown per row (rows 4-10; agent minutes unless stated)

| Stage | Measured | Source |
|---|---|---|
| Brief writing + gates (orchestrator) | **unmeasured** per stage; ~60-100 orchestrator turns per row at 540k (from tool counts) | sessions.txt; 8 check_brief refusals |
| Measure (Explore, Sonnet) | 0.6-1.6 min, 75-98k final ctx | rows 4, 6, 7, 9, 10 |
| Build (Sonnet) | 15-46 min; 78-152 calls; over budget in 8 of 12 builds | rows 4-10; "budget hard stop still prose" |
| Finish / follow-up dispatches | row 5: 2 (17 min); row 9: 4 (23% of its tokens); row 10: 2 (28 min) | builder-unfinished tests/mutants |
| Verify r1 (Opus, Tier A) | 12-28 min; 10-24M ctx read each | sample agents 10-22 18:45, 21:24; 10-23 08:20, 10:09, 12:45 |
| Fix round | 6-64 min | row 10 fix 1 = 64 min (CI reds from row 9's unrun dependents) |
| Verify r2 (full re-verify) | 6-31 min | rows 4, 5, 6, 8, 9, 10 |
| DB runs over the SSH tunnel | ~23 s/test; row 10: three ~20-min runs; row 8: 498-test selection ~3 h, never finished; a 40-min run abandoned; rows 12-14 throwaway DB: 224 tests in 397 s | R16 log; handover; results-rows-12-14 |
| Evidence / close / issue / review (orchestrator) | ~30-60 turns per row (**estimate**); 13 issues #512-#524 in 2 days (11 MINOR bundles) | gh issue list |
| Reports to the owner | whole table + process review + trend table after every row | 8 table prints |
| Waiting | row 9: 460 min on a question box; row 12's 17-min fix waits ~80 min for row 11 (strict order) | R17; ADR-171 rule 2 |
| Process/meta work inside the sequence | 10-22: 3 process items (316k final ctx); 10-23: 13 process-tool commits, 2 Tier A hook reviews, register build + verify + load, 4 ADRs | commits.txt |

---

## 2. Waste: steps that do not change the outcome

**W1. Round 2 as a full re-verify.** r2 re-runs every AC and the attack list (verify-row-10-r2: 17 min, ~13M read).
Results of the r2 rounds: row 4 PASS, 5 PASS, 6 FAIL (a switch keyed on `CI`, itself a process-guard defect), 8 MAJOR
(unguarded key parts, code correct), 9-A0 PARTIAL (MINOR test gaps), 10 PASS. A findings-only re-check would have
reached the same verdicts.

**W2. Mutation sweeps sized by the verifier, not by risk.** Row 8's 40-mutant key sweep parked a row whose numbers were
right; row 9 A0 r1 PARTIAL on 5 of 22 survivors with "no code defect"; rows 12-14: 24 mutants, 21 killed, 2 survivors
= a MINOR. Gate result files in the orchestrator's scratch: 6/7, 10/11, 16/17, 37/38 killed on process hooks; 19/22 on
row 9 A0 fix. Google's published experience (ICSE-SEIP 2018; arXiv 2102.11378): only ~15% of raw mutants are
"productive" until suppression raises it to 89%; mutants are surfaced sparingly at review, never as a per-change gate.
Here every survivor is a finding, so 30 untested cache-key parts rank beside a wrong IV.

**W3. Duplicated runs.** Builder: changed files' tests + guard tests + repo_scan + R13 DB selection + mutation gate.
Verifier: attack list + R13 selection + own mutants + guard tests. CI at the chunk PR (weeks later): everything again.
The DB selection is the expensive one (20-180 min per run on the tunnel) and ran 3 times for row 10 alone. The rows
12-14 verifier got 224 DB tests through the throwaway launcher in 6.6 min (1.8 s/test): the tunnel cost is highly
variable and nobody records which path a run took.

**W4. Briefs bigger than the change.** Row 12's fix: 131 lines in 2 files; its brief is 4.4 KB + the 13 KB common brief
+ 17 KB CLAUDE.md + kit rules, with 9 gated sections (Attack list, Standing items (a)-(d), Threat model, Findings
checked, Reviewer checklist, CI, Size, Reference, Budget). check_brief has 9 rule families (22.5 KB) and refused the
orchestrator's own briefs 8 times in one session. A brief hand-typed at 540k context and then checked by a script is
the wrong order: a generator that fills the template from the Measure output passes by construction.

**W5. Serial chain inside a row.** Row 10: build 34 -> finish 11 -> finish 18 -> verify 28 -> fix 64 -> verify 17, all
serial (172 agent-min in 180 wall-clock). ADR-171 allows four rows in flight, but rule 2 (close strictly in order) made
row 12's 17-minute fix wait on row 11's verify + fix + re-verify (~80 min).

**W6. Tier A applied per row, not per file.** Row 11 part B is the string "Reconnecting - prices as of <time>" (175
frontend lines); it got the row's Tier A Opus verifier (44 min, 12.9M read). Rows 27 (labels, stamp) and 41 (header OHLC)
are Tier A in the table although they compute no money. ADR-106 (1) already says "a change takes the tier of its
highest-risk FILE"; the table assigns tiers per REQUIREMENT, so a wording part inherits Opus.

**W7. Paperwork nobody acts on.** 11 "MINORs" issues in two days (#512-#522), each needing gh_issue.py --stage, a
coverage-stages row, a commit; a per-row review entry (row-review.md is 41 KB and read at every session start and meta
review); a trend table; the handover rewritten 6 times on 10-23 (09:06, 12:36, 12:37, 12:40, 12:43, 12:55); findings
regenerated; delivery-learnings-generic.md + a kit-issue comment per meta review. The meta reviews are cheap (1 min,
108-121k) and useful (they corrected five typed times) but could not see the 100x under-count because their input was
already wrong.

**W8. Process work inside the product sequence.** 10-23 12:07-13:35: 0 product rows closed, 13 process-tool commits, two
Tier A Opus reviews of one hook, an Opus data-entry job at 818k output tokens. The owner's plan point (3) is right; the
measurement says the freeze should have started at 12:10 today.

**W9. Wrong model for the job.** The register load (121 records from scratch notes) ran on Opus at 276 calls. Sonnet or
Haiku would do it at 1/5-1/15 the price; the global routing rule R5 already says Sonnet for a clear brief.

**W10. Owner-facing reporting.** After every row: whole 63-row table, open questions, trend table, evidence table,
three review lines. The status-artifact rule says a status page is generated from data and updated on stage changes
only; the table already lives in a file - printing it into the context is the waste.

---

## 3. Comparative research

- **Small changes, one reviewer.** Google's review study (Sadowski et al., ICSE-SEIP 2018; 9M reviewed changes): most
  changes are small (median ~24 lines), 75% have one reviewer, turnaround is hours. Reviews are light because changes are
  small, not because reviewers are many. Sources: https://research.google/pubs/pub47025 ;
  https://www.michaelagreiler.com/code-reviews/ ;
  https://plg.uwaterloo.ca/~migod/846/current/summaries/10-Youssef-GoogleCodeReview-summary.pdf
  Here: every row gets a 5-10 KB brief, a builder, an independent verifier, up to two rounds, plus a chunk review.
- **Heavyweight approval hurts.** DORA 2019: heavyweight change approval correlates with WORSE delivery performance and
  is NOT associated with lower change-failure rates; it pushes teams into bigger batches. Recommended: shift approval left
  into peer review + automation. Sources: https://dora.dev/capabilities/streamlining-change-approval/ ;
  https://dora.dev/research/2019/dora-report/ ;
  https://launchdarkly.com/guides/reconciling-change-management-and-continuous-delivery/the-downsides-of-heavy-change-management/
  Here: no PR and no CI until row 16, so the batch is 16 rows and CI's full DB suite has not run on any of them.
- **Mutation testing at scale.** Google surfaces a FEW selected mutants to reviewers, suppresses unproductive ones (15% ->
  89% productive), treats absolute mutation score as infeasible; 60% of endorsed mutants lead to a new test. Sources:
  https://research.google/pubs/pub46584/ ; https://arxiv.org/pdf/2102.11378 ;
  https://people.cs.umass.edu:443/~rjust/publ/industrial_mutation_icst_2018.pdf ;
  https://homes.cs.washington.edu/~rjust/publ/mutation_testing_resolution_icse_2023.pdf
  Here: every surviving mutant is a review finding and two rows are parked on survivors with correct code.
- **Regression test selection.** Impact-based selection saved ~34% in one industrial case, but "the cost of the analysis
  may well offset the savings" and selection gets less cost-effective as the change set grows. Sources:
  https://www.cs.umd.edu/%7Eaporter/Docs/jstvr04sep.pdf ; https://web-backend.simula.no/sites/default/files/publications/Simula.SE.303.pdf
  Here: the R13 selection over a 23 s/test tunnel costs more than the whole DB suite on a free CI runner.
- **Agentic coding cost model.** Subagents keep tool output out of the parent's context, but each dispatch pays its own
  prelude; agent teams can use ~7x the tokens of one session; small tasks pay startup overhead that outweighs the saving.
  Sources: https://vantaige.io/zh/blog/claude-code-subagents-save-context-3-patterns ;
  https://www.mindstudio.ai/blog/claude-code-subagents-cost-tokens
  Here: 6-15 dispatches per row, each with a 47-91k prelude, plus an orchestrator at 540k per turn.
- **Risk-based testing** (Amland; Chen and Probert): depth = probability of a fault x cost of the fault. ADR-106 (1)
  encodes this per file; the sequence table applies it per requirement (W6).

---

## 4. The orchestrator's 4-point plan: keep / change / drop

| # | Proposal | Verdict | Why |
|---|---|---|---|
| 1 | Tier by risk: text/labels/tooltips/buttons -> Sonnet diff-only, no mutation tests; Opus + mutation only for orders, money, live prices feeding Execute | **KEEP, and decide it per changed FILE at Measure** (ADR-106 (1) wording), not per row; the verify is Sonnet when a Tier A row's changed files are all display/wording | W6; Opus verifiers ~80% of agent spend; mutation value per Google data |
| 2 | Batch all of a row's gaps into one builder + one check | **CHANGE: batch per CHUNK, COPY records only; SPEC CHANGE records never block a row** | 55 COPY records: 23 in chunk-1 rows (row 11 has 6); 12 are owner SPEC CHANGE questions. One reference-copy builder + one Sonnet verify per chunk = 7 dispatches instead of ~25. Needs ADR-176 (2) "a row does not close while a COPY record is open" -> "a chunk": owner approval |
| 3 | Freeze process-tool work | **KEEP, effective now, one exception**: a brief GENERATOR (change 4) because it removes orchestrator turns instead of adding a gate | 10-23 after 12:10 was 100% process; each new gate added a refusal class the orchestrator trips |
| 4 | 5-line status per row; full table/review/trend once per chunk or when a row runs >50% over | **KEEP; the table stays a file the owner opens** (status-artifact R1/R5). Loosens the owner's 2026-10-22 "whole table after each requirement" and "review every row" -> owner approval | W7, W10; ~1.5M tokens per print |

---

## 5. Ranked changes (by estimated saving)

Cost unit = context tokens read ("ctx"), the number that scales. Per-row baseline (rows 4-10): ~135 min wall-clock mean
(97 median), 6-8 dispatches, ~120M agent ctx + ~160M orchestrator ctx = **~280M ctx/row** (**estimate**: 1,306M
orchestrator ctx over ~8 closed rows + process work; agent share from the 15-transcript sample scaled by dispatch counts).

| Rank | Change | Saving (arithmetic) | Risk added, and how it stays covered | Loosens an owner rule? |
|---|---|---|---|---|
| 1 | **Orchestrator context diet.** (a) A fresh session per 3 rows or per chunk-half (context < 250k); (b) the orchestrator never reads a transcript, test log or diff into its own context - last 20 lines of a file only; (c) briefs, evidence, issue bodies and the row table produced by scripts from JSON, not 300+ Edit calls; (d) no table prints. | Turns/row ~190 -> ~90; ctx/turn 540k -> ~220k: 160M -> ~20M per row (**about -50% of ALL tokens**). Wall-clock **estimate** -15 min/row (540k turns are slow). | None to product quality; the handover already carries state between sessions. The global rule "one session per phase" exists and was not followed (18.6 h session). | No. |
| 2 | **Verifier model and depth by changed FILES.** Measure outputs the file list; verifier = Opus only if a file is in the safety set (section 6), else Sonnet; mutation gate only on guards in safety-set files, capped at the attack list (<= 7 mutants), run ONCE by the builder; the verifier reads the results file and spot-checks 2, never re-sweeps. | Opus verify 10-24M -> Sonnet ~8M at 1/5 price = ~-85% of verify cost on display rows; on Tier A rows the re-sweep (~1/3 of verify minutes; row 8: 40 mutants) goes: -8 min, ~-5M per Tier A row. Across 47 rows (~19 B / ~28 A): **estimate** -300M price-weighted ctx. | A display row with a hidden money path: covered by the Measure file list, the repo guard tests (one engine, Decimal boundary, write allow-list) that run anyway, and the chunk Tier A review. | Partly: ADR-106 (1) already says per file; the per-row Tier column is the orchestrator's. "Every guard has a killing test" is a brief rule. Row 8's park stands. |
| 3 | **Round 2 = findings-only re-check** (diff of the fix, the listed findings, the attack items they touch; budget 15/20; same tier). Full re-verify only if the fix touched a safety-set file not seen in round 1. | r2 17-31 min / 10-13M -> ~8 min / ~3M: **-9 min, -8M per two-round row**; 9 of 11 rows had an r2. | A fix breaking an untouched AC: the changed files' tests + guard tests still run on the fix commit; CI at the chunk PR runs all. The rejected 2026-10-22 loosening concerned round 1; round 2 re-checking everything found nothing new in 6 of 6 PASS/PARTIAL cases. | Row-review rule (3): a loosening -> reviewer then owner. ADR-106 (2) "at most 2 rounds" stands. |
| 4 | **Brief generator instead of brief gates.** make_brief.py <row> <measure.json> fills the template's row part (Size, CI, Attack list, Standing items, Threat model, Findings, Reference, Budget, Report) from the Measure agent's JSON; check_brief stays as a CI test on committed briefs. Common brief shrinks to the rules a builder must obey, not the history of why: 13 KB -> ~5 KB. | 8 refusals x 2 turns x 540k = ~9M/session; ~100 Edit/Write turns per row at 540k = ~50M/row -> ~5M. Builder prelude 47k -> ~35k x ~100 calls = -1.2M per builder. | None: same content, produced by code. | No. |
| 5 | **DB tests to CI, not the tunnel.** Open the chunk PR as a DRAFT at row 1 so every push runs app-tests.yml on GitHub's runners (public repo, free; ~15 min full suite per CLAUDE.md). Builders and verifiers run locally only the row's own new DB test file through the throwaway launcher; the R13 selection is read from the CI run. | Row 10: 3 x ~20 min local runs; row 8: a 3 h selection never finished; a 40-min run abandoned: **-20 to -60 min per Tier A row**; CI runs in parallel with the next row's build. | The VPS PostgreSQL also serves IPODhan prod: fewer tunnel runs REDUCE that risk. A draft PR merges nothing; the freeze on main holds. | Changes the contract's "no PR until chunk 1" and R13/R16 (orchestrator rules): technical call. |
| 6 | **Process-tool freeze until the chunk-1 PR**, then a budget: 1 process item per chunk, Sonnet, Tier B unless it is a hook that blocks commands (then ONE Opus check). Model routing enforced: data entry and register loads on Sonnet/Haiku. | 10-23: ~2 h of orchestrator time + 2 Opus hook reviews + an 818k-output Opus job: **estimate** -60M per day of this. | A process defect stays prose for one chunk; the row logs carry it. | No (the owner proposed it). |
| 7 | **Rows CLOSE in order; fixes never wait.** Keep ADR-171 rule 2 for closes, but a row-ahead fix of <= 3 files (row 12) is dispatched the moment its Measure exists and verified as soon as built; only the close waits. | Row 12: a 17-min fix idle ~80 min; recurs on every pre-built row (13, 14, 15, 16, 18, 22, 48, 49, 55, 56: 10 of the next 40): **-60 min wall-clock each**. | None: verification stays independent and per row. | No; it is how ADR-171 (1) was meant. |
| 8 | **Reference-copy gaps per chunk.** One builder brief per chunk listing that chunk's open COPY records (chunk 1: 23 records, rows 2-16), one Sonnet verify (wording/labels), one close. The 12 SPEC CHANGE records go to the owner as the batched list ADR-176 (5) describes and never gate a row. | ~25 per-row fix dispatches (each ~10M read, 20-30 min) -> 7 chunk dispatches: **estimate** -180M, -8 h. | A copied label lands a few rows later than its requirement; the register still tracks each record. | ADR-176 (2) "a row does not close while a COPY record is open" -> "chunk": owner approval. |
| 9 | **Paperwork batched per chunk.** One deferred issue per chunk (a section per row), evidence from the verifier JSON in one call per row (already the design), the handover rewritten once per session end, the row-review measured table GENERATED from transcripts by script (R7's own backlog item, and it would fix the 100x under-count), the prose review only for a row > 20% over. | 11 issues x ~6 turns x 540k = ~36M; handover churn ~30 turns = ~16M; per-row prose review ~15 turns = ~8M/row: **estimate -50M/day**. | The deferred list stays complete; CI's coverage check needs one staged row per chunk issue. | "Every row, from row 5" review (owner 2026-10-22) -> owner approval for "only when over 20%"; the measured table itself stays, generated. |
| 10 | **Kit-guard false positives -> harvest issue.** Read-only commands (wc, cat, a heredoc mentioning a path, git log with a scratch redirect, writing a scratch file whose TEXT contains a kit word) are blocked: ~9-12 blocks per session. Meanwhile a runner script in scripts/orchestrator that takes tool names without the guarded words. | ~17 turns x 540k = ~9M/session, plus owner time. | None. | Kit files are never edited here -> harvest issue only. |

Checked and rejected:
- Dropping the independent verifier on Tier B rows: the stale-test class (rows 1, 2, 5->7, 7->9) was found by verifiers,
  not builders. Keep one Sonnet verify per Tier B row; cut its depth, not its existence.
- Dropping Measure: 1 min / 75-98k and it produced the attack and caller lists that cut round-1 failures from 2/2 (rows
  1-2) to 1 in rows 3 and 7.
- Resuming builders instead of fresh finishers: R5 is right (203k vs 93k context).

### 5.1 Plan to finish the remaining rows and the 55 COPY gaps

1. Now: close rows 11 (fix in flight), 12 (fix built), 13, 14 (verified), in order, same day; rows 15-16 with the one
   shared verifier as planned.
2. Chunk-1 reference-copy builder (23 COPY records, rows 2-16) in its own worktree in parallel with rows 15-16; one
   Sonnet verify. Then the chunk-1 draft PR becomes the real PR: fast checks, regen.py, land, ONE Tier A Opus chunk
   review (the real safety gate for rows 2-14), CI full suites.
3. Chunks 2-7: Measure 3 rows ahead (Sonnet Explore, parallel); build 2-3 rows in flight (disjoint files by
   overlap_gate); verify each at its file-set tier; chunk COPY builder at each chunk end; draft PR open from the chunk's
   first row so CI runs on every push.
4. Chunk 8 (held / switched-off rows 55-62): Tier B except 56 (POP), 58, 59; most are "built, switched off": verify only.

Model choice: Measure = Sonnet; builder = Sonnet (Opus only after two failed Sonnet rounds on a safety-set file);
verifier = Sonnet unless a changed file is in the safety set; chunk review = Opus; process items = Sonnet; data entry =
Haiku/Sonnet; orchestrator at < 250k context (change 1).

Before vs after (**estimates**; arithmetic shown):

| | Before (rows 4-10 measured, projected) | After (changes 1-9) |
|---|---|---|
| Work left | 47 rows + 55 COPY gaps (~25 per-row fix dispatches) | 47 rows + 7 chunk COPY builders |
| Wall-clock per row | mean ~135 min, median 97 (serial, DB on the tunnel, strict-order waits) | Tier B ~45 min (19 rows), Tier A ~80 min (28 rows), 2-3 rows overlapped (/1.7) |
| Total wall-clock | 47 x 135 + 25 x 30 = ~6,345 + 750 min = **~118 h** (~15 sessions) | (19 x 45 + 28 x 80 + 7 x 90) / 1.7 = **~37 h** (~5 sessions); ~63 h without overlap |
| Context tokens | 47 x 280M + 25 x 10M = **~13,400M** | 19 x ~40M + 28 x ~110M + 7 x ~60M = **~4,260M (-68%)** |
| Opus share | ~80% of agent spend + the orchestrator | chunk reviews + safety-set verifies only |

The ranges are wide because the orchestrator's cost per row is the least-measured number in the system; change 1 alone
decides whether "after" lands near 4,000M or 7,000M.

---

## 6. What must NOT be cut: the safety core and the checks that protect it

| Area | Rows | Checks that stay exactly as they are |
|---|---|---|
| Order path (building, sending, state; no retry; no substitution) | out of this contract ("No order is ever sent; Execute stays off", REQ-073 AC-6); rows 25 (margin read), 53-54 (tracking) feed its inputs | Execute-off test; write-allowlist + producer-inventory guard tests on every brief's Tests line; egress door guard (test_egress_gate.py, test_kite_http_guard.py); ADR-107 triage before any live run; a fresh Opus verifier on main for every money/order AC before a live window (ADR-106 (3)) |
| Money maths (one engine, Decimal, locked formulas) | 13, 14, 18, 22, 26, 36-39, 42, 54 | engine / scenario / table tests with hand-computed values (rows 12-14 verifier: 96/96 cells to the paisa); the decimal-money boundary rule and its edit-hook lint; the options-math-review skill on any engine change; Opus verifier for files under backend/ofo/engine, scenario, table, outcome, marketdata/forward.py and the money summary |
| Reconciliation | deferred to the order-path contract | ADR-016-019 invariant tests; nothing in this contract may touch them (overlap gate + chunk review) |
| Live-data liveness (stale never shown live; heartbeat is not a price; one snapshot instant) | 6, 7, 9, 11, 12, 23, 24, 33, 35, 41 | recorded-frame fixtures, test_no_wall_clock_asserts.py, injected-clock tests, R1 attack lists ("a heartbeat alone must not count as a price"), the row-63 live window; Opus verifier for marketdata, kite_ws, feed_*, outcome/service.py |
| Auth / tokens / secrets | 2, 58 | token-never-in-logs attacks, the reply-field inventory redesign (#517), the kit write-allowlist test; Opus verifier |
| Migrations | own PR each (ADR-106 (8)) | alembic_migration_guard.py; that migration's DB test file run locally |
| Repo-wide guards | every row | tests/test_*.py + -m repo_scan on every brief; ruff ratchet; trace_check; factory_lint; openapi check; chunk-PR CI full suites |
| Independence | every row | the verifier is never the builder; evidence written by the orchestrator from the verifier's JSON; trace_check refuses builder-written evidence |

Mutation testing stays for guards in safety-set files (every raise/refuse/block there has a killing test, run once
through mutation_gate.py); it is dropped only as a gate on display, wording and catalogue code.

---

## 7. Evidence table

| Claim | Evidence (tool call this audit) |
|---|---|
| Orchestrator sessions: 639M / 667M ctx, 1,196 / 1,223 turns, 940 / 941 tool calls, 67 / 55 dispatches, 6 / 2 table prints | python -X utf8 -I measure_sessions.py -> sessions.txt |
| 15 full agent transcripts 10-22/23: 290M ctx, 2.17M output; Opus 7 = 129M, Sonnet 8 = 162M | python -I measure_transcripts.py transcripts.json; summarize.py -> summary.txt |
| Row 9 A0 builder: 31.8M cache-read, 220k output, 118 calls, 269k avg ctx vs notice "289k" | summary.txt line "10-22 21:01"; row-review.md:194 |
| First-turn prelude 47k (Sonnet) / 91k (Opus); register loader 276 calls, 818k output | inline per-agent first-turn script; summary.txt "10-23 13:46" |
| 98 commits since 10-22: 33 product / 44 docs-close / 13 process-tool / 3 decisions; +10,410 vs +6,752 +3,851 lines | python -X utf8 -I classify_commits.py -> commits.txt |
| 0 product-closing commits 12:07-13:35 on 10-23 | commits.txt, lines 10-23 12:07..13:35 |
| Rows' expected vs actual, rounds, causes | Read docs/process/row-review.md lines 136-147, 151-396 |
| 13 issues #512-#524, 11 MINOR bundles, 2 process | gh issue list --state all --limit 40 (filtered >= 510) |
| Mutation results 6/7, 10/11, 16/17, 37/38 (process), 19/22 (row 9 A0) | python count over the orchestrator session's scratchpad *.jsonl |
| COPY records per row (row 11: 6; chunk-1 rows: 23 of 55) | grep over docs/process/reference-differences.md "COPY by builder row" |
| check_brief 9 rule families, 22.5 KB; CLAUDE.md 17.3 KB; common brief 13 KB; row briefs 5.5-9.8 KB | wc -c on scripts/orchestrator and the briefs; Read check_brief.py |
| Kit guard blocks read-only / scratch commands | 4 blocks in this audit's own ~30 calls (incl. writing this report via shell: the report's text contains kit words) |
| Research citations | WebSearch x 5 (section 3 links) |
| Unmeasured | orchestrator tokens per STAGE (only totals + tool-type counts exist); session-1 agents of row 8; exact prices (ratios used) |
