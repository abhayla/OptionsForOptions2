# Instrument list fixture

`instruments_slice.csv` is a slice of Zerodha's public instrument list.

- Source: `https://api.kite.trade/instruments` (Kite Connect public instrument dump, no login required).
- Captured: 2026-09-29.
- This is public data (Zerodha publishes the full instrument list without authentication); no
  credentials or account-specific data are included.
- Contents: every NIFTY (NFO) and SENSEX (BFO) option row for each underlying's two nearest expiries
  as of the capture date, every NIFTY (NFO-FUT) and SENSEX (BFO-FUT) futures row, plus ~20 unrelated
  rows (other names, segments and exchanges — equities, other index derivatives, ETFs) to prove that
  the parser filters correctly instead of reading everything.
- Full header (unchanged from the source): `instrument_token,exchange_token,tradingsymbol,name,
  last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange`.
