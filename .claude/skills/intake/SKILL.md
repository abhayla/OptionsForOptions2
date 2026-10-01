---
name: intake
description: >
  Use this skill to turn a new project idea into the owner's decisions and a working session
  entry point. Use it whenever someone says a new project idea, asks to start intake, or wants
  their idea turned into a spec — not for an already-decided project or a single follow-up
  question on an existing one.
---

# Intake

Turns the owner's idea into recorded decisions (`spec/decisions/ADR-###.md`), a project-owned
`CLAUDE.md` and `docs/HANDOVER.md`, and the first requirements — in that order, never building
anything before the decision that shapes it exists.

## Steps

1. **Take the idea in the owner's words.** Write down what they said before asking anything;
   do not paraphrase it into a decision yet.
2. **One question per turn, asked with the interactive question tool** (never buried in a report,
   never a stop that only says the owner is blocking you), until every choice a real input could
   not settle on its own has an answer. Each question:
   - opens with `*Sync-check:*`;
   - carries a `Spec basis:` line naming what already constrains the answer (an existing
     decision, a stated constraint), or, when the spec is silent on it,
     `Spec basis: none: the spec says nothing about <subject> (searched: <terms>)`;
   - offers a recommended option first, with a one-line reason;
   - shows real costs or cases inside the question text (a number, a file, a concrete example) —
     or, when there is none yet, says so plainly ("no real case in N days") rather than inventing
     a hypothetical.
3. **Record the answer as the next decision, in the same turn.** Write
   `spec/decisions/ADR-###.md` (numbered after the last one) with frontmatter valid against
   `factory/schemas/decision.schema.json`: `id`, `date`, `title`, `decision`, `status: accepted`,
   `options` (what was offered), `consequences` (what the choice implies for later work), and
   `source` quoting the owner's actual answer. When the answer carries a risk (something it
   leaves unchecked, unreviewed, or unproven), write that risk as a consequence naming the
   mechanism that must exist before it stops being a risk (a check, a review step, a gate) —
   never leave it unsaid.
4. **Stop asking what real input can already measure.** The moment a question can instead be
   answered by running something on real data (a real file, a real page, a real account), stop
   the question and hand it to the project's core proof instead: name the mechanism
   (`Core: <mechanism>`) and the smallest real run that would show it works
   (`Proof: <the run>`), and do that run before asking the owner anything the run could answer.
5. **Fill `CLAUDE.md` and `docs/HANDOVER.md`** from the decisions recorded so far: the project's
   purpose, its hard rules (including the ones the decisions in step 3 created), and a first
   `NEXT` step naming the core proof from step 4.
6. **Then write requirements** (`spec/requirements/REQ-###.md`) from the recorded decisions —
   never before they exist, and never inventing a decision the owner has not actually made.

## What this skill never does

- Never invents a decision to avoid asking a question — an unanswered fork stays a question.
- Never asks about something a real input, a file, or a command could already answer.
- Never leaves a risky answer's risk unrecorded — every risk becomes a named consequence.
- Never writes requirements before the decisions they rest on exist as `ADR-###.md` files.
