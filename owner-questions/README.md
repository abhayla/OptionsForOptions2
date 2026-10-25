# owner-questions

One file per question the owner has not answered yet: `OQ-###.md`, YAML frontmatter only, checked by
`python tools/factory_lint.py .` against `factory/schemas/owner-question.schema.json`.

```yaml
---
id: OQ-001
asked: 2026-09-30
question: One sentence, ending in a question mark.
recommendation: What you recommend and why, in one or two sentences.
spec_basis: The spec sections and decision rows it rests on, or "none - the spec says nothing about <subject> (searched: <terms>)".
status: open            # open | answered
answer_ref: OD-40       # required once status is answered: the decision row that records the answer
---
```

The status page's "Needs you" section lists exactly the `open` files here, with their recommendation, and
nothing else: it never guesses from plan prose. When the owner answers, write the answer into the spec as a
decision row, then set `status: answered` and `answer_ref`. An answered question is hidden from the page.
