# Session handover: GC-IC1 (iron condor complete), 2026-11-03 20:37 to 2026-11-04 ~04:00 IST

Contract: `docs/process/goal-contract-GC-IC1-2026-11-03.md`. Branch `feature/adjustments` in
`D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`. This session: e1f1ec0a..HEAD (about 50 commits).
Nothing on main, no PR (owner rule). Previous handover: `session-handover-2026-11-03-gcic1.md`.

## DONE this session (each proven by the orchestrator's own run)
| Step | Result | Proof |
|---|---|---|
| 5c #636 r5 | merged 989623c9: settings cache checks only the row in force; stale queued writes dropped; writer watchdog + drain on stop; lag counts the gate wait (LAG_SECONDS 5, REQ-167 AC-4 amended b624a859); the #639 read-window test rewritten (it deadlocked on the one DB gate; test-only) | worker + day rules DB files on the merge: 23 passed; 5/5 mutants red; #636 comment 6609441635; #636 OPEN (live 1.0 s owed) |
| 8 pass 2 | 390 px: builder page overflow FIXED (06c1cf6a, scrollWidth 458 -> 375); history, adjustment history, plan sheet, Compare + controls fit | `D:\Abhay\scratch\gcic1\step8\pass2-2026-11-03.md`; drawer NOT checked (needs a live detection: step 9) |
| 10 verifier pass | W-200..W-214: 80 of 80 ACs have an evidence block from an independent verifier: 65 PASS, 15 FAIL (5 rounds; every FAIL fixed in GC-IC1 was re-verified PASS: REQ-158 AC-2/AC-3, REQ-159 AC-4/AC-6, REQ-167 AC-4, REQ-168 AC-4, REQ-163 AC-1, REQ-170 AC-4, REQ-046 AC-5) | `find evidence/W-2*` 80 files, 65 `result: pass`; footers + reach baseline (#532) |
| 11 gate + push | prepush --full run 1 TOTAL FAIL (stale generated files, stage rows, a non-literal route path, 2 stale test expectations) -> fixed 71486176 -> run 2 TOTAL PASS 1569.9s; pushed 5e5eb400..71486176. Later commits (step 10 rounds 4-5 fixes) need their own gate + push | prepush logs D:\Abhay\scratch\gcic1\step11\ |
| Fixes from step 10 | own playbook never draft (REQ-158 AC-2); carry gap + S-02/S-12 thresholds are settings (REQ-167 AC-4); unbuilt day-rule pairs shown "not checked" (REQ-159 AC-4); gap-at-open line names the user's time (REQ-168 AC-4); history names every suggestion behind an adjustment, link survives reload (REQ-163 AC-1; Tier A review FIX FIRST -> fixed -> re-check PASS); held crossings shown (REQ-170 AC-4) | mutants red for each; merges b84b5b3c, ca2ee383, ef8ed5e5, 3a92ca27, 7dc98182 |
| Found + fixed on the way | 5 stored paper alerts hidden by the #629 wording (8abeb451, guard test; alerts back: 5); reply inventory / response door / template pin drift (1bde4efc, 8ca5c8d1); 71 non-DB tests_app regressions from GC-IC1 steps 0-7 (route fake lacked the ADR-172 live-book health, wording, openapi, labels fixture, pause route outside the error boundary, a route importing the alert gate into the risk-exit chain) fixed 9500fa50 + 874fa104 | full non-DB tests_app sweep: 71 failed (8ca5c8d1) -> 4 (9500fa50) -> the 4 files green on 874fa104 |

## PENDING
- Step 9 live day (market hours 4 Nov): owner's Kite login in a private window at 09:15; strategy 82 (paper mirror of the
  NIFTY 29 Dec IC); GC-LIVE4 section A; #636 live 1.0 s measurement (D3); the review-adjustment drawer at 390 px.
  Dev API is STOPPED (restart: `DB_POOL_SIZE=3 APP_ENV=development LIVE_MARKET=1 python <main>/scripts/orchestrator/dev_run.py
  <tree> python -m uvicorn --factory ofo_app.main:create_app --app-dir backend --loop ofo_app.event_loop:selector_loop
  --host 127.0.0.1 --port 8765`); Vite on 5174 still serves the tree. DB_POOL_SIZE=3 because the tunnel makes 2 too few.
- Step 11: prepush --full TOTAL PASS on the final head, then push feature/adjustments (see the push brief below).
- Step 10: the 15 FAIL ACs. Out of GC-IC1 scope, filed: REQ-112 AC-1/2/3/5, REQ-162 AC-2, REQ-163 AC-3 (#645, #648);
  REQ-155 AC-1 A-30, REQ-158 AC-7, REQ-159 AC-2, REQ-160 AC-3 (#646); REQ-046 AC-2 (#647). Owner decisions: REQ-046
  AC-4 (Q1 below), REQ-159 AC-5 (Q2 below). Partial by design: REQ-167 AC-5 (ADR-222 (11)). REQ-156 AC-1: spec now
  states the no-spot exception (2b208de4); its evidence is the round-4 FAIL until a verifier re-reads it.

## OWNER ANSWERS 2026-11-04 (question tool)
- Q1 roll basis: "Target delta" -> ADR-243. Then: target delta is the DEFAULT; each user picks the basis and each
  strategy can override it ("Yes, and per strategy too") -> ADR-243 CONFIGURABLE section.
- Q2 S-08 / S-09: "Add both as Guidance" -> ADR-244 (new iron condor system playbook version; not built yet).
- Every adjustment number and rule has three layers, admin default -> user override -> strategy override ("Yes, 3
  layers for all") -> ADR-245. Owner principle: act as an expert option trader building for other traders; every
  answer on an adjustment behaviour sets a default, never a fixed rule.
- Sequencing (process, no spec row): "New contract after live day" - the live day runs first on today's defaults;
  draft goal contract "Your adjustment settings" (was GC-CFG1) (roll basis with entry distance + per-strategy override, every admin-only adjustment
  number to three layers, Preferences / plan sheet show value in force and source, S-08/S-09 version, REQ-156 AC-1
  no-spot page) for ONE owner approval; GC-IC1 closes with the live day. APPROVED ~08:25 ("Approve as drafted"):
  docs/process/goal-contract-your-adjustment-settings-2026-11-04.md - runs after the live day. Estimate given: about 2 working days
  (14-18 h; 12-20 h range).

## OWNER ITEMS
- `docs/process/owner-questions-2026-11-04.md` Q1: roll basis - REQ-046 Q255 (entry distance from spot) vs the approved
  playbooks' target delta (what is built). Recommendation: target delta, mark Q255 superseded.
- Q2 (REQ-159 AC-5, evidence/W-206/AC-5.md): the iron condor system playbook lists 10 of the 12 situations; S-08 (day
  before a known event) and S-09 (weekend or holiday) are absent and ADR-240 never classifies them. Recommendation: add
  both labelled "Guidance" (as ADR-240 did for S-03..S-05: no event list yet), as a new system playbook version.
- Texts "pending owner read" in tests/errors/template_pins.json (new tonight: day rule not checked, gap line, carry gap,
  situation setting unavailable, history why unreadable).
- New admin settings tonight (Other group): other.carry_gap_percent (2), other.situation_net_delta_per_lot (0.15),
  other.situation_big_win_percent (40) - values unchanged, now editable.

## Issues filed tonight
#644 repeated per-request reads (dev 4-16 s) · #645 PARKED suggestion outcomes from real Zerodha fills · #646 catalogue
items with no path or label (A-30, T-10/T-10c/T-17, data-state labels, Test row form; + scenario-mode 409 drops the
acted ids) · #647 drawer lacks margin utilisation and IV/OI/LTP · #648 prepared exits create no record; why-view has no
outcome · #649 scenario fixtures expired 3 Nov: DB tests that switch scenarios fail on the lifecycle guard (CI red until
fixed).

## Findings registered
stored-text-orphaned-by-wording-change (guarded) · fixture-dates-expire-with-the-clock (unguarded) ·
nodb-app-tests-skipped-by-step-gates (unguarded).

## Process lessons (memory)
verifier-gate-blocks-builders · reply-inventory-in-briefs · run-nodb-app-tests-per-batch.
