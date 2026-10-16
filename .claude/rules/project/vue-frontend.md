---
paths:
  - "frontend/src/**"
---
# Scope: path-scoped (frontend source)

# Vue frontend (REQ-075, ADR-093; Vue style guide priority A/B)

- `<script setup>` with the Composition API; props declared as objects with types; `:key` on every `v-for`; no `v-html`.
- No P&L or money arithmetic in the browser: amounts arrive as strings from the API and are shown as given
  (`Number()` only to draw a chart).
- The browser talks only to same-origin `/api`; never a broker or vendor host (ESLint rule, ADR-012).
- API paths, colours and formatting live in one shared place (an api module, CSS variables / Tailwind theme,
  `lib/displayFormat.js`), not repeated per component.
- Pinia: setup stores, one per domain, when the first store is needed.
- ESLint runs with `--max-warnings 0`; the edit hook prints findings for the file just edited - fix them before moving on.
