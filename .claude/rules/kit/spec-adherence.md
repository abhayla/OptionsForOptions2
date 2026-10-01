---
paths:
  - "spec/**"
  - "docs/spec/**"
---
# Scope: global (this project)

# Spec adherence: the spec is the single source of truth; every departure is classified, proven and reviewed

version: "1.1.0" (generalized for the project kit)

See `spec/SPEC-DEVIATION.md` for worked examples and the class-3 request format.

Why: code that quietly departs from the spec leaves two truths, and the next reader builds on the wrong one.

`spec/` is the single source of truth for what this project does; owner/architecture decisions live in
`spec/decisions/`. **Code follows the spec.** Any change to what the system does goes into the spec first, or in the
SAME pull request — a code change that contradicts the spec while leaving the spec standing is a defect, whichever
of the two is right.

## The three classes

| If the work item, brief or spec... | Class | What you do |
|---|---|---|
| makes a FALSE factual claim about the codebase (a function, flag, file, heading, dependency or count that doesn't exist) | **1: card defect** | Build to the stated INTENT, correct the work item in the SAME PR, name it in the Spec-deviation block. Not a deviation. If intent can't be met at all: class 3. |
| changes HOW without changing what a user sees or what's stored, AND falls inside what the spec marks as configuration, a validation rule or a per-type exception | **2: minor** | Allowed ONLY through the six-step process below. |
| matches ANY class-3 trigger below | **3: major** | STOP. Go to the owner before writing code. |

**Class 2 is only** what the spec itself marks as configuration, a validation rule or a per-type exception (a
tolerance the spec leaves to the author, a normaliser, which field an extractor reads); otherwise it is not class 2.

**Class-3 triggers, ANY ONE:** touches a `spec/decisions/` row; changes what a user/admin sees; adds, removes or
reorders an external source/dependency or changes which wins; changes an owner-stated number, the schema or an enum;
repairs production data; can't be cleanly reversed; drops/narrows scope; relaxes a definition of done; adds a paid
call; or is the SECOND deviation on the same requirement.

## The class-2 process: six MUSTs

1. MUST be proven on at least **two differing real samples of every type touched** (different origin where data
   allows; at least one live or recent).
2. MUST write a type with fewer than two real samples as **`unproven for type <X>`**, and MUST NOT claim that type.
3. MUST NOT be labelled by its own builder: an **independent reviewer** (fresh context, a different model where
   available) confirms the class and the two-per-type evidence before merge.
4. MUST be written into the spec in the SAME PR (the section defining the configuration/exception), with samples and
   date.
5. MUST treat a **second deviation on the same requirement as class 3**; twice means the requirement is wrong.
6. MUST carry the class, spec section, samples and corrected claim in the PR's **Spec-deviation** block.

## The Spec-deviation block

Every PR body carries it, whether or not anything departs:

```
Spec deviation
Class: none | 1 | 2 | 3
Spec section: spec/<file>#<section>
Detail: <the corrected claim, or the samples and reviewer, or the owner decision id>
```

`Class: none` is a valid answer; a missing block is not.

## Briefs and findings

- Every builder brief and work item cites the spec section it implements (`Spec basis:` line); a brief that
  contradicts the spec is the author's defect, not the builder's.
- Every finding in `knowledge/findings/` carries `spec_ref`; a finding that CONTRADICTS the spec triggers a same-PR
  correction of one of the two, by the class table — the spec and the registry never stand against each other.

## CRITICAL RULES

- MUST treat `spec/` as the single source of truth, changed first or in the same PR as departing code.
- MUST classify every departure as 1, 2 or 3 before writing code and state it in the Spec-deviation block
  (`Class: none` is valid, silence is not); a second deviation on one requirement is class 3.
- MUST build to the spec's INTENT on a false factual claim, correcting the work item in the same PR.
- MUST NOT ship class 2 without the six-step process (two real samples per type, independent reviewer, spec written
  same PR); MUST NOT narrow scope, relax a definition of done, or repair production data as "minor".
- MUST cite the spec section in every builder brief, and carry `spec_ref` on every finding.
