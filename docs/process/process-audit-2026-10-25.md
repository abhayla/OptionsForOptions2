# Audit: rows 30-31, real work or waste? (2026-10-25, ~18:10-18:50 IST, independent, read-only)

Independent delivery-efficiency audit, 2026-10-25 (fresh-context Opus, read-only); adopted as ADR-188; follows docs/process/process-audit-2026-10-23.md

Verdict in one line: **the work is not that big; about half of row 30's 4.6 hours was waiting.** Row 30 has ~640
product lines. Its largest cost was waiting on owner questions (89 min). Row 31 has not started because a tool blocked
it on two GENERATED files (3.2 h idle so far). Both estimates are honest *for the current way of working*, and too high
for the work itself.

Times are IST. Scripts: scratchpad `audit_main.py`, `audit_agents.py`, `audit_diff.py`.

## 1. Row 30 timeline (13:33 -> 18:09 = 276 min)

| Category | Min | What |
|---|---|---|
| **Owner questions (waiting for an answer)** | **89** | 14:23 22.9 / 14:48 1.9 / 14:51 1.3 / 15:29 1.1 / **16:32 62.2** |
| Build (agents) | 72 | 30b 39, 30b2 18 (rebuild after a naming conflict the measure step missed), fix-1 15. 30f 18 ran alongside |
| Waiting for the orchestrator | 40 | 13:43-14:23: measure done; orchestrator busy with row 31's question, ADR-185, 32f's gate (foreground) |
| Spec write-back, briefs | ~24 | ADR-186 (1)-(5), REQ-078 edits, fix brief |
| Gates | 20 + 10 wait | 3 runs 16:02-16:22 (2 failed); 15:52-16:02 waited for the process item's gate |
| Check | 8 | Opus 16:23-16:31, REVISE, 2 MAJOR |
| Merge-conflict churn | ~8 | 18:00-18:09 coverage-stages.yaml + spec-digest after another session's kit 1.12.0 |

**Largest: owner waits (32%).** Owner waits plus orchestrator and machine queueing come to 50% of the time. Real work
(build, check, gate) is ~100 min.
Row 32 (Tier B, 10 files): 13:33-15:32 = 2 h. Build 18 min. Gates 4 runs (~39 min, 2 failed). Checker 73 min against
a 20-min budget (22.8 min of that was a full vitest re-run).
Process item (measure_process, 326+310 lines): 13:32 -> still open at 18:09 (4.6 h). 3 gates. A land refused
(RE-REVIEW NEEDED after main moved). A coverage fail caused by another session's issue #550.

## 2. Size of the work

| Part | Product lines | Test lines | Files |
|---|---|---|---|
| 30b (vs origin/main) | 495 | 771 | 10 product (leg_edit route + domain = Tier A, feeds Execute) |
| 30f (vs 30b) | 144 | 153 unit + 47 e2e + 386 fixture | 4 |
| 31b / 31f | 0 (only 68 spec lines) | 0 | 12 / 10 planned (measure JSONs) |

Rows 27/28/29 took 2.5 / 4.4 / 3.6 h (row-review.md:170,183,201). The measure step estimated 75 min for 30b and 90/70
min for 31b/31f. If row 30 closes at ~6.5-7 h, it costs 1.5x row 28, which was a Tier A row with a DB migration.
**That is not proportionate.** The extra time came from owner waits, a rebuild, and failed gates.

## 3. Waste (avoidable, measured)

1. **Orchestrator blocked on a question: 62 min (16:32-17:34).** The question tool stops the orchestrator until the
   owner answers. 30f's measure and worktree were ready at 16:23. MAJOR 2 of the fix did not depend on the answer.
   Both were dispatched only at 17:46: **~70 min lost.** The question itself came from the orchestrator's own brief
   error (MAJOR 1: "Width always moves both sides").
2. **Row 31 blocked on generated files: ~190 min so far.** dispatch-31b.log: `OVERLAP GATE: REFUSED - both rows touch:
   docs/process/coverage-stages.yaml, views/spec-digest.md`. These are not product files.
3. **Failed gate runs: ~44 min of 93 min.** 5 of 10 orchestrator gates failed:
   - prettier not run (32f);
   - OpenAPI not regenerated (30b2);
   - the eslint 10-second timed test, flaky under load. It failed 3 times today (orchestrator 16:02, builder 15:14,
     row-10 builder 15:33). Free memory was 2.6 GB at 16:04; 3.9 GB now; 11 claude processes use 1.77 GB;
   - #550 from another session.
   Separately, the 30b builder's 10-min gate ran on a tree that had already moved, so its result was thrown away.
4. **Three gates per change, plus CI.** builder gate + orchestrator gate + `--pre-push`, ~8-11 min each. CI then runs
   CI 7.2 min + App tests 10-16 min anyway (`gh run list`).
5. **Builders over budget:** 30b 115/80 calls, 30b2 144/80, measure-fix 62/40, 30b-fix1 65/40 (+ a finisher agent).
   30b + 30b2 read 58M context.
6. **Orchestrator brief errors:** 3 (30b Width MAJOR 1, measure row-10 timing definition, the ADR-186 (5) example). Each
   cost a fix round, an extra agent, or an owner question.
7. **Orchestrator context:** 574 turns at an average of 312k = 179M. That is 50% of the session's tokens (agents
   178M). The limit is <250k. **16 kit-guard blocks** at ~2 x 312k each = ~10M (this audit tripped it 3 times too).
8. **Opus where Sonnet was the rule:** measure agents for rows 30 and 31 = 29.9M context on Opus. The process item's
   two checks also ran on Opus.

## 4. Row 31, realistic

31b: build 40-60 + gate 10 + Opus check 10-15 + one fix 15 + round 2 5-15 + land/CI 20 = **1.7-2.3 h**. 31f, after
31b merges: build 20 + gate 10 + Sonnet check 10 + land 20 = **~1 h**. Total **3-3.5 h if items 1-4 above are removed**,
or 2.5-3 h if 31b starts now. The orchestrator's 4.5-5 h holds under today's pattern.
The swing factor is owner questions. RD-105 is already waiting as a SPEC CHANGE, and REQ-085 wording will likely differ
from Sensibull again. Row 30 remaining: **~1.5-2 h**, not 2-2.5 h, if each gate runs once.

## 5. Fast-track options (ranked by minutes saved / risk)

| # | Change | Saving | Risk | Who |
|---|---|---|---|---|
| 1 | Dispatch every independent item **before** asking; ask while agents run | 60-70 min today | none | technical |
| 2 | Overlap gate ignores generated files (spec-digest, coverage-stages, findings INDEX); spec write-backs go on one docs branch, not row branches | ~3 h on row 31; recurs | a regen conflict at merge (regen.py solves it) | process-tool change under the ADR-178 freeze -> **owner** |
| 3 | Batch every SPEC CHANGE question at measure time, with the Sensibull research done by the measure agent. Chunk 3 did this: 6 questions in 9 min (08:25-08:34) | 30-60 min/row | none | technical |
| 4 | One gate per commit: the orchestrator accepts the builder's `GATE PASS <sha>` when sha = HEAD; `--pre-push` only if the sha changed | 20-30 min/row | none (CI re-runs everything) | technical |
| 5 | Builder handover checklist: prettier + OpenAPI regen; hard stop at budget | 10-20 min/row | none | technical |
| 6 | Timed eslint test: warm run, or a longer limit in the gate | 10 min per flake | a slower hook goes unseen | hook test = kit? -> harvest issue |
| 7 | Close other Claude sessions during gates | flakes stop | none | **owner** |
| 8 | Process items in their own session, not the product orchestrator | 20 min of gate slots today | none | technical |
| 9 | Sonnet for measure and process checks; fresh orchestrator session every 2 rows | ~30M ctx/row | none | technical |
| 10 | CI as the only full run (no local gate on Tier B) | ~10 min/row | red found 10 min later | changes ADR-181 -> **owner** |

## 6. Gold-plating and skips

Gold-plating:
- the orchestrator re-ran full gates after builders;
- Opus checks on a non-safety process tool;
- a 22.8-min full vitest run in a Tier B check;
- tracker and row-review paperwork mid-session.

Skipped:
- the 32f builder skipped gate.py (common rule 1);
- builder budgets were not enforced;
- the context limit was not kept.

## A. Compliance with the 2026-10-23 audit (c4 = this session c097bcc4; c3 = a43256ae)

| Audit item | c4 | c3 | Evidence / cost |
|---|---|---|---|
| 4.1 / 5.2 checker model by file | partly | not | c4: 30b Opus legitimate; measures 30/31 on Opus (29.9M). c3: measure_process `MISS row 4: ... 7` |
| 4.2 / 5.8 COPY per chunk | unmeasured | unmeasured | 31b brief still lists per-row RD-030/RD-105 |
| 4.3 / 5.6 process freeze, Sonnet, 1/chunk | partly | partly | 1 item each, but Opus checks and 4.6 h inside the sequence; c3 `MISS row 7: 2 commits` |
| 4.4 no table prints | followed | followed | `OK row 3: 0` both |
| 5.1 context diet (<250k, fresh session) | **not** | **not** | c4 312k x 574 turns; c3 366k x 1,400 turns, 512M, 17.3 h. Cost ~50% of all tokens |
| 5.3 round 2 <= 15 min | followed | not | c4 3 min; c3 17/15/36 min |
| 5.4 brief generator | partly | partly | c4: 6 dispatch.py logs; check, measure and fix briefs hand-written or helper-scripted |
| 5.5 DB tests in CI, draft chunk PR | partly | **not** | c4: 0 local DB runs; no draft PR in `gh pr list`. c3: 4 DB runs incl. a 1 h 49 min run (row-review:168) |
| 5.7 row-ahead fix verified fast | unmeasured | not | c3 `MISS row 10: worst 52 min` |
| 5.9 paperwork per chunk | followed | followed | short status per row |
| 5.10 kit-guard false positives | **not** | **not** | 16 / 20 kit-guard blocks (c4/c3); ~10M per session |

## B. New (not in the 2026-10-23 audit)

- **NEW-1:** Never hold the question tool while dispatchable work exists (§3 item 1).
- **NEW-2:** The overlap gate must ignore generated files, and spec write-backs leave the row branches (§3 item 2).
- **NEW-3:** One gate per sha, with the builder's PASS reused (§5 #4). **CHANGES audit item 5.5/W3:** the duplicate is
  now the local gate, not the DB tunnel.
- **NEW-4:** A builder handover checklist (format, OpenAPI) plus a hard budget stop.
- **NEW-5:** A timed-test flake under memory pressure is a machine finding; owner action on other sessions.
- **CHANGES audit item 6:** the process item runs in its own session, not "1 per chunk inside the sequence".

## Evidence table

| Claim | Evidence (run in this audit) |
|---|---|
| Question waits 22.9/1.9/1.3/1.1/62.2 min | audit_main.py events: `16:32:02 62.2m AskUserQuestion` |
| 30f + fix dispatched 17:46; 30f measure 16:23 | ledger `"30f" ... 12:16:47Z`; scratchpad measure-30f.json mtime 16:23 |
| 31b refused on generated files | `tail dispatch-31b.log`: `OVERLAP GATE: REFUSED ... coverage-stages.yaml, views/spec-digest.md` |
| 5/10 gates failed, causes | gate result lines: `GATE FAIL frontend-format`, `openapi-drift`, `guard-tests`, `frontend-vitest-changed`, `coverage` |
| Agent calls vs budget | audit_agents.py: `calls=115 ... B=[60 min, 80 tool calls] Build row 30 backend`, `calls=144` 30b2 |
| Orchestrator 574 turns, 312k avg, 179M | audit_main.py last line |
| Line counts | audit_diff.py: `30b product 495 test 771`; `30f product 144 test 539` |
| c3 misses | measure_process.py --session a43256ae: `8 MISS, 4 OK` |
| Kit-guard blocks 16 / 20 | inline count over both transcripts |
| CI durations | `gh run list`: CI 7.2, App tests 9.7-15.6 min |
| Rows 27-29 wall clock | row-review.md:170,183,201 |
| Unmeasured | per-turn split of orchestrator time inside question windows; COPY items; whether tests_app/test_leg_edit_route.py at 18:03 hit the DB |
