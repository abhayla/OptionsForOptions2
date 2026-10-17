# Recorded Kite replies of the owner's 1-lot order (2026-10-16) - W-091 fixtures

Source: `D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/` (not in git), recorded by the owner's live session.

| File | Source file | Captured (file time, IST) |
|---|---|---|
| `orders-122104.json` | `real-order/orders-122104.json` | 2026-10-16 12:21:07 (after entry) |
| `trades-122104.json` | `real-order/trades-122104.json` | 2026-10-16 12:21:07 |
| `positions-122104.json` | `real-order/positions-122104.json` | 2026-10-16 12:21:07 |
| `orders-151006.json` | `real-order/orders-151006.json` | 2026-10-16 15:10:09 (after exit) |
| `trades-151006.json` | `real-order/trades-151006.json` | 2026-10-16 15:10:09 |
| `positions-151006.json` | `real-order/positions-151006.json` | 2026-10-16 15:10:09 |
| `instruments-2026-10-16-slice.json` | `instruments.json`, the one row for token 12080386 (NIFTY26O1923650CE) | 2026-10-16 12:07:30 |
| `basket-121848.json` | `real-order/basket-121848.json` (the entry basket the owner sent: BUY 65 LIMIT, tag OFS1V1L0) | 2026-10-16 12:18:48 |
| `quote-151720.json` | `real-order/fetch.json`, its `quote` key (5-level depth; the quote's own `timestamp` is 15:07:20, the file name follows the W-095 brief) | 2026-10-16 15:07:21 |
| `margins-basket-exit-150717.json` | `real-order/fetch.json`, its `margin_raw` key verbatim: Zerodha's real `POST /margins/basket` reply for SELL 65 NIFTY26O1923650CE @ 3.30 (`final.total` -214.5 -> required 0); the matching funds were 671.5 (`fetch.json` `funds`) | 2026-10-16 15:07:17 |
| `margins-basket-entry-derived.json` | DERIVED, not recorded: no raw entry margin reply exists. The exit reply's exact shape with `final.option_premium` 0 and `final.total` 354.25 (the recorder's entry basket total, `basket-121848.json`); funds 1003. Kite's real figure at 3.35 would be about 217.75, so 354.25 is an upper bound | derived 2026-10-17 |

Redaction: the owner's client id in `placed_by` and `account_id` (orders files) is replaced by `XX0000`; the replies
carry no user name, email or user id field. Nothing else is changed (byte-identical otherwise; the money strings such
as `"5.1"` are the recorder's shape, live Kite REST sends JSON numbers). `tests_app/test_kite_replies_to_domain.py`
asserts the client id appears nowhere in this folder.

## W-099 quote fixture

`quote-150720.json`: the `quote` object (the owner's real REST quote of NIFTY26O1923650CE, token 12080386, 2026-10-16
15:07:20) from `D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/real-order/fetch.json`, unchanged. The envelope
`{"status": "success", "data": {"NFO:NIFTY26O1923650CE": ...}}` is OURS (the recorder kept only the inner object); the
money strings such as `"0.05"` are the recorder's shape, live Kite REST sends JSON numbers (tests cover both).
