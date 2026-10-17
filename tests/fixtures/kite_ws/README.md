# tests/fixtures/kite_ws

- `frames-2026-10-08-092000-10s.bin.gz`, `instruments-2026-10-08-subscribed.csv`: the 2026-10-08 recording and its
  catalogue slice (W-059).
- `full-frame-12080386-150720.bin` (W-097): ONE real 184-byte full packet (wrapped as a one-packet frame, 188 bytes) for
  NIFTY26O1923650CE, token 12080386, exchange time 2026-10-16 15:07:20 IST. Source: recorder file
  `ofo-kite-ticks/2026-10-16/frames-120730.bin.gz`, frame index 46750, receive time 1792143439922205200 ns. Its ten depth
  levels equal Zerodha's REST quote of that second (`real-order/fetch.json`); proof in
  `docs/research/depth-proof-2026-10-17/`.
