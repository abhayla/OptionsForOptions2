# Load the reference-product studies of builder rows 1-16 into the difference register (ADR-176)

Size: M, 3 files, 4 items
CI: kit tests job (`tests/test_reference_register_real.py`; vars: none). No database.
Expected (orchestrator, before dispatch, clock 13:3x read at writing): 60 min / ~400k.

Core: every gap of the three studies becomes one valid record, so `reference_register.py --check` passes on the real
folder and `--close-check` blocks each row that still has an open COPY gap.
Proof: step 1 is ONE row end to end - row 11 (REQ-114): its four gaps G-11-1..G-11-4 plus its matches become records;
`--check` passes; `--close-check REQ-114` names the open ones; then the other rows.

Spec basis: ADR-176 decision (5) "including where ours is richer": where ours differs and no exception of ADR-152
applies, we copy the reference product; a measured bug is never copied; an extra of ours written in an approved requirement
goes on the batched SPEC CHANGE list. ADR-152 exceptions (a) stricter safety, (b) legal and compliance, (c) money.
ADR-174, ADR-175, ADR-177 (owner answers already given on gaps G-02-2, G-02-1, G-11-3).
Copy from: none.
Reference: none - searched register, study load (tooling); open records named: RD-001.
Mutation gate: `python scripts/orchestrator/mutation_gate.py` is not needed - this item writes records, no guard; say so in the report.

## Inputs (private scratch, read with Read)
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\0c676935-9a2f-45f8-b156-ae28fa0687d6\scratchpad\sensibull-study\`
`rows-01-07.md` (23 gaps), `rows-08-14.md` (21), `rows-15-16.md` (17), each with "Already match" lists and study-gap
lists. The record format and rules: `scripts/orchestrator/reference_register.py` and the example
`spec/reference-diffs/RD-001.json` (already holds G-05-1 - do not duplicate it). The builder table:
`docs/process/builder-sequence-2026-10-22.md` (row -> REQ).

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1` (the orchestrator merges the
register into it first). Write records with the Write tool only (the shell guard blocks commands naming `spec/`). Commit
with `git commit -F <msg> --pathspec-from-file=<list>`; do NOT push. Never stop a process by name. NAME RULE: never
write the reference product's name anywhere (records, commit text, report); the inputs use it - reword in your own words.

## What to do
1. One record per gap, per "already match" line (kind MATCH), and per study-gap line (kind NO-SCREEN). Ids RD-002
   upward, in row order.
2. Kind and fields, by rule (ADR-176 (5)):
   - COPY: ours differs, no ADR-152 exception and no owner ADR covers it. `req` = the requirement that OWNS the
     behaviour: the row's own REQ when it is about what that row built; a LATER row's REQ when that requirement already
     describes it (examples: Reset Prices and the price-moved marker = REQ-077; days to expiry and the prices-as-of stamp
     = REQ-135; the shape name on the builder = REQ-076; rename = REQ-134; delete = REQ-070; BANKNIFTY/FINNIFTY =
     REQ-090) - grep `spec/requirements/` for the behaviour before choosing; `row` = the builder row of that REQ in the
     table. When NO requirement describes it, use the closest REQ by subject, set `ac` empty and start `ours` with
     "NEW AC NEEDED:" - the orchestrator writes the AC.
   - `spec_change: true` (still kind COPY): copying would remove or change behaviour written in an APPROVED AC (quote the
     AC id in `ours`). Examples: REQ-114 AC-3's 50% jitter vs the reference's up to 1 s (G-11-1); plain doubling vs its
     escalation tiers (G-11-2); REQ-053's refusals with two offered strikes.
   - `bug: true`: the reference behaviour is a measured bug (e.g. the server error on a calendar over a monthly-only
     index); `ours` names the nearest working behaviour we keep; kind COPY status `decided`.
   - DIFFERENT-BY-DECISION: an ADR-152 exception or an owner ADR decides it (`adr` = that ADR: e.g. ADR-157 stocks out of
     scope, ADR-094 margin shortfall blocks, ADR-015 stale labels, ADR-174 no prices without Zerodha, ADR-055/ADR-150
     platform-picked strikes, ADR-003 advice wording - reword-not-drop cases stay COPY with the wording rule in `ours`);
     status `decided`.
   - NO-SCREEN: the study has no screen; status `open` (the owner captures it). ADR-177's market-closed text is NO-SCREEN
     with `adr` noted in `ours`.
   - MATCH: status `verified`.
   - Owner-decision gaps already answered: G-02-1 -> COPY under ADR-175 (status open, the build is not done);
     G-02-2 -> DIFFERENT-BY-DECISION ADR-174; G-11-3 -> NO-SCREEN plus a COPY (status open) for the one-wording fix
     under ADR-177 (row 11's fix round is building it).
   - Gaps a study marked as an owner question that are NOT answered yet (e.g. an unlimited max loss vs our finite tails
     rule, calendar and diagonal strategies, the share link): COPY with `spec_change: true` when an approved AC or ADR
     says otherwise, else COPY with "NEW AC NEEDED:"; list them in your report.
3. `reference_behaviour` in your own words (at most 400 characters), screens as "screen NNN" / "catalogue NNN" /
   "bundle-findings 6.1"; at most one short label quoted (40 characters). Never account data, never API bodies.
4. Run `python scripts/orchestrator/reference_register.py --check` (fix until it passes), then `--render`, then
   `--close-check` for every REQ of rows 1-16 and quote each result.

Attack list: (each names its test file)
1. `--check` passes on all records (`tests/test_reference_register_real.py`).
2. No record names the reference product (the name-ban check in `--check`).
3. Every COPY whose behaviour is in a later requirement names that requirement and its row (sample 5 and show the grep hit).
4. Every DIFFERENT-BY-DECISION names an ADR that exists and actually decides it (quote the ADR line for each).
5. Every gap id of the three studies (G-01-1 ... G-16-9) maps to exactly one record - a table in your report.

Standing items: (a) n/a; (b) n/a; (c) n/a: no detector; (d) n/a: no external answer.
Threat model: in scope - a gap lost in loading, a gap filed under the wrong requirement or row, a kept difference with no deciding ADR, the name in a record; out of scope - whether the studies are right.
Findings checked: brief-rule-from-memory

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (record count per kind, the gap-to-record table, every `--close-check` result, the open owner-question gaps)
