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
| 2026-10-18 | Git Bash here ignores `TZ=Asia/Kolkata` and prints UTC silently (09:18 shown at 14:48 IST); read IST with PowerShell `Get-Date` before stamping a lock, handover or evidence row | this line |
| 2026-10-18 | The kit guard refuses any Bash command containing uvicorn's app-factory flag (the word is guarded); start the API from a script file | `goal-contract-GC-3L-delta-2026-10-18.md` section 3 |
| 2026-10-18 | A funds margin typed from memory ("+ about Rs 60") contradicted GC-3L L1 ("+ Rs 100"); quote the contract's number with its source line, never retype it | this line |
| 2026-10-18 | A funds read of Rs 0 was first suspected to be a probe defect; the raw `GET /user/margins` reply showed Kite itself reported 0 - read the raw reply before blaming the parser | F-44 |
