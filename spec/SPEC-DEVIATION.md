# How a departure from the spec is handled — the guideline

> The 30-second version is `.claude/rules/kit/spec-adherence.md`; this file is the detail, the worked
> examples and the wording.
>
> `spec/` is the single source of truth for what this project does. Code follows it. Any change to
> what the system does goes into the spec first, or into the spec in the same pull request. A code
> change that contradicts the spec and leaves the spec standing is a defect — whichever of the two
> turns out to be right.

## 1. Why this guideline exists

Most things that look like "deviations" are not judgement calls at all: a work item or the spec
asserted a fact about the codebase that was false, and the builder patched around it instead of
correcting the record. Treating that as a deviation invites judgement where none is needed, and it
buries the deviations that really are judgement calls — a dropped scope, a relaxed definition of
done — so they arrive looking exactly like the safe ones. This guideline exists to tell the two
apart, every time, the same way.

## 2. The three classes

### Class 1 — card defect (not a deviation at all)

**Trigger.** The work item or the spec makes a factual claim about the codebase — a function, a
flag, a file, a heading, a dependency, a count — and the claim is false.

**What you do.** Build to the spec's stated intent. Correct the work item in the same pull request.
Name the correction in the PR's Spec-deviation block. Nothing is escalated; nothing waits.

**Worked examples.** (1) A work item says a helper function `computeRefundBatch()` already exists
to build on; it does not exist anywhere in the codebase — write it as part of this item, note the
correction, keep going. (2) A work item cites a config flag `ENABLE_RETRY_QUEUE` that no config file
declares — treat the flag as new, add it, correct the item, move on.

**The one exit.** If the false claim means the intent cannot be met at all — the state the item
needs is not representable, the field the item depends on cannot exist under the schema — it is
class 3, not class 1: stop and escalate rather than inventing a near-enough state.

### Class 2 — minor

**Trigger, both halves required.** (1) the change alters how the system does something, not what a
user or admin sees and not what is stored; **and** (2) it falls inside something the spec has
already marked as configuration, a validation rule, or a per-type exception.

**Worked examples.** (1) A validation check's numeric tolerance, where the spec's own section marks
that number as "the author's choice" — tightening or loosening it is class 2. (2) Which of two
equivalent fields an extractor reads for one document type, where the spec lists extraction mapping
as configuration — swapping the field it reads is class 2. Anything not inside such a spec-marked
list is not class 2, however small it looks.

**Process.** Section 3 below, in full, every time.

### Class 3 — major (stop, and go to the owner before writing code)

**Any ONE of these triggers, no weighing:** touches a decision row in `spec/decisions/`; changes
what a user or an admin sees; adds, removes or reorders an external source or dependency, or changes
which one wins; changes a number the owner stated; changes the schema or an enum; repairs production
data; cannot be cleanly reversed; drops or narrows a work item's scope; relaxes a definition of done;
adds a paid call; or is the second deviation on the same requirement.

## 3. The class-2 procedure, step by step

### 3.1 Prove it on two differing real samples of every type it touches

Not two runs of one sample, and not two samples of one type when the change touches two types.
"Differing" means a different origin (a different source, format version or provider) where the data
allows. At least one of the two must be live or recent — a rule proven only on old data is proven
against a shape that may no longer occur. Which types a change "touches" is read off the spec's own
per-type list, never guessed.

### 3.2 Say "unproven" out loud where the population is thin

A type with fewer than two real samples is written as:

```
unproven for type <X> — <N> sample(s) available on <date>; this change does not claim it.
```

and the change does not claim that type. It is never skipped silently.

### 3.3 What the report row looks like

One row per type touched, in the PR body, each cell naming an identity, never a count:

```
| type | sample A (origin, date) | sample B (origin, date) | result |
|---|---|---|---|
| type X | <name> (<origin>, <date>) | <name> (<origin>, <date>) | pass / pass |
| type Y | <name> (<origin>, <date>) | unproven for type Y — 1 sample on <date>; this change does not claim it | |
```

### 3.4 A builder never labels its own deviation

The class and the two-per-type evidence are confirmed before merge by an independent reviewer (a
fresh context, a different model where one is available) — not the builder, because the builder is
the one party who has already decided the deviation is fine.

### 3.5 Write the exception into the spec, same PR

The entry goes into the spec section that defines the configuration, validation rule or per-type
exception it touches, with the sample identities and the date. A deviation that lives only in a PR
body is a deviation the next reader of the spec will hit again from scratch.

## 4. The second time is always major

A second deviation on the same requirement is class 3, automatically. If the same requirement has
now been departed from twice, the requirement is wrong, not the samples. Fixing it is a spec change,
which is the owner's — no amount of care in a third work-around substitutes for it. This composes
with the standing rule that a second occurrence of a failure class earns an independent review rather
than a third guess: change who is aiming before firing again.

## 5. Findings sync — the registry and the spec never stand against each other

Every finding registered under `knowledge/findings/<slug>.json` carries `spec_ref`: the spec
section(s) the class touches. A finding that contradicts the spec triggers a same-PR correction of
one of the two, by the class table above — either the finding is right and the spec is wrong, or the
spec is right and the finding describes a defect in the code. What may not happen is both standing,
because then the next reader picks whichever they found first. `status` stays `unguarded` until a
named detection check or gate actually covers the class.

## 6. How a class-3 request to the owner is written

- **First line names the trigger.** For example: "class 3: changes an owner-stated number (decision
  OD-4)." The owner should not have to derive the class from the prose.
- **Then, in order:** purpose (what this achieves), place (where in the system), data (the real
  numbers or samples behind it), the impact of doing nothing, and the fork — the real options, with a
  recommendation and a `Spec basis:` line naming the spec section(s) the recommendation rests on.

## 7. Enforcement

1. `.claude/rules/kit/spec-adherence.md`, always loaded, which points to this guideline.
2. A required Spec-deviation block in the PR template — class none/1/2/3, spec section, sample
   identities for class 2, "card corrected: y/n".
3. A CI check that a PR's body carries the Spec-deviation block.
4. `spec_ref` on every finding, checked against the spec's real section list.
