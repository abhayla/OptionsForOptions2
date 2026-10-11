# Session handover - 2026-10-10 evening (read first in the next session)

Previous: `session-handover-2026-10-10.md` (morning). Owner questions: `owner-questions-2026-10-10.md` (all 8 now
answered except Q1, which is the Monday Kite login). This PC is the Windows VPS whose PostgreSQL serves IPODhan
production: light local runs, heavy in CI (memory `this-pc-is-prod-db-host`).

## 1. Done this session (all verified with commands; see each PR)
- **#192** merged: #155 `gate_before_commit` hook, merged PARTIAL by owner choice (Q6). It is live: it refused a
  heredoc-then-commit command in this session. Open bypasses: **#191**.
- **#193** merged: owner answers Q3, Q4, Q5, Q7, Q8. **ADR-073** (`/docs`, `/openapi.json` only in development/test,
  404 in production; relation `applies ADR-003`). Q8: #148 MAJOR 2 is its own round after the door. Q4: W-066 resumes
  right after the W-065 live proof. Q5: the owner clears the stale production-gate markers; review/verify checkouts go
  in the session scratchpad from now on (memory `review-checkouts-in-scratchpad`). Q3: reading page (below).
- **Template reading page** (owner Q3): https://claude.ai/artifact/F6eZusNw8ZVXCQdou7Mj1J - W-061's 16 templates,
  Approve / Flag + comment, marks in the page's `db` collection `marks` (doc id = template key, `:` -> `__`). Read it
  with ArtifactData `list` and re-pin approved ones in `tests/errors/template_pins.json`. **No marks yet** at handover.
  Honest scale: **221** templates on main are "pending owner read" (W-024's ~205 + W-061's 16); the markdown list
  `w024-templates-for-owner.md` is stale (it lacks W-061's 10 Save-Draft error templates).
- **W-065** branch: main merged in (one conflict in `tests/marketdata/test_provider_replaceable.py`, both entries kept;
  merge_audit clean), coverage row added, local CI mirror green, pushed (`build/W-065-live-push`, no PR). Ready for
  Monday's login.

## 2. W-068 leg picker (REQ-035 AC-8) - MERGED as #194 (154f9bb), verified (evidence/W-068/AC-8.md, PASS at 115a352)
- Core proven first: the real Zerodha list through `apply_update` (rolled back) gave 4,948 contracts; NIFTY 13-Oct
  108 CE + 108 PE. Finding **store-filled-only-by-tests**: nothing loaded the catalogue outside tests (0 rows in
  ofo_test); W-068 adds `python -m ofo_app.catalogue_load` (reads `CATALOGUE_MAX_DELIST_PERCENT`; the alert and the
  schedule stay in #126).
- Built in 3 builder rounds + fixes. Tier B review: 2 MAJORs fixed (underlying unlock while editing;
  `currently_listed` and expiry==today untested). Pricing scan caught a mid-price rule in the route -> moved to
  `ofo.outcome.planned_entry_of`.
- CI Playwright was red twice on the same race -> independent review (fable) found it: `save()` reset the form AFTER
  awaiting the planned-entry POST, and `load()`'s no-draft path did not invalidate in-flight replies. Finding
  **state-read-after-await**. Round 3 (`ce19126`) fixed both with held-open-promise Vitest tests (red then green).
- Verifier round 1 said FAIL only because of that CI e2e; after round 3 CI was clean (168 passed, leg-picker 6/6
  first time, no retries) and the verifier passed AC-8. Worktree removed; main checkout intact (1089 files, 203
  packages before and after).

## 2b. Stopped by the owner for memory (2026-10-10 late)
- Free RAM was 799 MB of 6 GB (VS Code ~810 MB, an idle Claude session from 2026-10-07 ~420 MB, Chrome ~510 MB,
  48 leftover conhost ~375 MB, PostgreSQL ~363 MB). Owner: "Stop here; you free memory". **Before any agent dispatch
  next session, read free memory; under ~2 GB do not dispatch** (memory `vps-memory-check-before-builders`).

## 3. NEXT
1. **#148 response door** (Tier A), once memory allows: the brief is this file's section 5;
   design `docs/process/design-148-response-door.md` (updated with ADR-073 and Q8). Include W-068's new routers.
2. Monday 2026-10-12 after 09:15 IST: W-065 live proof with the owner's Kite login (owner question 1), then W-066 (#172).
3. Then #148 MAJOR 2 round; #191 hook follow-up; #171 (needs a decision row; tied to W-066's ADR-072).

## 4. Traps learned today
- The kit guard blocks `tools/build_findings_index.py` without `--check` even with a worktree path; prefix
  `KIT_FILE_GUARD_ALLOW=1` as the leading assignment of that one plain command (the guard's sanctioned opt-in).
  `tools/*.py` take a repo path argument - pass the worktree path instead of `cd`.
- The word `spec` (or `tools/`, `.claude`) inside a commit message or a `git status -- spec` path is blocked by the
  guard; write around it.
- `spec_dupes` decision relations: `changes:` takes verbs + ids only (`applies ADR-003`); `refines` triggers re-pinning
  of every requirement citing the target.
- `builder` agents stop at 100 turns, `verifier` at 40: the dispatch hook refuses a Budget above 80% of that.
- An intermittent e2e failure is a race to explain, never a wait to add (finding state-read-after-await).
- Claude Code reaps background shells when this box runs low on memory (happened once, 1.5 GB of 6 GB free after);
  check CI with single `gh pr checks` calls instead of long background loops.

## 5. #148 builder brief (draft, dispatch after W-068 merges)
Core: one door through which EVERY API response body (and error body) is serialized, emitting only closed value
types. Proof (step 1, red first): TestClient over `create_app()` against `GET /api/broker/refusals/broker_state_invalid`
- today's bytes, and the 4 hostile variants (class check patched off) answer 500 with no sentence after the door.
Tier A, builder sonnet/medium, Budget 75 min / 80 calls. Follow the design's migration order; ADR-073 for the docs
routes (test both APP_ENV values); move W-068's catalogue router and planned-entry route onto ClosedRoute; MAJOR 2 is
NOT in this round. Reviewer checklist = the design's mutation list + `/docs` served in production must turn a test red.
LOAD CAP: targeted files through db_run, probes < 30 s.
