# Kit release notes

One entry per kit version (OD-23). The version in force is the project's `KIT_VERSION` file; a kit upgrade
replaces kit-owned files and adds an entry here. Every version entry carries at least one `Migration:` line
(`Migration: none` when nothing is needed); a test fails an entry without one.

## 1.4.0 — findings declare their scope; acceptance-criterion ids are unique (OD-32, OD-36, #39)

1. Why: a real project had 18 findings and none carried a scope, so `kit_harvest.py` brought back nothing without
   saying why (OD-32 item 2); and its REQ-018 once had two AC-9 entries and the lint passed, so one evidence file
   stood for two criteria (issue #39, OD-36).
2. Finding schema: `scope` is REQUIRED, `generic` (the class can happen in any project that uses the kit) or
   `project` (about this repository only). `factory_lint.py` reports a missing or other value as an error naming the
   file and both allowed values.
3. `factory_lint.py` also rejects a requirement that repeats an acceptance-criterion id (names the id and the file)
   and a work item whose `tests_required` names an AC id that none of its `requirement_ids` has (names the AC id and
   the work item).
   Every `tests_required` entry must start with `AC-<n>:`; a malformed prefix is a lint error naming the work item and
   the entry (it was silently skipped before).
3a. Models are named by family alias (e.g. opus, sonnet, haiku), which resolves to the latest model of the family
   (OD-42); `tests/test_model_aliases.py` fails naming file and line on a dated model id in config, and agent
   `model:` lines must be an alias.
4. Factory-side only: `kit_harvest.py` prints `findings: N, generic: G, no scope: S` and a WARNING line when every
   finding lacks a scope.
5. Migration: add `scope` to every `knowledge/findings/*.json`; renumber duplicate AC ids in requirements and fix any
   `tests_required` entry that names an AC its requirement lacks. Replaces `tools/factory_lint.py` and the finding
   schema (kit-owned).
6. Status page (REQ-008, OD-35): `tools/build_status_page.py ROOT --issues F --runs F --out FILE` (or `--fetch`
   instead of the two input files) renders one page from the repo, the issues and the CI runs: sections that
   collapse, sortable and filterable tables, an issues tracker where an issue maps to a requirement only from a
   `Relates-to:` line naming requirement ids or `section <name>` (else UNMAPPED, counted), "Needs you" from `owner-questions/OQ-###.md`
   (new schema `factory/schemas/owner-question.schema.json`, checked by `factory_lint.py`), and CI gates that never
   ran or were skipped every time. New files: the tool, the schema, `owner-questions/README.md`,
   `.github/ISSUE_TEMPLATE/issue.yml` (required Relates-to field); the `deliver` skill gains step 11 (regenerate and
   republish when a stage changed, never on an ordinary merge). The generated HTML is never committed.
7. Migration: after the first publish, create `views/status-page.json` as `{"url": "<the link>"}` and commit it
   (new projects already re-include it in `.gitignore`; existing ones add the line `!views/status-page.json`); tag existing issues with a `Relates-to:` line; add `owner-questions/`
   files for questions waiting on the owner. Replaces `tools/factory_lint.py`, the deliver skill and adds the tool
   (kit-owned).
8. Spec sections, lookup, a blocking duplicate check and decision pins (REQ-009; OD-30, OD-32 item 3, OD-38,
   OD-39). Why: a real spec restated the same line across requirements ("Learn ..." in two requirements, overlap
   0.88), nothing grouped requirements by subject, and a changed decision left the requirements built on it
   unchecked. The requirement schema REQUIRES a non-empty `section` (the lint names a requirement without one) and
   allows `distinct_from` and `confirmed_against`. New kit-owned tools: `tools/spec_text.py` (the one shared
   tokenizer and fingerprint), `tools/build_spec_index.py` (generates `spec/requirements/INDEX.md` grouped by section;
   `--check` in CI; the file is `generated`), `tools/spec_similar.py . "<text>"` (closest existing items; the
   spec-first rule says run it before writing any spec line) and `tools/spec_dupes.py`, which CI runs as a FULL scan
   on every PR and push (no base ref):
   - Duplicates: a requirement item vs another requirement's items, or a decision sentence vs another decision's
     (heading LINES removed, the prose under them kept; OD-row notes removed), at >= 0.40 word overlap blocks unless
     the NEWER record carries an exemption with the pair's current fingerprint and a difference of at least 3 content
     words: `distinct_from: ["REQ-001 AC-2 #<fp> — <the actual difference>"]` (ADR frontmatter the same way) or
     `(distinct from OD-12 #<fp>: <difference>)` in a Factory OD row. The fingerprint covers the exact pair of texts,
     so editing either text, renumbering criteria or copying an extra item makes it stale. A stale, unused,
     fingerprint-less or unknown-record exemption blocks; identical texts can never be exempted.
   - Pins (OD-39): a requirement that cites a decision (its id in any case, or its file path, in `source`,
     `spec_refs`, the statement or a criterion) carries `confirmed_against: ["<decision id> #<fp>"]`, the fingerprint
     of that decision's current text with notes removed. A missing, stale or orphaned pin blocks; editing the
     requirement never replaces re-pinning; a note-only change to a decision keeps pins valid.
   - Records (OD-40): every id is unique per kind — two OD rows, requirement files or decision files declaring one
     id block (`DUPLICATE-ID`, naming every file/row), and a requirement or decision file whose frontmatter does not
     parse blocks (`UNREADABLE`, naming the file and the error); nothing is skipped silently. A pin on a decision the
     requirement does not cite (orphan) or two pins for one decision block; an exemption's item label must name the
     older item; a `#` line inside a fenced code block is not a heading.
   - `spec_dupes.py . --suggest` prints the fingerprints as paste-ready lines (the exemption's placeholder difference
     fails the 3-word rule until you write the real one); it never writes a file.
9. Migration (your CI fails until done, which is the point): add `section: <subject>` to every
   `spec/requirements/REQ-*.md`; run `python tools/build_spec_index.py .` and commit `spec/requirements/INDEX.md`;
   run `python tools/spec_dupes.py . --suggest`, then settle each flagged pair (merge the two texts into one item for
   a real restatement, or paste the suggested exemption on the newer record with the real difference written in),
   re-read each cited decision and paste the suggested pins. Replaces the requirement schema,
   `tools/factory_lint.py`, the CI workflow and the spec-first rule; adds the four tools.
10. Status page (REQ-010): the requirements table gains an "Any section" filter listing each distinct section once (sorted), combining with the text, status and layer filters; no sections in the repo, no filter. Replaces `tools/build_status_page.py` (kit-owned).
11. Status page (REQ-012): a new "Owner decisions" section lists every decision (`| OD-n |` rows of
   `docs/spec/decisions.md`, or `spec/decisions/*.md` records) with its date, bold title, the owner's words, the
   changes cell, the requirements citing it (same rule as `spec_dupes.py`) and a rolled-up status ("no requirement",
   else the least-advanced status of the citing requirements); Overall gains decisions total / covered / not covered;
   filters for text, covered or not, and status. Escaped-pipe rule: a literal `|` inside a decision-table cell is
   written `\|`; `spec_text.od_cells` and the page treat `\|` as text, not a separator (a bare pipe made a row parse
   to six cells). Replaces `tools/build_status_page.py` (kit-owned).
12. Malformed decision rows are errors, not shifted cells (REQ-012): an OD row that is not exactly 5 cells makes
   `tools/spec_dupes.py` print `RECORD malformed decision row OD-n: N cells, expected 5` and exit 1, and the page lists
   it in a "Data problems" line at the top of Owner decisions instead of rendering it; a requirement with no status
   rolls up as `unknown`. Replaces `tools/spec_text.py`, `tools/spec_dupes.py`, `tools/build_status_page.py` (kit-owned).
13. Decision relations, the amends rule, source and coverage checks (REQ-013; OD-43, OD-44). Why: relations cells
   mixed relation words with work pointers ("W-009 round 3"), a decision that amended another left every requirement
   citing the old one green, and most decisions and spec sections were cited by no requirement without anyone
   seeing it. `tools/spec_dupes.py` now also checks:
   - relations: a decision file's new `changes` field (and a Factory OD row's last cell) is `;`-separated
     `<verb> <targets>`, verb in amends, supersedes, refines, extends, narrows, approves, starts, closes, applies,
     none, no-requirement; targets must exist: a known decision or requirement id, a milestone with a plan file
     (`docs/milestones/M4.1-plan.md` for `M4.1`; for any verb but approves, a planned milestone the decision's own
     text names also counts), or `handoff §N` that is a row of `docs/spec/handoff-sort.md` (any N
     where the repo has no sort); `none — <reason>` stands alone, and `no-requirement — <reason>` may join other
     entries but never amends / supersedes / refines / narrows; both must say why. Anything else is `RECORD <id> relations: ...` (blocks).
   - the amends rule: when decision B amends / supersedes / refines / narrows decision A, every requirement citing A
     must also cite B and pin it in `confirmed_against`, or have status Superseded (`PIN ... (amends rule)`, blocks).
     Every target of a multi-target entry counts. A requirement target works the same way: `refines REQ-7` makes
     REQ-7 cite and pin the decision (or be Superseded). extends and applies do not trigger it.
   - source: every requirement's `source` or `spec_refs` names an EXISTING target: a loaded decision's id, an
     owner-question id (`Q88`) that is a row id (first cell) of `spec/traceability/question-register.md`, not in a
     row whose `status` column says superseded or withdrawn (no register: Q-ids
     never count), a `handoff §N` that is a row of the sort, or an approved milestone plan (`docs/milestones/M*-plan.md`
     whose Status line says APPROVED or DONE) (`SOURCE <id>: ...`, blocks).
   - coverage counts deliberate citations (source, spec_refs); pins track every mention (a decision named only
     as an example in a criterion is pinned but not covered, and the status page lists only deliberate citations).
     Only a live requirement covers (status Superseded or Draft does not). Every decision must be cited by a
     requirement unless its relations are only `approves` of milestones (a pure approval) or carry
     `no-requirement — <reason>`; the verifier checks that each exemption is true, since no code check can; no other verb exempts (a rule relating as `closes M0` still
     needs a requirement), and the status page shows each exemption as `no requirement (exempt: <reason>)`; a `requirement` row of `docs/spec/handoff-sort.md` (where the repo has one) must be named as
     `handoff §N` in some requirement's source or spec_refs. Printed as `COVERAGE` lines and counts, and shown on the
     status page's Owner decisions section. They block only when `docs/spec/coverage-mode.txt` reads `block`; it
     ships reading `report`. A missing file runs in report mode and prints a WARNING; any other value blocks.
   - a decision file without `changes`: a `REPORT` line in report mode, a `RECORD` failure in block mode.
   The decision schema gains an optional `changes` field (string or list); `changes` is left out of the pinned text,
   so adding relations never stales a pin. Replaces `tools/spec_text.py`, `tools/spec_dupes.py`,
   `tools/build_status_page.py` and `factory/schemas/decision.schema.json` (kit-owned); adds
   `docs/spec/coverage-mode.txt` (project-owned).
14. Migration (the relation, amends and source checks block at once; coverage waits for you to switch it):
   (a) add `changes: "<verb> <targets>"` (or `changes: "none — <reason>"`; add `no-requirement — <reason>` only
   where the decision genuinely states no requirement) to every `spec/decisions/*.md`, rewriting
   any pointer to work ("W-###", "round 3") as the relation it implies against a decision, requirement, milestone or
   `handoff §N`; (b) run `python tools/spec_dupes.py .` and, for each `PIN ... (amends rule)` line, re-read the
   amending decision, cite it in the requirement's source and add its pin to `confirmed_against` (the line prints
   it), or set status Superseded; (c) give every requirement flagged by a `SOURCE` line a source naming a decision
   id, owner-question id, `handoff §N` or an approved milestone plan in source or spec_refs; (d) create `docs/spec/coverage-mode.txt` reading `report`, back-fill
   requirements until the COVERAGE counts are 0, then change it to `block`.
15. Evidence fingerprints, two honest statuses and a computed health (REQ-014; OD-43, OD-44, OD-47, OD-48). Why: an
   evidence file was never tied to the criterion text it proved, so an edited criterion kept its old proof (a real
   criterion's fingerprint moved f111e61460ba -> a32b267fdc30 when its text changed, and no check noticed).
   - Evidence schema: optional `ac_fp` (12 lowercase hex). New kit tool `python tools/ac_fp.py <REQ-id> <AC-id>`
     prints the fingerprint of that criterion's current text (the same `spec_text.fingerprint`); an unknown
     requirement or criterion exits 1 naming it. The `deliver` skill step 5 writes it into every new evidence file.
   - `trace_check.py`: evidence whose `ac_fp` differs from the criterion's current text is STALE; a requirement at
     Verified, Reviewed or Released with stale evidence fails with a `FAIL <REQ> <AC>: stale evidence <file>` line
     (below Verified it is reported). A stale fingerprint that equals another criterion's adds "matches AC-n's
     text: renumbered?", never a re-attachment. A malformed or unquoted all-digit `ac_fp` fails at any status
     (write it quoted: `python tools/ac_fp.py REQ AC --yaml` prints `ac_fp: "<hex>"`). Evidence WITHOUT `ac_fp` is
     "unpinned: before tracing" ONLY when its path is listed in `spec/traceability/unpinned-before-tracing.txt`
     (written once by `python tools/ac_fp.py --freeze-unpinned .`); any other evidence without `ac_fp` fails
     ("new evidence must carry ac_fp"). A missing list = nothing may be unpinned. An evidence file for an AC id the
     requirement no longer has prints a WARN line.
   - trace_check fails a work item whose requirements share an AC id (one evidence file cannot prove both).
   - Evidence is bound to ONE requirement: pinned evidence carries `requirement: REQ-###` (the schema requires it
     with `ac_fp`; `ac_fp.py REQ AC --yaml` prints both lines) and counts only for that requirement; evidence
     naming another requirement fails, so a split child with identical criterion text never inherits its parent's.
   - Requirement schema: statuses `Delivered-before-trace` (requires `delivered_in`: a `docs/milestones/*-report.md`,
     not a plan, inside docs/milestones, that names the requirement; never a PR, OD-48 — cite the PR inside the
     report; a requirement any work item links cannot use this status) and `Superseded` (requires `superseded_by`: an
     existing requirement or decision id; a loop fails, a Draft target warns); trace_check demands no evidence for
     either and prints DELIVERED-BEFORE-TRACE / SUPERSEDED. Optional `split_from: REQ-###` must name another
     existing requirement (no loop), and a split requirement's evidence must carry `ac_fp`. `build_order.py`
     counts Delivered-before-trace as done, never lists a Superseded requirement, and resolves a dependency on one
     through superseded_by (a loop, or a chain back to the dependent itself, fails). `spec_dupes` counts coverage
     only from an allow-list of statuses: a misspelt or unknown status never covers.
   - Status page: a Health column beside Status (first match wins: Changed - needs re-check, Blocked, Parked,
     Unpinned evidence, OK), one Overall tile per health, and an "Any health" filter. The headline counts done =
     verified + delivered before trace (shown split) and leaves Superseded out of the total, with its own tile.
   Replaces `tools/trace_check.py`, `tools/build_order.py`, `tools/build_status_page.py`, the evidence and
   requirement schemas and the `deliver` skill; adds `tools/ac_fp.py` (all kit-owned).
16. Migration: at the upgrade, run `python tools/ac_fp.py --freeze-unpinned .` ONCE and commit
   `spec/traceability/unpinned-before-tracing.txt`: it lists every existing evidence file without `ac_fp`, which
   then shows "unpinned: before tracing" and keeps its requirements verified (the tool refuses to overwrite the
   list without `--force`). New projects start with no list. Nothing else to back-fill, and never back-fill:
   new evidence carries `ac_fp`. Split any work item that delivers two requirements sharing an AC id. Do not add `ac_fp` to an old evidence file
   (today's fingerprint would claim the old proof covered today's text); re-verify the criterion instead when you
   want it fresh. A requirement delivered before tracing existed can move to `Delivered-before-trace` with
   `delivered_in`; a replaced one to `Superseded` with `superseded_by`.
17. The verifier cannot forge evidence (REQ-015, OD-47, issue #41). Why: the verifier's own definition said "You may
   write exactly one thing: the evidence file(s)" while its description said it cannot write; verifiers wrote evidence
   files through their shell four times despite briefs forbidding it (findings agent-definition-contradicts-its-role,
   agent-frontmatter-hooks-silent-headless).
   - `.claude/agents/verifier.md` grants no write: it returns one block per acceptance criterion in its reply only,
     each carrying the `requirement:` and `ac_fp:` lines; the orchestrator records the evidence files (deliver step 5).
   - New hook `.claude/hooks/verifier_write_guard.py` (source `capabilities/hooks/verifier-write-guard/`), wired by the
     kit settings on `PreToolUse`, `PostToolUse` and `PostToolUseFailure` for `Bash|PowerShell`. Only when the hook
     input's `agent_type` is `verifier` (also `plugin:verifier`, or a name in `VERIFIER_WRITE_GUARD_AGENTS`), one
     foreground call at a time, in `evidence/`, `work/` and `spec/` of the repo and every git worktree: a file absent
     when the call started and untracked by git when it ends is moved to `<system temp>/verifier-quarantine/<stamp>/`;
     every other change (changed, deleted, or new but tracked, e.g. a merge) is copied there and reported, never
     moved or reverted; `MANIFEST.json` lists each (checkout, path, sha256, action). The call is refused naming each
     path and its checkout. A background verifier shell call is refused before it runs. Judged by effect, never by
     the command text; links and junctions are never followed; the main session and other agents are untouched. No
     snapshot: refused, git's untracked/modified paths listed, nothing moved. Threat model: stops an honest
     verifier, not a same-user forger. `tools/kit_settings.py` accepts the `PostToolUseFailure` event. The deliver
     skill's step 4: the orchestrator records git status before the dispatch, flags only new lines after it, and
     reconciles each quarantine MANIFEST.json created in between.
   - Factory-side: `tools/kit_live_proof.py` adds a real verifier write attempt and checks the file is gone from the
     project, is in the quarantine folder, and that the refusal is in the verifier's own transcript.
   Migration: nothing to edit. The upgrade replaces the verifier definition, adds the hook and regenerates the
   settings file (`python tools/kit_settings.py .`). A project that changed its own verifier definition re-applies
   that change without any write grant.
18. The build order never schedules a requirement that is only recorded (REQ-036, OD-53). Why: after a batch of
   Specified requirements was added, six of them ranked ahead of approved work and `--may-start` refused that work,
   naming items nobody had approved. Behaviour change: a requirement at Draft or Specified (any case) is never
   `next` and is not in the order to build; `--may-start` answers NO saying it is recorded, not approved to build,
   and names its status; `views/build-order.md` lists each under a separate heading
   "Recorded, not approved to build"; an approved requirement that depends on one shows as waiting on it by id. Projects that hold Specified
   requirements will see them listed apart. Replaces `tools/build_order.py` (kit-owned). Migration: none; run
   `python tools/build_order.py .` to regenerate the view.
19. Releases and reviews are traceable (REQ-016, OD-49, OD-55). Why: no release record had ever been written, so
   nothing could answer "in which release was it delivered?" or "which review accepted it?" for any requirement.
   - Release records: `releases/R-###.md` (release schema; `date` is now required next to `version` and `items`, and
     each item is a requirement `REQ-###` or a work item `W-###`). New field `kind`: `kit` (a kit version, nothing
     deployed: status must be `released`, the new status value, and `authorization` is optional) or `production`
     (the default when absent: `authorization` with `required: true` as before, and only `deployed` counts as
     delivered). Kit releases are recorded from 1.4.0 on; earlier versions stay described by this file and are not
     back-filled. Only `R-###.md` records and `README.md` may sit in `releases/`; anything else fails.
   - `trace_check.py` checks both ways: a requirement at Released must name `release: R-###`, that record must exist,
     list it, and be at its kind's delivered status (a cancelled, preparing or rolled-back record fails); a record
     must not list a requirement that does not name it back or is not Released. Each FAIL names the requirement and
     the record. A record it cannot read (no frontmatter, `id` not R-### or not its file name, `items` not a list, an
     item that is neither id, an unknown `kind`) fails, naming the record. Verified and Reviewed requirements are
     listed as UNRELEASED (and in a new "Releases" part of `views/trace.md`), never as released.
   - Review link: a done work item's `review_status` STARTS with the pull request that merged it, `PR #<n>` (n >= 1;
     later `PR #` mentions are follow-ups, a bare `#n` reads as an issue). Tier A and B continue with `; reviewed`
     (e.g. `PR #12; reviewed (Tier B diff review PASS)`) or, for work merged before reviews were recorded, the
     explicit marker `; review not recorded`; anything else ("not reviewed", "review pending") fails. The legacy
     marker `review not recorded` is accepted on any done Tier A/B item and always shown as "not recorded"; it is
     for items delivered before this check, and a project should not use it for new work. The check proves that the
     merging pull request and a verdict are named, not that the review ended clean: a verdict such as "REVISE ...
     fixed" is accepted as written, because matching verdict words would misread honest records. Tier C
     starts with the pull request (e.g. `PR #7; not required (Tier C)`). A done work item without tier A, B or C
     fails.
   - Status page: the requirements table gains Release (or `unreleased`) and Review PR (the merging PR, with
     "(review not recorded)" for the marker) columns and an "Any release" filter.
   Replaces `tools/trace_check.py`, `tools/build_status_page.py` and the release schema (kit-owned).
   Migration (your CI fails until done, which is the point): once, start `review_status` of every existing done
   work item with its merging pull request, e.g. `review_status: "PR #42; reviewed (Tier B PASS)"`, or
   `"PR #42; review not recorded"` when no review was recorded (quote it: an unquoted ` #` starts a YAML comment);
   add `date` (and `kind: production`, optional) to any existing release record; then write one release record for
   the kit version you move to, listing the requirements it delivered, and add `release: R-###` to each of them as
   you set them Released. Regenerate the trace view (`python tools/trace_check.py . --write-view`).
   Example kit release record (`releases/R-001.md`, every required field):
     ```markdown
     ---
     id: R-001
     kind: kit
     version: 1.4.0
     date: "2026-10-01"
     status: released
     items:
       - REQ-001
     ---

     # R-001 - kit 1.4.0

     What this release delivered, in a few lines.
     ```
20. Factory-side only: a kit upgrade pull request lists every migration step between the project's kit version and the new one as a checklist, oldest first (REQ-034).
21. Factory-side only: a kit upgrade now resets a hand-edited kit file and names it at the top of the upgrade pull request (OD-57, REQ-041).
22. Migration: add one line to your `CLAUDE.md` telling a session to read `.claude/kit/GUIDE.md` before pushing or
   touching process files (for example "Before pushing or touching process files, read `.claude/kit/GUIDE.md` (kit
   commands and kit-owned files)."), and remove the kit-generic commands list and kit-file list from your
   `CLAUDE.md`; the new kit-owned `.claude/kit/GUIDE.md` carries both and every upgrade keeps it current (REQ-042,
   OD-58). `kit_selftest.py` check (f) now fails, naming `CLAUDE.md`, when the pointer is missing. Replaces
   `tools/kit_selftest.py` and adds `.claude/kit/GUIDE.md` (kit-owned). Why: `CLAUDE.md` is project-owned, so its kit
   text went stale (one real project listed 2 kit commands; the kit expects about 14).
23. Kit rule loading tiers (REQ-043, OD-59): only `evidence-and-proof`, `run-discipline` and `spec-first` stay
   always loaded; `learning` (paths `knowledge/**`) and `spec-adherence` (paths `spec/**`, `docs/spec/**`) are now
   path-scoped like `deployment` and `status-artifact`. Always-loaded kit rule bytes (LF-normalized, as
   `kit_selftest.py` check (c) counts them): 22489 before, 13407 after. The cap in `.claude/kit/budget.json` is now
   13407 plus 9000 of project headroom (two project rules of 4500) = 22407, down from 30000.
   Migration: none; kit-owned rule files replaced.

## 1.3.1 — questions are asked with the question tool, one per call, never buried (OD-37)

1. Why: the owner, 2026-09-29: "If you have questions for me, ask one at a time. Do not stop and just mention that
   I am blocking you. If you are not asking a question, how can I answer?" A session had ended on a question
   written inside a long status report instead of asking it.
2. `evidence-and-proof.md` E1: a question for the owner is ASKED with the interactive question tool, one per call,
   recommended option first with its reason and Spec basis inside; never buried in a report, never a stop that only
   says "waiting on you". Owner away: run-discipline B2 (park it) still applies. The E1 critical-rules line says so.
   Wording elsewhere in the file was tightened to stay under the always-loaded budget; no rule was removed.
3. `intake` skill step 2: each question is asked with the question tool (still opening `*Sync-check:*`).
4. Migration: none; replaces two kit-owned files.

## 1.3.0 — requirement prioritization: layer, checked dependencies, risk, walking skeleton, build order (OD-33, OD-34)

1. Why: requirements carried a free-text `priority` (one real project: 71 requirements, every one `priority: V1`),
   so nothing said what to build first, and a parked foundation item's knock-on blocks were discovered while
   building instead of being visible in the spec. Owner decisions OD-33 (criteria) and OD-34 (mechanisms).
   Core proof: lifting that project's work-item dependencies to requirements, a dependency sort predicted exactly
   the three requirements blocked behind its one parked foundation item, 3 of 3, none extra.
2. Requirement schema: `layer` is REQUIRED, one of core, foundation, feature, polish. `release` stays an optional
   free string. `priority` is now a lint error that names `layer` and `release` as its replacements. New optional
   fields: `risk` (high | normal, absent = normal; `risk: high` needs a non-empty `risk_reason`), `skeleton`
   (true marks the walking-skeleton path; needs layer core or foundation and a non-empty `smoke` list of commands).
3. `factory_lint.py` (repo level) now also rejects: a `depends_on` entry that is not an existing requirement id, a
   self-dependency, a dependency cycle (the message lists every member), an inner item depending on an outer one
   (core or foundation on feature or polish; feature on polish), a repo with requirements but none marked
   `skeleton: true`, and scoring fields (`score`, `rice`, `wsjf`, `value_score`, `effort_score`).
4. New kit tools: `tools/run_smoke.py ROOT` runs every smoke command of every skeleton requirement without a shell
   (shlex split, cwd ROOT, 600 s timeout each; the program is resolved with `shutil.which`, so `npm` finds
   `npm.cmd` on Windows) and fails naming the requirement and command. A smoke line containing a shell operator
   word (`&&`, `||`, `|`, `;`, `<`, `>`, `>>`, `2>`, `&`) is rejected by the lint and refused by run_smoke before
   anything runs (with no shell, `a && b` would never run `b`): write one program per smoke line. Use forward
   slashes in smoke paths (`python tools/x.py`), which work on Windows and Linux alike.
   `tools/build_order.py ROOT` writes `views/build-order.md` (owner `generated` in the lock; `--check` fails when
   it is missing or stale; `kit_upgrade.py` regenerates it and keeps it in the lock) with each open requirement's
   state (next / waiting / blocked, naming the blocking root and its work item's next_action);
   `--may-start REQ-###` gates a start (earlier-group `next` items first: skeleton, then core+foundation, then
   feature, then polish). A work item's `order_override: <reason>` skips ONLY that group-order check; it never
   lets through a done requirement, undone dependencies or a blocked chain. CI runs `build_order.py . --check` and `run_smoke.py .`; the `deliver` skill runs
   `--may-start` at Intake; `spec-first.md` gains a "Build order" section (re-run the order and re-read layers at
   each milestone start and whenever a decision changes; no scoring formulas). `kit_drift.py` checks the
   generated `views/build-order.md` against `build_order.py`'s output and reports a difference as STALE
   (regenerate and commit), not as a hand edit.
5. MIGRATION for an existing project (its CI fails after upgrading until this is done — that is the check doing
   its job, not a regression):
   a. add `layer:` (core | foundation | feature | polish) to every `spec/requirements/REQ-###.md`;
   b. remove every `priority:` line; if it named a version or date (e.g. `V1`), move that to `release:`;
   c. mark ONE core or foundation requirement `skeleton: true` with a `smoke:` list of commands that prove the
      app's core path still works (each one program plus arguments, forward slashes in paths; no `&&`, `|`,
      `;` or redirects), and check it with
      `python tools/run_smoke.py .`;
   d. fix any `depends_on` the lint now rejects (unknown id, duplicate, self, cycle, inner-on-outer);
   e. add `!views/build-order.md` to `.gitignore` (after `views/*`; new projects ship it), run
      `python tools/build_order.py .` and commit `views/build-order.md`;
   f. run `python tools/factory_lint.py .` until it exits 0.

## 1.2.0 — intake kit and session entry point (finding new-project-has-no-session-entry-point)

1. RCA: `new_project.py` shipped a project with no `CLAUDE.md` and no `docs/HANDOVER.md` at its root, and no
   reusable way to turn an owner's idea into decisions — two of two real copier projects
   (`factory-testbed`, `dashcam-youtube`) were built without either, so a fresh session in a new project had
   no recorded purpose, no decisions to read first, and no next step, and had to be told everything again by
   whoever started it.
2. Fix: a new `intake` skill (`.claude/skills/intake/`, kit-owned) takes the owner's idea, asks one question
   per turn with a `Spec basis:` line and a recommendation, records each answer as the next
   `spec/decisions/ADR-###.md` in the same turn, stops asking what a real-input core proof can measure, then
   fills the project's `CLAUDE.md` and `docs/HANDOVER.md` before writing requirements. The template now ships
   project-owned `CLAUDE.md` and `docs/HANDOVER.md` skeletons (`<fill in>` placeholders); `new_project.py`
   writes both with owner `project` in the lock, same as any other project-owned file.
3. `kit_selftest.py` gained check (f): it fails, naming the file, when `CLAUDE.md` or `docs/HANDOVER.md` is
   missing or empty at the project root, and passes once both exist — the check that makes the skeletons a
   requirement of every project, not just a convention.
4. `kit_upgrade.py` never creates or touches either file: both are project-owned (the default owner for any
   path not listed in `new_project.py`'s `OWNERSHIP` table), so an upgrade only ever replaces kit-owned files.
   A project made before 1.2.0 without these two files (the M3 testbed) fails check (f) after upgrading until
   it adds them; that is the check doing its job, not a regression.
   Migration: if the project has no non-empty `CLAUDE.md` and `docs/HANDOVER.md` at its root, add them (check (f)
   of `kit_selftest.py` fails until then); replaces kit-owned files.
5. Fix round 1 (Tier A review, MAJOR): the template's own `CLAUDE.md` was auto-loaded by Claude Code into a
   Factory session working on this repo (any `CLAUDE.md` on the path from cwd up to the drive root is
   auto-loaded), contradicting the real Factory `CLAUDE.md`. The template file is now `CLAUDE.md.tmpl`;
   `new_project.py`'s copier writes it into every project as `CLAUDE.md` (lock `path: CLAUDE.md`,
   `owner: project`, `source:` the `.tmpl` path) — the project still gets a plain `CLAUDE.md`, only the
   Factory's own tracked copy is renamed.
6. Fix round 1 (Tier A review, MAJOR, pre-existing, fixed here because W-004's core proof depends on it):
   `kit_live_proof.py` built its throwaway project under `$TEMP`, which sits under the user's home folder, so
   Claude Code's ancestor-directory memory walk loaded `~/.claude/CLAUDE.md` and `~/.claude/rules/*.md` as if
   they were the project's own memory (mislabeled `memory_type: Project`), making the "no user-level
   contribution" check pass falsely. The live-proof project now builds under a folder on the Factory repo's
   own drive, outside any git checkout and outside the user's home folder (`--root` overrides it), and a new
   hard check fails naming any `InstructionsLoaded` `file_path` that resolves outside the project folder at
   all — proven offline with a fake event log carrying such a path.
7. Fix round 2 (Tier A review, MAJOR (k)): the round-1 fix for item 6 shipped without a mutation test —
   reverting the default root or the project path to a bare `tempfile.mkdtemp()`/`tempfile.gettempdir()`
   stayed green. Added unit tests asserting the default root is neither under `Path.home()` nor inside a git
   checkout, and that the run's project path resolves under that root (killed).
8. Fix round 2 (MINOR, real cost): live-proof cleanup used `shutil.rmtree(..., ignore_errors=True)`, which
   silently left every read-only `.git` object file behind (126 per run, measured, at the drive root). Cleanup
   now clears the read-only bit and retries on failure (`onexc`/`onerror`), removes the run folder itself, and
   prints a `WARNING` naming the path on a genuine failure instead of staying silent.
9. Fix round 2 (MINOR): `kit_selftest.py` check (f) now strips whitespace before the emptiness test, so a
   whitespace-only `CLAUDE.md` or `docs/HANDOVER.md` counts as missing, same as 0 bytes.
10. Fix round 2 (MINOR): on non-Windows, the default live-proof root is `/tmp/kit-live-proof-tmp` (writable,
    outside the home folder), not the unwritable-by-normal-users `/kit-live-proof-tmp`; a non-writable default
    root now refuses with a message pointing at `--root` instead of silently falling back under the home
    folder.

## 1.1.4 — guards split shell commands only outside quotes (finding segment-split-before-quotes)

1. RCA: the three git guards' shared `_git_shell.py` and `kit-file-guard`'s own segment split both matched a
   separator regex (`&&`/`||`/`;`/`|`/`&`/`{`/`}`/`(`/`)`/newline) over the raw command TEXT before any quote was
   recognized, so a separator character INSIDE a single- or double-quoted argument (a `-m` commit message, a
   test loop's quoted case string) split the string in two and the quoted words on either side were read as
   their own command segments — a quoted bypass word could reach the parser as if it were a real, separate
   command, and (in `kit-file-guard`) a harmless quoted decoy could make an otherwise read-only command look
   like a real write and get denied instead.
2. Fix: `_git_shell.split_segments`/`split_segments_with_start` and `kit-file-guard`'s local segment scanner now
   walk the command character by character and only treat a separator as a boundary while it is NOT inside an
   open quote; an unterminated quote fails safe (the remainder of the command is kept as one segment).
   `git-stash-worktree-guard` was updated to call the shared `split_segments_with_start` instead of the module's
   former private `_SPLIT_RE` attribute.
3. Swept `full-suite-guard` and `pipe-exit-guard`: both still split on raw separator text before tokenizing, but
   neither is wired into this template yet — left as-is, to be fixed at the sweep that adopts them.
4. Migration: none; replaces kit-owned files.

## 1.1.3 — git guards catch every spelling (issue #14); budget guard checks the agent's turn limit

1. `git-discard-uncommitted-guard`, `git-hook-bypass-guard`, `git-stash-worktree-guard`: the git program is now
   matched as `git`, `git.exe`, or any path ending in `/git(.exe)` or `\git(.exe)`, case-insensitively; `&` (the
   PowerShell call operator), `{`, `}`, `(`, `)` are segment boundaries, and a backtick line-continuation is
   collapsed before scanning.
2. `git-hook-bypass-guard` also blocks `-n` on `commit`/`merge` (the short form of `--no-verify`), leaving it
   unblocked on `push`/`clean` where `-n` means `--dry-run`.
3. `git-discard-uncommitted-guard` now catches a whole-tree `git checkout .` with no `--` separator, the same way
   it already caught `git restore .`.
4. `agent-budget-required` refuses a `Budget: N min, M tool calls` line whose `M` exceeds 80% of the target
   agent's own `maxTurns` (read from `.claude/agents/<subagent_type>.md`), naming both numbers; an unknown agent
   or a file with no `maxTurns` skips this check.
5. Tier A round 2 (same issue #14 review, RCA: raw-text regexes let a quoted program path, bundled short flags,
   an unambiguous long-option prefix, a mixed-case config key or an env-var config mechanism slip through): the
   three git guards now tokenize each shell segment into real words (shared `_git_shell.py`) and reason about
   PROGRAM + ARGV instead of scanning text. `git-hook-bypass-guard` now also blocks any unambiguous prefix of
   `--no-verify` (from `--no-v` up), `-n` bundled into commit's short flags (`-nm`, `-anm`) — commit only, since
   merge's `-n` means `--no-stat`, not a bypass — a case-insensitive `-c core.hooksPath=`, and
   `GIT_CONFIG_PARAMETERS`/`GIT_CONFIG_KEY_*` setting `core.hooksPath`. `git-discard-uncommitted-guard` now also
   blocks `git checkout -f`/`--force` with no explicit path (discards every dirty file, like `checkout -- .`).
   `git-stash-worktree-guard` now treats every stash flag except `-h`/`--help` as a mutating push option (`-u`,
   `-m wip` used to be misread as read-only) and recognizes `Set-Location`/`pushd`/`chdir` as `cd`.
6. Tier A round 3 (same review, sweep): `git-stash-worktree-guard` kept its own quote-stripping/regex program
   match instead of going through the shared `_git_shell.py`, so a quoted program path with spaces
   (`& "<full path to git.exe>" stash`) was allowed inside a linked worktree; the program is now
   identified only via `_git_shell.py`, matching the other two git guards.
7. Migration: none; replaces kit-owned files.

## 1.1.2 — the self-test counts a guard as blocking only on exit 2

1. `kit_selftest.py` check (d) accepts only exit code 2 as a block. A crash (exit 1) is a non-blocking error to
   Claude Code, and a JSON deny at exit 0 can be overridden by another hook's allow; both used to read as "blocks".
2. Migration: none; replaces kit-owned files.

## 1.1.1 — kit-file-guard lets kit tools run; frontmatter split fixed; caches ignored; merge and upgrade reports

1. kit-file-guard: a shell segment running a kit tool (`python tools/<name>.py`) is no longer treated as a
   write to it; write forms into `tools/` still refuse.
2. `factory_lint.py` and `trace_check.py` split frontmatter only on a line that is exactly `---`, never on a
   `---` inside a quoted value.
3. The copier's `.gitignore` now ignores `__pycache__/` and `*.pyc`, so a fresh project's `git status` stays
   clean after running the shipped tools.
4. `merge_when_green.py` re-reads the PR state after `gh pr merge`; MERGED is reported as success even if
   local branch cleanup fails.
5. `kit_upgrade.py`'s summary reports "changed" and "identical" kit files separately, and skips rewriting an
   identical file.
6. The deliver skill: a headless (`claude -p`) run merges through `merge_when_green.py` in the foreground.
7. Migration: none; replaces kit-owned files.

## 1.1.0 — kit ships merge_when_green.py (refuses conflicted PRs; zero checks = wait); the deliver skill merges only through it

1. Migration: none; replaces kit-owned files.

## 1.0.0 — first kit release

Fixes made during M3, before the first release:

- The git guards also check PowerShell commands, not only Bash.
- Both agent guards also check the `Task` tool, not only `Agent`.
- The hook presence check also reads the local settings file.
- The production seatbelt is opt-in (the copier's `--seatbelt`); without it every call is allowed.
- The evidence guard starts log-only; the project turns blocking on after reading its log.
- The copier refuses to overwrite files, to write through a link, into the home folder or a drive root, and
  records a dirty template in the lock.
- The drift check confines every lock path to its base folder.
- Provenance hashes are taken over LF-normalized content, so Windows and Linux checkouts agree.
- The banned-term scan covers every text file in the kit; agent-guard messages are generic.
- OD-22 layout: kit rules in `.claude/rules/kit/`, project rules in `.claude/rules/project/`; the settings
  file is generated by `tools/kit_settings.py` from the kit wiring (`.claude/kit/settings.kit.json`) plus the
  project addendum (`.claude/project/hooks.json`), minus opt-outs with a reason (`.claude/project/optouts.json`).

1. Migration: none; first release.
