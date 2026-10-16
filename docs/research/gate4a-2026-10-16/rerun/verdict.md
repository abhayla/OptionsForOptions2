# Stage 4a gate re-run 2, 2026-10-16 10:20-10:25 IST (main 48d75a7, API :8765, ofo_dev, live Kite)

**Verdict: PASSED.** All five required checks pass. The text items left over are tracked in issue 297 and do not
block the gate.

Strategy: an iron condor on the 2026-10-19 NIFTY expiry (the nearest in the catalogue). SELL 23350 CE, BUY 23550 CE,
SELL 22950 PE, BUY 22750 PE. Spot when the legs were picked: 23136.20.

| # | Check | Result | Numbers |
|---|---|---|---|
| 1 | D8: live payoff vs the ADR-008 formula, TOTAL rows per ADR-076 | PASS | 3 calls, 65 s apart. Each call: 27 cells + 144 scenario cells, 0 mismatches; socket frame 27/27. Spot / spot_at: 23134.5 @10:20:23, 23133.9 @10:21:28, 23127.55 @10:22:33 (all different). TOTAL Entry Value Rs 4,140.50 Cr in every call. TOTAL Current Value 3,477.50 / 3,484.00 / 3,412.50 Cr. Entry minus current = unrealized P&L: 663.00 / 656.50 / 728.00 |
| 2 | Release-then-acquire repro, 60 s (D-1) | PASS | Socket B: 59 frames, 59 different spot_at values (10:22:59 to 10:23:59), largest gap 2 s, 49 different spot levels, all COMPUTED |
| 3 | Draft save, reload, reopen through the screen (ADR-075, D-2) | PASS | Draft 10: all 4 legs priced by the leg picker (35.60 / 11.55 / 49.00 / 20.45, each with its capture time). Screen before = screen after = stored row; 0 field differences |
| 4 | 8 screenshots (1280 and 390 px) | Taken | States: computed, stale, error, no-draft; no sideways scroll. #232 items 1, 2 and 4 are gone; item 3 is partly fixed (see below) |
| 5 | Far 28700 CE, LTP 0 (D-3) | PASS | LTP null, label "no live quote". The table shows "—" for LTP, Current Value, P&L and P&L %, and "—" for TOTAL Current Value. No Rs 0.00, no -100% |

## Left over (issue 297, does not block)
- #232 item 3, remainder:
  - Legs opened from a draft link still show "Contract details not available".
  - The notice box shows the raw trading symbol `NIFTY26O1928700CE`.
- The "estimated from spot" fragment, and the same notice printed twice.
- "Margin from Zerodha is not shown yet; it needs your Kite login" while a session exists.
- The "Loss" line in the payoff chart is drawn at 0 across the profit zone.
- Small detail: the far leg's `health` field is "available" while its LTP is null and its label is "no live quote".
