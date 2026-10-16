---
paths:
  - ".github/**"
---
# Scope: path-scoped (GitHub workflows)

# GitHub workflows (REQ-075 AC-6, AC-7; ADR-093)

- Pin every action to a full commit SHA with the version in a comment (`uses: actions/checkout@<sha> # v4.2.2`).
- Declare `permissions:` at least privilege (`contents: read` unless a job needs more), `timeout-minutes` per job, and
  `concurrency: {group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true}` for pull-request runs.
- Path filters: a docs/spec/knowledge/evidence-only change starts no app job; frontend-only starts no API job; a change
  under `backend/ofo/**` starts both (the domain feeds both layers).
- Cache pip, npm and Playwright browsers; never re-download per job.
- `.github/workflows/ci.yml` is kit-owned: never edit it here; file a `harvest` issue in the kit repo instead.
- Run the workflow's own checks locally before pushing; one push per batch, not one per small fix.
