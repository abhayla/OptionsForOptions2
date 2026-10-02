# Research: broker-connected trading architecture and cross-broker option identity (2026-10-02)

Owner request (2026-10-02): research the architecture of trading apps that work with one or many brokers, and how the
same option is coded at each broker, before more is built. Three read-only research streams; owner approved all four
recommendations the same day (ADR-050). Every proven fact is recorded with an F-id in `spec/findings.md`; this file is
the narrative and the source list.

## 1. The same option at five brokers (F-01 to F-05)

Instrument masters downloaded 2026-10-02: Zerodha `https://api.kite.trade/instruments`, Angel One
`https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json`, Upstox
`https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz`, Dhan
`https://images.dhan.co/api-data/api-scrip-master.csv`, Fyers `https://public.fyers.in/sym_details/NSE_FO.csv` and
`BSE_FO.csv`.

| Broker | NIFTY 06-Oct-2026 20050 CE as shown | Broker id | Exchange number |
|---|---|---|---|
| Zerodha | `NIFTY26O0620050CE` (NFO, NFO-OPT) | instrument_token 10383106 | exchange_token 40559 |
| Angel One | `NIFTY06OCT2620050CE` (exch_seg NFO, strike x100) | token "40559" | 40559 |
| Upstox | `NIFTY 20050 CE 06 OCT 26` (NSE_FO) | instrument_key `NSE_FO\|40559` | 40559 |
| Dhan | `NIFTY-Oct2026-20050-CE` (NSE, segment D) | security_id 40559 | 40559 |
| Fyers | `NSE:NIFTY26O0620050CE` | fytoken 101126100640559 | scrip code 40559 |

SENSEX 08-Oct-2026 75000 CE: 888931 at all five (Zerodha instrument_token 227566341). Conclusions: key on (segment,
exchange number); never on a symbol; store broker ids, scales, lot/tick/freeze per broker with dates; read expiry from
the master.

## 2. Architecture lessons (F-07, F-08)

Sources: OpenAlgo (github.com/marketcalls/openalgo; docs.openalgo.in/symbol-format), NautilusTrader
(nautilustrader.io/docs: orders, execution, reconciliation, live), QuantConnect LEAN brokerage key concepts, CCXT
manual (rate limiting), Kite Connect v3 docs (orders, postbacks, exceptions) and forum threads (kite.trade/forum
comments 52171, 52673).

Already in our design: order states where submitted is not executed, fills counted once by broker id, no automatic
retry, reconciliation gate, one route to the broker (`send_guard`), one intent to many slices.

Added to the broker-phase brief (ADR-050 item 4): our tag on every order with lookup on timeout; persist intent before
send; websocket + verified postbacks + polling; external orders recorded; per-key rate limits; re-login on token
expiry; kill switch; Zerodha API-order rules (market protection, 10 slices, 25 modifications).

## 3. Regulation (F-06, Q258)

SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013 (4 Feb 2025) and NSE INVG67858 (6 May 2025), per secondary sources
(moneylife.in, zerodha.com/z-connect, support.zerodha.com static-IP article, outlookbusiness.com): static IP for order
placement (Zerodha rejects others from 1 Apr 2026; sharing limited to family), algo ID, kill switch, registration above
10 orders/second, algo-provider empanelment. Open: whether our SaaS is an algo provider (Q258) - Zerodha's written answer
and the Q211 legal review decide it.

## 4. algochanakya (F-09)

Its cross-broker design keys on the Kite tradingsymbol, implements converters for 2 of 6 brokers, has two weekly
formats, assumes last-Thursday monthly expiry and uses three broker-name vocabularies. Not reused (ADR-050 item 5).

## Not covered
Hummingbot, Freqtrade, Jesse, Sensibull, Streak, Tradetron, Dhan/Upstox API docs; the SEBI extension circular PDF; the
OpenAlgo licence.
