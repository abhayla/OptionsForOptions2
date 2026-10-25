# Scope: global (this project)

# Spec first: questions and recommendations rest on the spec

version: "2.0.0" (lean: OD-117)

The spec is `spec/`; decisions are rows in `spec/decisions/`. With no spec yet, say the answer rests on best practice.

- **R1 Read by the subject's terms.** Before any question, recommendation or plan, read `views/spec-digest.md`, then
  grep the spec for every key term (fields, states, codes, labels). Before a new spec line run
  `python tools/spec_similar.py . "<text>"`; extend or cite a match. Counter: questions the spec already answered.
- **R2 Every question and recommendation carries a `Spec basis:` line** naming sections and decisions, inside the
  question text. Settled: build to it. Departs: label `SPEC CHANGE`, quote the text. Silent:
  `Spec basis: none: the spec says nothing about <subject> (searched: <terms>)`. Counter: questions refused by the
  `spec_basis_gate` hook.
- **R3 Real cases in the options:** real rows, names, numbers, dates, or "no real case in N days".
- **R3b Action design:** before recommending how a user action behaves (delete, undo, retry), list each reason the
  actor takes it and whether each option serves it.
- **R4 A decision row only for a decision about what the product does,** written with its section text before or
  with the code, the same turn. Process, scope and tooling answers go in the handover. The `answer_writeback_guard`
  hook blocks a turn once when an answer got no row, unless it ends `No spec change: <reason>`. Counter: product
  answers with no decision row.
- **R5 "Check the spec" from the owner is a miss:** record a finding, re-read per R1, return with a changed
  recommendation.
- **R6 Measured findings** that change what we know go into the spec section they bear on and, for a defect class,
  `knowledge/findings/`, the same turn. Counter: findings in chat only.

## Build order

Order: `layer`, `depends_on`, `risk`, `skeleton`; no scoring. Start if `build_order.py . --may-start REQ-###` exits 0
(or `order_override`). Re-read layers per milestone and decision change.
