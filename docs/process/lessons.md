# Process lessons (reviewed weekly)

Process misses that did not let a defect reach main go here, one line each, instead of the findings registry
(owner decision 2026-10-17, ADR-1NN item 5). A miss that let a defect reach main is a finding in
`knowledge/findings/`. Review this list once a week; a lesson seen twice becomes a mechanism (a check, a hook, a
template line), then its line is deleted.

| Date | Lesson | Where it now lives |
|---|---|---|
| 2026-10-17 | A process-change recommendation narrowed a safety rule without saying so | finding `process-change-narrows-safety-rule` (it could let defects reach main) |
| 2026-10-17 | A planned "new brief template" duplicated `docs/process/builder-brief.md`; grep `docs/process/` before proposing a new process file | this line |
