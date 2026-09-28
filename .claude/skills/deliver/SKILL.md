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
2. **Requirement + work item** — read them before anything else. They fix the acceptance
   criteria and the tier; nothing below may silently redefine them.
3. **Builder** — dispatch the `builder` agent in its own worktree. It writes code and one
   test per acceptance criterion in `tests_required`. It never writes `evidence/` files and
   never marks any status field verified or reviewed — doing so would make it its own
   verifier, which is not independent verification.
4. **Verifier (Tier B and Tier A only)** — dispatch the `verifier` agent in a fresh context
   (different agent from the builder). It is read-only: it re-runs the exact test commands
   itself, tries at least one way each acceptance criterion could plausibly fail, and
   returns one evidence block per AC. Tier C work skips this step; CI is the check instead.
5. **Evidence** — the orchestrator (never the builder, never the verifier) records the
   verifier's returned blocks as `evidence/<W-id>/<AC-id>.md`. For Tier C, the orchestrator
   records the CI run itself as the evidence.
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

## Tier table

| Tier | What runs |
|---|---|
| **C** | builder + CI. No dedicated verifier or review pass; CI runs (trace check, findings index, lint, tests) are the evidence. Docs, config text, renames, generated files. |
| **B** | Tier C, plus an independent verifier (fresh context, read-only) and a diff-focused review. Ordinary implementation work with green tests. |
| **A** | Tier B, plus an adversarial review from a fresh, independent context and mutation tests on any guard the work adds or changes. Irreversible operations, production deploy, auth/secrets/data migrations, anything that deletes or moves data, any check meant to be hard to bypass. |

When unsure which tier applies, use the higher tier.

## Recovery

- **Verifier fails an AC** — the builder fixes it (same worktree, new round). A **fresh**
  verifier (or the same verifier in a new context) then re-checks *every* AC again, not
  only the one that failed — a fix can break something the first pass already passed.
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
