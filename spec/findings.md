# Spec findings list

Research findings measured on real data or read from a named source, recorded the turn they are proven
(`.claude/rules/kit/spec-first.md` R6). Each carries an F-id, the real values, the source and the date, and names the spec
sections it bears on; those sections cite the F-id. A finding never changes a decision by itself: it is "open for owner
decision" until a decision row records the change. Failure classes are also registered in `knowledge/findings/`.

Status words: **decided** (a decision row acts on it), **open for owner decision**, **recorded** (fact kept for later
work, no decision needed yet), **unverified** (secondary source only; the row says what would verify it).

## F-01 - The exchange's contract number is the one identifier shared by every Indian broker
- Measured 2026-10-02 from each broker's public instrument file (Zerodha `api.kite.trade/instruments`, Angel One
  `OpenAPIScripMaster.json`, Upstox `complete.json.gz`, Dhan `api-scrip-master.csv`, Fyers `NSE_FO.csv`/`BSE_FO.csv`).
- NIFTY 06-Oct-2026 20050 CE: Zerodha `exchange_token` 40559 = Angel One `token` "40559" = Upstox `NSE_FO|40559` = Dhan
  `SEM_SMST_SECURITY_ID` 40559 = Fyers scrip code 40559. SENSEX 08-Oct-2026 75000 CE: 888931 at all five (BSE F&O).
  11,243 option contracts matched by (exchange, number) between the Zerodha and Angel One files.
- The number is unique only within an exchange segment; key on (segment, number). Do not match a Fyers fytoken by its
  suffix: fytoken 1011261123140559 (an OIL option) also ends in 40559.
- Bears on: REQ-053, REQ-054, ADR-050. Status: **decided** (ADR-050, Q257 amended 2026-10-02).

## F-02 - Zerodha's instrument_token is not a cross-broker identifier
- 10383106 = 40559 x 256 + 2 (NFO); 227566341 = 888931 x 256 + 5 (BFO). Inferred from two samples, not a documented rule.
- Bears on: REQ-053, ADR-050 (it moves to the per-broker table). Status: **decided**.

## F-03 - Broker trading symbols differ, and some are not unique
- Same NIFTY contract: Zerodha `NIFTY26O0620050CE`; Angel One `NIFTY06OCT2620050CE` (0 of 951 NIFTY CE symbols equal
  Zerodha's, yet Angel One's SENSEX symbols use Zerodha's style); Upstox `NIFTY 20050 CE 06 OCT 26`; Dhan
  `NIFTY-Oct2026-20050-CE` (the same symbol on 4 expiries: 06, 13, 19, 27 Oct, security ids 40559, 44442, 47029, 51212);
  Fyers `NSE:NIFTY26O0620050CE`. Zerodha weekly = name + YY + month char (1-9, O, N, D) + DD; monthly = name + YY + MON.
- Measured 2026-10-02 (files as F-01). Bears on: ADR-050 (never key on a symbol; the platform shows its own format).
  Status: **decided**.

## F-04 - Broker data scales and limits differ for the same contract
- Angel One stores strike and tick x 100 ("2005000.000000", tick "5.000000" = Rs 0.05); freeze quantity 3511 at Angel
  One vs 3510 at Upstox for the same NIFTY contract; Upstox expiry is an epoch in milliseconds; Dhan shows NSE expiry
  time 14:30 and BSE 15:30 (unexplained).
- Measured 2026-10-02. Bears on: REQ-054 (lot, tick, freeze limit are per-broker data with dates), REQ-056 AC-1 (freeze
  limit). Status: **decided** (ADR-050 item 2).

## F-05 - Expiry dates must be read from the instrument master, never computed from a weekday
- Zerodha NIFTY CE expiries in the 2026-10-02 file: 712 rows on Tuesdays and 239 on Mondays (2026-10-19, 2026-11-23,
  2029-12-24), consistent with holiday shifts; SENSEX expires on Thursdays. The holiday reason is not confirmed.
- Bears on: REQ-053, ADR-050. Status: **recorded** (our parser already reads expiry from the file).

## F-06 - SEBI's retail algo framework puts architecture rules on API order placement
- SEBI circular SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013, 4 Feb 2025 ("Safer participation of retail investors in
  algorithmic trading"); NSE implementation circular INVG67858, 6 May 2025. Per secondary sources: orders through
  registered brokers only, an algo ID on every API order, a kill switch, registration above 10 orders per second per
  segment per API key, algo providers empanelled with the exchange with each strategy registered, static IP required
  for order placement (not for data), primary + secondary IP, IP change at most once a week; full applicability to all
  brokers from 1 Apr 2026 after extensions. Zerodha: orders from a non-whitelisted IP rejected from 1 Apr 2026, static IP
  sharing limited to family.
- Sources: moneylife.in/article/.../76294.html, zerodha.com/z-connect (NSE circular overview), support.zerodha.com static
  IP article, outlookbusiness.com (deadline extension). The SEBI extension circular PDF was not read.
- Bears on: REQ-054, REQ-063, REQ-066, ADR-034, open question Q258. Status: **unverified / open for owner decision**
  (Q258: does a SaaS sending many users' orders count as an algo provider; verify with Zerodha's written answer and the
  legal review Q211).
- **Update 2026-10-07:** the SEBI circular and the NSE implementation standards were read from the primary PDFs; see
  F-11 and F-12. Their verified clauses supersede the secondary-source summary above. The Zerodha-specific points (1 Apr
  2026 rejection date, family-only sharing at Zerodha) are still unverified until read on Zerodha's own pages.

## F-07 - Zerodha API order behaviour the broker phase must handle
- From Kite Connect docs (kite.trade/docs/connect/v3: orders, postbacks, exceptions) and forum threads, read 2026-10-02:
  a successful place_order only means accepted, never executed; interim statuses (PUT ORDER REQ RECEIVED, VALIDATION
  PENDING, OPEN PENDING, TRIGGER PENDING, CANCEL PENDING) are not final; postbacks cover only orders placed with our API
  key and need the checksum SHA-256(order_id + order_timestamp + api_secret) verified, while the websocket covers all of
  a user's orders; a place_order timeout can leave an order that exists, so look it up by our tag instead of resending;
  limits 10 orders/second, 400/minute, a daily cap (3,000 per Zerodha's support page vs 5,000 per Kite docs -
  conflicting, unverified; **settled 2026-10-07: 5,000 per day and 400 per minute per user/API key**, kite.trade/docs/
  connect/v3/exceptions "will not be able to place more than 5000 orders per day", re-read raw), 25 modifications per
  order; autoslice returns mixed success and failure per slice, at most
  10 slices; market and SL-M API orders need non-zero market protection; TokenException (403) means the session expired
  or the user logged in elsewhere.
- Bears on: REQ-056, REQ-057, REQ-058, REQ-060, ADR-017, ADR-050 item 4. Status: **decided** for the P4 brief (ADR-050);
  the daily cap is **unverified**.

## F-08 - Multi-broker platforms isolate each broker in a plugin with a contract master and a capability file
- OpenAlgo (github.com/marketcalls/openalgo, docs.openalgo.in): 36 broker plugins, each `broker/<name>/` with
  `api/auth_api.py`, `api/order_api.py`, `api/data.py`, `mapping/`, `database/master_contract_db.py`, `plugin.json`; a
  `symtoken` table maps its common symbol to each broker's symbol and token; broker tokens are encrypted server-side.
  NautilusTrader: explicit order states, fills de-duplicated by trade id, reconciliation at startup and periodically,
  orders found at the broker but unknown locally recorded as external. Read 2026-10-02.
- OpenAlgo's licence is not checked (possibly AGPL): reference design only. Bears on: REQ-054, ADR-050 item 5.
  Status: **decided** (reference only).

## F-09 - algochanakya's cross-broker symbol design keys on a Zerodha symbol string and is mostly stubs
- `broker_instrument_tokens` joins on `canonical_symbol` = the Kite tradingsymbol (`models/broker_instrument_tokens.py:23-56`);
  `SymbolConverter` implements only Kite and SmartAPI, the other four raise NotImplementedError
  (`symbol_converter.py:171-194`); two competing weekly formats (`symbol_converter.py:41,85` vs `utils/tradingsymbol.py:37-44`);
  monthly expiry assumed to be the last Thursday (`symbol_converter.py:43-53`); three broker-name vocabularies
  (`zerodha`/`kite`, `angelone`/`angel`/`smartapi`, `.claude/rules/broker-name-mapping.md`). Read 2026-10-02 at `bf9faf7`.
- Bears on: spec/technical-design/legacy-reuse.md (rows stay SKIP), ADR-050 item 5. Status: **decided**.

## F-10 - Zerodha's `exchange` column is not an exchange segment: (exchange, exchange_token) collides
- Measured 2026-10-02 on Zerodha's public instrument file (`api.kite.trade/instruments`) by the W-056 builder: 30 pairs
  of (`exchange`, `exchange_token`) appear twice, all with `exchange` = NSE, one row in Zerodha segment INDICES and one
  NSE cash row. Example: NSE / 1001 is both "NIFTY 50" (segment INDICES) and "94SFL28-YL" (segment NSE). None of the
  4,970 in-scope NFO/BFO option and future rows collide.
- So "exchange segment" in ADR-050 and REQ-054 AC-3 means the exchange's market segment, not Zerodha's `exchange`
  column, and is our own fixed list (REQ-054, "Exchange segment vocabulary"). The W-056 stage 1 code keyed on Zerodha's
  `exchange`; the brief misstated the requirement (spec-adherence class 1), corrected in W-056.
- Bears on: REQ-054 AC-3, REQ-053, ADR-050 items 1 and 2. Status: **decided** (wording of the existing decision; no
  rule change). Registry: `knowledge/findings/instrument-identity-keyed-on-one-broker.json`.

## F-11 - SEBI's retail-algo circular (primary text): brokers are principals, algo providers their agents, empanelled with exchanges
- Source: SEBI circular SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013, 4 Feb 2025, "Safer participation of retail
  investors in Algorithmic trading" (sebi.gov.in/sebi_data/attachdocs/feb-2025/1738665456458.pdf), read raw 2026-10-07.
  Level P1 (primary).
- Para I(a): brokers "shall be the principal" and any algo provider or fintech/vendor "shall act as its agent". I(b):
  every algo order through a broker API is tagged with an exchange-provided unique identifier. I(c): a retail investor's
  own algo is registered only above the order-per-second threshold, and may be used for the family (self, spouse,
  dependent children, dependent parents) "but not for other investors". I(d): brokers give API access only "through a
  unique vendor client specific API key and static IP whitelisted by the broker", OAuth only, two-factor
  authentication, and "deal with empaneled algo providers only". III(a): an algo provider "providing the facility to
  place algo orders with Brokers through API, shall require to be empaneled with Exchanges". Footnotes define white-box
  and black-box algos (5, 6) and the kill switch (4). Applicability: "with effect from August 01, 2025" (para 7(b)).
- In force: as dated; later extensions of that date are not yet read (Stage 1 stream S1a checks them).
- Bears on: Q258, REQ-042, REQ-054, REQ-063, REQ-066, ADR-009, ADR-050 item 4. Status: **decided** (ADR-054,
  2026-10-07: the platform sends no orders through the API; Zerodha's confirmation pending).
  Whether our platform is an "algo provider" sending "algo orders" is not settled by this text alone; S1a reads the
  definitions and FAQs, and Q258 stays with Zerodha's answer and the Q211 legal review.

## F-12 - NSE's implementation standards: a static IP maps to one client only (family excepted); API sessions end daily
- Source: NSE circular NSE/INVG/67858 (Circular Ref. 471/2025), 5 May 2025, annexure "Implementation Standards"
  (nsearchives.nseindia.com/content/circulars/INVG67858.pdf), read raw 2026-10-07. Level P1 (primary).
- A.1: clients "must mandatorily provide the stockbroker with a static IP address(es)" for API access; A.2 one primary,
  optional secondary. A.5: for algos via an empanelled algo provider "the static IP shall be that of the vendor or the
  client". A.6: the mapped IP may change at most "once a calendar week". A.7: "A static IP can only be mapped to one
  client at a time", shared only within one family (SEBI circular SEBI/HO/MIRSD/MIRSD-PoD1/P/CIR/2024/169, 3 Dec 2024)
  on the client's written or 2FA request. A.8: "All API sessions shall be compulsorily logged out every day before the
  start of the next trading day". B.2: the Threshold Order Per Second (TOPS) is 10 orders per second per exchange; below
  it a client need not register the algo, above it registration with each exchange is required (C.1).
- Consequence to verify, not a conclusion: if our server sends many unrelated users' orders from one IP, A.7 does not
  let that IP be each user's client IP; A.5 allows a vendor IP only for an empanelled algo provider. This is the centre
  of Q258 and of master-plan decisions D1 and D5.
- In force: as dated; later NSE circulars and BSE's equivalent are not yet read (S1a).
- Bears on: Q258, Q205 (daily session end), REQ-015 AC-7, REQ-054, REQ-063. Status: **decided** (ADR-053 daily
  session pause; ADR-054 no orders from our server, so no shared static IP).

## F-13 - OpenAlgo is licensed AGPL-3.0: copying any of its code would put our whole hosted backend under AGPL
- Source: github.com/marketcalls/openalgo, file `License.md` on `main` (raw.githubusercontent.com/.../main/License.md;
  a `LICENSE` file does not exist, 404), read raw 2026-10-07: "GNU AFFERO GENERAL PUBLIC LICENSE Version 3, 19 November
  2007"; GitHub's licence API reports AGPL-3.0. Level P1. AGPL section 13: a modified version that users interact with
  over a network must offer them its source. OpenAlgo's own docs describe it as a single-user, self-hosted tool, "not a
  multi-tenant SaaS" (docs.openalgo.in/responsibilities, read by stream S2b, not re-checked).
- Closes the gap left open in F-08 and ADR-050 item 5 ("no code is copied until its licence is checked"): ideas only,
  never code.
- Bears on: ADR-050 item 5, F-08, REQ-054, spec/technical-design/legacy-reuse.md. Status: **recorded** (the existing
  decision already says reference design only; this confirms it).

## F-14 - Exchanges do empanel SaaS algo providers by circular; a comparable product is empanelled "on provisional basis"
- Source: NSE circular NSE/INVG/71820, 16 Dec 2025, "Algo Provider - Provisional Empanelment for providing Algorithmic
  Trading Solutions" (nsearchives.nseindia.com/content/circulars/INVG71820.pdf), read raw 2026-10-07. Level P1. It lists
  "M/s. Oraph Private Limited" (the company behind AlgoTest, per algotest.in), category "White Box", empanelled "on
  provisional basis". AlgoTest's home page says "Exchange Empanelled" without "provisional" (stream S2b, P1 page).
- Meaning for us: empanelment is a real route that comparable SaaS platforms use; whether we need it is still Q258.
  Whether the NSE list has more entries, and BSE's list, is not yet read.
- Bears on: Q258, REQ-066, master-plan decisions D1/D2. Status: **decided** (ADR-054: empanelment is the fallback path
  if Zerodha says basket orders are algo orders).

## F-15 - SEBI penalised a stock broker for its association with a SaaS algo platform whose strategies showed assured returns
- Source: SEBI adjudication order Order/JS/YK/2025-26/32256, 25 Mar 2026, "In the matter of TradeTron and other Algo
  Platforms", in respect of R. K. Stockholding Pvt. Ltd. (sebi.gov.in/sebi_data/attachdocs/mar-2026/ORDER_1774428858.pdf),
  read raw 2026-10-07. Level P1. SEBI found TradeTron was "a Software as a Service (SAAS) platform" where a few
  strategies "were giving guaranteed returns/misleading content"; the broker associated with it was charged under clause
  4.2 of SEBI circular SEBI/HO/MIRSD/DOP/P/CIR/2022/117 (2 Sep 2022) and penalised Rs 2,00,000. SEBI also ran a
  "Settlement Scheme on Association with Certain Algo Platforms, 2025" (16 Jun - 16 Oct 2025) for such brokers.
- Meaning for us: what a platform shows (returns, performance, "assured" wording) becomes the associated broker's
  problem, and so the owner's (a Zerodha Authorised Person) and Zerodha's. It strengthens ADR-003 (decision-support
  wording) and the REQ-005 forbidden-phrase check; the 2022 circular's clause 4.2 text is not yet read (stream S1b).
- Bears on: ADR-003, REQ-005, REQ-051 (simulation results), REQ-066, H4, H10. Status: **decided** (ADR-055: no return
  claims, no marketplace)
  (whether past-performance or backtest display needs a rule beyond REQ-051 AC-7).

## F-16 - Brokers' public option chains are delayed for signed-out visitors; live prices only after login
- Source (P1, the brokers' own public pages, read 2026-10-07): Dhan dhan.co/options-trader "Current prices on the
  website are delayed by 15 mins, login to check live prices" (re-checked raw); Upstox upstox.com/option-chain/nifty
  "Price is delayed. Login to view real-time data" (stream S2b, not re-checked).
- Meaning for us: even brokers do not show live option prices to signed-out visitors. This matches REQ-010 AC-1 ("no
  live data without login") and is evidence for hypothesis H1; the rule behind it (exchange data policy) is S1b's.
- Bears on: REQ-010, REQ-029 AC-7, REQ-052, H1. Status: **recorded**.

## F-17 - Every order sent through a broker API counts as an algo order, even one the user confirms; only the broker's own front end is not
- Source: NSE circular NSE/INVG/69255, 22 Jul 2025, Annexure I "Detailed operational modalities for empanelment of Algo
  Providers and registration of Retail Algo", para 2.8 (read raw 2026-10-07): "all orders received via API from clients /
  Algo Provider's platform shall be considered as Algo and will be required to be tagged". NSE FAQ "Safer participation
  of Retail investors in Algorithmic trading" (3 Nov 2025), Q8: "all orders received via API from clients are considered
  Algo orders and require appropriate tagging including ... within the threshold of 10 OPS". Para 2.4 of the same
  annexure keeps non-algo status only for orders entered in the trading member's own front end with manual entry of
  every order attribute. Level P1. (Found by stream S1a; the quoted lines re-read raw by the orchestrator.)
- Meaning for us: hypothesis H5(b) is answered by the text: "the user reviews and presses Execute" does not make an
  order sent by our server through the Kite Connect API a non-algo order. This rests on reading the circular text; it
  is not a legal opinion (Q211).
- In force: yes, for all brokers from 1 Apr 2026 (F-19).
- Bears on: ADR-009, ADR-017, ADR-050 item 4, REQ-042, REQ-054, REQ-056, REQ-063, REQ-066, Q258, master plan D1/D2 and
  Stage 4b. Status: **decided** (ADR-054; Zerodha's confirmation pending, Q259).

## F-18 - Algo providers must be empanelled and their algos run on the broker's servers; a client's own static IP is only for a tech-savvy client's own API use
- Source (P1, read raw 2026-10-07): NSE FAQ (3 Nov 2025) Q5 quoting NSE/INVG/69255 Annexure I para 14: "all the
  strategies shall be run on the brokers servers. The order messages shall be originated from brokers server"; Q4:
  "all Algos developed by Algo Providers need to be hosted on the Trading Member's server"; Q3: "Client static IP will
  be required only in case of Tech savvy Investor using API for placing orders". Annexure I para 3: an algo provider
  "can be any fintech / vendor providing algo facility through the usage of API"; para 2.7: a black-box algo's provider
  must be registered as a Research Analyst with SEBI. Stream S1a also reported (not re-read by the orchestrator):
  empanelment criteria in NSE/INVG/70309 (ISO 27001:2022, half-yearly VAPT by a CERT-In empanelled auditor, two years'
  market experience of one director, net-worth certificate) and turnaround of 30 working days.
- Meaning for us: a hosted SaaS that sends many users' orders from its own server is, on this text, an algo provider
  whose strategies would have to run on the broker's (Zerodha's) servers. Paths to weigh, none decided: (a) become an
  empanelled provider hosted on Zerodha's infrastructure (whether Zerodha offers that is unknown); (b) hand the
  prepared orders to Zerodha's own front end for the user to place (e.g. a Kite basket - whether that counts as the
  broker's front end is unknown); (c) a planning-only product with no order sending. F-14 shows (a) is used by peers.
- Bears on: as F-17, plus REQ-003, REQ-015, master plan D5. Status: **decided** (ADR-054 chose path (b)).

## F-19 - The framework applies to all brokers from 1 April 2026; Zerodha allows up to two static IPs, used only by the client and immediate family
- Source (P1, read raw 2026-10-07): SEBI circular SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/132, 30 Sep 2025, para 8: "W.e.f.
  April 01, 2026, algo framework ... will be applicable for all stock brokers." Zerodha support article on static IP:
  "You can add up to two IPs"; the user confirms "the above static IPs will be used exclusively by me and/or my
  immediate family". Stream S1a found no later SEBI extension (searched SEBI titles "algorithmic"/"algo"; a zero-hit
  search is a check, not proof).
- Supersedes F-06's "1 Apr 2026" (now P1) and its Zerodha family-only line (now P1).
- Bears on: F-06, F-12, Q258, REQ-054, REQ-063, master plan D5 and Stage 4b (a test order needs a whitelisted IP used
  only by the owner's family). Status: **recorded**.

## F-20 - Index F&O today: NIFTY lot 65 expiring Tuesdays (some Mondays), SENSEX lot 20 expiring Thursdays
- Measured 2026-10-07 on the exchanges' own daily files for 6 Oct 2026: NSE BhavCopy_NSE_FO_..._20261006: 1,918 NIFTY
  option rows, lot (`NewBrdLotQty`) 65 on all 1,918; expiry weekdays Tue 1,437, Mon 481. BSE F&O bhavcopy of the same
  day: 603 SENSEX option rows, lot 20 on all 603, every expiry a Thursday. Level P1 (data).
- Rules behind it (stream S1a, P1, not all re-read by the orchestrator): SEBI CIR/2024/132 (1 Oct 2024) - one weekly
  benchmark expiry per exchange, contract value Rs 15-20 lakh, option premium collected upfront, extra 2% ELM on short
  options on expiry day, no calendar-spread benefit on expiry day; SEBI CIR/2025/76 - each exchange's expiries on Tuesday
  or Thursday; NSE moved to Tuesday from 1 Sep 2025; NSE FAOP70616 (NIFTY lot 65).
- Meaning for us: matches ADR-042's lots (65/20) and F-05 (read expiry from the file). Mondays are presumably holiday
  shifts (unverified).
- Bears on: REQ-001, REQ-026, REQ-053, REQ-054 AC-4, ADR-042, F-05. Status: **recorded**.

## F-21 - Exchange contract numbers are reused for different contracts after expiry (NSE), so (segment, number) is unique only on a given day
- Source: NSE circulars FAOP60133 (5 Jan 2024) and FAOP48511: F&O token numbers "should range from 1 to 31980 & 750001
  to 999999" (P1, stream S1a; not re-read by the orchestrator). The only statement of reuse is a Zerodha staff forum
  post from Dec 2016, "exchange reuses token after expiry" (P2, **unverified**); it would be verified by NSE's F&O
  consolidated circular Part D or the contract-file specification, or by stream S3's data count (pending).
- **Measured 2026-10-07 (stream S3, recounted by the orchestrator with its own script):** across 45 NSE F&O
  bhavcopies (every trading day 3 Aug - 6 Oct 2026), 65,265 contract numbers (`FinInstrmId`); 4,768 of them map to more
  than one contract (symbol, expiry, strike, option type). Example: 67245 was ABCAPITAL 25-Aug-2026 410 PE, then
  NIFTYNXT50 29-Dec-2026 72200 PE; 421 such numbers touch NIFTY (e.g. 53334: TATAELXSI 25-Aug-2026 2900 PE, then NIFTY
  03-Nov-2026 20550 CE). No file has two contracts on one number on the same day. BSE: no reuse in 3,575 numbers over
  the same dates; 107 SENSEX numbers reused in the 2025 samples (S3, not recounted). S3 also saw a live contract's
  strike change under the same number (NSE 79199 HINDPETRO 410 -> 390.75 from 14 Aug 2026, likely a corporate action,
  unconfirmed). Zerodha's own docs: "Exchanges may reuse instrument tokens for different derivative instruments after
  each expiry" (kite.trade/docs/connect/v3/market-quotes, P1, re-read raw).
- Meaning for us: the identity in the ADR-050 decision, (exchange segment, exchange token), is unique on a given day
  but not over time; a stored strategy leg keyed on it alone could later point at a different contract. The identity
  needs the expiry (or a validity range) as well; changing it is an owner decision (Q262). Closes the data question of
  #116.
- **Also measured 2026-10-07 (orchestrator, raw NSE files):** the exchange moves the expiry of LIVE contracts under the
  same number - 62964 NIFTY 31000 PE 26-Mar-2026 (Jun 2025) -> 31-Mar-2026 (Sep 2025, the NSE expiry-day move); 61746
  NIFTY 23000 CE 27-Dec-2029 -> 24-Dec-2029 (Sep 2025), later reused for WIPRO (2026). So the expiry cannot be part of
  the key.
- Bears on: ADR-050 item 1, F-01, REQ-053, REQ-054 AC-3, #116, #115. Status: **decided** (ADR-057, correcting ADR-052:
  identity holds while the contract is live; the token retires after expiry).

## F-22 - Zerodha's "offsite order execution" (Kite basket / Publisher) lets the user place our prepared multi-leg orders on Zerodha's own exchange-approved order page
- Source: Kite Connect v3 docs, "Offsite order execution" (kite.trade/docs/connect/v3/basket/) and Kite Publisher
  (kite.trade/docs/connect/v3/publisher/, kite.trade/publisher), read raw 2026-10-07 (page footer "2015 - 2025"). Level
  P1 (Zerodha's own docs).
- Quotes: it redirects users "to Kite's exchange approved order page where they place orders and come back to your
  application seamlessly, like a payment gateway"; "you do not have to build, maintain, and get exchange approvals for
  order execution screens". The basket is a JSON list of orders (the example mixes NSE and NFO, MARKET and LIMIT);
  `readonly: true` means users "can only review and execute"; each order may carry a `tag` (alphanumeric, max 20 chars);
  the user returns to our redirect URL with `status` and `request_token`. Kite Publisher "is available free of charge".
- Not stated (gap): whether orders placed this way count as non-algo under the 2025 framework (F-17 keeps non-algo
  status for the broker's own front end with manual entry of the order attributes); how many orders a basket may hold;
  how a failed leg is reported back. Only Zerodha's written answer settles the first (ADR-034 thread).
- Meaning for us: a candidate for Q259 path (b) that keeps "every order belongs to a strategy" (our `tag` per order,
  ADR-050 item 4(a)) while the order is placed on Zerodha's own page; it also fits ADR-009 (the user executes).
- Bears on: Q259, Q258, ADR-009, ADR-017, ADR-050 item 4, REQ-042, REQ-054, REQ-056, REQ-057. Status: **decided**
  (ADR-054: the planned order path; Zerodha's confirmation of its algo status pending).

## F-23 - Live exchange prices: SEBI bars sharing them with platforms, NSE bars redistribution without an agreement, and Kite's terms bar public display
- Source (P1, read raw 2026-10-07, stream S1b, re-read by the orchestrator): SEBI circular of 24 May 2024 on sharing
  of real-time price data, para 2(i): MIIs and brokers shall "ensure that no real time price data is shared with any
  third party including various platforms" except where required for orderly functioning or regulation. SEBI circular
  of May 2026 (forwarded by NSE/COMP/74156, 11 May 2026): "a time lag of 30 days for both sharing and usage of price data
  for educational purposes", effective 1 Jul 2026. NSE Data Sharing & Usage Policy cl. 7.3-7.4: no redistribution of
  market data "except as agreed in the Relevant Agreement"; not to be provided to virtual-trading or simulation (S1b,
  not re-read). Kite Connect terms (kite.trade/terms): content returned by the APIs may not be distributed or "publicly
  display"-ed; but "You may use the APIs to build platforms which You may in turn offer to other Clients of Zerodha
  (after obtaining the required exchange approvals)".
- Also reported by S1b (P1, not re-read): NSE prices display "per medium" (website and app are two media); 15-minute
  delayed F&O data is itself a paid product; using market data to derive values falls under NSE's non-display policy.
- Meaning for us: (a) signed-out visitors: no live, delayed or recent prices without an NSE (and BSE) licence;
  "education" needs data at least 30 days old. (b) A user's own Kite data shown to that user inside our SaaS: allowed
  by Kite's terms for "platforms ... offer[ed] to other Clients of Zerodha" only after exchange approvals; whether the
  SEBI 2024 "third party ... platforms" bar applies is not settled by the text. Only Zerodha's written answer (ADR-034)
  settles (b).
- Bears on: ADR-012, ADR-014, ADR-034, REQ-010, REQ-029, REQ-048, REQ-050, REQ-052, Q204, Q210, H1. Status: **decided**
  for (a) and for V1's per-user feed (ADR-053); (b) for other users waits for Zerodha's written answer (Q210, ADR-034;
  ADR-051 covers the owner's own account only).

## F-24 - SEBI's Research Analyst definition is broad and has no exemption for tools; a comparable app holds RA registration
- Source (P1, read raw 2026-10-07): SEBI (Research Analysts) Regulations 2014 as amended (Third Amendment, Gazette 16
  Dec 2024; consolidated to 25 Nov 2025), reg 2(1): research services include price targets, stop losses, trading calls
  and "any other service of similar nature or character"; a research report excludes only "comments on general trends
  in the securities market" and discussions of broad-based indices. No exemption for calculators or tools was found.
  SEBI's RA register: INH200006895 = RISKILLA SOFTWARE TECHNOLOGIES PRIVATE LIMITED (Sensibull's operator), "Validity
  Jul 30, 2025 - Jul 29, 2030". The 2025 algo framework (F-18) also requires RA registration for black-box algo
  providers.
- Interpretation (not a ruling): payoff and what-if tools look outside RA; "suggested setups" with strikes, stop-loss or
  adjustment triggers on a paid plan may fall inside it. Our wording rule (ADR-003) does not by itself decide this.
- Bears on: ADR-003, ADR-005, ADR-011, REQ-005, REQ-024, REQ-025, REQ-027, REQ-045, REQ-046, REQ-068, REQ-069, Q211, H3.
  Status: **decided** (ADR-055 strict default until the legal review answers Q261).

## F-25 - Regulated entities, Authorised Persons included, may not associate with unregistered advisers or anyone making return claims
- Source (P1, read raw 2026-10-07): SEBI circular of 29 Jan 2025 on association with unregistered entities (updated 8
  May 2026), FAQs: agents include "Authorised Persons of stock brokers"; association includes money, client referral or
  "interaction of information technology systems". NSE Code of Advertisement NSE/COMP/55482 (2 Feb 2023) §5.7(c): no
  direct or indirect association "with any platform providing any reference to the past or expected future
  return/performance of the algorithm". PaRRVA (SEBI circular of 29 Apr 2026, S1b, not re-read): verified past
  performance only for IAs, RAs and algo services.
- Meaning for us: if the platform gave unregistered advice or performance claims, the owner (an AP) and Zerodha would be
  exposed - the same class as F-15. Together with F-24 this decides how suggestions and simulations may be worded.
- Bears on: ADR-003, ADR-013, REQ-005, REQ-051, REQ-066, F-15, H4. Status: **decided** (ADR-055 strict default; Q261).

## F-26 - An Authorised Person may not charge clients and brokers may not give incentives for account opening or subscription plans
- Source (P1, read raw 2026-10-07): SEBI Master Circular for Stock Brokers (17 Jun 2025), chapter on Authorised
  Persons: the AP receives remuneration "only from the stock broker and he shall not charge any amount from the
  clients". NSE/COMP/55482 §5.5(a): members "shall refrain from providing any form of incentive/vouchers/coupons/
  certificates/tokens, by whatever name called, to their clients for account opening/trading ... or any kind of
  subscription plan". An NSE consultation of 6 Aug 2026 would narrow the AP rule to charging "in the capacity of AP" -
  a **proposal, not in force** (S1b, not re-read).
- Interpretation (not a ruling): three owner decisions are exposed as written - free Pro for clients who opened Zerodha
  accounts through the owner (ADR-024), 30 days of Pro per referred account opening (ADR-025, ADR-038), and the owner as
  an AP selling Rs 600/month Pro to clients (ADR-026). A separate legal entity, Zerodha's written view or the proposed
  AP framework may change the answer.
- Bears on: ADR-024, ADR-025, ADR-026, ADR-038, ADR-044, REQ-019, REQ-020, REQ-021, REQ-022, REQ-023, H11. Status:
  **decided** (ADR-055: paid plan, free Pro and referral rewards held until Zerodha compliance answers Q260).

## F-27 - Data-protection and cyber-security duties with dates
- Source (P1, read raw 2026-10-07): DPDP Rules 2025 (G.S.R. 846(E), 13 Nov 2025), rule 1(4): rules 3, 5-16, 22, 23 come
  into force "eighteen months after the date of publication" (13 May 2027); rule 7: breach report to the Board "within
  seventy-two hours"; rule 8 (S1b, not re-read): logs kept at least one year. CERT-In directions of 28 Apr 2022: report
  cyber incidents "within 6 hours of noticing", keep ICT logs "for a rolling period of 180 days" in India; applies to
  every body corporate.
- Bears on: REQ-013, REQ-063, REQ-064, Q96, ADR-029, H6, H10. Status: **recorded** (requirements to be written in Stage 3).

## F-28 - Payments, GST and advertising gates (stream S1b, not re-read by the orchestrator)
- Razorpay's prohibited list names "Securities ... related financial products" and lets the bank refuse at its sole
  discretion; trading tools are not named (razorpay.com/terms, P1). RBI e-mandates: authentication at registration and
  first debit, later debits up to Rs 15,000 without it, notice at least 24 hours before each debit (RBI/2019-20/47,
  RBI/2023-24/88, P1). GST registration above Rs 20 lakh turnover for services (CGST Act s.22, P1); the SaaS GST rate is
  unknown. Google and Meta verify financial-services advertisers in India and ask for SEBI registration or exemption
  (P1 policy pages; Meta read through a rendered page only).
- Bears on: ADR-026, REQ-023, H9, H10. Status: **unverified** until re-read in Stage 3 (each is cited by the Stage 3
  payments requirement only after a re-read).

## F-29 - Core data proof on the owner's own account: live Kite login, quotes and basket margin work; the real field shapes differ from our model in three ways
- Measured 2026-10-07 ~20:00 IST (market closed; prices from that day's close) under ADR-051, with a throwaway script
  (`docs/research/kite-proof-2026-10-07/kite_core_proof.py`, raw replies beside it; no personal data). Level P1 (real
  data from Zerodha's API).
- Values: NIFTY 50 22,603.05, SENSEX 72,638.70. Nearest expiries: NIFTY 13-Oct-2026 (216 contracts, ATM 22,600), SENSEX
  08-Oct-2026 (336 contracts, ATM 72,600). NIFTY26O1322600CE (exchange token 44616) last price 124.30, OI 6,697,665,
  lot 65, timestamp "2026-10-07 16:54:19"; SENSEX26O0872600CE (889159) 189.40, lot 20. Basket margin of a 1-lot NIFTY
  iron condor (sell 22,800 CE, buy 23,000 CE, sell 22,400 PE, buy 22,200 PE): initial total 293,560.08, final total
  66,431.68 (`/margins/basket`, consider_positions=false).
- Field shapes our adapter must map (the domain `Quote` model, backend/ofo/marketdata/quote.py, uses normalised
  names): (1) `timestamp` and `last_trade_time` are naive "YYYY-MM-DD HH:MM:SS" strings - the adapter attaches IST
  (our model refuses a naive time, correctly); (2) bid/ask exist only inside `depth.buy/sell`, and after the close
  every level reads price 0, quantity 0 - 0 must map to "absent", never to a Rs 0 price; (3) there is no OI-change
  field (`oi`, `oi_day_high`, `oi_day_low` only). The reply also carries fields not in Kite's public docs:
  `high_limit_price_protection`, `low_limit_price_protection`, `reference_limit_price`, `total_imbalance_qty`,
  `indicative_close_price`. `ohlc.close` is the previous day's close (643.35 for the 22,600 CE).
- Margin reply shape: `initial`, `final`, `orders` (each with span, exposure, option_premium, additional, total,
  charges ...) and `charges`.
- Still to prove in market hours (master-plan 4a step 2): live WebSocket ticks, reconnect, stale detection, our Greeks
  against Kite's, and the next morning's token expiry.
- Bears on: REQ-048, REQ-049, REQ-052, REQ-053, REQ-055, REQ-072, ADR-051, W-017 (real responses now exist). Status:
  **recorded**.

## F-30 - The exchange removes contracts before their expiry and reuses their numbers; "any unexpired contract disappears" is not a sign of a broken download
- Measured 2026-10-07 by the orchestrator. NSE F&O bhavcopies: token 61746 was NIFTY 23000 CE expiring 27-Dec-2029
  (Jan 2025), 24-Dec-2029 (Sep 2025); from 26-Aug-2026 the same token is WIPRO 23-Nov-2026 futures, and no NIFTY
  Dec-2029 23000 CE appears in any 2026 file. Zerodha's instrument list read the same day (api.kite.trade/instruments,
  108,383 rows): token 61746 = NFO WIPRO26NOVFUT; NIFTY Dec-2029 CE strikes listed are 15000, 16500, 18000, 19500,
  21000, 22500, ... (13 in all, 1,500 points apart) - no 23000 CE. Level P1 (real data).
- Meaning: (1) a contract can leave the market before its expiry date (here a long-dated strike grid was rebuilt), and
  its number can be reused while the old contract's expiry date is still in the future - so ADR-057's "retired after
  expiry" needs a second exit, "no longer listed"; (2) the Q244 guard (refuse a daily update that would remove any
  unexpired contract) would refuse every daily list after such a clean-up and freeze the catalogue, the failure Q257
  was written to avoid. The bhavcopy alone cannot date the removal (it may omit untraded contracts); Zerodha's list can.
- Bears on: ADR-057, REQ-053 (Q244, Q257), REQ-054 AC-3, W-057, F-21. Status: **decided** (ADR-058).

## F-31 - Zerodha grants multi-user Kite Connect access only to a production-ready platform, after a demo; the API fee is waived for active traders
- Read 2026-10-08 by the orchestrator from the owner's mailbox (with the owner's request). Level P1 (Zerodha's own
  written words).
- Ticket 403947 (talk@rainmatter.com, reply of 2026-09-29 to the owner's 2026-09-28 request): "To review your request
  for multi-user access, kindly provide": a complete workflow and how trades are executed; the specific use case;
  whether the platform is in Production or Beta - "permissions are granted only for production-ready platforms"; "A
  demo video showcasing the complete functionality"; the website/application link with demo credentials; the API
  endpoints required (Holdings, Positions, Orders, Portfolio, Trade Book ...); unique and additional features; whether
  use is limited to Holdings, Portfolio, Positions, Order Book and Trade Book; a SEBI RA registration number if the
  platform "provides investment research, recommendations, or advisory services"; the market-data endpoints required
  (Quote, Historical Data, WebSocket). "If required, we will schedule a demo call." The owner's five questions
  (eligibility, WebSocket data, display to the same client, limits, AP conditions) were not answered.
- The ticket was set to "resolved" on 2026-10-01 because no reply came within 24 hours; reapplying needs the ticket
  reopened or a new one.
- Zerodha email of 2026-10-07 ("Free API subscription for active users"): from October 2026, an account with Rs 2,000
  or more brokerage in a calendar month gets 500 developer credits (= Rs 500), which renew its Kite Connect app the
  next month; below Rs 2,000 the regular Rs 500 charge applies.
- Meaning: Zerodha's answer to Q210/Q258 depends on a working product, so waiting for it before building cannot end;
  a per-user own-app path (Q210 option) costs an active trader nothing.
- Bears on: Q210, Q258, Q259, Q261, ADR-034, ADR-051, ADR-054, REQ-015, REQ-052. Status: **decided** (ADR-060).

## F-32 - Live market-hours checks on the owner's account: one Kite WebSocket carries both full two-expiry chains; IV from index spot is wrong on every chain; "no tick for 60 s" is not staleness
- Measured 2026-10-08 08:38-09:45 IST (window 09:15-09:45) under ADR-051/ADR-060, throwaway script
  `docs/research/kite-proof-2026-10-07/kite_live_checks.py`, summary (no personal data) in `live-2026-10-08/summary.json`;
  raw frames kept outside the repo (`D:\Abhay\Ventures\ofo-kite-ticks\2026-10-08\`, 108,113,971 bytes gzip). Level P1.
- Subscription: 1,091 instruments on ONE connection, full mode (NIFTY 13-Oct 216 + 19-Oct 208, SENSEX 08-Oct 336 +
  15-Oct 328, NIFTY 50, SENSEX, INDIA VIX); every one ticked at least once; 17,380 frames, 1,214,932 ticks, 1,336
  heartbeats, 0 unplanned disconnects, 0 error messages (2 text messages, type `instruments_meta`).
- Feed: the longest gap without a data frame in market hours was 0.51 s (360 samples, 5 s apart). Receive time minus
  exchange timestamp: median 0.63 s, 95th percentile 1.12 s (includes clock skew).
- Forced reconnect at 09:30:00.150: reconnected and re-subscribed in 1.628 s, first data 2.171 s, data gap 2.176 s.
  The gap was shorter than the 3 s feed-stale threshold sampled every 5 s, so the feed-stale flag was NOT exercised
  live (not proven; to be proven by replaying these frames with an inserted gap).
- Per-contract quiet periods: 99.5% of inter-tick intervals were 30 s or less, but at any moment a median of 59
  contracts (max 354 of 1,091) had sent no tick for over 60 s while the feed was live - Kite sends nothing when a
  contract does not change. So the existing rule "older than 60 s = stale" (backend/ofo/marketdata/health.py
  `stale_after`) would mark about 5% of a healthy chain stale at any time. Staleness must follow the feed's state for
  the subscription, not the age of a contract's last change.
- History: the frame file read back complete (17,380 of 17,380 frames, 1,214,932 ticks). Size about 1.6 MB per
  minute gzip for 1,091 instruments, so about 600 MB per full trading day per feed.
- Engine on live prices (7 snapshots 09:18-09:45, the 21 strikes nearest the money per expiry, bid-ask mid): the
  engine's own IV reprices every option to Rs 0.00; IV 12.1-14.6% (NIFTY), 27-31% (SENSEX expiring that day),
  12.8-17.3% (SENSEX 15-Oct); INDIA VIX 14.06-14.20; no Greek sign violation. With index SPOT as the input, the call and
  put at the same strike differ by a median 1.2-10.5 vol points; with the put-call-parity forward, 0.02-0.26 points.
  The forward sat 12.76-77.06 points below spot. Up to 5 of 42 IV solves per snapshot failed, all deep in-the-money
  calls priced below the intrinsic value that SPOT implies (e.g. NIFTY 21,950 CE at 531.75 against a floor of 542.37).
  The forward's spread across strikes was 0.9-13.5 points except SENSEX 15-Oct at 09:18 (97.5 points, the opening
  minutes), so the forward needs a quality check, not only a strike count.
- Kite exposes no Greeks or IV anywhere (quote, WebSocket), so "our Greeks against Kite's" cannot be run; the check
  became internal consistency (above).
- ADR-030 Phase-0 checks: live ticks 30 min - PASS; full chain rebuild - PASS (every contract ticked; bid and ask on
  216/216, 208/208, 334/336, 271-328 contracts); Greeks against Kite - NOT POSSIBLE (no Kite Greeks), internal check
  PASS with the forward, FAIL with spot; stale flagged - PARTIAL (per-contract ages measured; feed-stale not
  exercised); forced reconnect - PASS (2.2 s); history persisted - PASS; fan-out to 100/1,000 users - NOT RUN (frames
  recorded for the replay); licence status - recorded in F-23, F-31; next-morning token expiry - running (to be added).
- Afternoon run (2026-10-08 14:41-15:45, 1,603 instruments after the intraday strike additions of F-33): a forced
  disconnect with a 10 s pause at 14:51:02 was flagged stale at 14:51:08 (feed age 6.34 s), data resumed after a
  13.47 s gap, and the feed was flagged live again at 14:51:18 - **the feed-stale flag is now proven live (PASS)**.
  An unplanned laptop network outage (DNS failures, 15:08:13-15:10:08) was flagged stale after 7.88 s and recovered by
  itself with 16 s retries. 1,617,672 ticks; the frame file read back complete (11,075 of 11,075 frames).
- Bears on: REQ-048, REQ-049 (AC-2 health), REQ-072 (AC-3), REQ-047 AC-4, REQ-051, ADR-015, ADR-030, ADR-061.
  Status: **decided** for the Greeks input (ADR-061) and the staleness rule (W-059, merged: health follows the feed).

## F-33 - Afternoon market-hours capture: strikes are added during the day, Kite's REST includes charges and historical candles, money arrives as binary floats, and the expiry close was not recorded live
- Measured 2026-10-08 14:39-16:40 IST by the orchestrator on the owner's account (ADR-060), scripts
  `docs/research/kite-proof-2026-10-07/kite_rest_capture.py` and `kite_live_checks.py --tag pm`; replies in
  `rest-2026-10-08/` (market data in full; personal endpoints as key names and types only). Level P1.
- **Strikes are added during the trading day.** Kite's instrument list at 08:05 had 108 NIFTY 13-Oct strikes
  (20,050-25,400); at 14:39 it had 236 (17,150-28,900) - 128 added, none removed; NIFTY 19-Oct the same (104 -> 232);
  SENSEX unchanged. A once-a-day instrument load misses strikes listed after it ran.
- **REST endpoints during market hours** (all HTTP 200): `/quote` with live depth (NIFTY26O1322000CE bid 298.25 x 65,
  ask 298.95 x 780 at 14:59:40); `/margins/basket` for a 1-lot NIFTY iron condor initial 291,444.67, final 66,003.57;
  `/charges/orders` returns Zerodha's own breakdown per order (one leg: brokerage 20, STT 7.3125, exchange 1.7320875,
  SEBI 0.004875, stamp 0, GST 3.91265325, total 32.96211575); `/instruments/historical` returns minute candles with OI
  for today (344 for NIFTY 50 and for an option) and 21 daily candles for NIFTY 50 - **so the owner's Kite Connect plan
  includes historical data**, contrary to REQ-052 AC-1 "with no historical data" (open for owner decision).
- **Money arrives as binary floats** (e.g. initial margin `291444.67000000004`, charges `32.962115749999995`): the
  adapter must parse JSON numbers as Decimal from their text (never through float), or rupee totals pick up error.
- **Several Kite sessions coexist.** Logins at 08:38, 14:41 and 14:52 each issued a working token; the 08:38 token still
  answered after the later logins (its 14:45 and 15:00 probes passed). A new login does not end the previous token.
- **The SENSEX 08-Oct expiry close was NOT recorded live**: the laptop's internet dropped from about 15:26 to 16:26 and
  the feed stopped at 15:26. Recovered afterwards from historical minute candles: SENSEX's last index candle is 15:29
  (71,593.24); the expiring options have candles until 15:39 (e.g. SENSEX26O0872500CE 0.05, 72500PE 905.00, volume and
  OI still changing). Why options trade after 15:30 when the engine's expiry close is 15:30 is **unmeasured** (BSE
  closing session or a data artefact) - to check against BSE's published session timings.
- **Expired contracts stay in the instrument list the same evening** (398 SENSEX 08-Oct rows in the 16:30 BFO list).
- Bears on: REQ-052 AC-1 (history), REQ-053 (daily load timing), REQ-049 AC-1 (Decimal parsing), REQ-015 (sessions),
  ADR-008 / scenario-calculations §4 (expiry close time), ADR-057/W-057 (retirement), REQ-047/REQ-051 (history source).
  Status: **open** for the history decision and the expiry-close timing; **recorded** for the rest.

## F-34 - One-minute bars built from our own Kite ticks match Kite's minute candles on close and OI, not on open, high and low; a network drop leaves a gap
- Measured 2026-10-08 ~18:30 IST by the orchestrator on the owner's account (ADR-060), script
  `docs/research/kite-proof-2026-10-07/history_bars_proof.py`; result `history-bars-2026-10-08.json`. Level P1.
- Input: the two raw recordings of 2026-10-08 (08:38-09:45 and 14:41-15:26), 74 full market minutes; 1-minute bars
  built per instrument (index: by exchange timestamp; options: a trade = a rise in cumulative volume, bucketed by last
  trade time), compared with Kite's `/instruments/historical/<token>/minute?oi=1` for the same day and instrument.
- **OI matches every minute** (73 of 73 compared on each of 6 SENSEX 08-Oct options). **Close** matches 66-71 of 74 on
  the options and 72 of 74 on SENSEX, 45 of 74 on NIFTY 50 (largest non-gap miss 3.45 points). **Volume** matches 50-66
  of 74. Re-run bucketing option trades by the packet's exchange timestamp instead of last trade time: close 70-72 and
  volume 64-70 of 74, OI unchanged - as good or better, so bars use the exchange timestamp the normalized quote already
  carries (no last-trade-time field needed).
- **Open, high and low are approximate**: full-mode ticks are snapshots (about one a second), so trades between them are
  missed. E.g. NIFTY 50 09:16 high 22,563.45 from ticks vs 22,564.30 in Kite's candle; SENSEX26O0871000PE 09:15 open
  3.20 vs 3.95. Exact OHLC: 14-61 of 74 per instrument.
- **A network drop is a real gap**: 15:09 is missing from our bars and 15:08's close is stale (SENSEX 71,404.83 vs
  Kite 71,346.89, 57.94 points) - the laptop outage of F-32. Kite's candles cover both minutes.
- **Expired contracts keep their candles the same evening** (the SENSEX 08-Oct options returned 375 candles at ~18:30).
  Two far-from-the-money SENSEX 15-Oct options returned 0 candles - no trades that day.
- Meaning: bars from the live feed are good enough for intraday use (REQ-051 AC-4 "where practical") but not an exact
  record; Kite's own candles are exact and available after the close.
- Bears on: REQ-051 (AC-3, AC-4), REQ-047 AC-1, ADR-066. Status: **decided** (ADR-067).
