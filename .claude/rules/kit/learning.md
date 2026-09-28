# Scope: global (this project)

# Learning: every proven finding is a class in the registry, and every repeat becomes a mechanism

version: "1.0.0" (generalized for the project kit)

Why: lessons written as prose were re-derived every session, and the same failure classes repeated because nothing
checked for them.

The project's registry is `knowledge/findings/`: one JSON file per class (format in its `README.md`).

## F. Findings registry

- **F1 One file per finding, never a shared list.** Any index/table is GENERATED from the files by a script, never
  hand-edited, staleness checked in CI — lets parallel PRs each add a finding without conflicting.
- **F2 Written as a CLASS, not an instance.** The `class` field states the mechanism generically ("any queue whose
  capacity is smaller than its starved candidates"); the instance, identities and numbers go in `first_seen`. Name
  a wider shape where one exists ("a check that joins against a population can never see a missing member").
- **F3 Proven before it is written**: carries the measurement that established it (query+counts, log line, file:line)
  and, for a proposed fix/check, evidence it DISCRIMINATES ("of 20 live rows it flags exactly the 2 bad ones"). An
  unproven observation is a question, not a finding.
- **F4 Registered in the SAME turn it is proven**, alongside (never instead of) the issue/PR, with `spec_ref` naming
  the spec sections it touches (see `spec-adherence.md`).
- **F5 Read BEFORE answering a logical question** (why the system behaves a certain way, is a defect new, what a
  check covers, how to design a mechanism). After registering, grep the GENERATED index for the new text — a fixed-
  column aggregate can drop a field.
- **F6 Honest status.** `detection.status` is `unguarded` until a named check covers the class; a fix without
  detection says so. A check finding nothing is still recorded, including what it does NOT cover; an undeliverable
  number is written as unmeasured, never a default.

## L. Learn or block

- **L1 Every failure/incident/owner correction gets a registry entry the same turn** (new class) or an occurrence
  added to the existing one (known class); never only prose.
- **L2 Second occurrence of a class = a mechanism, same turn**: a gate/test/lint/CI check with a red-then-green
  self-test, planned as a work item. "Fixed" means the mechanism landed and the entry's detection is `guarded`.
- **L3 Root cause beats instance fix:** sweep equivalent places in this repo when a class is found in one, and
  record the sweep in the entry.

## R. Repeated failure: change who aims

- **R1 Second red of the same class** (same root cause, not symptom) after one fix round, in CI, staging or a gate:
  dispatch an INDEPENDENT reviewer the same turn, no owner question — fresh context, a different model or instance,
  never the builder/fixer. Give it the class, both rounds' diffs, evidence lines and "what did both rounds miss?".
  Output: findings and an approach, no code.
- **R2** Accept/reject each finding with a line of evidence, write the third-round brief AROUND them; its PR body
  cites the review; the owner is told afterwards, as information.
- **R3 Third red after the reviewed round is a stop:** escalate with the review, both briefs and a recommendation.

## D. Detection-gap RCA (high-risk reviews and production defects)

Between a fix wave and the next review of high-risk work (deletes, deploys, auth, payments, secrets, migrations,
hooks), and for every production defect, record per finding: (a) instance fixed; (b) class mechanism shipped;
(c) which check should've caught it and why it didn't; (d) a detection upgrade shipped BEFORE the next review
(scheduled audit, monitor or CI test). Next review requires (a)-(d) done. Success: recurrences of a fixed class = 0
and findings a listed check should've caught = 0; either non-zero means RCA the RCA first.

## CRITICAL RULES

- MUST follow F: one JSON file per finding in `knowledge/findings/`, written as a class with evidence and
  `spec_ref`, registered the same turn it is proven (never an unproven observation), read before answering a
  why/design/is-this-new question, and marked `unguarded` until a named check covers it.
- MUST follow L: give every failure or correction a registry entry the same turn, and turn a second occurrence of a
  class into a mechanism (red-then-green test) the same turn.
- MUST follow R: dispatch an independent reviewer on the second red of a class, and escalate a third red to the owner.
- MUST follow D: ship a detection upgrade for every high-risk review finding and production defect before the next
  review.
