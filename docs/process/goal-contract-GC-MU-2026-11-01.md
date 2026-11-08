# Goal contract GC-MU: multi-user foundation steps 1-4 + GC-ADJ3 rest, side by side with GC-SET (2026-11-01)

Approved scope (owner, 2026-10-31 ~23:45 IST, question tool): "Foundation 1-4 + GC-ADJ3 rest". Product answers:
ADR-230 (Q-ADJ3-2..5). Coordination rule (owner, 2026-11-01 ~00:00): both goal sessions keep working, nothing blocks,
the sessions talk to each other, overlaps are settled when the branches merge. Run it with `/goal` from the run tree
in §0.1. Suggest-only stays (ADR-003): no order is ever placed.

Core: one option's figures computed once per price update and read by every strategy, with a cache key that cannot
drift from what the engine reads (REQ-050 AC-1/AC-3, issue #519).
Proof: step 1 - 1,000 strategies on the same NIFTY strike fed the recorded ticks: engine call count = 1 per update;
and the 40-mutant key script: 0 non-redundant survivors.

## Owner decisions behind this contract (the run never re-asks them)

- **Nothing to `main`.** Every change stays on `build/gcmu` and later `feature/adjustments`. No PR to main, no push to
  main, ever, without the owner's new explicit approval (rule 2026-10-30; the 10-31 approval was withdrawn, PR #622).
- Do not interfere with GC-SET (owner 2026-10-31 and 2026-11-01): the protocol in
  `D:\Abhay\Ventures\OptionsForOptions2-coord\PROTOCOL.md` is binding for this run; read it at step 0.
- ADR-220 (server roles api / maths / user orders / liveprices / background; one machine first; four speeds +
  safety valve; pricing model kept; Greeks from our engine). REQ-164, REQ-165, REQ-125 Approved 10-31; REQ-166.
- The foundation order: `docs/process/multi-user-foundation-plan-2026-10-31.md` (steps 1-4 here; 5-7 later: step 5
  needs sign-in, which is not built).
- ADR-230: liquidity limits flag + refuse roll ("OI not known" live); "N adjustment opportunities" card mark; Compare
  rows "Cost as % of premium left" + "Change in max profit", charge breakdown on tap; two stops = whichever first.
- ADR-221 (T-19 = cheapest approach's cost) and ADR-222 (calculation numbers are admin settings) are GC-SET's to
  build. This run uses them through MERGE-SWAP stand-ins (PROTOCOL P4.3), never builds them.
- Test data (owner 2026-10-30): proofs on the generated scenario library + one real-chain anchor; no captured Kite
  quotes in the repo. Browser steps in the owner's visible Chrome (Claude-in-Chrome), never headless.

## §0.1 Where the run works

- Run tree `D:\Abhay\Ventures\OptionsForOptions2-gcmu`, branch `build/gcmu` (created 2026-10-31 from
  origin/feature/adjustments 554035b5; ADR-230 at 4b41da80; this contract on top). Builders: worktrees via
  `~/.claude/tools/wt-new.ps1 -Base build/gcmu`, branches `build/gcmu-<item>`, merged back into `build/gcmu` by the
  builder's reported sha (memory: merge builders by sha).
- First, in the run tree: `~/.claude/tools/wt-link-modules.ps1` failed at creation (the main checkout has no
  `frontend/node_modules`). Fix: `npm ci` in `<run tree>/frontend` (log to a file, tail only), under the heavy slot.
- Dev servers for this run: API on 8100, web on 5273 (`OFO_API_TARGET=http://127.0.0.1:8100`, vite
  `--port 5273 --strictPort`). Never 8000/5173 (GC-SET's). Refuse a busy port; kill only own PIDs.

## §0.2 Preflight (never redo finished work)

- `python D:\Abhay\Ventures\OptionsForOptions2-coord\coord.py inbox GC-MU` and `status`.
- `git -C <run tree> log --oneline -5`; read §0.3 below; a step marked DONE is not redone.
- Read before code: PROTOCOL.md; ADR-220, ADR-230, ADR-221, ADR-222, ADR-008, ADR-003, ADR-053, ADR-068, ADR-078;
  REQ-048, REQ-050, REQ-113, REQ-115, REQ-155, REQ-156, REQ-159, REQ-161, REQ-162, REQ-165, REQ-166; issues #519,
  #517, #520; `work/W-136.md`, `work/W-134.md`, `work/W-137.md`; `spec/findings.md` F-59, F-77, F-78;
  `knowledge/findings/` grep for every key term of the step.
- Read GC-SET's plan to stay off its lines: `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings\docs\process\goal-contract-GC-SET-2026-11-01.md`
  (read only) and `git log build/settings` / `git diff 554035b5..build/settings --stat` at every step start.

## §0.3 Progress log (the run appends one line per step: time from `date`, sha, proof line)

- step 0 (contract written) 2026-11-01 ~00:00 IST.

## Coordination duties (every step; PROTOCOL.md is the full text)

- Check points: start of each step, before each dispatch, before each heavy job, before each merge:
  `coord.py inbox GC-MU` + `coord.py status`; answer every message in the same step (`coord.py send GC-MU GC-SET ...`
  and, if the other session is listed by `ListAgents`, also `SendMessage`).
- Heavy jobs (prepush --full, full vitest/e2e, `npm run build`, `npm ci`, dev servers + browser proof) only under
  `coord.py take-heavy GC-MU <job>`; busy or < 4 GB free -> do the next light item, retry at the next check point.
  Release immediately after.
- At most 2 builders at once; `coord.py mem` under 3 GB -> no new dispatch, message GC-SET, light work.
- Every change to a shared file (PROTOCOL P4 list, or any file in `git diff 554035b5..build/settings --stat`) gets a
  ledger line in `D:\Abhay\Ventures\OptionsForOptions2-coord\overlaps\GC-MU.md` and one message to GC-SET.
- New logic in new files; shared files get thin call sites. Stand-ins for GC-SET work carry `# MERGE-SWAP(GC-SET): ...`.
- Ids only from GC-MU ranges: ADR-230..239, F-90..99, REQ-180..189, scenarios ADJ-50..ADJ-69, migrations 0040..0049
  (avoid; if needed `down_revision` = newest on build/settings, announced). Migration/DB tests via
  `scripts/orchestrator/db_run_fresh.py`; `ofo_dev` ahead of the branch -> mirror only those migration files (P6).
- `coord.py note GC-MU "<step N started/done, files in play>"` at each step start and end.

## Steps

Order: steps 1, 2, 3 and A (GC-ADJ3 work) can run in parallel (max 2 builders at once); step 4 after 3; step 9 last.
Each step opens with its core proof. At most 2 fix rounds per step, then PARK (issue labelled `parked`, evidence, what
is left) and move on (run discipline B1). Briefs carry `Budget:`, `Report: evidence-table`, `Core:`/`Proof:`, the
kit's builder-brief standing items, `python scripts/orchestrator/check_brief.py` passes, and a `Sensibull:` line.

| Step | What | Done when (proof) | Review |
|---|---|---|---|
| 1 (core) | #519 / REQ-050: build each shared-compute cache key FROM the exact arguments passed to the engine function (one helper: call -> key + result) in `backend/ofo/marketdata/shared_compute.py`; one parametrized test on the recorded snapshot changing ONE input at a time; T1: a frontend test/lint rule failing on arithmetic over price/P&L/quantity fields outside named drawing exceptions; T2: check `frontend/src/lib/guided.js` `readingFromRange` against the server rule, record the answer (finding F-9x if the browser holds a rule the server lacks) | 1,000 strategies on one strike, recorded ticks: engine calls = 1 per update; 40-mutant script re-run: 0 non-redundant survivors; T1 test red on an injected `a.pnl + b.pnl`, green after; #519 closed with the evidence | Tier A (fresh Opus, adversarial, mutation) |
| 2 | #517 / REQ-048 AC-5 redesign: a fresh independent designer (Opus, not a builder or earlier verifier) reviews the plan first; then a checked-in INVENTORY of every response field path generated from the response models, asserted both ways; bundle inputs only from a reviewed `VITE_*` list; the text scan stays as a second layer with exact URLs and IP literals refused | Each of round 2's escapes (`token`, `auth_token`, `secret`, `kite_session` reply fields; `enc_token`, bare-IP URLs, prefix traversal) now fails a test; a new response field fails until added with a reviewer note; #517 closed | Tier A |
| 3 | W-137 / REQ-113 finish: re-run the core proof (`tests_app/test_feed_restart_core.py`) on the head; fix #520's MINORs (ended status vs real store, DB outage at 06:00 keeps the socket, isolation test without DB); name the `liveprices` role in code (start command, folder or module name, settings key) per ADR-220 (1) | Core test green on the head; one test per #520 item red-then-green; `python -m ofo_app.<liveprices entry>` starts the feed process; W-137 -> done; #520 closed | Tier A (live data) |
| 4 | REQ-115 workers + REQ-165 + REQ-166: the `background` role process; playbook triggers checked on fresh prices, at most once a second per strategy, with no screen open, as light sums of the shared per-option figures (never the full table); the four speeds (a)-(d) read through ONE function in a new module with defaults 1 s / 1 s / 1 s / on-open, `# MERGE-SWAP(GC-SET): read from the settings store` (GC-SET's registry adds the Speeds group; message GC-SET the four keys and defaults); safety valve 1 s -> 2 s -> 5 s and back, every screen shows "as of"; nothing recomputed with the market closed; workers rebuilt after a restart, paused on stale data, never place an order | Core: scenario ADJ-02 through the worker, no browser connected: one opportunity record within 1 s of the price; valve test: an injected slow maths step drops the speed to 2 s then 5 s and back to 1 s, the "as of" time is shown; a restart test rebuilds the workers; a stale-feed test pauses them | Tier A |
| A1 | ADR-230 (1) / F-78: liquidity limits applied in a new module (e.g. `backend/ofo/adjustment/liquidity.py`); strikes breaking the OI or spread limit flagged "Below your liquidity limit" in the adjust drawer and Compare, never hidden; a roll over "Most debit paid for one roll" refused with the catalogue reason; live strikes with no OI source shown "OI not known"; a test that every playbook guard key has a reader | Scenario ADJ-5x with a thin strike flags it; a roll over the limit is refused with the reason; live-mode test shows "OI not known"; class `setting-saved-but-never-applied` -> guarded (only for the three limits; GC-SET owns the rest) | Tier B |
| A2 | ADR-230 (3): Compare rows "Cost as % of premium left" and "Change in max profit", charge breakdown (brokerage, STT, exchange, GST, stamp) on tap under the cost row; figures from the one engine (ADR-008) in a new module; the cost input is today's `compare.py` "This adjustment" cost through a stand-in `# MERGE-SWAP(GC-SET): ADR-221 one cost function`; wording pinned and screened (ADR-003) | Values equal the generator's engine-free figures on ADJ-02 / ADJ-13 to the paisa; owner's Chrome screenshot of the rows and the open breakdown | Tier B |
| A3 | ADR-230 (2): Live Strategies card mark "N adjustment opportunities" linking to that strategy's inbox row; dismissing the row clears the mark; count from the existing suggestion records (REQ-112, REQ-162) | Owner's Chrome, scenario ADJ-02: the card shows the mark; dismissing in the inbox clears it | Tier B |
| A4 | ADR-230 (4): two stops with no rule = "whichever comes first"; plan sheet and summary show both values; trigger behaviour unchanged | Plan sheet and summary on a playbook with both stops show both; trigger tests unchanged and green | Tier B |
| A5 | Leftovers: "Adjustments used" on the Compare fed from the GC-ADJ2 history count (today "-", `adjustment_readers.py:109-112`); phone width 390 px checked in Chrome for Compare, editor, inbox | Compare shows the count on ADJ-13; 390 px screenshots, no clipped table | Tier C |
| T3 | ADR-220 (4) Greeks comparison with the reference product on one real NIFTY chain (theta gap above Rs 5 per lot per day goes to the owner with the real numbers) | Needs market hours and the owner's Kite login: run at the first market session the owner is present (Mon 2026-11-03 09:15 IST earliest); until then it is listed as PENDING, not parked, and blocks nothing | - |
| 9 | Close: merge and finish per PROTOCOL P9. If GC-SET has merged into `feature/adjustments`: merge it into `build/gcmu`, resolve with both overlap ledgers, swap every MERGE-SWAP stand-in (speeds -> settings store, A2 cost -> ADR-221 function), regenerate generated files, re-point any migration, run the tests of every overlap file, then `prepush.py --full` (heavy slot) TOTAL PASS, then `git merge --no-ff build/gcmu` into LOCAL `feature/adjustments`, push `feature/adjustments` to origin as backup (prepush marker). If GC-SET has NOT merged yet: do not touch `feature/adjustments`; `prepush.py --full` on `build/gcmu`, push `build/gcmu` to origin as backup, write the integration as NEXT in the handover | Pass record for the head sha; `git log feature/adjustments` shows the merge (or the handover names the pending integration); no PR, nothing on main | none (gates) |

## Failure budget and stops

- 2 fix rounds per step, then park and move on. A second red of the same class gets an independent reviewer first
  (owner rule 2026-09-17), then the third round is built around its findings.
- Genuine stops only: a credential only the owner holds, spend, a production deploy, an irreversible act, a true
  product fork. Owner away: never ask; write the question to `docs/process/owner-questions-2026-11-01.md` with a
  recommendation and continue. Anything from GC-SET is never a stop (PROTOCOL P1).
- No prod deploy, no VPS runs (production host). DB tests: one targeted file at a time or `db_run_fresh.py`.

## Definition of Done (every box, literally)

- [ ] Steps 1-4 DONE or PARKED with an issue; A1-A5 DONE or PARKED; T3 DONE or listed PENDING for the next market day.
- [ ] Core proof of step 1 recorded with the engine call count and the mutant survivor count.
- [ ] Step 4 core: an opportunity record with no browser connected, within 1 s, recorded.
- [ ] Every shared-file change has a ledger line; every MERGE-SWAP is listed in the ledger; GC-SET was messaged for
      each new overlap and every GC-SET message got a reply (`coord/log.md` shows both directions).
- [ ] Heavy jobs ran only under the slot (`coord/log.md`); no process of GC-SET was touched.
- [ ] Findings, decision rows and failure classes registered the turn they were proven (F-90..99, ADR-231..239).
- [ ] Step 9 done per its branch; `prepush.py --full` TOTAL PASS on the final head; nothing on main; no PR.
- [ ] Handover `docs/process/session-handover-2026-11-01-gcmu.md` (DONE / PENDING / BLOCKED / PARKED / NEXT) and memory
      note updated; worktrees whose use ended removed with `wt-rm.ps1` (proof counts printed).

## Final report (the run's last message)

Evidence table (claim | command run this turn + result line), the parked list with issue numbers, the overlap ledger
summary (files, MERGE-SWAPs left), what GC-SET was told, and NEXT (the integration merge if pending, T3 on the next
market day, foundation steps 5-7 after sign-in).

## Known facts the run must not re-discover

- `shared_compute.py` and the feed process (`feed_main.py`, `feed_bus.py`) are already on this branch (chunk 1, #525).
  #519 and #517 list exactly what is left; do not rebuild what they say stays.
- `dev_run.py` refuses any database but `ofo_dev`; `db_run_fresh.py` makes and drops a throwaway database.
- `low_oi_blocked` has no live source (F-78); live OI state is "not known".
- Wording changes run `tests/strategy/test_templates.py` and `scripts/ruff_ratchet.py` (REQ-028 AC-5).
- `git show <ref>:<path>` needs `MSYS_NO_PATHCONV=1` in Git Bash on this PC.
- prepush --full gets killed by Claude Code's low-memory reaper when the PC is short on memory: take the heavy slot.
