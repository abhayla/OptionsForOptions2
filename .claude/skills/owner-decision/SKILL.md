---
name: owner-decision
description: The six steps from "the owner must decide something" to "the decision row is written, the lane told, committed and queued to push". Use when about to ask the owner a product question, when an owner answer arrives, or when asked to record a decision (ADR point). Holds the search command, the question shape, the row shape and a script that writes the row.
when_to_use: A product question for the owner (what the product shows or does); an owner answer in chat or the question tool; "record this decision"; "add a point to ADR-330".
---

# Owner decision: ask once, record the same turn

Only what the product shows or does is the owner's to decide. Technical calls, process and scope are yours; they go in
the handover, not in a decision row (spec-first R4). If the owner is away (22:00 to 08:00 IST, hook
`question_night_guard`), do not ask: write the question with your recommendation to `docs/process/owner-questions-<date>.md`
and decide the spec-conformant choice meanwhile.

## 1. Search before asking (one command)
`python .claude/skills/owner-decision/spec_search.py "<the subject's own words>"` prints the best lines in `spec/` and
in the decisions index (`docs/process/owner-decisions-by-subject-*.md`) with file and line. Try two or three word sets
(the screen's label, the field name, the state). If a line answers the question, cite it and do not ask (finding
`owner-question-asked-without-the-requirement-that-answered-it`). For a NEW spec sentence also run
`python tools/spec_similar.py . "<text>"` and extend a match. Zero hits proves only that the words failed.

## 2. Ask ONE question (question tool, alone in the message)
Fill in:
```
<The question, one sentence, in the owner's words.>
Spec basis: <ADR-nnn (point), REQ-nnn, section>   [SPEC CHANGE: quote the text it departs from]
   or: none: the spec says nothing about <subject> (searched: <the words you used>)
Real case: <date, time, row, screen, number>   (or: no real case in N days)
Why he does this: <reason 1> | <reason 2>        (each reason, and which option serves it)
Options (recommended first): A <recommended: what he sees, in the exact sentence> / B <...> / C <...>
```
The hook `spec_basis_gate` refuses a question with no `Spec basis:` or an id that does not exist.

## 3. Write the decision row the same turn
Never leave an answer without a row (hook `answer_writeback_guard`; an answer with no row is lost at restart). The row
goes into the ADR the coordinator names (ADR-330 for the 25 to 27 Nov screen test), as the next number after the last
point; the coordinator hands out numbers, a lane never picks one. Shape (read points (59) to (63) of ADR-330 as the model):
```
(N) <Title: the subject in plain words> (owner <date and time of day>, <question tool | chat>; <SPEC CHANGE beside ...
| amends point (x) | settles its clash with ...>): <the decision in plain words, with the exact on-screen
sentences in quotes, as in "...">. Real case <date time>: <what happened, with numbers>. Reasons <he does this>:
<reason> (served: <how>) or <reason> (served: <how>). Not chosen: <option>; <option>.
```
Run (prints the row; add `--write` to insert it after the last point; it refuses a number that exists and wraps at the
file's own width):
```
python .claude/skills/owner-decision/add_decision_row.py spec/decisions/ADR-330.md --number 64 \
  --title "..." --asked "owner 27 Nov night, question tool" --decision "..." \
  --real-case "27 Nov 16:02: ..." --reasons "he opens it after the close: to ... (served: ...)" \
  --not-chosen "...; ..." --write
```
(or `--json fields.json`; `--after N` inserts after point N instead of the last.) Read the printed row once for the
exact sentences. Plain English, no em dashes. New on-screen sentences are "pending owner read" in the lane's RESULTS.

## 4. Tell the lane that owns the code
One `send_message` line to the lane (or, where refused, a line in the handover): `ADR-330 (N): <title>. Build to the
row on <branch>@<sha>. Files: <its files>.` The lane never edits the ADR; it cites the point.

## 5. Commit
`git add spec/decisions/<ADR>.md`, then `git commit` (separate calls): `ADR-330 (N): <the decision in 12 words>`. If
the row changes what a screen says, regenerate the spec digest with its tool, never by hand.

## 6. Queue the push
Add the commit to the next gated push (one push per batch of decisions; the gate runs once). Record in the handover
under PENDING: `ADR-330 (N) committed <sha>, push queued`. Tell the owner only the answer was recorded and where.
