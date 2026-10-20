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
| 2026-10-18 | A new ADR's `changes:` line used a verb the checker does not know ("clarifies") and a target with words after the id; CI's spec_dupes step failed (#392). A docs PR that adds or changes a decision row runs `python tools/spec_dupes.py .` locally too; `changes:` uses only amends / supersedes / refines / extends / narrows / approves / starts / closes / applies with bare ids, and every requirement a `refines` names lists and pins the ADR | this line |
| 2026-10-18 | A funds read of Rs 0 was first suspected to be a probe defect; the raw `GET /user/margins` reply showed Kite itself reported 0 - read the raw reply before blaming the parser | F-44 |
| 2026-10-18 | The W-090 brief copied the work item's "range and step" without re-reading REQ-034; the builder built a user step menu and a 50-point grid that AC-4 / AC-5 / ADR-042 rule out, costing a fix round. check_brief only checks quotes that are present: every brief quotes the AC text it builds, not the work item's summary of it | this line |
| 2026-10-18 | W-089 was briefed Tier B but its builder had to touch `kite_reads.py` and `live_market.py` (live path), which made it Tier A; re-tier from the files a builder report names before choosing the reviewer | this line |
| 2026-10-18 | A PR body's `Spec section:` anchor must be a markdown heading slug; `REQ-034.md#AC-4` failed `check_pr_spec_block.py` in CI (#399). Run it with `--body-file` before `gh pr create`, for draft PRs too | this line |
| 2026-10-18 | W-108 needed three review rounds' worth of findings on input completeness (a subset of plans, then open plans): a reconciliation brief lists every state of the stored data it reads (plan open / closed / exited, fills stored or not, other strategies, standalone) as B4 (d) answer states, not only the broker reply's states | #405 |
| 2026-10-18 | GC-2f closed at 18:41 with its cap at 23:13: W-108 was parked after review round 2 although the rule also allows an independent redesign, W-111 was parked unreviewed, and the evidence passes were parked whole without trying the 1-hour one. The owner asked "did you stop short?" - yes. Parking is for the cap; before it, take the item's next allowed step. Run contracts through `/goal` | goal-chain.md rule 4b; GC-2g |
| 2026-10-20 | pytest-html needs pytest-metadata; with `-p no:metadata` (PR #424) use `-p metadata` when running with --html. No developer README section on running tests exists, so the note lives here (GC-6 row HTML-PLUGIN) | GC-6 #409 |
