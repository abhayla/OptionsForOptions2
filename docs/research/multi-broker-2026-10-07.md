# Multiple brokers and option-chain data (2026-10-07)

Stage 1 research, stream S3 (master plan 2026-10-07). Extends `docs/research/broker-architecture-2026-10-02.md`.
Record: `spec/findings.md` F-07 (daily cap settled), F-20, F-21, F-22. Raw files in the session scratchpad `raw/S3`.

## 1. The same contract at a sixth broker

ICICI Breeze's security master is public (directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip, found by
trying URLs, not from its docs). Kotak Neo's master needs an app key (HTTP 401 "Consumer key is blank").

| Contract | Zerodha | ICICI Breeze |
|---|---|---|
| NIFTY 13-Oct-2026 25000 CE | exchange_token 44778, NIFTY26O1325000CE, lot 65, tick 0.05 | Token 44778, ShortName NIFTY, strike 25000 (not scaled), lot 65, TickSize 5 (paise) |
| SENSEX 08-Oct-2026 75000 CE | 888931, SENSEX26O0875000CE, lot 20 | Token 888931, ShortName **BSESEN**, lot 20 |

The exchange number matches again (F-01 holds for a sixth broker). Breeze leaves FreezeQty at 0 and Kite's file has
no freeze column, so freeze limits stay unknown from these files (F-04, #43).

## 2. Broker API facts (official docs read; Angel One and Fyers docs were not readable)

| | Zerodha Kite v3 | Upstox | Dhan v2 |
|---|---|---|---|
| Order limits | 10/s, 400/min, **5,000/day per user/API key** (re-checked), 25 modifications | 10/s, 500/min, 2,000/30 min (50/s for registered algos) | 10/s, 250/min, 1,000/hour, 7,000/day |
| Session | token valid until 6 AM next day | until 3:30 AM next day | 24 h, renewable while active |
| Order updates | postback (SHA-256 checksum) for our key's orders; websocket "order" messages for all of the user's orders | webhook + portfolio stream | postback (not to localhost) |

## 3. Contract numbers are reused (F-21, #116)

| Set | Numbers | Mapped to more than one contract |
|---|---|---|
| NSE, every trading day 3 Aug - 6 Oct 2026 (45 files) | 65,265 | **4,768** (recounted by the orchestrator); 421 touch NIFTY |
| BSE, same dates | 3,575 | 0 |
| BSE, Jan/Jun/Sep 2025 samples | 6,600 | 107 SENSEX numbers reused (agent count) |

No two contracts share a number on the same day. A live contract's strike can change under the same number (HINDPETRO
79199, 410 -> 390.75 on 14 Aug 2026, likely a corporate action). One contract can also appear under two numbers
(strike-adjusted stock options). Zerodha's docs: "Exchanges may reuse instrument tokens ... after each expiry".
Consequence: identity needs the expiry (Q262).

## 4. Can one user's Kite connection carry a full chain?

Kite websocket: 3,000 instruments per connection, 3 connections per API key; OI only in `full` mode. Today's file:
NIFTY nearest two expiries 424 contracts, SENSEX 664 - **1,088 subscriptions plus 2 index tokens fit one connection**.
If all users shared one platform API key, the 9,000-instrument cap would be for the whole app, so per-user keys (ADR-014
model) avoid it. Quote API: 500 instruments per call, 1 call/second. Historical: 3/s, minute candles with OI; the
lookback for option minute data is not stated in the docs (unknown).

## 5. Gaps

Kotak Neo master (needs a key); Angel One and Fyers official docs (JavaScript-only); freeze quantities; Kite's
historical lookback for options; redirect-URL rules (forum only: https, localhost allowed for testing - unverified).
BSE's bhavcopy site returns an HTML page with HTTP 200 on non-trading days - a downloader must check the content.
