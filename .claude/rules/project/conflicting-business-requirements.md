---
paths:
  - "spec/**"
  - "docs/process/**"
---
# Scope: path-scoped (spec, docs/process)

# Conflicting business requirements: stop and ask, never auto-decide

Owner, 2026-10-19, verbatim: "If you think if I have given any conflicting business requirement, or there are my
two different requirements conflict with each other, obviously you should come back and ask me. There should be a
rule if not already there. Okay, never take auto decision when there is a conflicting business requirement given by
me."

- Applies when two business rules clash: ADR rows, REQ acceptance criteria, owner answers, or a design note against a
  REQ.
- Stop that item only (other ready items continue). Ask ONE question quoting both texts with their ids, the real case
  where they clash, and a recommendation. Business question, so it carries a `Business call:` line and a
  `Spec basis:` line.
- Owner away: write the question to the dated owner-questions file with the recommendation; do not decide.
- Never resolve it by technical judgement, a design role, or "the newer one wins".
- The answer is written as a decision row in the spec the same turn it is given (spec-first R4).
