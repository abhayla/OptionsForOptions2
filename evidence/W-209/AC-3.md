---
work_item: W-209
requirement: REQ-162
ac: AC-3
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "b89775c967a5"
commands: "cd frontend && npx vitest run tests/adjustment-opportunities.test.js; read AdjustmentOpportunitiesPage.vue, frontend/src/lib/adjustDrawer.js compareUrl, frontend/src/router/nav.js:32, frontend/src/router/routes.js:26"
---
A group with an open record shows 'Compare approaches'; compareUrl builds /strategy/builder?adjust=<id>&pick=...&opp=<open ids>, carrying only open records with regex-filtered ids. The server sends 'No adjustment opportunities' (suggestion_inbox_empty) and the page shows no table then. Route and nav entry are wired; vitest covers AC-3 incl. the empty inbox.
