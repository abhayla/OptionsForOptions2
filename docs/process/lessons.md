# Process lessons (reviewed weekly)

Process misses that did not let a defect reach main go here, one line each, instead of the findings registry
(owner decision 2026-10-17, ADR-106 item 5). A miss that let a defect reach main is a finding in
`knowledge/findings/`. Review this list once a week; a lesson seen twice becomes a mechanism (a check, a hook, a
template line), then its line is deleted.

| Date | Lesson | Where it now lives |
|---|---|---|
| 2026-10-17 | A process-change recommendation narrowed a safety rule without saying so | finding `process-change-narrows-safety-rule` (it could let defects reach main) |
| 2026-10-17 | A planned "new brief template" duplicated `docs/process/builder-brief.md`; grep `docs/process/` before proposing a new process file | this line |
| 2026-10-17 | A docs PR that changes a requirement's status or adds a finding/ADR also needs: a coverage stage per new id, the build-order view, the requirements index and the spec digest regenerated, and ONE path in the Spec-deviation block; #382 took three CI rounds. Run every generated `--check` + `coverage.py --check` + `check_pr_spec_block.py --body-file` before the push | this line |
| 2026-10-17 | An owner-needed contract run unattended stops at its owner step by closing PARTIAL (parked items + the next contract written, checked, merged, lock deleted), not by holding the lock and waiting | this line |
