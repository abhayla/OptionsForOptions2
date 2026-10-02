# Builder brief: W-055 every screen works at phone and desktop widths

Core: the route list is read from the router itself, so every route (today's and any added later) is checked at 390 px
and 1280 px without editing the test.
Proof (step 1): run the check on the merged W-054 shell: every route passes at both widths with a screenshot each; then
add a deliberately over-wide element to one route in a throwaway change and show the check fails naming that route and
width (record the failing output, then remove the change).

Budget: 30 min wall-clock, 50 tool calls. At budget, stop and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`).
Tier: B.

## Spec basis
- REQ-004 AC-1: "Every screen works at desktop and phone widths from the first release."
- ADR-049 (layout look); ADR-030 (no feature screens).

## Copy from (legacy-reuse.md M7)
- The merged `frontend/playwright.config.js` already has the 390x844 and 1280x800 projects (adapted from
  algochanakya@bf9faf7); reuse them. No new legacy copy needed.

## What works means (test definition, fail closed)
- For each route from `frontend/src/router/nav.js` plus `/settings/*`, `/health-status` and the not-found page: no
  horizontal page scroll (`document.documentElement.scrollWidth <= window.innerWidth`), the primary navigation (or its
  mobile toggle) is visible and usable, and the page title is visible. Store a screenshot per route and width under
  `frontend/test-results/responsive/` and upload it in the CI frontend job.
- The test must fail if `nav.js` gains a route the check did not visit.

## Also in this item (W-054 review follow-ups)
- `frontend/eslint.config.js`: anchor the dhan pattern to the real hosts (`dhan\.co`, `api\.dhan`) so ordinary words that
  contain the letters dhan are not flagged; extend `tests/vendor-host-lint.test.js` with a passing case for a word containing dhan.
- `.github/workflows/app-tests.yml` frontend job: Node version `20.19` or newer explicitly (vite 7 needs it).
- `AppHeader.vue` account menu: close on Escape and on a click outside; `aria-controls`/`aria-expanded` set; a Playwright
  test for both closes.

## Standing items (run-discipline B4)
- Fail closed: a route that cannot be visited fails the test; an unknown route list is an error.
- Kit CI stays green; nothing under `tests/` changes.

## Rules
- Branch from origin/main (W-054 merged). Do not edit kit files. Never write `evidence/`. No secrets.
- Run lint, vitest and the Playwright responsive spec locally (stub API is fine for layout); full run is in CI.
- Commit; do not push. Report worktree path, branch, commits.
