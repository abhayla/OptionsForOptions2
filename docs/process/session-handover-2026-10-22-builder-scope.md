# Session handover 2026-10-22 08:40 IST (builder scope, run 1 end) - continue with the same /goal prompt

Session ended because its context was full (owner's call). No order was ever sent. Read this first, then the
contract `goal-contract-builder-scope-2026-10-21.md`. Earlier detail: `session-handover-2026-10-21-builder-scope.md`.

## Helper scripts (NOT in the repo; persistent folder `D:\Abhay\scratch\ofo2-builder-scope\`)
- `run_api_live.py` - live API on 127.0.0.1:8765 against ofo_dev, LIVE_MARKET=1, order path off. Start it with
  `python D:\Abhay\scratch\ofo2-builder-scope\run_api_live.py` (background), check `curl http://127.0.0.1:8765/health`
  and `/features` -> `{"order_path":"off"}`.
- `step2_live.py <base-url> build` then `read <near-id> <far-id>` - the Step 2 live proof (near condor: short CE within
  0.5% of spot must detect; far condor 2% away must NOT); hand checks inside; writes a JSON log next to itself.
- `dev_alembic.py <alembic args>` - alembic on ofo_dev as owner (ofo_dev is at 0021_strategy_tracking; run
  `upgrade head` after any merged migration, e.g. A3's 0022).
- `samelines.py <pr> <reviewed-sha>` - is a PR's own +/- diff unchanged since review (SAME -> the head may be the
  reviewed sha); `land_held2.sh <log> < queue` - sequential lander using it.
- `fps.py REQ:AC ...` (ac fingerprints), `pin_adr.py`, `regen_all.py <checkout>` (all 4 generated files),
  `dupes_summary.py <checkout>` (spec_dupes summary), `keep_both.py <file>` (append-only conflict resolve).
- `todo-docs-batch3.txt` - items to file/write in the next docs batch (listed below too).

## STATE
**Merged on main (this run):** #494 (ADR-165, plan, contract, 36 REQs Approved, REQ-073 AC-6), #496 W-121 order path
off, held PRs #424 #474 #417 #448 #419 #451 #452 #393 #465 #457 #466 #450, #498 W-111 Positions, #501 + #505 docs
(ADR-166 "Start tracking", Sensibull-first + copy-first rules in CLAUDE.md and the contract, copy_from_check.py, 24
lane briefs in docs/process/builder-scope-briefs/), #503 create-strategy e2e race fix (main was red 00:00-05:56 IST),
#504 W-122/W-123 Start tracking + Q253 detection (Step 2 core code), #506 #500 fix (stored contracts priced only through
tracked_contracts.resolve app-wide), #508 ADR-167 (owner 2026-10-22: curves and scenario values BEFORE charges, charges
shown once; sentences keep charges).

**Open PRs at the stop (re-run the gate; nothing merges without a green gate):**
- #507 W-125/W-128 (lane B4: held switches, ready-made shapes, POP). Tier A PASS WITH MINORS on 0f170403; evidence
  committed; CI fix round pushed 40ac682d (features body exact, selector pin). Next: `PYTHONUTF8=1 python
  scripts/orchestrator/merge.py 507 --reviewed-sha 40ac682d9c7430bc26ee7fcb081d360440067995` (if RE-REVIEW NEEDED, run
  samelines.py against 40ac682d and use the head when SAME).
- #509 W-124 (lane A3: option chain values, stale-spot safe shading, migration 0022 user settings). Tier A round 2
  PASS WITH MINORS on 627acfb7; evidence committed (head cd6fca2d). Next: `merge.py 509 --reviewed-sha
  cd6fca2d72d2576d45ba874feda1913713c3f8f5`; after merge: `dev_alembic.py upgrade head` (ofo_dev -> 0022).
- **B2 W-127 (lane B2: what-if, payoff chart, ADR-167 before-charges, charges breakdown) - NO PR YET.** Branch
  build/W-127-b2-payoff head 56f0d8ab (main merged; door 212 passed, ratchet OK). Tier A PASS WITH MINORS on 25e33c3a.
  Evidence NOT yet recorded: record REQ-084 AC-4, AC-6, AC-8, AC-9 from `ev-W-127.json` in the scripts folder
  (`record_evidence_fp.py <path-or-agent> W-127 ...`), AC-1/2/3 are PARTIAL (not claimed). Then open the PR (body:
  write from the verifier result in this file's B2 notes) and land with the evidence commit as reviewed sha.
- **A1 W-126 (lane A1: leg rows, Shift/Width/Hedge) - fix round 1 DONE, pushed 6fcdd0bd** (after Tier A REVISE on
  b9355453). Next: Tier A round 2 (the last allowed round) on 6fcdd0bd. Check: (a) the half-step Width rule follows
  REQ-078 AC-4 / Sensibull 7.2 literally - the side NEARER spot moves one gap, so 23,000 PE / 23,050 CE with spot
  23,010 becomes a 23,050 straddle; a tie or no spot moves the calls down (the orchestrator's brief had said "straddle
  at the strike nearer spot" - that was wrong, the builder followed the spec); (b) NEW exception added by the builder:
  Width is offered on a Custom shape whose only near miss on a width-adjustable template is the ATM position rule -
  judge it (alternative: loosen the template constraint in catalogue.yaml); (c) new read-only POST
  /api/strategies/leg-controls drives disabled-with-reason controls; (d) Width measured as lowest CE - highest PE over
  all legs (long straddle/strangle now work). Builder results: 9/9 mutants killed, Tests line 1195 passed, repo_scan
  981, app tests 233, vitest 510 + the known learn.test.js CRLF failure, ratchet OK.

**Shared test DB:** ofo_test at 0021_strategy_tracking (main's head before #509). Known pollution #497 ("Catalogue
update refused ...") blocks some local DB tests; CI is the judge.

## NEXT (in order)
1. Start the live API; ask the owner (question tool) for the Kite login; run Step 2 live proof (`step2_live.py`);
   record the result here and in the contract row. PASS -> lanes C and D may start; FAIL -> stop Steps 3-7.
2. Land #507, #509, B2; finish A1's fix round, verify, land.
3. Re-verify evidence/W-075/AC-7.md (REQ-034 AC-7): it proved the OLD with-charges basis that ADR-167 reversed; its
   fingerprint did not change so trace_check will not flag it.
4. Not built yet (follow-up parts): A3 - REQ-030 AC-3/7/12/13, REQ-029 AC-10; B2 - REQ-084 AC-1 move text, AC-2 date
   steps, AC-3 per-leg IV; B4 - POP in the outcome reply (REQ-082 AC-1/3/5); A1 leftovers listed in its report.
5. Next clusters: A2, A5, B1, B3, B5, B6 (A4 waits on A3/B4: now landing); lanes C, D after the live proof.
6. Docs batch 3 (from todo-docs-batch3.txt): REQ-087 AC-2 wording (ATM marker off on a stale spot, ADR-015); issues for
   B4 minors (.env switches ignored), B2 minors (breakdown 235.74 vs 235.75 note; STALE ATM IV still draws bands -
   judge severity under ADR-015), W-124 test SPOT_KEYS lacks Greeks; "17 templates vs Sensibull presets - measure
   against preset-matrix.md"; tracker rows for #507 #509 W-127 W-126; lessons below.

## Lessons (this run)
- Cluster briefs are too big for one 80-call builder run (A1, A3, B2, B4 all ran out with frontend unbuilt): dispatch
  backend part, then frontend part, each with ratchet + mutation pass inside its budget.
- The orchestrator allocates ALL W-ids (B4 created a W-126 that A1 already had); a work item links one requirement.
- Agents share the session scratchpad; give each a named subfolder (A3's helper files were overwritten).
- A new reply field must grep every full-definition comparison (two CI reds on #506 from `contract_state`).
- Response-door model count conflicts on every merge; a clean git merge can leave the count wrong - recount the union.
- Use general-purpose read-only agents (not the `verifier` type) for verification while builders commit in parallel.
