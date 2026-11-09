# Owner questions 2026-11-09 (GC-ICTRACK, parked at night by the question guard)

## Q1 (01:47 IST): a private account figure reached the public repo; how far to clean it?

**What happened (my mistake):** the session handover committed and pushed at 01:45 IST to the public branch
`build/gc-ictrack` (commit 67dd4b42) recorded the owner's Zerodha available-margin figure from the 20:05 read-only
probe. It is removed from the file in commit e777a1fc (not pushed) and kept out of the PR text. The old commit still
holds it in the branch history on GitHub.

**Held until you answer:** the PR is NOT opened (a PR's commit list is permanent on GitHub) and nothing more is pushed.

Business call: this is your account data on a public site, and the full clean-up rewrites a public branch
(force-push), which is outward-facing and cannot be undone.
Spec basis: none: the spec says nothing about account figures in public repo files (searched: margin, public,
privacy, account data); nearest rule: CLAUDE.md "never copy ... into this public repo".

- **A (recommended): rewrite the branch.** Rebuild `build/gc-ictrack` as one squashed commit of the cleaned tree on top
  of main, force-push it, run the full gate on it (~30 min), then open the PR. The figure leaves the branch and never
  reaches main; GitHub may keep the old commit reachable by its sha for a while.
- **B: fix forward only.** Push the redaction on top, open the PR and squash-merge it. Main never holds the figure, but
  the PR's commit list shows the old commit permanently.

Why A: B leaves the figure on a permanent public page; A costs one gate run.
