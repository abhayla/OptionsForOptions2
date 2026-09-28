---
paths:
  - "views/**"
  - "status/**"
  - "board/**"
  - "dashboard/**"
---
# Scope: path (status pages: `views/` and any status, board or dashboard folder)

# A status artifact other people read is generated, role-complete, and cheap to update

version: "1.0.0" (generalized for the project kit)

Why: a hand-typed status page drifted three items from its source and was believed; a renderer that patched its own
output broke on the first layout change; and a page that answered only "what is the status?" failed most readers.

Applies to any page or document that reports the state of work to people other than the session that wrote it (a
project board, a release status page, a readiness page). Not to a session note, a ledger or a log.

## R1: Generated from data files, never hand-edited

One command renders the whole artifact from data on disk. The renderer MUST NOT read the published artifact to update
it; a page nobody can regenerate becomes a page nobody updates.

## R2: Every number is derived, or labelled unknown

Derive counts from the source that owns them, per record (never by matching a word across a document, since a row's
own prose can contain the word). Where a value cannot be computed, the row says `unverified` or `unmeasured` and names
the command that would measure it. Never a plausible default.

## R3: One block per role, each asserted by a test

Before building, list the roles who will open it and the ONE question each brings: owner (what needs me?), product
(what does a user see?), architect (what depends on what?), implementer (what do I pick up?), delivery (what
changed?), deployment (what ships, how do I undo it?), environments (what runs where?), QA (what ran, what never
ran?), domain owner (are the numbers right?). Every block has a test assertion, so a refactor that drops one fails
the suite. Bar: every role rates it above 9/10.

## R4: Say what has NEVER run, not only what is red

A gate that never ran reads as absent, or as fine to a skimming reader. Name it, in those words.

## R5: Update when a stage crosses, not when a commit lands

Update for a verdict change, a deploy that changes what an environment serves, a decision landing or newly waiting,
a gate changing state, or a change in what a user sees. Not for ordinary merges, docs commits, CI re-runs, or reviews
that found nothing.

## R6: Freshness is stated and read from the clock

The artifact carries when it was last updated and, where different, when each number was measured, read from the
system clock in the same step, never typed from memory.

## R7: Update in place; the link is the address

Republish to the same location, so every shared link stays current.

## R8: Cost check before the design is fixed

State two numbers when proposing the approach: cost to build once, cost per future update. Anything read repeatedly
should be generated; let the owner pick.

## CRITICAL RULES

- MUST render from data files with one command; MUST NOT hand-edit the published artifact or read it back to update it.
- MUST derive every number, or label it unknown with the command that would measure it.
- MUST give every reading role its own block, with a test asserting the block exists.
- MUST name what has never run, in those words.
- MUST update on stage changes only, stamp from the clock, and republish to the same location.
- MUST state build-once and update-forever cost before the approach is fixed.
