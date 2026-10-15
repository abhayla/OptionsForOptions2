# Stage 4a gate review (draft, 2026-10-15 evening)

Verdict: **NOT YET PASSED.** Two gate checks were run at 11:55 IST on code that three later merges the same day
changed (#212 proxy, #211 TOTAL Cr/Dr, #216 planned entries saved), and the Save Draft screen (W-071) did not exist yet.
Those checks must be re-run on current main; the run is ready to go as soon as W-071 merges, in the next market session
with the owner's one daily Kite login.

Gate source: `docs/process/master-plan-2026-10-07.md` section 4a, "Gate". Evidence for the 11:55 run lives outside the
repo in `D:\Abhay\Ventures\ofo-kite-ticks\2026-10-15\gate4a\` (`results.json`, `shots-report.json`, 8 screenshots, draft
GETs); a copy goes into the repo with the re-run.

## 1. Every Phase-0 check recorded with pass or fail (ADR-030)
| Check | Result | Record |
|---|---|---|
| Live ticks over the WebSocket, 30 min | PASS | spec/findings.md (2026-10-08) |
| Full NIFTY and SENSEX chain rebuild | PASS (bid/ask on 216/216, 208/208, 334/336, 271-328 contracts) | spec/findings.md |
| Our Greeks against Kite's | NOT POSSIBLE (Kite has no Greeks); internal check PASS with the forward (ADR-061) | spec/findings.md |
| Stale or missing data flagged, never shown as live | PASS (feed-stale flagged 6.3 s after a forced pause, 2026-10-08 14:51); browser-side: W-065 two-holder fallback guarded (PR #235) | spec/findings.md; finding liveness-from-shared-subscribers |
| Forced reconnect | PASS (2.2 s) | spec/findings.md |
| History persisted | PASS | spec/findings.md |
| Fan-out to 100/1,000 simulated users from recorded ticks | PASS on the replay (W-059) | handover 2026-10-08 |
| Licence status | recorded (F-23, F-31) | spec/findings.md |
| Next-morning token expiry | **PENDING**: watcher running since 15:50:34 on the 11:47 token (`token-watch-2026-10-15.json`), 1-minute probes 04:00-09:00 on 2026-10-16 | to be recorded as an F-id |

## 2. Payoff equals the ADR-008 formula on live inputs (D8), Sensibull as a cross-check
- 11:55 run: 3 live calls x 38 comparisons; 36 per call matched by hand, 0 mismatches; the 2 TOTAL rows (Entry Value,
  Current Value) were recorded as "convention not defined" - ADR-076 (#211) has since defined them (net with Cr/Dr).
- Sensibull: not run (no access); ADR-056 makes it a cross-check only.
- **Re-run needed** on current main so the TOTAL rows are graded against ADR-076.

## 3. The saved draft reloads unchanged
- 11:55 run: definition equal across save / GET / GET (draft 948), but planned entry and capture time were NOT stored
  (harness finding F3) - #216 (ADR-075) fixed that afterwards, and the screen had no Save Draft action.
- **Re-run needed** through the screen once W-071 merges (its Playwright core proof is the same check in CI).

## 4. Desktop and mobile screenshots of every state (REQ-067 AC-4)
- 11:55 run: 8 screenshots (live, stale leg, API unreachable, no draft; 1280 and 390).
- They show #232: the leg picker's error (cause confirmed: the pre-#212 proxy rewrite, harness finding F2), a broken
  message fragment, raw instrument ids and ISO times. **Re-take on current main**; items 2-4 of #232 are to be decided
  in this review (recommendation: 2 blocks the gate as wrong wording on the main screen; 3-4 fixed before the 4b demo).

## Re-run plan (next market session, one owner login in a private window)
1. Token-expiry result read from the watcher; F-id recorded.
2. API from main on 8765 with `DATABASE_URL = DEV_DATABASE_URL` (ofo_dev, ADR-078); owner logs in.
3. D8 on 3 live calls incl. TOTAL rows per ADR-076; draft save -> reload -> reopen through the screen (W-071);
   8 screenshots of every state on current main.
4. Copy results + screenshots into `docs/research/gate4a-<date>/`; write the verdict here.
