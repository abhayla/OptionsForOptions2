# GC-ICLIVE: common rules for the five cloud contracts (A to E)

**Executor:** /goal in a cloud session   ·   **Created:** 2026-11-24   ·   **Owner approval:** 24 Nov 2026 (chat)

This file is not run by itself. Each part contract (`goal-contract-GC-ICLIVE-A` to `-E-2026-11-24.md`) names its
issues and its Definition of Done and says "follow the common rules". Everything below binds every part.

**Mission of the chain.** The live iron condor paper test of 23 Nov 2026 produced 71 issues (D-01 to D-71). Seven
critical ones were built on 23 Nov on branch `fix/ic-live-test-1123` (draft pull request). The chain finishes those
seven properly and fixes the other 64, one issue at a time, on the same branch, without the owner present. A cloud
session cannot open the app, so the highest status it may set is **"Fixed, not tested"**; "Closed" is set later on the
owner's PC after a screen check.

## 0.1 Where the run works (isolation)

1. Work only on branch `fix/ic-live-test-1123` in this cloud checkout: `git fetch origin && git checkout
   fix/ic-live-test-1123 && git pull --ff-only`. Never commit to `main`. Never create another branch or pull request.
2. One GC-ICLIVE run at a time. First action: read `docs/process/.run/GC-ICLIVE-PROGRESS.md` (see 0.3). If its last
   entry is not a `DONE` or `HALT` line and is less than 2 hours old, another run is live: stop and say so.
3. Never force-push. Never rebase the branch. Merge `origin/main` into the branch only at the START of a part, and
   only if `git log HEAD..origin/main --oneline` is not empty; then run the gates of section 6 before any new work.

## 0.2 Preflight (idempotent: never redo finished work)

Before any issue: read `docs/process/ic-live-test-2026-11-23-status.md` (the status ledger, section 7), the tracker
row if the tracker is reachable, `git log --oneline -40`, and the code. An issue whose ledger row says
`Fixed, not tested` AND whose test exists and passes is SKIPPED (verify-only: run its test once). A half-done issue
gets only the missing part. List every skip in the final report.

## 0.3 Progress log

Append-only file `docs/process/.run/GC-ICLIVE-PROGRESS.md` (create the folder; add `docs/process/.run/` to
`.gitignore` if it is not ignored). First line of each part: part letter, branch, start time, contract path. One
entry of at most two lines at: issue start, issue done (with the test result line), every defect found, every
"not working" event and what was done, every review verdict, every park, every push, the end.
Format: `[YYYY-MM-DD HH:MM] <ISSUE|DONE|DEFECT|EVENT|DECISION|PARK|PUSH|HALT> - <text>`. Read the clock for every stamp
(`date`); never type a time from memory.

## 1. Read first (in this order; do not skip)

1. `CLAUDE.md`, `docs/process/standing-direction.md` (this work is step 4, item 10), `docs/process/runbook.md`,
   `.claude/kit/GUIDE.md`, `.claude/kit/builder-brief.md`.
2. `docs/process/session-handover-2026-11-24.md` (state of the seven critical issues, parked follow-ups).
3. `docs/process/ic-live-test-2026-11-23-issues.md` (all 71 issues: what the trader saw, where, on which trade).
4. `docs/process/ic-live-test-2026-11-23-reviews.md` (review findings on the seven critical fixes).
5. `spec/decisions/ADR-317.md`, `ADR-318.md`, `ADR-319.md`, `ADR-320.md` (the owner's decisions of 23 and 24 Nov).
6. `views/spec-digest.md`, then grep `spec/` for every key term of the issue in hand BEFORE designing its fix.
7. Before any screen or wording change: `knowledge/findings/` for the mechanism.
The private competitor study named in CLAUDE.md is on the owner's PC and is NOT available here: do not cite it and do
not design new screens; this chain repairs existing ones.

## 2. Step 1 of Part A only: prove the database route (core first)

Measured on the owner's PC on 24 Nov: a database-backed test spends about 90% of its time waiting on a remote
database (about 52 statements a test at about 113 ms each). A database next to the tests removes that.

1. Read `.github/workflows/app-tests.yml`: it starts `postgres:16`, creates the database `ofo_test`, the limited role
   `ofo_app`, runs the migrations and sets `TEST_DATABASE_URL`, `TEST_ADMIN_DATABASE_URL`, `ALEMBIC_DATABASE_URL`.
2. Start a PostgreSQL 16 server in this cloud machine the same way (package install or the container runtime, whichever
   the machine has), create the same database, role and grants, run the migrations, export the same three variables.
3. Proof: `python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_paper_duplicate_leg_d60.py`
   prints `2 passed`, then `tests_app/test_paper_triggers_routes.py` passes in full. Record both result lines and the
   seconds in the progress log.
4. Then `python scripts/orchestrator/prepush.py` must pass on the unchanged branch head. The repository's pre-push
   hook refuses a push whose head commit has no passing `prepush.py` run, and that gate needs the database.
5. **If a local database cannot be started, or `prepush.py` cannot pass for a reason that is not a code fault: HALT.**
   Write the exact error to the progress log and the final report. Do not bypass the hook, do not push, do not build
   further: without this route nothing built here can leave the machine.

## 3. One issue at a time: the method (every issue, no exceptions)

1. **Read** the issue text and its real case. Grep the spec by every key term. Write in the progress log one line:
   `Core: <the one mechanism> - Proof: <smallest real run>`.
2. **Reproduce first.** A failing test on the REAL function or component, built from the real case in the issue list
   (strikes, levels, lots, prices as recorded). If it cannot be made to fail, the issue is not understood: read more.
   Seen-once items (D-20, D-37, D-50, D-69, D-70): try to reproduce from the code and the recorded values; if that is
   not possible in one attempt, mark `Could not reproduce` with what was tried and build nothing.
3. **Tests first as their own commit** (`Tests first: <what> (<D-id>) (red)`), run red, then the code commit.
4. **Fix at the one place every case passes through** (the engine function, the single route, the shared component),
   never at the screen that happened to show it. A number shown on a screen must come from the code that computes it
   for acting; never add a second reader. Money is exact decimal, never float (ADR-008).
5. **Two checks before the review** (each was a real miss on 23 Nov): (a) what on the surrounding page can remove,
   hide or contradict this (parent refresh, error state, a `v-if` chain)? (b) does the server enforce what the screen
   now shows (offered and accepted, hidden and refused)?
6. **Independent review** by a fresh-context helper that did not build it: diff only, 10 minutes, findings only, with
   the class stated and "covers the class: yes/no". CRITICAL or MAJOR findings are fixed (round 2). After round 2 a
   remaining MAJOR finding means PARK (step 8), not a third round.
7. **Run** the issue's own tests (new tests while building; the whole touched test file once at the end of the
   issue), the non-database tests of the touched area, and after every issue the fast gates of section 6a.
8. **Park, don't drag.** Two rounds per issue. Park = ledger row `Parked` with what is done, what is left and the next
   step; the code stays only if its tests are green and it makes nothing worse, else revert that issue's commits
   (`git revert`, never reset).
9. **Record**: ledger row and tracker row (section 7) at every stage change; a finding that changes what is known goes
   into `knowledge/findings/` in the same commit as the fix.

## 4. Decisions: what the run decides and what it must not

- **The spec decides.** Where an ADR or an acceptance criterion settles the behaviour, build to it and cite it in the
  commit message. Read the ADR body, not its title.
- **Owner decisions already taken** (ADR-317 to ADR-320) are binding and listed per part.
- **Technical choices** (code design, test strategy, where a function lives): decide, record one line in the progress
  log, continue.
- **A trader-facing choice the spec does not settle** (what a trader sees, is told or is allowed to do): take the
  option that (a) changes least, (b) matches the nearest existing decision, and (c) follows these standing owner
  rules: decision-support wording, never advice; an adjustment is never judged on max loss or max profit alone (show
  the trade-off, no verdict); practice trades behave like real ones; nothing a trader set is moved or cancelled by the
  app silently. Write it as a numbered decision row in a new ADR file marked `PENDING OWNER READ` with the options not
  chosen, add it to `docs/process/owner-questions-2026-11-24.md` with the real case and a recommendation, mark every
  new user-facing sentence `pending owner read` in `tests/errors/template_pins.json`, and continue.
- **Two owner requirements that clash** (two ADRs, an ADR against an acceptance criterion, an ADR against ADR-320):
  STOP THAT ISSUE ONLY. Do not decide, not even "the newer one wins". Write both texts with their ids, the real case
  and a recommendation to `docs/process/owner-questions-2026-11-24.md`, mark the ledger row `Needs owner decision`,
  and take the next issue.
- **Never** ask a question with a tool that waits for an answer: nobody is watching.

## 5. Pull request, pushes and the automatic checks

- **One pull request for the whole chain:** the existing DRAFT pull request of `fix/ic-live-test-1123`. It stays a
  draft. Never mark it ready, never merge it, never close it, never open another.
- **One push per part,** at the end of the part, after section 6b passes. No push per issue. After the push, add one
  comment to the pull request: the part letter, the issues with their status, the result lines of 6b.
- **Never wait for or poll the automatic checks.** After the push, finish the part's report. The NEXT part reads the
  result once at its start (`gh pr checks`); a red check from the previous part is fixed first, as that part's
  leftover, before new issues.
- Commit messages: plain sentences, the D-id in brackets, no closing keyword before an issue number (no "fixes #",
  "closes #", "resolves #"). End every commit message with the attribution lines the session's own instructions give.
- Generated files (`tests_app/reply_inventory.py`, `docs/api/openapi.json`, `views/spec-digest.md`, the coverage map)
  are regenerated in ONE commit at the end of the part, not per issue.

## 6. Gates

**6a. After every issue (fast, no database needed except the issue's own tests):**
`python -m pytest -q tests -m repo_scan` · `python -m pytest -q -c pytest-app.ini tests_app -m repo_scan` ·
the interface gate as the runbook describes · the ruff ratchet check · `npx vitest run` on the touched front-end
test files. These gates were skipped all day on 23 Nov and blocked the push three times: they are not optional.

**6b. At the end of every part, before the push, in this order:** regenerate the generated files and commit;
`python scripts/reply_inventory.py --check`; the OpenAPI drift test; `coverage.py --check` (the requirement and test
coverage map); `npx vitest run` (whole front end, once); every database test file the part touched, in one pass;
`python tools/ci_local.py`; `python scripts/orchestrator/prepush.py`. All green, then push. A gate is never bypassed,
an allow-list or a ratchet baseline is never edited to make it pass, a gate test is never weakened.

**Verification rules that apply** (blast radius decides depth): a helper's "green" is a claim: rerun the test or read
the result line before relaying it; every computed number a trader reads is checked by hand arithmetic on the real case
in the issue (the 23 Nov hand checks are in the issue list); every bug fix answers "why was this missed" and checks
sibling places for the same class; every claim of done ends with a table `| Claim | Evidence (command + result line) |`.

## 7. Status: the ledger and the tracker

- **Ledger (always):** `docs/process/ic-live-test-2026-11-23-status.md`, one row per issue D-01 to D-71:
  `| Id | Status | Part | Commits | What changed (one plain line) | Proof (test + result line) | Screen check owed |`.
  Create it in Part A from the handover and the issue list. Update the row at every stage change, same commit as the
  work where possible.
- **Tracker (if reachable):** the owner's private tracker page is given in the launch message, not in this repository.
  If the session has the artifact database tool, update the issue's row at every stage change (`get` the row first,
  pin the version, merge fields; never republish the page): `status`, `fix_notes` (plain words: what was wrong, what
  changed, proof, what is not tested), `branch`, `root_cause`, `updated_at` (from the clock). If the tool is absent or
  a write is refused, write nothing there, say so once in the progress log, and keep the ledger exact: a PC session
  will copy it over.
- **Allowed status values:** `Open` · `Root cause found` · `Fix in progress` · `Fix built, in review` ·
  `Fixed, not tested` · `Needs owner decision` · `Parked` · `Could not reproduce` · `Not a defect` ·
  `Feature request (parked)`. Never `Closed`, never `Fixed, verified`: those need a screen check on the owner's PC.
- A status of `Fixed, not tested` may carry only what a screen check or live market would add. Anything else left
  open means the issue is not fixed: use `Fix in progress` or `Parked` and say what is left.

## 8. Budgets and halts

- Per issue: two rounds (section 3). Per helper brief: a line `Budget: <N> min wall-clock, <M> tool calls`, targeted
  tests only, long output to a log file with only the tail read, report under 300 words with an evidence table.
- Helpers: mechanical work on the cheapest model that can do it; building and reviewing on a mid model; the strongest
  model only for money and order maths or a design that failed once. The main session routes, verifies and records.
- Hand over at a part boundary: one part per session. Context getting long is not a reason to stop early or to call
  unfinished work done: write a continuation note in the progress log and finish the issue in hand.
- **Hard halts only:** section 2 step 5; a dependency that cannot be installed; a contradiction inside these contracts;
  a gate that stays red after the issue causing it was reverted; a missing credential. Everything else: park the
  issue and continue.

## 9. Guardrails (never)

- No real order, no broker call, no Kite login, no change to real-order code paths beyond what an issue names
  (real orders are frozen, ADR-281). No deploy. No production or staging host.
- No new dependency. No database migration unless the issue cannot be fixed without one; then park it with the reason.
- No account figure (funds, margin from the broker, account P&L) and no other project's name in any file: this
  repository is public.
- No edit to kit files (list in `.claude/kit/GUIDE.md`) or to legacy repositories.
- No fabricated data, no number filled with a plausible default: "not measured" with the command that would measure it.
- Not built in this chain (owner, 24 Nov): D-34, D-35, D-48, D-51, D-62. Their ledger rows read
  `Feature request (parked)` with the 23 Nov observation.

## 10. Final report of each part (committed as `docs/process/GC-ICLIVE-<part>-report-2026-11-24.md`, and in chat)

Plain words, short sentences. Per issue: what was wrong, what changed, how it is known to work (test + result line),
what is not tested and why, the screen check owed. Then: skipped (already done) list; parked list with next steps;
decisions taken pending the owner's read; owner questions written; gate result lines of 6b; the pushed commit; and a
`DONE / PENDING / BLOCKED / PARKED / NEXT` summary naming the next part's launch line.
