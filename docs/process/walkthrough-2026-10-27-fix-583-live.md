# #583 fix: live re-check (2026-10-27, 10:35 IST, market open)

Branch fix/583-index-lease-futures-entry (commits e30e87b9, c0662daf, f875baad), API on 127.0.0.1:8766 against ofo_dev
with the owner's Kite session and no other client; control = main 2e1134d5 on 127.0.0.1:8765 at the same minute.

| Item | Fix branch (8766) | Main (8765) | Verdict |
|---|---|---|---|
| I-1 ready-made, empty builder, no other holder | 10:35:16 POST load-template bull_call_spread NIFTY 3 Nov -> 200 in 2.25 s, legs BUY 22750 CE / SELL 22950 CE | 200 at 10:35:18, but NOT a clean control: the browser page on 8765 holds the index. Clean "before": 09:23:37 -> 503 (walkthrough-2026-10-26.md, RESUMED section) | FIXED |
| I-6 spot on the futures read alone | 10:35:39 spot 22744.50, reason none | held by the browser page, not clean | FIXED (on 8766 nothing else held the index) |
| I-12 futures leg planned entry | 10:35:40 planned-entry NSE_FO:61471 (23 Nov FUT) -> 22865.60, source ltp | 10:35:43 -> planned_entry null, reason no_live_price, while its futures read showed LTP 22865.30 | FIXED (clean A/B) |
