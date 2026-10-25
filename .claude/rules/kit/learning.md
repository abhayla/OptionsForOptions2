---
paths:
  - "knowledge/**"
---
# Scope: global (this project)

# Learning: every proven finding is a class in the registry, and every repeat becomes a mechanism

version: "2.0.0" (lean: OD-117)

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
  number is written as unmeasured, never a default. Counter: findings whose `detection.status` is `guarded`.

## L. Learn or block

- **L1 Every failure/incident/owner correction gets a registry entry the same turn** (new class) or an occurrence
  added to the existing one (known class); never only prose.
- **L2 Second occurrence of a class = a mechanism, same turn**: a gate/test/lint/CI check with a red-then-green
  self-test, planned as a work item. "Fixed" means the mechanism landed and the entry's detection is `guarded`.
- **L3 Root cause beats instance fix:** sweep equivalent places in this repo when a class is found in one, and
  record the sweep in the entry. Counter: repeat occurrences of a registered class.

## R. Repeated failure: change the aim, not the number of reviewers

- **R1 Second red of the same class** (same root cause, not symptom) is round 2, the last one (run-discipline B1):
  write its brief around the class and both diffs ("what did round 1 miss?"), never just the symptom. There is no
  automatic independent review. Counter: items reaching round 2.
- **R2 Red after round 2 stops the item:** park it, or ship it with the findings listed, and tell the owner with the
  evidence and a recommendation; the owner may ask for an independent review. Counter: parked items.
- **R3 A process change shows the current rule quoted beside the proposed one** (finding
  `process-change-narrows-safety-rule`), gets one diff review like any change, and goes to the owner for approval.

- **R4 A repeated orchestrator miss gets a hook, not a memory note.** Three lessons for such a hook: check only the
  brief the dispatch names (never a file the prompt merely mentions); treat a crash of the checked tool as
  fail-open (allow); expect interpreter-flag and wrapper spellings (`python -X utf8 ...`, `timeout 900 python ...`).

## D. Detection-gap RCA (Tier A findings and production defects)

Between a fix and the next review of Tier A work (deploys, money and order maths, migrations, auth and secrets), and
for every production defect, record per finding: (a) instance fixed; (b) class mechanism shipped;
(c) which check should've caught it and why it didn't; (d) a detection upgrade shipped BEFORE the next review
(scheduled audit, monitor or CI test). Next review requires (a)-(d) done. Success: recurrences of a fixed class = 0
and findings a listed check should've caught = 0; either non-zero means RCA the RCA first.

## CRITICAL RULES

- MUST follow F: one JSON file per finding in `knowledge/findings/`, written as a class with evidence and
  `spec_ref`, registered the same turn it is proven (never an unproven observation), read before answering a
  why/design/is-this-new question, and marked `unguarded` until a named check covers it.
- MUST follow L: give every failure or correction a registry entry the same turn, and turn a second occurrence of a
  class into a mechanism (red-then-green test) the same turn.
- MUST follow R: aim round 2 at the class, stop after it (park or ship with findings listed), and take a process
  change to the owner with the current rule quoted beside the new one.
- MUST follow D: ship a detection upgrade for every Tier A review finding and production defect before the next
  review.
