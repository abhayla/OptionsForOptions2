# Session handover - builder walkthrough, then the Sensibull redesign (2026-10-26 19:45 -> 2026-10-27 ~07:50 IST)

## DONE
- Walkthrough of the claimed builder requirements started on the real app (log: `docs/process/walkthrough-2026-10-26.md`);
  REQ-080 and REQ-076 checked criterion by criterion, REQ-077 AC-2 in part; 12 issues logged.
- I-4 (leg picker listed no strikes on real data since 2026-10-20): **PR #580 merged** - `stored_chain` passed the
  permission map into `ChainCatalogue.unreadable`; catalogues are kw_only now, real-reader tests for `stored_chain` and
  `stored_futures`. Finding `route-tests-always-override-the-real-reader`.
- Owner stopped the walkthrough for the UI: **ADR-193** (Sensibull layout for every screen the spec has, our brand,
  builder first, walkthrough resumes after), **ADR-194** (P&L Table compact + Full table; REQ-035 AC-1/AC-7 amended),
  **ADR-195** (with a leg left out: count only, no shape name, Width/Hedge disabled - Sensibull 111 under ADR-152).
- UI study `docs/design/ui-study-2026-10-26.md` (+ Revision 1 after an independent review); a private side-by-side page
  sits in the competitors folder next to the Sensibull study (`2026-10-26-ui-study`).
- **PR #581 (builder redesign) OPEN, CI 7/7 green on 6b7992f0, NOT merged**: PR-1 shell (W-191), PR-2a left column
  (W-192), PR-2b summary card (W-193), PR-2c chart card (W-194), PR-2d margin wording, PR-3 strike drawer (W-195),
  checkpoint polish, CI fixes. Local final pass: unit 1,100/1,100, lint, build, guards 954, 15 e2e specs.
- Issues filed: #582 (redesign deferred items), #583 (open walkthrough items I-1, I-2, I-5, I-6, I-12),
  kit Startup-Factory #186 (ci_local runs tests_app under the kit pytest.ini).

## UPDATE 2026-10-27 ~08:15 IST (supersedes PENDING/NEXT below where they differ)
- Owner chose **"Builder first"**: merge #581 (DONE: merged 558b1ff5, CI 7/7), then fix the #582 small defects, then
  during market hours (09:15-15:30, owner Kite login in a private window) resume the walkthrough on live prices and
  re-check I-1/I-6/I-12 (#583), then build the builder's missing Sensibull features: rows 33-35 (option chain into the
  builder), 36-38 (payoff extras, what-if + Greeks, payoff/SD tables), then 40-42. Other screens (PR-4..6) AFTER that.
  Q-UI-1 is answered by this (merge done).
- Main checkout is at 558b1ff5 and clean except this handover and pid.txt. Three edits must be RE-APPLIED on a docs
  branch (never on main) from `D:\Abhay\scratch\ofo2-redesign-2026-10-27\main-backup\`:
  `docs/process/coverage-stages.yaml` (rows `"#582": S6.1`, `"#583": S6.1` - CI coverage fails without them),
  `docs/process/owner-questions-2026-10-26.md` (Q-UI-1 entry + "answered: Builder first, 08:15"),
  `knowledge/findings/local-ci-mirror-runs-a-subset.json` (4th occurrence), then `regen.py` and this handover.
- #582 now has 8 items (comment adds: drawer list bleeds under the footer; strikes print "22150.00").
- Walkthrough-only closing-price harness copy: `D:\Abhay\scratch\ofo2-redesign-2026-10-27\run_api_closing_prices.py`.
- Redesign worktrees to remove with `wt-rm.ps1` (all merged): ui-pr1-shell, ui-pr2a-left, ui-pr2b-summary, ui-pr2c-chart,
  ui-pr2d-wording, ui-pr3-drawer. Stop the servers listed at the end of this file by PID first (8765 is now PID 13744).

## PENDING (owner)
- **Checkpoint answer Q-UI-1** (`docs/process/owner-questions-2026-10-26.md`): 1 merge #581 then the other screens
  (PR-4 option chain/positions/orders/alerts, PR-5 strategy pages/home, PR-6 info pages) - recommended; 2 merge then
  resume the walkthrough (26 requirements left); 3 change the builder first.
- The half-removed worktree `OptionsForOptions2-fix-chain-reader` (PR #580, merged): its factory gate file went with the
  partial removal, so the gate now refuses any command naming that folder until the owner clears the factory's governed
  marker for it (the gate message names the file). Then finish with `wt-rm.ps1`. Main checkout proven intact.
- A Kite login (private window) to re-check I-1, I-6, I-12 live (#583); the 26 Oct session expired 06:00 IST.

## NEXT (session)
1. On the owner's answer: `python scripts/orchestrator/merge.py 581 --reviewed-sha 6b7992f0c2339f92e034edd0195cce76e0d98a53`,
   prove main intact, remove the redesign worktrees with `wt-rm.ps1` (ui-pr1-shell, ui-pr2a-left, ui-pr2b-summary,
   ui-pr2c-chart, ui-pr2d-wording, ui-pr3-drawer).
2. **Mechanism due (4th occurrence of `local-ci-mirror-runs-a-subset`)**: make the pre-push gate run
   `scripts/ruff_ratchet.py` and `scripts/orchestrator/coverage.py . --check` (project wrapper or kit harvest), red-then-green.
3. Uncommitted in the main checkout, goes into the next docs batch: this handover, the #582/#583 stage rows in
   `docs/process/coverage-stages.yaml` (CI coverage fails without them), the finding occurrence in
   `knowledge/findings/local-ci-mirror-runs-a-subset.json` (regenerate the index), the Q-UI-1 owner-questions file,
   `W-191.md`..`W-195.md` copies (already in #581 - drop the main-checkout copies after merge).

## Ways of working agreed tonight (owner)
- Build first, check once at the end: stacked local PRs, builders run only touched tests + lint + build; ONE full unit
  suite, ONE e2e run, ONE combined review, ONE fix round, ONE push (auto-memory `build-first-check-once-at-end`). The
  final pass includes the runbook's pre-push list (ruff ratchet, coverage).

## Servers left running (started this session, stop by PID when done)
API 8765 (closing-price harness, PID 23704), replay API 8001 (PID 10184), vite 5173 (PID 7180), previews 4175 (30092)
and 4183 (30044, serves the redesign build for the owner's look). Harness: scratchpad `run_api_closing_prices.py`.
