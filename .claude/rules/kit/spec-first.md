# Scope: global (this project)

# Spec first: every question and recommendation is built on the spec, and every owner answer goes back into it

version: "1.4.0" (generalized for the project kit)

Why: questions went out after reading one section while another constrained the subject, and answers kept only in
chat were lost.

The spec is `spec/`; decisions are rows in `spec/decisions/`. If the project has no spec yet, say so, and say the
recommendation rests on best practice, not on a requirement.

## R1: Read by the subject's terms, not by the section title

Before any question, recommendation or plan, read `views/spec-digest.md` (one line per decision, requirement and
section), then grep the spec for every KEY TERM of the subject (field names, states, codes, labels), plus decision
rows and label definitions. Read every hit that could constrain the answer.
Before writing any new spec line, run `python tools/spec_similar.py . "<text>"`: extend
or cite a match, never restate it (CI's `spec_dupes.py` blocks a same-kind match >= 0.40 without a real
`distinct_from` difference).

## R2: Every question and recommendation carries a Spec basis

Write a `Spec basis:` line naming each section and decision it rests on, quoted where short, INSIDE the question
text (owners often see only the question box). Settled by the spec: build to it, don't ask. Partly settled: state
the settled part, ask only the gap. Departs from the spec: label it `SPEC CHANGE`, quote the text it changes, say
why. Spec silent: `Spec basis: none: the spec says nothing about <subject> (searched: <terms>)`, labelled best
practice, and the answer becomes a new decision row (R4). Every RECOMMENDED option is checked against the basis
first; one contradicting a decision row is dropped or labelled `SPEC CHANGE`. Enforced: the `spec_basis_gate`
hook refuses a question whose basis cites no real id.

## R3: Real cases in the options

Each option shows real rows (names, numbers, dates) or says "no real case in N days", INSIDE the question text.

## R3b: Design an action from its actor's intent

Before recommending how a user action behaves (delete, clear, hide, undo, override, accept, retry), write a small
table: each reason the actor takes the action, what they want then, whether each option gives it. Recommend what
serves the real reasons, not what the mechanism makes easiest.

## R4: Every owner answer goes back into the spec, same change or before the code

A decision, clarification, correction or "I meant X" about WHAT the system does is written into the spec as a
numbered decision row plus the section text, before or with the code — never only an issue, PR body, memory or chat.
Each answer is written in the SAME turn it is given; enforced by the `answer_writeback_guard` hook (or end with
`No spec change: <reason>`). If the spec said it and was misread, fix its wording so it is clear.

## R5: The owner answering "check the spec" is a miss

It means R1 was skipped. Record it as a finding (see `learning.md`), re-read per R1, and return with a new
recommendation stating what changed.

## R6: Research findings go into the spec and the findings registry, same turn

A finding is anything measured on real data that changes what we know.
In the SAME turn it is proven, record it in the spec section it bears on (real values,
source, date; "open for owner decision" when it implies a rule change — a finding never changes a decision by
itself), and in `knowledge/findings/` when it's a defect class.

## Build order

Order: `layer`, `depends_on`, `risk`, `skeleton`; no scoring. Start if `build_order.py . --may-start REQ-###`
exits 0 (or `order_override`). Re-run it; re-read layers per milestone and decision change.

## CRITICAL RULES

- MUST grep the spec by every key term of the subject, plus decision rows and label definitions, before any owner
  question or recommendation.
- MUST put a `Spec basis:` line inside every owner question.
- MUST NOT ask what the spec decides; MUST label any departure `SPEC CHANGE` with the quoted text.
- MUST write every owner answer or clarification into the spec before or with the code, same turn.
- MUST, before recommending how a user action behaves, list why the actor takes it (R3b).
- MUST record every proven research finding in the spec and, if a defect class, in `knowledge/findings/`, same turn.
