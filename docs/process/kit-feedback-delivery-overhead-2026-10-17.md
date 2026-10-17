# Feedback to the Startup-Factory kit: delivery overhead measured in OptionsForOptions2 (2026-10-17)

Why this file exists: the owner asked (2026-10-17) that what this project learned about wasted delivery time goes back
to Startup-Factory, so the kit and every project built on it improves. It is filed as one `harvest` issue on
`abhayla/Startup-Factory` that links here; each row was reviewed by three independent reviewers (delivery process,
trading safety, platform feasibility) and checked against open harvest issues. Project-side decisions: ADR-1NN.

## What was measured (2026-09-28 .. 2026-10-17, from git and GitHub)
- 272 merged PRs: 102 on `docs/` branches (about 60 by title), 95 build, 36 fix, 29 spec.
- Lines added: 49% docs/process files, 25% tests, 15% product code.
- 300 CI runs in about 18 h (about 75 pushes x 4 workflows); the two real workflows were red about 25% of the time,
  mostly repo-wide scans and the lint ratchet found only in CI.
- 96 of 580 commits since 2026-10-15 only merged main into a branch.
- Writing the code took 7-60 minutes per work item; an item took hours. One guard (W-080) took about 21 h over 10
  review rounds and stopped only when the owner ruled an attack class out of scope.
- Root pattern: each safeguard is applied at the smallest unit (every work item, every round, every run), so a
  feature split into 8-12 items pays for its reviews, verifiers and paperwork 8-12 times.

## Kit-level problems and proposed changes
| # | Problem (evidence) | Proposed kit change | Related |
|---|---|---|---|
| 1 | The deliver skill's tier table plus "when unsure, use the higher tier": in a money/orders product nearly every item becomes Tier A. Tiering by code TYPE instead misses reads that feed orders (market depth decided which legs are refused; a depth-loop crash was a real MAJOR). | Tier by DATA FLOW from a project-declared Tier A list (order building/state, reconciliation, money maths, live-data liveness, migrations, auth/secrets, hooks, and any read that feeds a price, quantity, band, margin, fill or position). The tier of a change is that of its highest-risk file. | new |
| 2 | The two-round cap is prose; no tool counts rounds, so a guard ran 10 rounds. Guard briefs have no place for what attack is in or out of scope. | A per-item round counter the merge route reads; a required `Threat model: in scope / out of scope` line before round 1 of any guard; a CRITICAL or MAJOR on Tier A code is never deferred (redesign or park unmerged). | new |
| 3 | A verifier plus per-criterion evidence for EVERY item, enforced only by prose; quarantine conflicts across worktrees. | Per-PR verifier for Tier A; requirement-close verifier (on main's combined code) for Tier B; a verifier pass on main for every money/order criterion before any live run; the review is pinned to the pushed head SHA. | #110 |
| 4 | Every run's plan (contract) gets a full independent review, though most findings are logistics found within minutes of starting. The real catches were design catches (a rounding change reversing a safe-side margin check; a "merged" claim that was false before a live run). | Every run: a short precondition check (each "merged"/"exists" claim against GitHub) and a wiring map. Full review only for new or changed money/order behaviour and for any run before a live real-money step. | new |
| 5 | Run close-out is heavy: a long handover, a hand-typed scorecard, process misses filed as findings. | A capped handover template (DONE / PENDING / BLOCKED / PARKED / NEXT); a scorecard generated per stage from git/GitHub. | new |
| 6 | "A run is in progress" is a merged PR (a PR and three CI runs to change one line); no race-safe lock. | Lock = push of `refs/heads/lock/<run>` (a second push is rejected), owner session, start time and cap in the commit, stale locks reported. | #106 |
| 7 | No rule against parallel DEPENDENT branches (they kept merging each other and main); the kit `ci.yml` has no `concurrency`, so superseded PR runs keep running. | Dependent items as stacked PRs; one base update right before the merge gate; `concurrency` in `ci.yml` with cancel only for pull_request runs (main runs grouped by commit). | #104 |
| 8 | No brief template in the kit; brief hooks read the dispatch prompt text, so `Budget:` and `Report:` lines must stay literal even when a template is used. | Ship a common builder-brief template; `check_brief`-style tooling reads the template; document which hooks read the prompt text. | #106 |
| 9 | No work-item size guidance; items get cut per internal layer and each pays the full fixed routine. | A user-visible step is the planning and e2e unit; the PR unit stays small and stacked (Tier A about 1,000 lines of product code); a migration is always its own PR. | new |
| 10 | The kit guard blocks read-only actions by text match: `git ls-remote`, `cmp`, loops, the kit repo name in `-R`, the word "spec" inside a grep pattern, the word "tools" in a user-level tool path (`~/.claude/tools/wt-new.ps1`, the sanctioned worktree tool). Each forced a rewrite through a script file. | Block writes to kit paths and reads of secret files only; allow plain reads and user-level paths outside the project. | #89, #40 |
| 11 | A process recommendation silently narrowed a safety rule (dropped "live-data liveness" from Tier A) and over-claimed savings; it was approved before any review. Finding `process-change-narrows-safety-rule` (scope generic). | A process change that touches review tiers, rounds, verifiers or guards gets role reviewers (safety, delivery, platform) before the owner sees it; the current rule is quoted next to the proposed one. | new |

| 12 | The kit's rule copies lag the owner's user-level rules, and both load in every kit project (about 10 KB twice): kit `run-discipline` 1.0.0 lacks user-level 1.1.0's B4 standing brief items (a)-(d) and B8 "prefer a structural guarantee over a detector"; kit `spec-first` 1.4.0 is ahead of user-level 1.2.0. | Bring the kit copies level with the user-level versions (add B4 (a)-(d) and B8 to kit run-discipline), so a project can drop the user-level duplicate with the documented `claudeMdExcludes` setting (code.claude.com/docs/en/memory.md) without losing a rule. | new |

Not sent to the kit: the coverage check's grace window (project-owned `coverage.py`); the laptop-sleep loss (owner
setting).

## How the kit can check the gain
Each project that adopts these can run the same measurement (PRs by type, lines by area, CI runs and reds, merge-only
commits, review rounds per item) before and after one run; OptionsForOptions2 adds `scripts/orchestrator/stage_scorecard.py`.
