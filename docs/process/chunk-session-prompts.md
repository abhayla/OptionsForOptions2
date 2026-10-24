# Builder-sequence session prompts, chunks 3B to 8

Written 2026-10-24 (session f1b75d11) at the owner's request. Each chunk runs as two fresh sessions:

- **Session A** builds the rows whose core proof needs no live market. Any day works.
- **Session B** builds the rows whose core proof needs a market day and a Kite login, then closes the chunk.

Each session is a fresh `/goal` and stops at its own handover, so no session runs more than about 3-5 rows (ADR-178
change 1a). Rows and tiers come from `docs/process/builder-sequence-2026-10-22.md`.

**Before using a prompt:**
- Read the newest handover block first. If it changed a rule or reordered the rows, it wins over this file; edit the
  prompt to match.
- Session order: 3B, 4A, 4B, 5A, ... If no market day is free, the next chunk's session A may run before the current
  chunk's session B. A chunk still closes only in its own session B.
- Market hours: NSE 09:15-15:30 IST on trading days. Start a session B at about 09:00, so the owner's Kite login is
  done before the open.

## Common rules (every session A and B below)

Learned in chunks 1-2. Measured in `docs/process/row-review.md` and issue #532.

1. **Gate command first.** Every builder and checker runs the ADR-181 local gate command and pastes its last 5 lines,
   including `GATE PASS <sha>`. A PASS report without them is not a pass. The orchestrator runs it before every push
   and pushes only after `GATE PASS`, chained with `&&`. Never push while an App-tests run of the branch is in progress,
   unless the push fixes a red.
2. **Dispatch command only.** Briefs go out through the ADR-181 dispatch command: make_brief, check_brief,
   copy_from_check, overlap_gate. Every brief carries:
   - `Core:` / `Proof:`. Step 1 is the core proof on real input, or on a recorded real fixture.
   - `Spec basis:` with verbatim quotes.
   - `Sensibull:` with screen numbers and the hit count from a grep of
     `D:\Abhay\Ventures\competitors\sensibull\2026-10-21`.
   - `Copy from:`, `Budget:` and `Report: evidence-table`.
   - The C4 standing items a-d.
   - The coding-standards line: "no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not
     rise; targeted tests only; no regenerated files in the PR".
3. **Size rows to the budget.** Split a row into backend and frontend parts at brief time, so each part fits about 60
   tool calls. Builders overran 14 times in chunk 2; nothing enforces this rule yet.
4. **Checkers.** The brief says "check against the REQ/ADR text, not this brief; hands-on attacks first". Dispatch a
   checker only when no builder must commit and the orchestrator is not about to push: a running checker blocks
   commits in every worktree.
5. **Defect classes from chunk 2.**
   - A new answer state or enum: the brief lists every reader found by grep, plus an e2e test.
   - Twin tests use the smallest realistic shape (one leg priced, one not).
   - Test fakes are built from the real class or server. Playwright socket fakes use
     `frontend/e2e/support/echoSeq.ts`.
   - The brief's file list comes from a grep of the call chain. A checker confirms the real values are not null on a
     recorded fixture.
6. **Reviews.** At most 2 rounds. Round 2 checks round 1's findings only. A MAJOR after round 2 on Tier A code means an
   independent Opus redesign, or park the row with an issue (ADR-106 rule 5).
7. **Records.** Findings go into `knowledge/findings` the same turn they are proven; a second occurrence of a class
   means its mechanism is due. Each chunk has one deferred issue. Generated files stay out of feature PRs.
8. **Owner.** Never wait on owner answers. Questions go to `docs/process/owner-questions-<date>.md` with a
   recommendation. Business calls only.
9. **Landing.** Land each batch as soon as it is green: a PR under 300 files through `PYTHONUTF8=1 python
   scripts/orchestrator/merge.py <pr> --reviewed-sha <full sha>` (ADR-180). Run `npm ci` in every new worktree. Remove
   each worktree with wt-rm when its PR merges.
10. **Session end.** Write a handover block (DONE / PENDING / BLOCKED / PARKED / NEXT) and update the memory note.
11. **Live proofs.** Use `scripts/orchestrator/dev_run.py` (database `ofo_dev` only). The Kite login happens once, in a
    private window, from the cached daily token. Never click inside a live order panel. Use options only and never sell
    holdings; the owner presses Execute.

## Chunk 3

### Chunk 3 - session A (any day)

```
/goal OptionsForOptions2 builder-sequence chunk 3, SESSION A, under ADR-178, ADR-180 and ADR-181, following the Common rules in docs/process/chunk-session-prompts.md. Start from the "UPDATE chunk 2 LANDED" block of docs/process/session-handover-2026-10-22-builder-sequence.md. Use one branch per batch, off main. Common rules 1-2 apply from the moment PR 1 merges.
(1) PR 1: the two ADR-181 tools, before anything else.
 (a) Gate command. Runs: ruff ratchet; guard tests; pytest -m repo_scan; the whole tests/errors; tests/orchestrator; every DB-free file select_app_tests.py selects; OpenAPI regenerate-and-compare; money guard; frontend lint + format:check + changed Vitest files; coverage --check; reach_check --root .; reference_register --check; findings index --check. Stops on the first failure (select_app_tests exit 3 included). Ends with a fixed "GATE PASS <sha>" line. Refuses a push while an App-tests run of the branch is in progress, unless the push fixes a red.
 (b) Dispatch command. Renders the brief with make_brief.py, runs check_brief.py, copy_from_check.py and overlap_gate.py. Refuses a third fix round of the same row. Prints the worktree setup steps, npm ci included.
 Sonnet builds. Opus checks at Tier A, with one mutation test per step (break the step and the command must fail).
(2) PR 2: the #532 C mechanisms, as repo guard tests (not process tools).
 C1: a test that fails when a Playwright test answers **/api/strategies/live without frontend/e2e/support/echoSeq.ts.
 C2: the all-routes order-closure guard (Tier A).
(3) PR 3: rows 27 (REQ-135, Tier A), 29 (REQ-134, Tier B), 28 (REQ-070, Tier B), in that order. Run 27 and 29 in parallel only if overlap_gate passes. 28 waits for 29 (same save path).
Stop condition: PR 1, PR 2 and PR 3 merged with CI green (or a row parked with an issue), and a "chunk 3 session A END" handover block on main. Session B does rows 25, 26 and the chunk close.
```

### Chunk 3 - session B (market day)

```
/goal OptionsForOptions2 builder-sequence chunk 3, SESSION B, under ADR-178, ADR-180 and ADR-181, following the Common rules in docs/process/chunk-session-prompts.md. Start from the "chunk 3 session A END" block of docs/process/session-handover-2026-10-22-builder-sequence.md.
(1) Row 25, margin check (REQ-055). Step 1 is the core proof: a real Zerodha basket-margin call for a real 2-leg NIFTY plan through the product path, on today's token. The owner logs in once in a private window if no token is cached. Output is read back and recorded.
(2) Row 26, money summary (REQ-081). Check branch W-127's code against REQ-081 and the Sensibull study before reusing any of it.
(3) Chunk close: reference copy; one chunk Tier A review (at most 2 rounds); conformance check, recorded in docs/process/adr-178-tracker.md (rows 1-6 and 10 stay unmeasured: #532 F, measuring-script fix proposed as chunk 4's one process item); one deferred issue for chunk 3; handover block; memory note.
Stop condition: rows 25 and 26 merged (or parked with an issue), the chunk close done, and the handover on main.
```

## Chunk 4 (rows 30-35)

### Chunk 4 - session A

```
/goal OptionsForOptions2 builder-sequence chunk 4, SESSION A, under ADR-178 and ADR-180, following the Common rules in docs/process/chunk-session-prompts.md. Start from the newest block of docs/process/session-handover-2026-10-22-builder-sequence.md.
(1) This chunk's one process item (ADR-178: one per chunk, on Sonnet): fix scripts/orchestrator/measure_process.py so it reads the right transcript folder (#532 F), proven on chunk 3's transcripts, so the tracker's rows 1-6 and 10 can be measured.
(2) Rows 30 (Shift / Width / Hedge, REQ-078, Tier A; check branch W-126's code against the spec before reuse), 31 (warnings and "How this trade works", REQ-085, Tier A), 32 (figure definitions and the projections note, REQ-136, Tier B). Run two at a time only where overlap_gate passes.
Stop condition: the item and the rows merged (or parked with an issue), and a "chunk 4 session A END" handover on main.
```

### Chunk 4 - session B (market day)

```
/goal OptionsForOptions2 builder-sequence chunk 4, SESSION B, under ADR-178 and ADR-180, following the Common rules in docs/process/chunk-session-prompts.md. Start from the "chunk 4 session A END" block of docs/process/session-handover-2026-10-22-builder-sequence.md.
(1) Row 33, option chain display and live data (REQ-029, Tier A). Step 1 is the core proof: the live NIFTY chain for the nearest expiry through the product path, with live ticks moving, read back and recorded.
(2) Row 34, pick legs from the chain into the builder (REQ-030, Tier B), and row 35, live strategy preview (REQ-031, Tier A). Check PR #509's code against the spec before reusing any of it.
(3) Chunk close, as in chunk 3 session B (the conformance check now measures every tracker row).
Stop condition: rows 33-35 merged (or parked with an issue), the chunk close done, and the handover on main.
```

## Chunk 5 (rows 36-42)

### Chunk 5 - session A

```
/goal OptionsForOptions2 builder-sequence chunk 5, SESSION A, under ADR-178 and ADR-180, following the Common rules in docs/process/chunk-session-prompts.md. Start from the newest handover block. Every row here is Tier A engine or money code: use the options-math-review skill in every brief and check.
Rows 37 (what-if level/date/IV and the Greeks panel, REQ-084; it also completes W-150 AC-6's what-if part), 38 (payoff table and SD table, REQ-137), 39 (manual P&L entries, REQ-089), 40 (builder settings saved per user, REQ-138). Check branch W-127's code against the spec before reusing any of it. Core proofs run on the recorded real frames (tests/fixtures/kite_ws).
Stop condition: the rows merged (or parked with an issue), and a "chunk 5 session A END" handover on main.
```

### Chunk 5 - session B (market day)

```
/goal OptionsForOptions2 builder-sequence chunk 5, SESSION B, under ADR-178 and ADR-180, following the Common rules in docs/process/chunk-session-prompts.md. Start from the "chunk 5 session A END" block.
(1) Row 36, payoff chart extras: "now" curve, hover, SD bands, OI bars (REQ-083). Core proof: live OI and the "now" curve moving on live ticks.
(2) Row 41, header with the day's change and OHLC (REQ-139). Row 42, market context strip: ATM IV, PCR, max pain, VIX (REQ-106). Each core proof shows live values read back against Kite's own numbers at the same minute.
(3) Chunk close, as in chunk 4 session B.
Stop condition: rows 36, 41 and 42 merged (or parked with an issue), the chunk close done, and the handover on main.
```

## Chunk 6 (rows 43-52) - ten rows, so session A is split in two

### Chunk 6 - session A1

```
/goal OptionsForOptions2 builder-sequence chunk 6, SESSION A1, under ADR-178 and ADR-180, following the Common rules in docs/process/chunk-session-prompts.md. Start from the newest handover block.
Rows 43 (private notes, REQ-111), 44 (share a read-only link, REQ-086), 45 (option chain display options, REQ-087), 47 (guided strategy creation, REQ-024), 48 (expected market range input, REQ-026). All Tier B.
Stop condition: the rows merged (or parked with an issue), and a "chunk 6 session A1 END" handover on main.
```

### Chunk 6 - session A2

```
/goal OptionsForOptions2 builder-sequence chunk 6, SESSION A2, under ADR-178 and ADR-180, following the Common rules in docs/process/chunk-session-prompts.md. Start from the "chunk 6 session A1 END" block.
Rows 49 (strategy preferences, REQ-068), 50 (strategy discovery, REQ-025), 51 (strike selection modes, REQ-027), 52 (suggested setups, REQ-069). Rows 51 and 52: build only the parts Q211 does not hold. If Q211 is still open, the held part stays held and is named in the handover. All Tier B.
Stop condition: the rows merged (or parked with an issue), and a "chunk 6 session A2 END" handover on main.
```

### Chunk 6 - session B (market day)

```
/goal OptionsForOptions2 builder-sequence chunk 6, SESSION B, under ADR-178 and ADR-180, following the Common rules in docs/process/chunk-session-prompts.md. Start from the "chunk 6 session A2 END" block.
(1) Row 46, adds BANKNIFTY and FINNIFTY (REQ-090, Tier A; also closes REQ-001 AC-1). Step 1 is the core proof: live instruments, chain and spot for both indices through the product path, and lot sizes and freeze limits read from Kite's instrument list, not typed.
(2) Chunk close, as in chunk 4 session B.
Stop condition: row 46 merged (or parked with an issue), the chunk close done, and the handover on main.
```

## Chunk 7 (rows 53-54) - one market-day session

```
/goal OptionsForOptions2 builder-sequence chunk 7, under ADR-178 and ADR-180, following the Common rules in docs/process/chunk-session-prompts.md. Start from the newest handover block. Market day.
(1) Row 53, start tracking with paper P&L (REQ-109, Tier A). Step 1 is the core proof: a tracked strategy's paper P&L updating on live ticks, checked by hand against the engine for one minute's prices.
(2) Row 54, profit left and loss left for a tracked strategy (REQ-140, Tier A).
(3) Chunk close, as in chunk 4 session B.
Stop condition: rows 53 and 54 merged (or parked with an issue), the chunk close done, and the handover on main.
```

## Chunk 8 (rows 55-63)

Most of chunk 8 is held:
- rows 55-56 by Q211;
- row 58 until REQ-016 is approved;
- rows 60-61 for display rights;
- row 62 for a data source.

Before this chunk starts, the owner is asked (business call) which holds are released. A held row stays held.

### Chunk 8 - session A

```
/goal OptionsForOptions2 builder-sequence chunk 8, SESSION A, under ADR-178 and ADR-180, following the Common rules in docs/process/chunk-session-prompts.md. Start from the newest handover block.
Rows 57 (market-data sourcing and licensing, REQ-052, Tier B) and 59 (historical price storage, REQ-051, Tier A, with its own migration PR). Also every held row 55, 56, 58, 60, 61, 62 that the owner has released, in table order. A held row stays held and is listed in the handover.
Stop condition: the buildable rows merged (or parked with an issue), and a "chunk 8 session A END" handover on main.
```

### Chunk 8 - session B (market day: the live close-out, row 63)

```
/goal OptionsForOptions2 builder-sequence chunk 8, SESSION B (row 63 close-out), under ADR-178 and ADR-180, following the Common rules in docs/process/chunk-session-prompts.md. Start from the "chunk 8 session A END" block. Market day, owner present for the Kite login and for pressing Execute.
(1) Collect every "live check pending" criterion across rows 1-62 (grep the work items, evidence and handover blocks). Plan entry AND exit for each through the product path, and validate each probe on a known-good state first.
(2) Prove each one in one live window, recording evidence through the verifier.
(3) Chunk close and the builder-sequence close: the final 63-row table, the open deferred issues triaged per ADR-107, and the handover for the next contract (adjustments including REQ-037, alerts, import).
Stop condition: every live check proven or parked with an issue, and the close-out handover on main.
```
