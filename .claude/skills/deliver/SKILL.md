---
name: deliver
description: >
  Use this skill to deliver one approved work item (`work/W-###.md`) through the project's
  delivery loop, from intake to merge. Use it whenever a work item's status moves out of
  `todo` and its requirement is Approved — not for exploratory spikes or work with no
  requirement record yet.
---

# Deliver

Delivers exactly one work item through the loop: intake, build, verify (where the tier
requires it), evidence, trace check, review, PR, merge, status update.

## Loop steps

1. **Intake** — confirm the requirement (`spec/requirements/REQ-###.md`) and the work item
   (`work/W-###.md`) both exist and are lint-clean (`python tools/factory_lint.py .`). The requirement's acceptance criteria are what the work item's
   `tests_required` must cover.
   Then run `python tools/build_order.py . --may-start REQ-###` for each requirement the work
   item delivers; a non-zero exit stops the delivery (it names the earlier `next` items, the
   undone dependencies or the blocking root). Start out of order only when the work item carries
   `order_override: <reason>` (the reason is the record), which --may-start prints.
2. **Requirement + work item** — read them before anything else. They fix the acceptance
   criteria and the tier; nothing below may silently redefine them.
3. **Builder** — dispatch the `builder` agent in its own worktree. It writes code and one
   test per acceptance criterion in `tests_required`. It never writes `evidence/` files and
   never marks any status field verified or reviewed — doing so would make it its own
   verifier, which is not independent verification.
4. **Verifier (Tier B and Tier A only)** — dispatch the `verifier` agent in a fresh context
   (different agent from the builder). It is read-only: it re-runs the exact test commands
   itself, tries at least one way each acceptance criterion could plausibly fail, and
   returns one evidence block per AC, each carrying the two lines `requirement: <REQ-id>` and
   `ac_fp: "<hex>"` printed by
   `python tools/ac_fp.py <REQ-id> <AC-id> --yaml` at the time it checked that criterion. Before
   dispatching the verifier, the orchestrator records
   `git status --porcelain --untracked-files=all -- evidence work spec`; after it returns, it runs
   the same command and flags only NEW lines (lines present before are its own work and are left
   alone). It also lists the quarantine folders under `<system temp>/verifier-quarantine/` created
   since the dispatch and reconciles each entry of their `MANIFEST.json` (`moved`: a verifier file,
   keep it out; `copied`/`deleted`: decide whose change it was). Flagged lines are reported, never
   deleted blindly (REQ-015). Tier C work skips this step; CI is the check instead.
5. **Evidence** — the orchestrator (never the builder, never the verifier) records the
   verifier's returned blocks as `evidence/<W-id>/<AC-id>.md`. For Tier C, the orchestrator
   records the CI run itself as the evidence. Every new evidence file carries the verifier's
   `requirement: <REQ-id>` line (evidence proves only the requirement it names) and its
   `ac_fp: "<hex>"` line, QUOTED (an all-digit hex would load as a number). Before writing,
   run `python tools/ac_fp.py <REQ-id> <AC-id>`: if it differs from the verifier's value the
   criterion changed after the check, so re-verify instead of writing. trace_check fails new
   evidence without `ac_fp`; only files listed in `spec/traceability/unpinned-before-tracing.txt`
   (written once at adoption) may lack it. Never add `ac_fp` to an existing evidence file.
6. **Trace check** — run `python tools/trace_check.py .` (default mode; never `--strict` in
   CI), so that a requirement cannot move to `Verified` while its chain to a work item and its
   evidence is broken. Also `python tools/build_findings_index.py --check` and
   `python tools/check_spec_refs.py .` when findings changed.
7. **Review** — sized by tier (see the tier table below).
8. **PR** — open the pull request from `.github/pull_request_template.md`; its Spec-deviation
   block is required (`tools/check_pr_spec_block.py` fails the PR without it). CI must run and
   pass (see CI below).
9. **Merge** — merge ONLY with `python tools/merge_when_green.py <pr>`, once the tier's required
   review is in. Never `gh pr checks --watch && gh pr merge`: `gh pr checks --watch` exits 0 on
   "no checks reported" before CI has even started, so that sequence merges an unproven PR. The
   tool also refuses a CONFLICTING/DIRTY PR at once, since GitHub runs zero CI on one. In a
   headless run (`claude -p`), run it in the FOREGROUND and wait for it to exit — a headless
   session's turn ends when the turn ends, so a backgrounded merge_when_green never finishes and
   the PR never gets merged.
10. **Update statuses** — after merge, the orchestrator (never the builder, never the
    verifier) advances `verification_status`, `review_status`, and the requirement's
    lifecycle status.
11. **Status page** — if a stage changed (a requirement's status, a work item blocked or
    unblocked, an owner question opened or answered, a gate changing state), regenerate the page
    with `python tools/build_status_page.py . --fetch --out views/status-page.html` and republish
    that file to the link in `views/status-page.json` (Artifact publish with `url`, so the link
    stays the same). Never on an ordinary merge. First publish of a project: publish once, then
    create `views/status-page.json` as `{"url": "<the link>"}` and commit it.

## Model and effort per dispatch

Name the model (by alias) and the effort on every dispatch; the choice comes from `.claude/kit/model-routing.yaml`,
and the dispatch hook refuses an unknown model, `opus` without a `Why Opus:` line and `fable` without a
`Why Fable:` line. At intake run `python tools/model_mix.py --alarms`. On a `NEW MODEL` or `UNROUTED MODEL` line do
not edit `.claude/kit/` (kit-owned, replaced by the next kit upgrade): record it as a finding with scope generic, so
`kit_harvest` carries it to the kit's maintainers, and continue with the table as it is.
On `NO TRANSCRIPTS: <path>` the report could not find this project's transcripts: check the path and continue (it is not an alarm).

| Dispatch | Model / effort |
|---|---|
| builder | builder sonnet/medium, always (the building class, whatever the tier; a fuzzy multi-file spec gets a design pass first on opus/high with a `Why Opus:` line) |
| verifier, Tier B | verifier sonnet/high |
| verifier, Tier A | verifier opus/high |
| review, Tier B | review sonnet/high |
| review, Tier A | review opus/xhigh |
| independent review after the same class fails twice | fable/high with a `Why Fable:` line |
| read-only search across the codebase | the `Explore` agent (haiku/medium) |

## Tier table

| Tier | What runs |
|---|---|
| **C** | builder + CI. No dedicated verifier or review pass; CI runs (trace check, findings index, lint, tests) are the evidence. Docs, config text, renames, generated files. |
| **B** | Tier C, plus an independent verifier (fresh context, read-only) and a diff-focused review. Ordinary implementation work with green tests. |
| **A** | Tier B, plus an adversarial review from a fresh, independent context and mutation tests on any guard the work adds or changes. Irreversible operations, production deploy, auth/secrets/data migrations, anything that deletes or moves data, any check meant to be hard to bypass. |

When unsure which tier applies, use the higher tier.

## Batches: check once per batch, not once per change

Changes to the same module, or similar changes, are batched: built together and checked once.

- **Review first, verifier after.** The review runs on the batch's final state, and the verifier
  runs once, AFTER a clean review.
- **Views and CI's local checks run once per batch** before the push (generated views, spec checks,
  the commands in `.claude/kit/GUIDE.md` or the project's equivalent), not after each edit.
- **One command mirrors CI:** run `python tools/ci_local.py` once, in the foreground, before the
  first push of a batch (`--list` shows the plan); it runs every step CI runs.
- **Not batched (exceptions):** the core proof, which always comes first and alone; unrelated
  modules; a hook or guard that can block every session; a batch bigger than one reviewer can
  read end to end.
- **Reviewer scope:** the real inputs and the work's structural rule, never hypothetical
  malformed input for files only this project writes.

## Recovery

- **Verifier fails an AC** — the builder fixes it (same worktree, new round). The builder's
  targeted tests and the orchestrator's re-run are the only checks inside the fix loop; a
  fresh verifier then re-checks *every* AC once, on the final state after the review is clean,
  not after each fix round — a fix can break something an earlier pass already passed, and a
  verifier pass made before a review that forces a code change is wasted.
- **The same class of failure is red twice** — before the next builder round, dispatch an
  independent review (a different model or a fresh instance, never the builder or verifier
  that already touched it) with both failed rounds' diffs and evidence, asking what both
  rounds missed. The next round is built around that review's findings.
- **Red a third time after the independent review** — stop. Escalate to the owner with the
  review, both prior rounds, and a recommendation. Do not attempt a fourth guess alone.

## Builder is never the verifier

This project's traceability check refuses any evidence file whose `verified_by` equals
`builder` (or matches the builder's own identity). This is enforced by the checker, not
only by agent instructions — a work item cannot reach `Verified` on self-certified evidence.

## CI runs the default (non-strict) trace check

CI runs the traceability check in its default mode, never a "strict" mode that would fail
every pull request that adds a new, not-yet-delivered requirement (see
`knowledge/findings/` for the finding this avoids, if the project has recorded one): a
whole-repository check that demands every item be finished fails the moment a new,
legitimately unfinished item is added, blocking normal intake of new work.
