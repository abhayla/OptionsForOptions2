# GC-5S run log (2026-10-19)

- 10:20 lock/gc-5s taken (session aad6f47b, cap 17:20 IST); lock/gc-3l present (owner-approved parallel run).
- 10:30 server-side check on live ticks, API :8766: 27 pushes in 30 s, min gap 1.028 s, LTP changed on all 4 legs,
  health `available`, spot 23121.3 (a check, not the page proof).
- 10:33-10:40 first page run stopped by the orchestrator: role `ofo_app` connection limit 5 reached
  (`TooManyConnectionsError` x11, `GET /strategies/11` unhandled error); API :8766 stopped at ~10:40; GC-3L session told
  (cross-session message). Finding F-45 / `db-role-limit-below-pool-size`. Rule for the rest of the run: nothing of
  GC-5S touches the `ofo_app` role while lock/gc-3l exists (no API, no local DB test; DB tests run in CI).
- ~10:46 (clock read 10:48:25 just after) **owner decision (question tool, "Start 2-3 on fakes now (Recommended)")**: builders for items 2 and 3 start
  before item 1's page proof, on fakes/replay only (no DB, no live, nothing merged); item 1's page proof and each item's
  own live proof run after GC-3L ends, before 15:30. Process order only; no spec change (no product rule changed).
- ~11:27 (clock read 11:24:22 just before the question) **owner decision (question tool, "4a + 6 shells now, park 5
  (Recommended)")**: item 4a (W-116 chain route + socket) and item 6 display-only shells start on fakes; item 5 parked
  as #434 (REQ-044 AC-2 needs execution state). Process order only; no spec change.
- W-113 PASS (Tier B, 2 rounds), W-114 PASS (Tier A, round 2), W-115 AC-4/AC-5 PASS and AC-2 FAIL on scope (Tier A
  re-verify, round 2) -> #433 parked (Home state 3, name, trial, landing). F-46 registered. #429's red e2e is the
  pre-existing #370 / F-45 class (main a614b16 fails the same test).
- ~13:02 (clock read 13:01:19 just before) **owner decision (question tool, "Start 4b on fakes now (Recommended)")**:
  item 4b (W-118 Option Chain screen, display only) starts on fakes, stacked on W-116 (#437). Process order only; no
  spec change.
- W-116 (#437): round 1 Tier A FAIL (error storm, AC-4 gaps); round 2 fixes held under attack; AC-1/AC-4/AC-8 recorded
  `fail` as written (screen parts are W-118; IV needs the engine) -> #439 deferred. F-47 (no previous close), F-48
  (rate gate on the success path only). W-117 (#436) PASS for the part built; REQ-011 AC-1 recorded fail (no content) ->
  #435 deferred.
- 14:24 GC-3L stopped its API/preview (cross-session); 14:26 GC-5S run API :8766 (PID 10744, parent 22696) and preview
  :4174 (PID 19956) started from a local run branch (W-113 + W-114/115/117 stack + W-116/118 merged, never pushed);
  `/api/health` through the proxy: healthy, database connected. 0 TooManyConnectionsError in its log.

## Live proofs, Mon 2026-10-19, market hours (evidence rows)
| Claim | Evidence |
|---|---|
| Item 1 core: >= 3 pushes with changing spot_at on the Live Strategies page | GC-5S draft 16 (NIFTY 2026-10-27 22900/22950 CE, planned entries, never executed), page socket frames 14:29:32.856-14:29:39.184: 8 COMPUTED pushes, spot_at 14:29:33, :34, :35, :36, :37, :38, :39, spot 22853.6 -> 22856.05, LTPs 165.8/143.25 -> 166.9/143.65; card text sampled 14:29:34-14:29:42 showed the same (screenshot .playwright-mcp/gc5s-proof-live.png) |
| Item 1 core: forced disconnect shows REQ-049 AC-5's message | drop at 14:30:54.350, 3 reconnects refused at the proxy; card 16 at 14:30:56-14:31:06: data-live down, paused, label "Live market data disconnected. Last updated: 02:30:55 PM. Live strategy monitoring is paused.", the paused badge, data-health unknown dot, no spot number; REST fallback (fallback=true) answered NOT_CONNECTED with that label at 14:30:55.373 (screenshot gc5s-proof-disconnect.png). Harness note: Playwright's server-side close did not end the proxied server connection, so "Last updated" advanced to 02:31:01 PM; the page never showed those frames |
| Item 1 AC-6: pausing is per card | card 15 stayed data-paused false while card 16 was paused |
| Item 2: index socket live | 14:31:24-14:31:39, 15 messages, min gap 1.002 s, all LIVE; NIFTY 22864.40 -> 22864.90 -> 22864.35, SENSEX 73770.03 -> 73771.12 -> 73773.46 with their own times (first push: SENSEX unavailable, no value, just subscribed) |
| Item 2: index page live and not-live | page 14:32:15/14:32:17: NIFTY 22869.20 -> 22868.95, SENSEX 73783.55 -> 73784.43; after a forced drop (14:32:21): both panels "Not available", Last updated time, no number |
| Item 4a: chain socket live | 14:31:41-14:31:55, 14 messages, min gap 1.01 s, all LIVE; spot 22861.90 -> 22862.85, ATM 22850.00, 22600 PE LTP 75.45 -> 75.70 (first push: LTPs null, just subscribed) |
| Item 4b: chain screen live | 14:32:27 NIFTY 22865.45 "live", full Calls - Strike - Puts table, exactly 1 ATM row (data-atm), Change "-" (F-47) |
| Item 3 / 6: Home strip and Market context live | 14:33:23-14:33:29 NIFTY 22867.60 -> 22866.90, SENSEX 73792.50 -> 73791.29, Market context "Index values are live." |
| Finding during the proof (MINOR, deferred) | draft 13 (saved via API without planned entries) shows "Draft - Live data not connected" although data is connected: misleading label for a strategy the engine cannot price; the Builder always captures entries (ADR-075) |
| Servers stopped | 14:34 API PID 10744 + parent 22696, preview PID 19956 stopped by PID; no listener on 8766/4174 |

- ~14:50 #429 red in CI 4/4 on `strategy-save-draft.spec.ts:71` with 9 `too many connections` (main 1dae5de green):
  second red of the F-45 class after one round -> independent Opus review (owner rule): the defect is the per-process DB
  pool (5 kept + 10 overflow vs a shared role limit of 5), not W-113; W-113's e2e visits trigger it; #395 is the CI fix;
  the class fix (pool budget per process + startup check + no nested token-read connection + single-flight rates) is
  Tier A for the next contract.
- ~14:52 **owner decision (question tool, "Merge #395 now, then GC-5S PRs (Recommended)")**: GC-5S merges GC-3F's held
  #395 first, then its own PRs in item order. Cross-contract order only; no spec change.
- GC-3L asked (cross-session) for a no-verifier window to merge its close-out and delete lock/gc-3l; GC-5S replied
  "go" and holds verifiers until "done" or 20 minutes.
