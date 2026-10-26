---
name: deliver
description: >
  Use this skill to deliver one approved work item (`work/W-###.md`) through the project's
  delivery loop, from intake to merge. Use it whenever a work item's status moves out of
  `todo` and its requirement is Approved — not for exploratory spikes or work with no
  requirement record yet.
---

# Deliver

Delivers exactly one work item: intake, build, check, evidence, trace check, PR, merge, status update.

## Principles

- The agent is a careful colleague; guards and gates protect against accidents. A guard or gate change gets one diff
  review and its tests, with known bypasses written down in the guard's README, not chased.
- The main session stays small: it never reads logs, diffs or tables into its context, only the last lines
  (output to a log file, `tail`).
- Models: Sonnet by default, Opus for Tier A only, Haiku for records and searches.
- Kit work and kit upgrades go in a weekly batch.

## Loop steps

1. **Intake** - the requirement (`spec/requirements/REQ-###.md`) and work item (`work/W-###.md`) exist and are
   lint-clean (`python tools/factory_lint.py .`); the work item's `tests_required` cover the requirement's acceptance
   criteria. Run `python tools/build_order.py . --may-start REQ-###` per requirement; non-zero stops the delivery,
   unless the work item carries `order_override: <reason>`. Any plan is written as `plans/PL-###.md`; a change
   appends a `changes` entry (was, now, why), never rewrites silently.
2. **Builder** - dispatch the builder of the tier in its own worktree: `builder-c` (Tier C, 40 turns), `builder-b`
   (Tier B, 75 turns) or `builder` (Tier A, 100 turns). `maxTurns` is the hard stop and the budget hook refuses a Budget
   line above 80% of it. It writes code and one test per acceptance criterion in `tests_required`, never writes
   `evidence/` files and never marks a status verified or reviewed.
2a. **Heavy CI first** - run `python tools/change_scope.py --base <base> --triggers`. When it prints any path
   or `UNKNOWN`, open a draft pull request right after the builder and start the checker only once the project's heavy
   CI is green on that head; a red run goes back to the builder first (a fix round).
3. **Checker (Tier B and A)** - one checker, the `verifier` agent (fresh context, read-only; Sonnet for B, Opus for A),
   reviews the diff, re-runs the test commands and returns one evidence block per AC with the lines
   `requirement: <REQ-id>` and `ac_fp: "<hex>"` from `python tools/ac_fp.py <REQ-id> <AC-id> --yaml`. It replaces
   verifier plus reviewer: there is no independent-review step. Record, before dispatch,
   `git status --porcelain --untracked-files=all -- evidence work spec`; after, flag only NEW lines, never delete them
   blindly. Tier C skips this step; CI is the check.
4. **Evidence** - the orchestrator (not the builder or checker) writes the blocks as `evidence/<W-id>/<AC-id>.md`; for
   Tier C the CI run is the evidence. The orchestrator writes the checker's blocks with
   `python tools/record_evidence.py <reply.json>`. Every new evidence file carries `requirement: <REQ-id>` and a QUOTED
   `ac_fp: "<hex>"`; run `python tools/ac_fp.py <REQ-id> <AC-id>` first and re-verify if it differs. Never add
   `ac_fp` to an existing file.
5. **Trace check** - `python tools/trace_check.py .` (never `--strict` in CI), plus
   `python tools/build_findings_index.py --check` and `python tools/check_spec_refs.py .` when findings changed.
6. **PR** - from `.github/pull_request_template.md`; its Spec-deviation block is required.
7. **Merge** - only with `python tools/merge_when_green.py <pr> --reviewed-sha <full sha of the checked commit>`, in the
   FOREGROUND (a headless `claude -p` run waits for it, never backgrounds it), chained with `&&`. Never `gh pr checks --watch && gh pr merge` ("no checks reported" exits 0 before CI
   starts).
8. **Update statuses** - after merge the orchestrator advances `verification_status`, `review_status` and the
   requirement's status.
9. **Status page** - the `status-page-due` Stop hook builds `views/status-page.html` itself if a stage changed
   (a requirement, work item, plan step or owner question status, a release, a merged pull request) and asks once
   for one publish: Artifact with `file_path` + the `url` in `views/status-page.json`. Do that when asked; do not run
   the build by hand. A merged pull request IS a stage change once the merge is in your local checkout, so pull first
   (`merge_when_green.py` does not pull); a commit or a test run alone is not a stage change. With no `views/status-page.json`
   yet, build with `python tools/build_status_page.py . --fetch --out views/status-page.html`, publish once, create
   `views/status-page.json` as `{"url": "<the link>"}` and commit it.
10. **Process review** - after each item record minutes, rounds and the cause of each extra round; apply the fix that
    removes the cause the same turn.

## Tiers (chosen by the changed files; unsure: the higher one)

| Tier | Changed files | What runs |
|---|---|---|
| **C** | docs, records, text, test-only | builder + CI only |
| **B** | normal code, kit tools and hooks | builder + one Sonnet checker |
| **A** | production deploy path, money and order maths, data migrations, auth and secrets | builder + one Opus checker |

A change takes the tier of its highest-risk file. Mutation tests apply only to Tier A guards: at most 5 mutants, run by
the builder on a scratch copy, not a gate.

## Rounds and parking

At most 2 rounds. Round 2 re-checks round 1's findings and the fix's files only, 15 min. Then park, or ship with the
findings listed for the owner. Do not dispatch an independent review.

## Model and effort per dispatch

Name the model (alias) and effort on every dispatch from `.claude/kit/model-routing.yaml`; the dispatch hook refuses an unknown model and
`opus` without a `Why Opus:` line. At intake run `python tools/model_mix.py --alarms`: on a `NEW MODEL` or `UNROUTED MODEL` line do not edit `.claude/kit/` (kit-owned): record a finding with scope generic so `kit_harvest` carries it, and continue. `NO TRANSCRIPTS: <path>`
is not an alarm.

| Dispatch | Model / effort |
|---|---|
| builder (any tier) | sonnet/medium (a fuzzy multi-file spec gets a design pass first on opus/high with `Why Opus:`) |
| checker, Tier B | verifier on sonnet/high |
| checker, Tier A | verifier on opus/high |
| records, data entry, search | haiku (the `Explore` agent for read-only search) |

## Sizing

- 5 or fewer small, 6 to 15 medium, more than 15 or backend plus frontend large and split before the build. A migration
  is its own pull request. Dependent items go as stacked pull requests; update a branch from its base once, right
  before the merge gate. If that changed a file in the diff or a Tier A path, the gate says `RE-REVIEW NEEDED`.

## Batches

Batch similar changes: build together, check once. Run `python tools/ci_local.py` once, in the foreground, before
the first push of a batch (once per batch). The core proof comes first and alone.

When `python tools/measure_tokens.py` shows the main session reading more than 300,000 context tokens per call
(its context tokens divided by its calls; that report is the counter and 300,000 a starting value to re-tune), write the handover and continue
in a fresh session.

## Builder is never the checker

`trace_check` refuses evidence whose `verified_by` is `builder`. CI runs the trace check in default mode, never `--strict`, which would fail every pull request that adds a new, not-yet-delivered requirement.
