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

Redaction: the owner's client id in `placed_by` and `account_id` (orders files) is replaced by `XX0000`; the replies
carry no user name, email or user id field. Nothing else is changed (byte-identical otherwise; the money strings such
as `"5.1"` are the recorder's shape, live Kite REST sends JSON numbers). `tests_app/test_kite_replies_to_domain.py`
asserts the client id appears nowhere in this folder.

## W-099 quote fixture

`quote-150720.json`: the `quote` object (the owner's real REST quote of NIFTY26O1923650CE, token 12080386, 2026-10-16
15:07:20) from `D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/real-order/fetch.json`, unchanged. The envelope
`{"status": "success", "data": {"NFO:NIFTY26O1923650CE": ...}}` is OURS (the recorder kept only the inner object); the
money strings such as `"0.05"` are the recorder's shape, live Kite REST sends JSON numbers (tests cover both).
