# Kit release notes

One entry per kit version (OD-23). The version in force is the project's `KIT_VERSION` file; a kit upgrade
replaces kit-owned files and adds an entry here. Every version entry carries at least one `Migration:` line
(`Migration: none` when nothing is needed); a test fails an entry without one.

## 1.15.0 — measure before speeding up (OD-124, REQ-062)

1. Red CI report (W-071): `python tools/ci_reds.py --repo OWNER/NAME [--workflow FILE] [--event NAME] --since
   YYYY-MM-DD` lists every red run with its failed jobs and steps and the commit that followed it on the branch, then
   the count per step and the median minutes of red and green runs. It reads run metadata through `gh` only (no logs)
   and writes nothing. Use it before changing a process to save CI time.
   Migration: none.
2. Budget report (W-072): `python tools/measure_tokens.py --budgets` shows each agent's Budget line beside its actual
   tool calls and wall-clock minutes (waits included), marked OVER, OK or NO-BUDGET, with the number of transcripts per
   folder. The pattern is the budget hook's own. The default report is unchanged.
   Migration: none; a project script that counted builder calls by hand can be retired.
3. Kit text (W-073): the builder brief asks for a work-in-progress commit after each acceptance criterion and the next
   command at the end of the report; the deliver skill continues in a fresh session when the token report shows the
   main session reading more than 300,000 context tokens per call.
   Migration: a project brief template copied from the kit's adds the same two lines in the project's own session.

## 1.14.0 — the parts 1.13.0 left out (OD-121, REQ-061)

1. Rules (W-069): `learning.md` 2.0.0 follows the two-round process. A second red of a class is round two, the last;
   red after round two parks the item or ships it with the findings listed; there is no automatic independent review,
   and a process change goes to the owner with the current rule quoted beside the new one (the role-review rule is
   gone). The detection-gap RCA covers Tier A only. The reviewer agent runs only when the owner asks for an independent
   review, with accidents as its threat model. Every kit rule names its counter.
   Migration: a project doc that asks for an independent reviewer on a second red, or for role reviews of a process
   change, is brought in line by the project's own session.
2. Evidence (W-070): `tools/record_evidence.py <reply.json>` writes the checker's blocks as evidence files with their
   `ac_fp`, and writes nothing for the whole batch on any bad block; the deliver skill's evidence step names it.
   Migration: none; a project script that wrote evidence files from agent output can be retired.
3. Status page (W-070): every first-screen text passes one plain-words function, so record wording (a plan step, a
   plan note, a record title) can no longer fail the first-screen test.
   Migration: none.
4. Budget (W-070): `kit_selftest.py` prints a `BUDGET:` line counting CLAUDE.md plus the always-loaded rules against
   the cap in `.claude/kit/budget.json`, as a warning when over; its exit code is unchanged.
   Migration: a project whose line says `over` slims its own CLAUDE.md (the kit never edits project files).

## 1.13.0 — lean delivery process (OD-117 to OD-120, REQ-059, REQ-060)

1. Process (W-063): the deliver skill and builder brief now spend review effort by the risk of the changed files.
   Tier C (docs, records, text, test-only) gets CI checks only; Tier B (normal code, kit tools and hooks) gets the builder
   plus one Sonnet checker; Tier A (production deploy path, money and order maths, data migrations, auth and secrets)
   gets one Opus checker. One checker replaces verifier plus reviewer: at most two rounds, round two on round one's
   findings and the fix's files only, then park or ship with the findings listed. Guards protect against accidents by a
   careful agent; a deliberate bypass is out of scope and known gaps are written in the guard's README. Mutation tests
   are no longer a gate (Tier A guards only, at most five mutants, run by the builder). The main session stays small
   and reads only the last lines of logs. Sonnet by default, Opus only for Tier A, Haiku for records and searches. Kit
   work and upgrades go in a weekly batch. The three always-loaded kit rules shrink from 14632 to 5912 bytes; the cap is
   8192 bytes; spec-first R4 asks for a decision row only for a decision about what the product does.
   Migration: a project-owned builder brief or delivery doc that restates the old tiers, review rounds or mutation gate
   is brought in line by the project's own session (the kit never edits project files).
2. Records (W-064): `spec_dupes.py` reports restatements, decision pins, relation grammar and coverage as `WARN` lines
   and exits 0; only an unreadable spec file fails.
   Migration: none; a CI step that relied on a duplicate failing the build now sees a warning.
3. Tests (W-065): `ci_local.py` runs every check plus only the affected tests by default and fails closed to the full
   suite on any file it cannot place; `--full` runs everything. CI runs spec checks only on a records-only pull request
   with no opt-in list; code pull requests and pushes to main run the full suite.
   Migration: none; `.claude/project/ci-docs-only-tests.txt`, if present, now adds tests to the records-only run.
4. Guards (W-066): `kit_file_guard.py` (1946 to 403 lines) blocks a command, edit or write only when it would change a
   kit-owned file by name, and allows reads, kit tool runs, commit messages and paths outside the project (issue 162's
   blocked commands now pass). The verifier write guard refuses a read-only agent's write but never moves or deletes a
   file.
   Migration: none; a project workaround script that built kit paths at runtime to get past a read can be removed.
5. Merge gate (W-067; issue 165): when GitHub's file list may be truncated, the complete list and the trace-check archive
   are read in a fresh empty temporary repository fetched by sha (no template, grafts, commit-graph, replace refs or
   alternates from the checkout; neutral git attributes; `safe.bareRepository` allowed); the kit job counts only when
   its run comes from the kit workflow (checked by workflow id and the job's run id, head sha and name).
   Migration: none; OptionsForOptions2's `GIT_GRAFT_FILE` stop-gap for the gate can be removed.
6. New tool (W-068): `python tools/measure_tokens.py [--since YYYY-MM-DD]` prints calls, context tokens read, output
   tokens and top tools per project, main session versus agents, and model, from Claude Code session files.
   Migration: none.
7. Mechanical steps for every project that takes 1.13.0 (when the owner names it): `python tools/kit_upgrade.py`, then
   `python tools/kit_settings.py .`.
   Migration: run those two commands.

## 1.12.0 — merge gate lands big pull requests, no Windows print crash, cheaper delivery (OD-103, OD-107, REQ-058)

1. Delivery cost (W-057; issue 161): `builder-brief.md` gains an `Attack list:` fill-in line (the attacks the final
   verifier will run, written by the start check or the measure step before the build, never by the builder) and four
   standing items: run each listed attack and report it before reporting done; run every changed test file in full
   (no name-filtered subset) before reporting done; a skipped test counts as not run; a mutation check edits a scratch
   copy, never a checked-out file. The deliver skill sizes a work item by files touched (5 or fewer small, 6 to 15
   medium, more than 15 or backend plus frontend large and split before the build) and adds step 12, process review:
   after each item the orchestrator records minutes, tokens, rounds and the cause of each extra round and removes that
   cause the same turn; a fresh agent reviews those records every third item; adding a check applies at once, removing
   or loosening one needs an independent read and the owner's yes; the final verifier still checks every acceptance
   criterion in full, never only the attack list.
   Migration: none; a project whose own brief or deliver text replaced the kit's copies the new items across by hand.
2. Merge gate (W-058; issue 163): `tools/merge_when_green.py` no longer refuses a pull request of 300 or more changed
   files. Staleness is judged by commit counts only; when GitHub's compare answer may be truncated (300 or more files,
   no `files` key, or an empty list while the head is ahead), the complete list comes from local git over the same
   three-dot range with renames off. Each ref is fetched into a private, fully qualified ref (a tag named like the
   base branch cannot shadow it; a sha must resolve to itself), git runs with replace objects off and repository
   config that could shorten a diff overridden, and an option-like base name is refused. Any failed fetch, missing
   merge base or failed git call refuses, as before.
   Migration: none; run the gate from a full clone of the project (a shallow clone without the merge base refuses).
3. Windows print crash (W-059; issue 159): every kit tool that runs as a script sets standard output and standard
   error to replace characters the console cannot encode, keeping the stream's encoding (six tools keep their
   existing UTF-8 choice), before it prints anything; `tools/selftest_deploy.py` gained an entry-point guard. A
   Factory test keeps the rule.
   Migration: none; a project-side `PYTHONIOENCODING=utf-8` workaround for kit tools can be removed.
4. Not in 1.12.0: the kit file guard's outside-project exemption (W-060, issue 162) is parked after its final review
   round (OD-107); its code is kept in the Factory for a later round. Two of issue 162's three blocked commands already
   pass since 1.9.0 in the Bash tool; a command naming the user-level Claude folder is still denied.
   Migration: none.
5. Mechanical steps for every project that takes 1.12.0 (when the owner names it): `python tools/kit_upgrade.py`,
   then `python tools/kit_settings.py .`.
   Migration: run those two commands.

## 1.11.1 — spec digest folds older decisions (OD-102, #138)

1. Spec digest: the newest 40 decisions keep one line each, and every older decision folds into one summary line
   (count, id range, a pointer to the decision log and to `python tools/spec_similar.py`). The decision log no longer
   grows the digest: 100 more decisions add about 460 bytes. The Factory's digest went from 22563 to 16540 bytes.
   Migration: regenerate `views/spec-digest.md` with `python tools/build_spec_digest.py .`; a project test that
   expects one digest line per older decision must stop asserting that.
2. Mechanical steps for every project that takes 1.11.1 (when the owner names it): `python tools/kit_upgrade.py`,
   then `python tools/kit_settings.py .`.
   Migration: run those two commands.

## 1.11.0 — harvest queue: UTF-8 everywhere, fewer guard false denies, honest trace, safer verifier guard, cheaper CI (OD-98..OD-100, REQ-057)

1. Text decoding (W-050; issues 153, 154, 44, 135): every text-mode subprocess call in kit tools and hooks passes
   `encoding="utf-8", errors="replace"`, and every kit hook decodes its JSON input from the raw stdin bytes as UTF-8.
   On Windows (cp1252) the merge gate no longer refuses a green pull request as "staleness unreadable" when GitHub's
   reply holds a rupee sign or an en dash. The merge gate prints one flushed `waiting:` line per poll. A Factory test
   fails on any new text-mode call without an encoding. A command that names a kit path and holds non-ASCII text is
   still denied by the 1.10.0 printable-text rule, on purpose.
   Migration: none; a project-side `PYTHONUTF8=1` workaround for the merge gate can be removed.
2. Kit file guard (W-051; issues 40, 89, 113; OD-99), Bash tool only: allows the four generator regenerates
   (`python tools/build_spec_digest.py <dir>`, `build_spec_index.py`, `build_order.py`, `build_findings_index.py`) and
   `python tools/trace_check.py <dir> --write-view`, where `<dir>` is `.` or one absolute folder holding the project
   lock file; `cd <absolute or ./ path to a folder holding a lock> && <one allowed kit tool run>`; and bare flag words
   such as `--factory`. A denial for a path outside the project now names the Read and Write tools. A bare relative
   `cd sub` stays denied (CDPATH). Writer commands naming files outside the project (`cp ~/... docs/`) stay denied;
   use the Read and Write tools for those.
   Migration: none.
3. Trace check (W-052; issues 96, 116, 94): a fail for an acceptance criterion's current fingerprint, in any owning work
   item, makes the criterion incomplete (`FAILED (evidence/<W>/<AC>.md, <date>)`) unless a pinned pass carries a
   strictly newer date; same date, the fail wins. Any result other than exactly `pass`, a missing `ac_fp`, or a case
   difference counts as a fail. A done work item whose `tests_required` names a missing path fails the check; a
   not-done item gets a warning.
   Migration: run `python tools/trace_check.py .`; a new FAILED line is a real recorded failure (re-verify or fix it);
   a done item naming a missing test file needs its `tests_required` corrected.
4. Verifier write guard (W-053; issues 110, 151): moves a file only inside the worktree the verifier call started in
   (fixed at PreToolUse); in any other worktree a new or changed file is copied and reported, never moved, so an
   orchestrator's work is no longer lost. A snapshot recorded without a session id is cleaned at SubagentStop for a
   matching agent id. `reviewer` is read-only by default.
   Migration: none; a project stand-in that matched snapshots by agent id only can be deleted.
5. Kit upgrade seeds (W-053; issue 151): `kit_upgrade.py` creates each project-owned template file that is absent from
   both the lock and the disk (for example `plans/README.md`), records it in the lock as project-owned and prints
   `created (project-owned seed): <path>`; it never overwrites or re-creates a file the lock lists.
   Migration: none; the upgrade creates the file.
6. CI cost (W-054; issues 152, 154; OD-100): the kit CI workflow runs on opened, synchronize, reopened and
   ready_for_review only, and its job is skipped for draft pull requests. New `tools/change_scope.py` classes a pull
   request docs-only or code (code on any doubt). Opt-in: a docs-only pull request runs only the tests listed in
   `.claude/project/ci-docs-only-tests.txt`; with no list, the full suite runs as before; a push to main always runs
   the full suite. The merge gate now treats a skipped, neutral or missing kit CI job as not run: it merges only on a
   passing newest kit CI result on the head, waits otherwise, and refuses a draft pull request. A pull request with
   only other checks no longer merges through the gate.
   Migration: to opt in, create `.claude/project/ci-docs-only-tests.txt` with one test path per line, including every
   test that reads real spec data; do not opt in if your pytest collects `.md` or `.json` files. If your CI job is
   renamed from `lint-and-test`, the merge gate will wait and refuse: keep the kit job name.
7. Agents by tier (W-055; issues 98, 107): new `builder-c` (40 turns, Tier C) and `builder-b` (75, Tier B) beside
   `builder` (100, Tier A), and a `reviewer` agent (80 turns, attacks first, read-only) for hands-on Tier A review; the
   deliver skill names the agent per tier, and the budget hook holds each to 80% of its own limit.
   Migration: none.
8. `ci_local.py --regen` (W-055; issue 109) runs every applicable generator's regenerate form before the checks; the
   decision guide lists the relation verbs `spec_dupes.py` accepts.
   Migration: none; run `python tools/ci_local.py --regen` before a push that changes spec or decision files.
9. Delivery lessons as kit text (W-055; issues 105, 106, 108): two builder-brief standing items, hook lessons in the
   learning rule, and the park rule's "merge main into a parked branch before any new round". The always-loaded context
   cap rises by 134 bytes to 23632, on purpose.
   Migration: none.
10. Mechanical steps for every project that takes 1.11.0 (when the owner names it): `python tools/kit_upgrade.py`, then
    `python tools/kit_settings.py .`.
    Migration: run those two commands.

## 1.10.1 — spec digest headroom (#138)

1. Spec digest: decisions older than the newest 40 keep 50 characters of lead sentence (was 60), so the digest keeps
   room for at least 15 more decisions under its 24000-byte cap (the 1.10.0 setting had dropped below that after five
   new decision rows).
   Migration: regenerate `views/spec-digest.md` with `python tools/build_spec_digest.py .`.
2. Mechanical steps for every project that takes 1.10.1 (when the owner names it): `python tools/kit_upgrade.py`,
   then `python tools/kit_settings.py .`.
   Migration: run those two commands.

## 1.10.0 — kit file guard tightened (partial), spec digest keeps recent decisions longer (OD-94, OD-96, #138)

1. Kit file guard tightening (W-046, REQ-055 AC-6, partial by OD-96): once a command names a kit path, the guard's own
   verdict also denies any character outside printable ASCII plus tab and line feed; in PowerShell, grouping,
   sub-expressions and backticks outside quotes; and banned flags of read-only programs in every spelling the shell
   accepts (git `--output`, `--ext-diff`, `--textconv`, `--filters`, `-c`; rg `--pre`, `--pre-glob`, `--hostname-bin`;
   less and more `+` commands, `-o`, `-O`, `--log-file`). This closes writes such as `git diff --output=<kit file>`
   that 1.9.0 allowed. In Bash, `2>$null` no longer counts as harmless. It only tightens: a comparison over 32,182
   commands found nothing 1.9.0 denies that 1.10.0 allows. Known gap: a kit path glued onto a banned short flag
   (`more -o<kit path>`) is still allowed, as in 1.9.0 (issue 142).
   Migration: none; a command that relied on one of these spellings is now refused with the usual kit-file message.
2. Spec digest (#138): the newest 40 decisions (by date, then id number) keep 100 characters of lead sentence and
   older ones are cut at 60, so a growing decision log stays under the digest's size cap for longer.
   Migration: regenerate `views/spec-digest.md` with `python tools/build_spec_digest.py .`.
3. Not in 1.10.0: review records and round caps (W-045) are parked for good after a red round 5 (issue 128); the
   merge gate's review-record seam stays a stub that passes.
   Migration: none.
4. Mechanical steps for every project that takes 1.10.0 (when the owner names it): `python tools/kit_upgrade.py`,
   then `python tools/kit_settings.py .`.
   Migration: run those two commands.

## 1.9.0 — no orphaned verifier snapshots, fewer false kit-guard denies (OD-90, OD-91, REQ-056)

1. Verifier write guard: each snapshot records the session id and agent id of its call, and when a read-only agent
   stops (SubagentStop) the guard deletes that agent's leftover snapshots and no other agent's. A verifier call that
   another hook blocked never gets a Post event, so before 1.9.0 its snapshot stayed on disk for up to 24 hours and
   could hold up anything that reads those snapshots. At stop the guard never judges or moves a repository file and
   always exits 0; the 24-hour prune stays for an agent that is killed. `settings.kit.json` wires the guard on
   SubagentStop (REQ-056 AC-1).
   Migration: regenerate the settings file with `python tools/kit_settings.py .`; a project-side stand-in that
   cleaned these snapshots can be deleted.
2. Kit file guard, from the Bash tool only and failing closed on any other shape (REQ-056 AC-2): the title or body of
   `gh pr|issue create|comment|edit` and the message of `git commit -m` is data and is not judged as a path when it is
   a plain word, a single- or double-quoted word with nothing that expands, a single-quoted string over several lines,
   or `"$(cat <<'EOF' ... EOF\n)"` with a single-quoted delimiter (a body line that contains the delimiter word is
   refused, because bash can end the heredoc there); `sed -n` (flags n, E, r only) with one script printing a line or
   a line range is a read; a leading `cd <dir> &&` before an otherwise allowed command passes. Before any of this, the
   whole command must be printable characters plus tab and line feed (bash drops a NUL byte, which could end a heredoc
   where the guard does not). Real writes (redirects, `rm`, `sed -i`, unlisted `gh`/`git` flags) stay denied.
   Migration: none.
3. Spec digest: `tools/build_spec_digest.py` cuts each decision's lead sentence at 100 characters (was 150), so a
   growing decision log stays under the digest's size cap for longer.
   Migration: regenerate `views/spec-digest.md` with `python tools/build_spec_digest.py .`.
4. Already in 1.8.0 and not repeated here: the template CI workflow cancels superseded pull-request runs and groups
   main by commit (the `concurrency` block).
   Migration: none.
5. Mechanical steps for every project that takes 1.9.0 (when the owner names it): `python tools/kit_upgrade.py`, then
   `python tools/kit_settings.py .`.
   Migration: run those two commands.

## 1.8.0 — plans, a status page by reader role, a safer merge gate and run discipline 1.1.0

1. Plan records: `plans/PL-###.md` hold a plan's steps, each with a status and the work items it covers, and a
   `changes` list (was, now, why); `factory/schemas/plan.schema.json` validates them and `factory_lint.py` checks them.
   Migration: create the `plans/` folder (the kit ships `plans/README.md`).
2. Status page: `tools/build_status_page.py` renders one page per project from data files, with a block for each
   reading role (owner, product, architect, implementer, delivery, deployment, environments, QA, domain owner), a
   design pass, derived numbers and an explicit "never ran" list. `tools/ci_local.py` now writes one JUnit file per
   pytest call and a `views/test-results.json` summary that the page reads.
   Migration: add `views/status-page.state.json` and the `views/test-results` files (name pattern `views/test-results` plus any suffix) to the ignore file; the first publish creates
   `views/status-page.json` (`{"url": "<the link>"}`), which is committed.
3. Stage-change hook: the new `status_page_due.py` runs at session start and at the end of a turn, notices a stage
   change (a requirement, work item, plan step or owner question status, a release, a merged pull request), builds the
   page and asks once for one publish to the same link. `settings.kit.json` wires it.
   Migration: regenerate the settings file with `python tools/kit_settings.py .`.
4. Merge gate newest run: `tools/merge_when_green.py` judges the newest run of each check, so an older red run that
   was re-run green no longer blocks a merge.
   Migration: none.
5. Merge gate review pin and stale branches: `tools/merge_when_green.py` requires `--reviewed-sha` (a full 40-character
   sha), merges only that reviewed commit, and, when the branch is behind and every check is green, updates it once
   by a merge commit (never a rebase), at most three times; if the update changed a file of the pull request's diff or
   a Tier A path it refuses with `RE-REVIEW NEEDED`.
   Migration: every caller of `tools/merge_when_green.py` now passes `--reviewed-sha <full sha of the reviewed
   commit>`; the tool refuses without one.
6. Merge-gate bookkeeping and CI: the project template's CI workflow cancels a superseded run on the same pull
   request (a run on the main branch is grouped by its commit and never cancelled); the deliver skill gains a
   "Stacked items" section (stacked pull requests, one base update right before the gate, and the local-gate rule
   that a base update voids the tested tree).
   Migration: none; a project that edited its CI workflow merges the `concurrency` block by hand.
7. Kit file guard: `kit_file_guard.py` lets a simple read of a protected path through from the Bash tool (a plain
   file read or listing with no write, redirect or substitution) while still refusing writes (REQ-055 AC-1).
   Migration: none.
8. Builder brief, run discipline and handover: `builder-brief.md` in the kit folder is a brief template carrying the
   standing items; `run-discipline.md` is version 1.1.0 (standing brief items a to d, and C8 prefer a structural
   guarantee over a detector); `docs/HANDOVER.md` gains DONE, PENDING, BLOCKED, PARKED and NEXT sections under a
   line cap; `budget.json` raises the always-loaded rule byte budget on purpose for the larger run-discipline.
   Migration: none; a project that copied the old handover or brief text replaces it from the template.
9. Deliver skill: sections for work-item size, plans (claims checked against the hosting service, design review of
   a Tier A plan, a one-reviewer check of a plan's first outside effect), and role review of process changes; the
   intake skill points to plans.
   Migration: none.
10. Run lock and delivery metrics: `tools/run_lock.py` keeps one owner-recorded lock per running job so two sessions
    do not run the same job, and `tools/delivery_metrics.py` computes delivery measures from the project's own
    history.
    Migration: none; both tools are optional to call.
11. Learning rule R4: `learning.md` adds that a change to review tiers, rounds, verifiers or guards goes to
    independent role reviewers with the current rule quoted beside the proposed one (finding
    `process-change-narrows-safety-rule`).
    Migration: none.
12. Mechanical steps for every project that takes 1.8.0 (when the owner names it): `python tools/kit_upgrade.py`,
    then `python tools/kit_settings.py .`.
    Migration: run those two commands.
13. Not in 1.8.0: review records and round caps (parked, issue 128) and the guard tightening that closes holes in the existing
    read-only allowlist, issue 120 (parked, issue 127).
    Migration: none.

## 1.7.0 — every agent and dispatch runs on the routed model and effort (OD-73)

1. Why: in 13 real sessions the main session carried 57.9% of list-price spend, builders defined as the mid-size
   model were dispatched on the large one 12.2% of the time, and no agent stated an effort level (defaults differ
   silently between models). Model aliases also moved on their own: the last call of one model version and the first
   of the next were 11 hours apart, with nothing to tell anyone.
2. `.claude/kit/model-routing.yaml` (new, kit-owned) is the one routing table: classes lookup, checking, building,
   review_b, design, review_a, verify_a and escalation, each with a model alias, an effort, `use_for` and `never_for`;
   an `agents:` map naming the class of every agent file; and `reviewed_for`, the model id each alias was last
   reviewed for (the only place a dated model id is allowed).
3. Agents: `builder.md` gains `effort: medium`, `verifier.md` gains `effort: high` (it stays on the large model),
   and a new read-only `Explore.md` (small model, `effort: medium`, no edit tools, 40 turns) overrides the built-in
   search agent. A Factory test fails an agent whose model or effort differs from its class.
4. Hook `agent_model_required.py` now checks the choice: the model must be a known alias
   (the four family aliases; case and spaces ignored; `inherit` and a dated id are refused); opus needs a `Why Opus:` line of 12+ characters by default
   (`FACTORY_REQUIRE_OPUS_REASON=0` turns that off); the escalation model needs its own reason line, always. Every
   refusal lists the table's classes with model and effort. A reason label counts only at the start of a line (a label
   inside a sentence, the refusal text pasted back, or a placeholder like `<reason>` is no reason). The fork exemption
   is an exact match of `subagent_type` (`forklift` is not exempt); `AGENT_MODEL_REQUIRED=0` stays.
5. The deliver skill names the model and effort of every dispatch (builder, verifier and review per tier, the
   escalation review after the same class fails twice, Explore for search) and runs
   `python tools/model_mix.py --alarms` at intake.
6. `tools/model_mix.py` (new, kit-owned) reads a Claude Code transcripts folder without any network call and prints
   output and cache-read tokens per role and model, counting each message once. It prints
   `NEW MODEL: <alias> latest id <id> differs from reviewed <id> - re-check the effort table` when the latest model
   of a family differs from `reviewed_for`, `UNROUTED MODEL: <id>` for a model of a family the table does not name,
   and `NO TRANSCRIPTS: <path>` (in every mode) when the folder is missing. It always exits 0.
7. Migration: a project's own agent files (under `.claude/agents/`, not the kit's three) need an `effort:` line
   chosen from the table; run `python tools/kit_settings.py .` so the settings file carries the changed hook; run
   `python tools/model_mix.py` once to see the project's own mix. When `model_mix.py` prints `NEW MODEL` or
   `UNROUTED MODEL`, do NOT edit `.claude/kit/` (kit-owned, replaced by the next upgrade): record it as a finding
   with scope generic so `kit_harvest.py` brings it to the Factory, and carry on. A dispatch with a dated model id, or opus without
   a `Why Opus:` line, is now refused. Adds `tools/model_mix.py`, `.claude/kit/model-routing.yaml` and
   `.claude/agents/Explore.md`; replaces the hook, the builder and verifier agents, the deliver skill and this file
   (kit-owned).

## 1.6.0 — owner questions are checked against the spec; every answer is written back (OD-69)

1. Why: the spec-first rule was text only; a word-match lookup found the right decision for 4 of 4 questions worded
   like the spec but cleanly for only 1 of 4 paraphrased ones, and nothing checked that an answer given in the
   question box reached the decision log.
2. `tools/build_spec_digest.py` (new, kit-owned) writes `views/spec-digest.md` (generated): one line per decision
   (id, date, lead sentence, relations), per requirement (id, status, title) and per spec section heading. CI runs
   `python tools/build_spec_digest.py . --check`; `tools/kit_drift.py` reports the file STALE when it differs.
3. Hook `spec_basis_gate.py` (PreToolUse, matcher `AskUserQuestion`) refuses, with exit 2, a question whose text
   has no `Spec basis:` line citing an existing requirement or decision id, or `none (searched: <terms>)`. The
   refusal names `views/spec-digest.md` and shows up to 3 word-match hits. It allows the question when the spec,
   the digest or `tools/spec_text.py` is missing.
4. Hook `answer_writeback_guard.py` (Stop) blocks a turn once when the owner answered a question and no decision
   row (`spec/decisions/`, or the Factory's `docs/spec/decisions.md`) was written after the answer, unless the
   session says `No spec change: <reason>` after the answer. A write is an Edit/Write to the log or to a decision
   record (`spec/decisions/<PREFIX>-<n>...md`, not README.md), or a Bash/PowerShell call that names the log by path
   and writes it (redirect to it, tee, sed -i, Set/Add-Content, Out-File, python open() a/w/x, .write( ); a read does
   not count, and `No spec change:` counts only at the start of a line; file times are never read. It never blocks twice in a row (`stop_hook_active`). The ask gate compares ids by prefix in any
   case and by number (`od-37` = `OD-037`) over the project root and the session's working folder.
5. `.claude/rules/kit/spec-first.md` 1.4.0: R1 reads the digest first; R2 and R4 name the two hooks.
6. Migration: the upgrade writes `views/spec-digest.md` and re-includes it in `.gitignore` (mechanical step
   `unignore-spec-digest`); regenerate it with `python tools/build_spec_digest.py .` after any spec change. Run
   `python tools/kit_settings.py .` so the settings file wires both new hooks, then ask one test question without a
   `Spec basis:` line to see the refusal. Adds `tools/build_spec_digest.py` and the two hooks; replaces
   `tools/kit_drift.py`, the CI workflow, the kit hook wiring, the spec-first rule and this file (kit-owned).

## 1.5.1 — the upgrade does the mechanical migration steps; every CI step runs after a failure (OD-67)

1. Why: the 1.5.0 upgrade pull request in a real project (71 requirements, 45 work items) left about 140 hand edits
   that a tool could derive, showed 1 of its 8 failing CI steps, and reported two generated files wrongly
   (`views/build-order.md` MISSING, `spec/requirements/INDEX.md` EDITED IN PROJECT) straight after the upgrade.
2. Factory-side: `kit_upgrade.py` applies the mechanical migration steps itself, in a second commit on the upgrade
   branch, each named with its file count in the pull request body under `## Done by the upgrade (mechanical steps)`:
   freeze unpinned evidence (`ac_fp.py --freeze-unpinned`), re-include `views/build-order.md` in `.gitignore`,
   normalize a done work item's `review_status` that names exactly one pull request and records no review
   (`merged PR #8` becomes `"PR #8; review not recorded"`, Tier C `"PR #8"`); a value recording a review, naming
   several numbers, or missing is left untouched and listed for you with the git-history candidate shown only as a
   hint (it may be a bookkeeping pull request, never written), paste the pins `spec_dupes.py --suggest` computes, add the `.claude/kit/GUIDE.md`
   pointer line to `CLAUDE.md`, rename `priority:` to `release:`. Judgment steps (requirement `layer` and `section`,
   the walking skeleton and its smoke commands, settling duplicate pairs, finding `scope`) are never written; they are
   listed under `## Left for the project`, with every `review_status` the upgrade could not normalize. Every generated
   file the lock lists is committed even when `.gitignore` hides it.
3. `tools/kit_drift.py` checks each generated file with the tool that writes it, from one table: the settings file
   (`kit_settings.py`, EDITED IN PROJECT), `views/build-order.md` (`build_order.py`, STALE) and
   `spec/requirements/INDEX.md` (`build_spec_index.py`, STALE; before, it was compared with the settings renderer
   and always reported edited). A generated lock entry it has no check for fails, naming the file.
4. The kit CI workflow runs every check step after an earlier one fails (`if: ${{ !cancelled() }}`, combined with the
   event tests), so a pull request shows every failing step at once. `tools/ci_local.py` mirrors exactly
   `!cancelled()` and `!cancelled() && github.event_name ==/!= 'x'`; any other use of `cancelled()` or `always()`
   stays UNSUPPORTED.
5. Release-record migration step (1.4.0 item 19) now says what to do when nothing is Released: write no record yet.
6. Migration: the upgrade does the mechanical steps (see its pull request body); you do the judgment steps listed
   under `## Left for the project` in the pull request body. Replaces `tools/kit_drift.py`, `tools/ci_local.py`,
   the CI workflow and this file (kit-owned).

## 1.5.0 — one command runs every CI step locally before the first push (OD-65, OD-66)

1. Why: a Factory PR went red on checks that a laptop run of the same workflow would have caught; the full suite and
   the generated-file checks were skipped before the push.
2. `tools/ci_local.py` (new, kit-owned) reads the project's CI workflow and runs every step in the foreground, in file
   order; `--list` prints the plan without running anything (`PLAN` / `SKIP` with the reason, one line per step).
   It decides `if: github.event_name == 'x'` and its exact complement `!= 'x'` from `--event` (default
   `pull_request`), takes `--pr-body FILE` for steps that read the PR description, and fails closed
   (`UNSUPPORTED`, exit 2, before anything runs) on any other `if:` shape. It plans the kit's own CI workflow and
   two real project workflows with no `UNSUPPORTED`.
3. The `deliver` skill names `python tools/ci_local.py` as the one command run once, before the first push of a batch.
4. Migration: run `python tools/ci_local.py` once before your next push. If it prints `UNSUPPORTED`, your workflow
   uses a shape the mirror cannot run: the message names the step and the shape; rewrite that step's `if:` to
   `github.event_name == 'x'` or `!= 'x'`, or move the condition into the step's script. Replaces the `deliver` skill
   and adds `tools/ci_local.py` (kit-owned).

## 1.4.0 — findings declare their scope; acceptance-criterion ids are unique (OD-32, OD-36, #39)

1. Why: a real project had 18 findings and none carried a scope, so `kit_harvest.py` brought back nothing without
   saying why (OD-32 item 2); and its REQ-018 once had two AC-9 entries and the lint passed, so one evidence file
   stood for two criteria (issue #39, OD-36).
2. Finding schema: `scope` is REQUIRED, `generic` (the class can happen in any project that uses the kit) or
   `project` (about this repository only). `factory_lint.py` reports a missing or other value as an error naming the
   file and both allowed values.
3. `factory_lint.py` also rejects a requirement that repeats an acceptance-criterion id (names the id and the file)
   and a work item whose `tests_required` names an AC id that none of its `requirement_ids` has (names the AC id and
   the work item).
   Every `tests_required` entry must start with `AC-<n>:`; a malformed prefix is a lint error naming the work item and
   the entry (it was silently skipped before).
3a. Models are named by family alias (e.g. opus, sonnet, haiku), which resolves to the latest model of the family
   (OD-42); `tests/test_model_aliases.py` fails naming file and line on a dated model id in config, and agent
   `model:` lines must be an alias.
4. Factory-side only: `kit_harvest.py` prints `findings: N, generic: G, no scope: S` and a WARNING line when every
   finding lacks a scope.
5. Migration: add `scope` to every `knowledge/findings/*.json`; renumber duplicate AC ids in requirements and fix any
   `tests_required` entry that names an AC its requirement lacks. Replaces `tools/factory_lint.py` and the finding
   schema (kit-owned).
6. Status page (REQ-008, OD-35): `tools/build_status_page.py ROOT --issues F --runs F --out FILE` (or `--fetch`
   instead of the two input files) renders one page from the repo, the issues and the CI runs: sections that
   collapse, sortable and filterable tables, an issues tracker where an issue maps to a requirement only from a
   `Relates-to:` line naming requirement ids or `section <name>` (else UNMAPPED, counted), "Needs you" from `owner-questions/OQ-###.md`
   (new schema `factory/schemas/owner-question.schema.json`, checked by `factory_lint.py`), and CI gates that never
   ran or were skipped every time. New files: the tool, the schema, `owner-questions/README.md`,
   `.github/ISSUE_TEMPLATE/issue.yml` (required Relates-to field); the `deliver` skill gains step 11 (regenerate and
   republish when a stage changed, never on an ordinary merge). The generated HTML is never committed.
7. Migration: after the first publish, create `views/status-page.json` as `{"url": "<the link>"}` and commit it
   (new projects already re-include it in `.gitignore`; existing ones add the line `!views/status-page.json`); tag existing issues with a `Relates-to:` line; add `owner-questions/`
   files for questions waiting on the owner. Replaces `tools/factory_lint.py`, the deliver skill and adds the tool
   (kit-owned).
8. Spec sections, lookup, a blocking duplicate check and decision pins (REQ-009; OD-30, OD-32 item 3, OD-38,
   OD-39). Why: a real spec restated the same line across requirements ("Learn ..." in two requirements, overlap
   0.88), nothing grouped requirements by subject, and a changed decision left the requirements built on it
   unchecked. The requirement schema REQUIRES a non-empty `section` (the lint names a requirement without one) and
   allows `distinct_from` and `confirmed_against`. New kit-owned tools: `tools/spec_text.py` (the one shared
   tokenizer and fingerprint), `tools/build_spec_index.py` (generates `spec/requirements/INDEX.md` grouped by section;
   `--check` in CI; the file is `generated`), `tools/spec_similar.py . "<text>"` (closest existing items; the
   spec-first rule says run it before writing any spec line) and `tools/spec_dupes.py`, which CI runs as a FULL scan
   on every PR and push (no base ref):
   - Duplicates: a requirement item vs another requirement's items, or a decision sentence vs another decision's
     (heading LINES removed, the prose under them kept; OD-row notes removed), at >= 0.40 word overlap blocks unless
     the NEWER record carries an exemption with the pair's current fingerprint and a difference of at least 3 content
     words: `distinct_from: ["REQ-001 AC-2 #<fp> — <the actual difference>"]` (ADR frontmatter the same way) or
     `(distinct from OD-12 #<fp>: <difference>)` in a Factory OD row. The fingerprint covers the exact pair of texts,
     so editing either text, renumbering criteria or copying an extra item makes it stale. A stale, unused,
     fingerprint-less or unknown-record exemption blocks; identical texts can never be exempted.
   - Pins (OD-39): a requirement that cites a decision (its id in any case, or its file path, in `source`,
     `spec_refs`, the statement or a criterion) carries `confirmed_against: ["<decision id> #<fp>"]`, the fingerprint
     of that decision's current text with notes removed. A missing, stale or orphaned pin blocks; editing the
     requirement never replaces re-pinning; a note-only change to a decision keeps pins valid.
   - Records (OD-40): every id is unique per kind — two OD rows, requirement files or decision files declaring one
     id block (`DUPLICATE-ID`, naming every file/row), and a requirement or decision file whose frontmatter does not
     parse blocks (`UNREADABLE`, naming the file and the error); nothing is skipped silently. A pin on a decision the
     requirement does not cite (orphan) or two pins for one decision block; an exemption's item label must name the
     older item; a `#` line inside a fenced code block is not a heading.
   - `spec_dupes.py . --suggest` prints the fingerprints as paste-ready lines (the exemption's placeholder difference
     fails the 3-word rule until you write the real one); it never writes a file.
9. Migration (your CI fails until done, which is the point): add `section: <subject>` to every
   `spec/requirements/REQ-*.md`; run `python tools/build_spec_index.py .` and commit `spec/requirements/INDEX.md`;
   run `python tools/spec_dupes.py . --suggest`, then settle each flagged pair (merge the two texts into one item for
   a real restatement, or paste the suggested exemption on the newer record with the real difference written in),
   re-read each cited decision and paste the suggested pins. Replaces the requirement schema,
   `tools/factory_lint.py`, the CI workflow and the spec-first rule; adds the four tools.
10. Status page (REQ-010): the requirements table gains an "Any section" filter listing each distinct section once (sorted), combining with the text, status and layer filters; no sections in the repo, no filter. Replaces `tools/build_status_page.py` (kit-owned).
11. Status page (REQ-012): a new "Owner decisions" section lists every decision (`| OD-n |` rows of
   `docs/spec/decisions.md`, or `spec/decisions/*.md` records) with its date, bold title, the owner's words, the
   changes cell, the requirements citing it (same rule as `spec_dupes.py`) and a rolled-up status ("no requirement",
   else the least-advanced status of the citing requirements); Overall gains decisions total / covered / not covered;
   filters for text, covered or not, and status. Escaped-pipe rule: a literal `|` inside a decision-table cell is
   written `\|`; `spec_text.od_cells` and the page treat `\|` as text, not a separator (a bare pipe made a row parse
   to six cells). Replaces `tools/build_status_page.py` (kit-owned).
12. Malformed decision rows are errors, not shifted cells (REQ-012): an OD row that is not exactly 5 cells makes
   `tools/spec_dupes.py` print `RECORD malformed decision row OD-n: N cells, expected 5` and exit 1, and the page lists
   it in a "Data problems" line at the top of Owner decisions instead of rendering it; a requirement with no status
   rolls up as `unknown`. Replaces `tools/spec_text.py`, `tools/spec_dupes.py`, `tools/build_status_page.py` (kit-owned).
13. Decision relations, the amends rule, source and coverage checks (REQ-013; OD-43, OD-44). Why: relations cells
   mixed relation words with work pointers ("W-009 round 3"), a decision that amended another left every requirement
   citing the old one green, and most decisions and spec sections were cited by no requirement without anyone
   seeing it. `tools/spec_dupes.py` now also checks:
   - relations: a decision file's new `changes` field (and a Factory OD row's last cell) is `;`-separated
     `<verb> <targets>`, verb in amends, supersedes, refines, extends, narrows, approves, starts, closes, applies,
     none, no-requirement; targets must exist: a known decision or requirement id, a milestone with a plan file
     (`docs/milestones/M4.1-plan.md` for `M4.1`; for any verb but approves, a planned milestone the decision's own
     text names also counts), or `handoff §N` that is a row of `docs/spec/handoff-sort.md` (any N
     where the repo has no sort); `none — <reason>` stands alone, and `no-requirement — <reason>` may join other
     entries but never amends / supersedes / refines / narrows; both must say why. Anything else is `RECORD <id> relations: ...` (blocks).
   - the amends rule: when decision B amends / supersedes / refines / narrows decision A, every requirement citing A
     must also cite B and pin it in `confirmed_against`, or have status Superseded (`PIN ... (amends rule)`, blocks).
     Every target of a multi-target entry counts. A requirement target works the same way: `refines REQ-7` makes
     REQ-7 cite and pin the decision (or be Superseded). extends and applies do not trigger it.
   - source: every requirement's `source` or `spec_refs` names an EXISTING target: a loaded decision's id, an
     owner-question id (`Q88`) that is a row id (first cell) of `spec/traceability/question-register.md`, not in a
     row whose `status` column says superseded or withdrawn (no register: Q-ids
     never count), a `handoff §N` that is a row of the sort, or an approved milestone plan (`docs/milestones/M*-plan.md`
     whose Status line says APPROVED or DONE) (`SOURCE <id>: ...`, blocks).
   - coverage counts deliberate citations (source, spec_refs); pins track every mention (a decision named only
     as an example in a criterion is pinned but not covered, and the status page lists only deliberate citations).
     Only a live requirement covers (status Superseded or Draft does not). Every decision must be cited by a
     requirement unless its relations are only `approves` of milestones (a pure approval) or carry
     `no-requirement — <reason>`; the verifier checks that each exemption is true, since no code check can; no other verb exempts (a rule relating as `closes M0` still
     needs a requirement), and the status page shows each exemption as `no requirement (exempt: <reason>)`; a `requirement` row of `docs/spec/handoff-sort.md` (where the repo has one) must be named as
     `handoff §N` in some requirement's source or spec_refs. Printed as `COVERAGE` lines and counts, and shown on the
     status page's Owner decisions section. They block only when `docs/spec/coverage-mode.txt` reads `block`; it
     ships reading `report`. A missing file runs in report mode and prints a WARNING; any other value blocks.
   - a decision file without `changes`: a `REPORT` line in report mode, a `RECORD` failure in block mode.
   The decision schema gains an optional `changes` field (string or list); `changes` is left out of the pinned text,
   so adding relations never stales a pin. Replaces `tools/spec_text.py`, `tools/spec_dupes.py`,
   `tools/build_status_page.py` and `factory/schemas/decision.schema.json` (kit-owned); adds
   `docs/spec/coverage-mode.txt` (project-owned).
14. Migration (the relation, amends and source checks block at once; coverage waits for you to switch it):
   (a) add `changes: "<verb> <targets>"` (or `changes: "none — <reason>"`; add `no-requirement — <reason>` only
   where the decision genuinely states no requirement) to every `spec/decisions/*.md`, rewriting
   any pointer to work ("W-###", "round 3") as the relation it implies against a decision, requirement, milestone or
   `handoff §N`; (b) run `python tools/spec_dupes.py .` and, for each `PIN ... (amends rule)` line, re-read the
   amending decision, cite it in the requirement's source and add its pin to `confirmed_against` (the line prints
   it), or set status Superseded; (c) give every requirement flagged by a `SOURCE` line a source naming a decision
   id, owner-question id, `handoff §N` or an approved milestone plan in source or spec_refs; (d) create `docs/spec/coverage-mode.txt` reading `report`, back-fill
   requirements until the COVERAGE counts are 0, then change it to `block`.
15. Evidence fingerprints, two honest statuses and a computed health (REQ-014; OD-43, OD-44, OD-47, OD-48). Why: an
   evidence file was never tied to the criterion text it proved, so an edited criterion kept its old proof (a real
   criterion's fingerprint moved f111e61460ba -> a32b267fdc30 when its text changed, and no check noticed).
   - Evidence schema: optional `ac_fp` (12 lowercase hex). New kit tool `python tools/ac_fp.py <REQ-id> <AC-id>`
     prints the fingerprint of that criterion's current text (the same `spec_text.fingerprint`); an unknown
     requirement or criterion exits 1 naming it. The `deliver` skill step 5 writes it into every new evidence file.
   - `trace_check.py`: evidence whose `ac_fp` differs from the criterion's current text is STALE; a requirement at
     Verified, Reviewed or Released with stale evidence fails with a `FAIL <REQ> <AC>: stale evidence <file>` line
     (below Verified it is reported). A stale fingerprint that equals another criterion's adds "matches AC-n's
     text: renumbered?", never a re-attachment. A malformed or unquoted all-digit `ac_fp` fails at any status
     (write it quoted: `python tools/ac_fp.py REQ AC --yaml` prints `ac_fp: "<hex>"`). Evidence WITHOUT `ac_fp` is
     "unpinned: before tracing" ONLY when its path is listed in `spec/traceability/unpinned-before-tracing.txt`
     (written once by `python tools/ac_fp.py --freeze-unpinned .`); any other evidence without `ac_fp` fails
     ("new evidence must carry ac_fp"). A missing list = nothing may be unpinned. An evidence file for an AC id the
     requirement no longer has prints a WARN line.
   - trace_check fails a work item whose requirements share an AC id (one evidence file cannot prove both).
   - Evidence is bound to ONE requirement: pinned evidence carries `requirement: REQ-###` (the schema requires it
     with `ac_fp`; `ac_fp.py REQ AC --yaml` prints both lines) and counts only for that requirement; evidence
     naming another requirement fails, so a split child with identical criterion text never inherits its parent's.
   - Requirement schema: statuses `Delivered-before-trace` (requires `delivered_in`: a `docs/milestones/*-report.md`,
     not a plan, inside docs/milestones, that names the requirement; never a PR, OD-48 — cite the PR inside the
     report; a requirement any work item links cannot use this status) and `Superseded` (requires `superseded_by`: an
     existing requirement or decision id; a loop fails, a Draft target warns); trace_check demands no evidence for
     either and prints DELIVERED-BEFORE-TRACE / SUPERSEDED. Optional `split_from: REQ-###` must name another
     existing requirement (no loop), and a split requirement's evidence must carry `ac_fp`. `build_order.py`
     counts Delivered-before-trace as done, never lists a Superseded requirement, and resolves a dependency on one
     through superseded_by (a loop, or a chain back to the dependent itself, fails). `spec_dupes` counts coverage
     only from an allow-list of statuses: a misspelt or unknown status never covers.
   - Status page: a Health column beside Status (first match wins: Changed - needs re-check, Blocked, Parked,
     Unpinned evidence, OK), one Overall tile per health, and an "Any health" filter. The headline counts done =
     verified + delivered before trace (shown split) and leaves Superseded out of the total, with its own tile.
   Replaces `tools/trace_check.py`, `tools/build_order.py`, `tools/build_status_page.py`, the evidence and
   requirement schemas and the `deliver` skill; adds `tools/ac_fp.py` (all kit-owned).
16. Migration: at the upgrade, run `python tools/ac_fp.py --freeze-unpinned .` ONCE and commit
   `spec/traceability/unpinned-before-tracing.txt`: it lists every existing evidence file without `ac_fp`, which
   then shows "unpinned: before tracing" and keeps its requirements verified (the tool refuses to overwrite the
   list without `--force`). New projects start with no list. Nothing else to back-fill, and never back-fill:
   new evidence carries `ac_fp`. Split any work item that delivers two requirements sharing an AC id. Do not add `ac_fp` to an old evidence file
   (today's fingerprint would claim the old proof covered today's text); re-verify the criterion instead when you
   want it fresh. A requirement delivered before tracing existed can move to `Delivered-before-trace` with
   `delivered_in`; a replaced one to `Superseded` with `superseded_by`.
17. The verifier cannot forge evidence (REQ-015, OD-47, issue #41). Why: the verifier's own definition said "You may
   write exactly one thing: the evidence file(s)" while its description said it cannot write; verifiers wrote evidence
   files through their shell four times despite briefs forbidding it (findings agent-definition-contradicts-its-role,
   agent-frontmatter-hooks-silent-headless).
   - `.claude/agents/verifier.md` grants no write: it returns one block per acceptance criterion in its reply only,
     each carrying the `requirement:` and `ac_fp:` lines; the orchestrator records the evidence files (deliver step 5).
   - New hook `.claude/hooks/verifier_write_guard.py` (source `capabilities/hooks/verifier-write-guard/`), wired by the
     kit settings on `PreToolUse`, `PostToolUse` and `PostToolUseFailure` for `Bash|PowerShell`. Only when the hook
     input's `agent_type` is `verifier` (also `plugin:verifier`, or a name in `VERIFIER_WRITE_GUARD_AGENTS`), one
     foreground call at a time, in `evidence/`, `work/` and `spec/` of the repo and every git worktree: a file absent
     when the call started and untracked by git when it ends is moved to `<system temp>/verifier-quarantine/<stamp>/`;
     every other change (changed, deleted, or new but tracked, e.g. a merge) is copied there and reported, never
     moved or reverted; `MANIFEST.json` lists each (checkout, path, sha256, action). The call is refused naming each
     path and its checkout. A background verifier shell call is refused before it runs. Judged by effect, never by
     the command text; links and junctions are never followed; the main session and other agents are untouched. No
     snapshot: refused, git's untracked/modified paths listed, nothing moved. Threat model: stops an honest
     verifier, not a same-user forger. `tools/kit_settings.py` accepts the `PostToolUseFailure` event. The deliver
     skill's step 4: the orchestrator records git status before the dispatch, flags only new lines after it, and
     reconciles each quarantine MANIFEST.json created in between.
   - Factory-side: `tools/kit_live_proof.py` adds a real verifier write attempt and checks the file is gone from the
     project, is in the quarantine folder, and that the refusal is in the verifier's own transcript.
   Migration: nothing to edit. The upgrade replaces the verifier definition, adds the hook and regenerates the
   settings file (`python tools/kit_settings.py .`). A project that changed its own verifier definition re-applies
   that change without any write grant.
18. The build order never schedules a requirement that is only recorded (REQ-036, OD-53). Why: after a batch of
   Specified requirements was added, six of them ranked ahead of approved work and `--may-start` refused that work,
   naming items nobody had approved. Behaviour change: a requirement at Draft or Specified (any case) is never
   `next` and is not in the order to build; `--may-start` answers NO saying it is recorded, not approved to build,
   and names its status; `views/build-order.md` lists each under a separate heading
   "Recorded, not approved to build"; an approved requirement that depends on one shows as waiting on it by id. Projects that hold Specified
   requirements will see them listed apart. Replaces `tools/build_order.py` (kit-owned). Migration: none; run
   `python tools/build_order.py .` to regenerate the view.
19. Releases and reviews are traceable (REQ-016, OD-49, OD-55). Why: no release record had ever been written, so
   nothing could answer "in which release was it delivered?" or "which review accepted it?" for any requirement.
   - Release records: `releases/R-###.md` (release schema; `date` is now required next to `version` and `items`, and
     each item is a requirement `REQ-###` or a work item `W-###`). New field `kind`: `kit` (a kit version, nothing
     deployed: status must be `released`, the new status value, and `authorization` is optional) or `production`
     (the default when absent: `authorization` with `required: true` as before, and only `deployed` counts as
     delivered). Kit releases are recorded from 1.4.0 on; earlier versions stay described by this file and are not
     back-filled. Only `R-###.md` records and `README.md` may sit in `releases/`; anything else fails.
   - `trace_check.py` checks both ways: a requirement at Released must name `release: R-###`, that record must exist,
     list it, and be at its kind's delivered status (a cancelled, preparing or rolled-back record fails); a record
     must not list a requirement that does not name it back or is not Released. Each FAIL names the requirement and
     the record. A record it cannot read (no frontmatter, `id` not R-### or not its file name, `items` not a list, an
     item that is neither id, an unknown `kind`) fails, naming the record. Verified and Reviewed requirements are
     listed as UNRELEASED (and in a new "Releases" part of `views/trace.md`), never as released.
   - Review link: a done work item's `review_status` STARTS with the pull request that merged it, `PR #<n>` (n >= 1;
     later `PR #` mentions are follow-ups, a bare `#n` reads as an issue). Tier A and B continue with `; reviewed`
     (e.g. `PR #12; reviewed (Tier B diff review PASS)`) or, for work merged before reviews were recorded, the
     explicit marker `; review not recorded`; anything else ("not reviewed", "review pending") fails. The legacy
     marker `review not recorded` is accepted on any done Tier A/B item and always shown as "not recorded"; it is
     for items delivered before this check, and a project should not use it for new work. The check proves that the
     merging pull request and a verdict are named, not that the review ended clean: a verdict such as "REVISE ...
     fixed" is accepted as written, because matching verdict words would misread honest records. Tier C
     starts with the pull request (e.g. `PR #7; not required (Tier C)`). A done work item without tier A, B or C
     fails.
   - Status page: the requirements table gains Release (or `unreleased`) and Review PR (the merging PR, with
     "(review not recorded)" for the marker) columns and an "Any release" filter.
   Replaces `tools/trace_check.py`, `tools/build_status_page.py` and the release schema (kit-owned).
   Migration (your CI fails until done, which is the point): once, start `review_status` of every existing done
   work item with its merging pull request, e.g. `review_status: "PR #42; reviewed (Tier B PASS)"`, or
   `"PR #42; review not recorded"` when no review was recorded (quote it: an unquoted ` #` starts a YAML comment);
   add `date` (and `kind: production`, optional) to any existing release record; then write one release record for
   the kit version you move to, listing the requirements it delivered, and add `release: R-###` to each of them as
   you set them Released. If no requirement is Released yet, write no release record now: the first record comes
   with your first release (a record listing nothing, or listing a requirement that is not Released, fails
   trace_check). Regenerate the trace view (`python tools/trace_check.py . --write-view`).
   Example kit release record (`releases/R-001.md`, every required field):
     ```markdown
     ---
     id: R-001
     kind: kit
     version: 1.4.0
     date: "2026-10-01"
     status: released
     items:
       - REQ-001
     ---

     # R-001 - kit 1.4.0

     What this release delivered, in a few lines.
     ```
20. Factory-side only: a kit upgrade pull request lists every migration step between the project's kit version and the new one as a checklist, oldest first (REQ-034).
21. Factory-side only: a kit upgrade now resets a hand-edited kit file and names it at the top of the upgrade pull request (OD-57, REQ-041).
22. Migration: add one line to your `CLAUDE.md` telling a session to read `.claude/kit/GUIDE.md` before pushing or
   touching process files (for example "Before pushing or touching process files, read `.claude/kit/GUIDE.md` (kit
   commands and kit-owned files)."), and remove the kit-generic commands list and kit-file list from your
   `CLAUDE.md`; the new kit-owned `.claude/kit/GUIDE.md` carries both and every upgrade keeps it current (REQ-042,
   OD-58). `kit_selftest.py` check (f) now fails, naming `CLAUDE.md`, when the pointer is missing. Replaces
   `tools/kit_selftest.py` and adds `.claude/kit/GUIDE.md` (kit-owned). Why: `CLAUDE.md` is project-owned, so its kit
   text went stale (one real project listed 2 kit commands; the kit expects about 14).
23. Kit rule loading tiers (REQ-043, OD-59): only `evidence-and-proof`, `run-discipline` and `spec-first` stay
   always loaded; `learning` (paths `knowledge/**`) and `spec-adherence` (paths `spec/**`, `docs/spec/**`) are now
   path-scoped like `deployment` and `status-artifact`. Always-loaded kit rule bytes (LF-normalized, as
   `kit_selftest.py` check (c) counts them): 22489 before, 13407 after. The cap in `.claude/kit/budget.json` is now
   13407 plus 9000 of project headroom (two project rules of 4500) = 22407, down from 30000.
   Migration: none; kit-owned rule files replaced.

## 1.3.1 — questions are asked with the question tool, one per call, never buried (OD-37)

1. Why: the owner, 2026-09-29: "If you have questions for me, ask one at a time. Do not stop and just mention that
   I am blocking you. If you are not asking a question, how can I answer?" A session had ended on a question
   written inside a long status report instead of asking it.
2. `evidence-and-proof.md` E1: a question for the owner is ASKED with the interactive question tool, one per call,
   recommended option first with its reason and Spec basis inside; never buried in a report, never a stop that only
   says "waiting on you". Owner away: run-discipline B2 (park it) still applies. The E1 critical-rules line says so.
   Wording elsewhere in the file was tightened to stay under the always-loaded budget; no rule was removed.
3. `intake` skill step 2: each question is asked with the question tool (still opening `*Sync-check:*`).
4. Migration: none; replaces two kit-owned files.

## 1.3.0 — requirement prioritization: layer, checked dependencies, risk, walking skeleton, build order (OD-33, OD-34)

1. Why: requirements carried a free-text `priority` (one real project: 71 requirements, every one `priority: V1`),
   so nothing said what to build first, and a parked foundation item's knock-on blocks were discovered while
   building instead of being visible in the spec. Owner decisions OD-33 (criteria) and OD-34 (mechanisms).
   Core proof: lifting that project's work-item dependencies to requirements, a dependency sort predicted exactly
   the three requirements blocked behind its one parked foundation item, 3 of 3, none extra.
2. Requirement schema: `layer` is REQUIRED, one of core, foundation, feature, polish. `release` stays an optional
   free string. `priority` is now a lint error that names `layer` and `release` as its replacements. New optional
   fields: `risk` (high | normal, absent = normal; `risk: high` needs a non-empty `risk_reason`), `skeleton`
   (true marks the walking-skeleton path; needs layer core or foundation and a non-empty `smoke` list of commands).
3. `factory_lint.py` (repo level) now also rejects: a `depends_on` entry that is not an existing requirement id, a
   self-dependency, a dependency cycle (the message lists every member), an inner item depending on an outer one
   (core or foundation on feature or polish; feature on polish), a repo with requirements but none marked
   `skeleton: true`, and scoring fields (`score`, `rice`, `wsjf`, `value_score`, `effort_score`).
4. New kit tools: `tools/run_smoke.py ROOT` runs every smoke command of every skeleton requirement without a shell
   (shlex split, cwd ROOT, 600 s timeout each; the program is resolved with `shutil.which`, so `npm` finds
   `npm.cmd` on Windows) and fails naming the requirement and command. A smoke line containing a shell operator
   word (`&&`, `||`, `|`, `;`, `<`, `>`, `>>`, `2>`, `&`) is rejected by the lint and refused by run_smoke before
   anything runs (with no shell, `a && b` would never run `b`): write one program per smoke line. Use forward
   slashes in smoke paths (`python tools/x.py`), which work on Windows and Linux alike.
   `tools/build_order.py ROOT` writes `views/build-order.md` (owner `generated` in the lock; `--check` fails when
   it is missing or stale; `kit_upgrade.py` regenerates it and keeps it in the lock) with each open requirement's
   state (next / waiting / blocked, naming the blocking root and its work item's next_action);
   `--may-start REQ-###` gates a start (earlier-group `next` items first: skeleton, then core+foundation, then
   feature, then polish). A work item's `order_override: <reason>` skips ONLY that group-order check; it never
   lets through a done requirement, undone dependencies or a blocked chain. CI runs `build_order.py . --check` and `run_smoke.py .`; the `deliver` skill runs
   `--may-start` at Intake; `spec-first.md` gains a "Build order" section (re-run the order and re-read layers at
   each milestone start and whenever a decision changes; no scoring formulas). `kit_drift.py` checks the
   generated `views/build-order.md` against `build_order.py`'s output and reports a difference as STALE
   (regenerate and commit), not as a hand edit.
5. MIGRATION for an existing project (its CI fails after upgrading until this is done — that is the check doing
   its job, not a regression):
   a. add `layer:` (core | foundation | feature | polish) to every `spec/requirements/REQ-###.md`;
   b. remove every `priority:` line; if it named a version or date (e.g. `V1`), move that to `release:`;
   c. mark ONE core or foundation requirement `skeleton: true` with a `smoke:` list of commands that prove the
      app's core path still works (each one program plus arguments, forward slashes in paths; no `&&`, `|`,
      `;` or redirects), and check it with
      `python tools/run_smoke.py .`;
   d. fix any `depends_on` the lint now rejects (unknown id, duplicate, self, cycle, inner-on-outer);
   e. add `!views/build-order.md` to `.gitignore` (after `views/*`; new projects ship it), run
      `python tools/build_order.py .` and commit `views/build-order.md`;
   f. run `python tools/factory_lint.py .` until it exits 0.

## 1.2.0 — intake kit and session entry point (finding new-project-has-no-session-entry-point)

1. RCA: `new_project.py` shipped a project with no `CLAUDE.md` and no `docs/HANDOVER.md` at its root, and no
   reusable way to turn an owner's idea into decisions — two of two real copier projects
   (`factory-testbed`, `dashcam-youtube`) were built without either, so a fresh session in a new project had
   no recorded purpose, no decisions to read first, and no next step, and had to be told everything again by
   whoever started it.
2. Fix: a new `intake` skill (`.claude/skills/intake/`, kit-owned) takes the owner's idea, asks one question
   per turn with a `Spec basis:` line and a recommendation, records each answer as the next
   `spec/decisions/ADR-###.md` in the same turn, stops asking what a real-input core proof can measure, then
   fills the project's `CLAUDE.md` and `docs/HANDOVER.md` before writing requirements. The template now ships
   project-owned `CLAUDE.md` and `docs/HANDOVER.md` skeletons (`<fill in>` placeholders); `new_project.py`
   writes both with owner `project` in the lock, same as any other project-owned file.
3. `kit_selftest.py` gained check (f): it fails, naming the file, when `CLAUDE.md` or `docs/HANDOVER.md` is
   missing or empty at the project root, and passes once both exist — the check that makes the skeletons a
   requirement of every project, not just a convention.
4. `kit_upgrade.py` never creates or touches either file: both are project-owned (the default owner for any
   path not listed in `new_project.py`'s `OWNERSHIP` table), so an upgrade only ever replaces kit-owned files.
   A project made before 1.2.0 without these two files (the M3 testbed) fails check (f) after upgrading until
   it adds them; that is the check doing its job, not a regression.
   Migration: if the project has no non-empty `CLAUDE.md` and `docs/HANDOVER.md` at its root, add them (check (f)
   of `kit_selftest.py` fails until then); replaces kit-owned files.
5. Fix round 1 (Tier A review, MAJOR): the template's own `CLAUDE.md` was auto-loaded by Claude Code into a
   Factory session working on this repo (any `CLAUDE.md` on the path from cwd up to the drive root is
   auto-loaded), contradicting the real Factory `CLAUDE.md`. The template file is now `CLAUDE.md.tmpl`;
   `new_project.py`'s copier writes it into every project as `CLAUDE.md` (lock `path: CLAUDE.md`,
   `owner: project`, `source:` the `.tmpl` path) — the project still gets a plain `CLAUDE.md`, only the
   Factory's own tracked copy is renamed.
6. Fix round 1 (Tier A review, MAJOR, pre-existing, fixed here because W-004's core proof depends on it):
   `kit_live_proof.py` built its throwaway project under `$TEMP`, which sits under the user's home folder, so
   Claude Code's ancestor-directory memory walk loaded `~/.claude/CLAUDE.md` and `~/.claude/rules/*.md` as if
   they were the project's own memory (mislabeled `memory_type: Project`), making the "no user-level
   contribution" check pass falsely. The live-proof project now builds under a folder on the Factory repo's
   own drive, outside any git checkout and outside the user's home folder (`--root` overrides it), and a new
   hard check fails naming any `InstructionsLoaded` `file_path` that resolves outside the project folder at
   all — proven offline with a fake event log carrying such a path.
7. Fix round 2 (Tier A review, MAJOR (k)): the round-1 fix for item 6 shipped without a mutation test —
   reverting the default root or the project path to a bare `tempfile.mkdtemp()`/`tempfile.gettempdir()`
   stayed green. Added unit tests asserting the default root is neither under `Path.home()` nor inside a git
   checkout, and that the run's project path resolves under that root (killed).
8. Fix round 2 (MINOR, real cost): live-proof cleanup used `shutil.rmtree(..., ignore_errors=True)`, which
   silently left every read-only `.git` object file behind (126 per run, measured, at the drive root). Cleanup
   now clears the read-only bit and retries on failure (`onexc`/`onerror`), removes the run folder itself, and
   prints a `WARNING` naming the path on a genuine failure instead of staying silent.
9. Fix round 2 (MINOR): `kit_selftest.py` check (f) now strips whitespace before the emptiness test, so a
   whitespace-only `CLAUDE.md` or `docs/HANDOVER.md` counts as missing, same as 0 bytes.
10. Fix round 2 (MINOR): on non-Windows, the default live-proof root is `/tmp/kit-live-proof-tmp` (writable,
    outside the home folder), not the unwritable-by-normal-users `/kit-live-proof-tmp`; a non-writable default
    root now refuses with a message pointing at `--root` instead of silently falling back under the home
    folder.

## 1.1.4 — guards split shell commands only outside quotes (finding segment-split-before-quotes)

1. RCA: the three git guards' shared `_git_shell.py` and `kit-file-guard`'s own segment split both matched a
   separator regex (`&&`/`||`/`;`/`|`/`&`/`{`/`}`/`(`/`)`/newline) over the raw command TEXT before any quote was
   recognized, so a separator character INSIDE a single- or double-quoted argument (a `-m` commit message, a
   test loop's quoted case string) split the string in two and the quoted words on either side were read as
   their own command segments — a quoted bypass word could reach the parser as if it were a real, separate
   command, and (in `kit-file-guard`) a harmless quoted decoy could make an otherwise read-only command look
   like a real write and get denied instead.
2. Fix: `_git_shell.split_segments`/`split_segments_with_start` and `kit-file-guard`'s local segment scanner now
   walk the command character by character and only treat a separator as a boundary while it is NOT inside an
   open quote; an unterminated quote fails safe (the remainder of the command is kept as one segment).
   `git-stash-worktree-guard` was updated to call the shared `split_segments_with_start` instead of the module's
   former private `_SPLIT_RE` attribute.
3. Swept `full-suite-guard` and `pipe-exit-guard`: both still split on raw separator text before tokenizing, but
   neither is wired into this template yet — left as-is, to be fixed at the sweep that adopts them.
4. Migration: none; replaces kit-owned files.

## 1.1.3 — git guards catch every spelling (issue #14); budget guard checks the agent's turn limit

1. `git-discard-uncommitted-guard`, `git-hook-bypass-guard`, `git-stash-worktree-guard`: the git program is now
   matched as `git`, `git.exe`, or any path ending in `/git(.exe)` or `\git(.exe)`, case-insensitively; `&` (the
   PowerShell call operator), `{`, `}`, `(`, `)` are segment boundaries, and a backtick line-continuation is
   collapsed before scanning.
2. `git-hook-bypass-guard` also blocks `-n` on `commit`/`merge` (the short form of `--no-verify`), leaving it
   unblocked on `push`/`clean` where `-n` means `--dry-run`.
3. `git-discard-uncommitted-guard` now catches a whole-tree `git checkout .` with no `--` separator, the same way
   it already caught `git restore .`.
4. `agent-budget-required` refuses a `Budget: N min, M tool calls` line whose `M` exceeds 80% of the target
   agent's own `maxTurns` (read from `.claude/agents/<subagent_type>.md`), naming both numbers; an unknown agent
   or a file with no `maxTurns` skips this check.
5. Tier A round 2 (same issue #14 review, RCA: raw-text regexes let a quoted program path, bundled short flags,
   an unambiguous long-option prefix, a mixed-case config key or an env-var config mechanism slip through): the
   three git guards now tokenize each shell segment into real words (shared `_git_shell.py`) and reason about
   PROGRAM + ARGV instead of scanning text. `git-hook-bypass-guard` now also blocks any unambiguous prefix of
   `--no-verify` (from `--no-v` up), `-n` bundled into commit's short flags (`-nm`, `-anm`) — commit only, since
   merge's `-n` means `--no-stat`, not a bypass — a case-insensitive `-c core.hooksPath=`, and
   `GIT_CONFIG_PARAMETERS`/`GIT_CONFIG_KEY_*` setting `core.hooksPath`. `git-discard-uncommitted-guard` now also
   blocks `git checkout -f`/`--force` with no explicit path (discards every dirty file, like `checkout -- .`).
   `git-stash-worktree-guard` now treats every stash flag except `-h`/`--help` as a mutating push option (`-u`,
   `-m wip` used to be misread as read-only) and recognizes `Set-Location`/`pushd`/`chdir` as `cd`.
6. Tier A round 3 (same review, sweep): `git-stash-worktree-guard` kept its own quote-stripping/regex program
   match instead of going through the shared `_git_shell.py`, so a quoted program path with spaces
   (`& "<full path to git.exe>" stash`) was allowed inside a linked worktree; the program is now
   identified only via `_git_shell.py`, matching the other two git guards.
7. Migration: none; replaces kit-owned files.

## 1.1.2 — the self-test counts a guard as blocking only on exit 2

1. `kit_selftest.py` check (d) accepts only exit code 2 as a block. A crash (exit 1) is a non-blocking error to
   Claude Code, and a JSON deny at exit 0 can be overridden by another hook's allow; both used to read as "blocks".
2. Migration: none; replaces kit-owned files.

## 1.1.1 — kit-file-guard lets kit tools run; frontmatter split fixed; caches ignored; merge and upgrade reports

1. kit-file-guard: a shell segment running a kit tool (`python tools/<name>.py`) is no longer treated as a
   write to it; write forms into `tools/` still refuse.
2. `factory_lint.py` and `trace_check.py` split frontmatter only on a line that is exactly `---`, never on a
   `---` inside a quoted value.
3. The copier's `.gitignore` now ignores `__pycache__/` and `*.pyc`, so a fresh project's `git status` stays
   clean after running the shipped tools.
4. `merge_when_green.py` re-reads the PR state after `gh pr merge`; MERGED is reported as success even if
   local branch cleanup fails.
5. `kit_upgrade.py`'s summary reports "changed" and "identical" kit files separately, and skips rewriting an
   identical file.
6. The deliver skill: a headless (`claude -p`) run merges through `merge_when_green.py` in the foreground.
7. Migration: none; replaces kit-owned files.

## 1.1.0 — kit ships merge_when_green.py (refuses conflicted PRs; zero checks = wait); the deliver skill merges only through it

1. Migration: none; replaces kit-owned files.

## 1.0.0 — first kit release

Fixes made during M3, before the first release:

- The git guards also check PowerShell commands, not only Bash.
- Both agent guards also check the `Task` tool, not only `Agent`.
- The hook presence check also reads the local settings file.
- The production seatbelt is opt-in (the copier's `--seatbelt`); without it every call is allowed.
- The evidence guard starts log-only; the project turns blocking on after reading its log.
- The copier refuses to overwrite files, to write through a link, into the home folder or a drive root, and
  records a dirty template in the lock.
- The drift check confines every lock path to its base folder.
- Provenance hashes are taken over LF-normalized content, so Windows and Linux checkouts agree.
- The banned-term scan covers every text file in the kit; agent-guard messages are generic.
- OD-22 layout: kit rules in `.claude/rules/kit/`, project rules in `.claude/rules/project/`; the settings
  file is generated by `tools/kit_settings.py` from the kit wiring (`.claude/kit/settings.kit.json`) plus the
  project addendum (`.claude/project/hooks.json`), minus opt-outs with a reason (`.claude/project/optouts.json`).

1. Migration: none; first release.
