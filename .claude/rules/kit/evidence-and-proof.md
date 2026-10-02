# Scope: global (this project)

# Evidence and proof: prove the core first, prove every claim, fix the class, answer honestly

version: "1.0.0" (generalized for the project kit)

Why: scaffolding built around an unproven core is thrown away, and a "done" nobody checked gets relayed as fact.

## E1: Understand WHAT is asked before doing it (95% gate)

Do not proceed below 95% confidence about WHAT is asked (the gate is on what, not how), nor past a choice the owner
would plausibly want to make. ASK it with the interactive question tool, one question per call, recommended option
first with its reason and Spec basis inside. Never bury a question in a report or stop on "waiting on you" without
asking it: the owner can only answer what was asked. Owner away: run-discipline B2. Never ask what the spec, repo or
a command can answer.

## E2: Honest answers

Every answer is a straight assessment: bad named as bad with its cost, good named as good only when true. Plain
words, a one-line explainer per technical term, a concrete example per important claim.

## E3: Prove the core first

The CORE of new work is the one mechanism everything else depends on (the extractor on a real file, the external
endpoint returning what we assume). Every plan, work
item and brief opens with `Core: <mechanism>` / `Proof: <smallest real run that shows it works>`. Step 1 IS the core
proof: the thinnest end-to-end run on REAL input (never a fixture typed from memory), output read back and recorded.
Nothing is built around it first. A core that fails or can't be proven STOPS the build: report the failure with its
output and re-plan. If the core can't be named, the work isn't understood yet.

## E4: Evidence before claims

A turn that claims done / pass / green / verified / merged / deployed ends with a table:

```
| Claim | Evidence (tool call this turn) |
```

One row per claim; Evidence is the exact command run THIS turn and its result line. Unverified: say so in the row. A
failed step is reported as failed WITH its output. Another agent's report is a claim, not evidence — re-run the gate
or read the artifact before relaying it. Every builder brief asks for this table.

## E5: Defect-fix contract: fix the class, prove on real data

Every defect is a sample of a class. The brief, PR body and finding carry six items, in order: (1) **RCA**, the
mechanism in one sentence; (2) **Class**, the population as a data filter (types, states, sources), size before and
after; (3) **failing test first**, on the real function; (4) **fix at class level** — bad rows repaired by a
re-runnable, source-backed tool, never by hand; (5) **retest plus ONE real-data proof** before merge (a real
fixture, the real job's output naming the counter that moved, or the script against a staging copy); (6)
**detection upgrade**, or an explicit `No detection change: <reason>`.

Fix briefs carry `Class:`/`Proof:` lines; a review verdicts "covers the class: yes/no"; a parser/extractor brief
carries a real fixture from the live source.

## CRITICAL RULES

- MUST follow E1: ask with the question tool, one per call; never bury a question or stop without asking it.
- MUST follow E2: answer honestly, costs named, a concrete example per important claim.
- MUST follow E3: open new work with `Core:`/`Proof:` lines, step 1 the core proof on real input; a failing core
  stops the build.
- MUST follow E4: end every done/pass claim with an evidence table of commands run this turn (unverified said as
  such), and re-check a worker's report before relaying it as fact.
- MUST follow E5: carry RCA, Class, failing test, class-level fix, real-data proof and detection change on every
  defect fix.
