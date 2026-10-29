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
  recorded for the replay); licence status - recorded in F-23, F-31; next-morning token expiry - measured once in F-37
  (the token stopped between 04:29:48 and 04:30:48 IST).
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
- Added 2026-10-08 from the W-062 replay (`tests/fixtures/kite_history/`, 56 full minutes outside the drop, 8
  instruments incl. NIFTY26O1322550CE/PE, which the first run did not measure): **OI is not exact on every minute** - one
  miss, NIFTY26O1322550PE at 09:21 (ours 4,367,480, Kite 4,612,660): the exchange stamped the OI change 09:22:00 and
  Kite counts it in the 09:21 candle; assigning boundary-stamped OI to the earlier minute fixed that case and broke
  NIFTY26O1322550CE at 09:22, so it was not adopted. Close matched 3-4 of 7 minutes on the NIFTY rows, 7 of 7 on every
  SENSEX row; volume 7 of 7 on every option. The after-close final copy (ADR-067) replaces all such minutes with Kite's
  candles.
- Meaning: bars from the live feed are good enough for intraday use (REQ-051 AC-4 "where practical") but not an exact
  record; Kite's own candles are exact and available after the close.
- Bears on: REQ-051 (AC-3, AC-4), REQ-047 AC-1, ADR-066. Status: **decided** (ADR-067).

## F-35 - Zerodha's published F&O options rates reproduce its own charges reply exactly, except rounding: the brokerage calculator rounds STT and stamp duty to whole rupees, the order-level reply does not round STT
- Measured 2026-10-15 ~18:00 IST by the orchestrator. Sources: zerodha.com/charges (F&O options column, read
  2026-10-15; no date on the page), the brokerage calculator's script `zerodha.com/static/js/brokerage.js`
  (`cal_options`, read 2026-10-15), and Kite's `/charges/orders` reply captured 15:10 IST
  (`docs/research/kite-proof-2026-10-07/rest-2026-10-15-order/charges_CE.json`). Level P1.
- Published rates (charges page): brokerage "Flat Rs. 20 per executed order"; STT "0.15% on sell side (on premium)" and
  "0.15% of the intrinsic value on options that are bought and exercised"; NSE transaction "0.03553% (on premium)", BSE
  "0.0325% (on premium)"; GST "18% on (brokerage + SEBI charges + transaction charges)"; SEBI "Rs 10 / crore"; stamp
  "0.003% or Rs 300 / crore on buy side". The calculator splits NSE as 0.03503% transaction + 0.0005% IPFT (= 0.03553%).
- Check on 1 lot NIFTY26O1923550CE at 3.95 (premium Rs 256.75): rates give brokerage 20, NSE 0.0912, SEBI 0.0003, GST
  3.6165, STT on the sell 0.3851 - each equal to Kite's reply to 4 decimals; stamp on the buy gives 0.0077 where Kite's
  reply says 0.
- Rounding differs by source: the calculator applies `Math.round` (whole rupees) to STT and stamp, so it shows STT 0 on
  this sell; the order-level reply keeps STT 0.3851 and stamp 0. Which rounding the contract note applies per day or
  per scrip is **unmeasured** until a real fill (the Stage 4b order).
- Meaning: a rate table from the published page is accurate to the paisa on brokerage, exchange, SEBI and GST; STT and
  stamp need a stated rounding rule, and an estimate can differ from the contract note by under Rs 1 per order.
- Bears on: Q267 / ADR-082, ADR-071, REQ-032 (charges interface), REQ-059 AC-3. Status: **decided** (ADR-082).
- Added 2026-10-16 00:45 IST (orchestrator): all 4 real BUY rows in the 2026-10-15 replies (`charges_orders.json`,
  `charges_CE.json`, `charges_PE.json`) carry stamp 0, the largest at premium Rs 2,210.00 (BUY NIFTY26O1922550PE 34 x
  65), where 0.003% gives 0.0663; every other component of all 8 rows (4 BUY, 4 SELL) equals the published rates to 4
  decimals (e.g. SELL NIFTY26O1923150CE 53.3 x 65: STT 5.19675, exchange 1.23093685). Whether the order-level reply
  omits stamp or rounds it to whole rupees cannot be told from these rows (all under Rs 0.50).

## F-36 - NSE no longer publishes a separate freeze-quantity file; the freeze limit is the `MaxTradQty` column of NSE's daily F&O contract file, one more than the largest allowed order, keyed by the exchange token
- Measured 2026-10-16 00:35-00:45 IST by the orchestrator. Sources: NSE circular NSE/FAOP/61157 (29/2024, 15 Mar
  2024), served at `https://nsearchives.nseindia.com/content/fo/qtyfreeze.xls` (a PDF despite the name), and
  `https://nsearchives.nseindia.com/content/fo/NSE_FO_contract_15102026.csv.gz` (1,835,945 bytes, 85,592 lines, sha256
  9b4e035d...4140; kept outside the repo at `D:\Abhay\Ventures\ofo-exchange-files\2026-10-15\`). Level P1.
- The circular discontinued `Qtyfreeze.csv` and `fo_mktlots.csv` from 15 Apr 2024: "said MII contract file also
  contains quantity freeze & market lot related information", file `NSE_FO_contract_ddmmyyyy.csv.gz` on the "all
  reports - derivatives" page. The old `archives.nseindia.com/content/fo/qtyfreeze.xls` still answers with a stale
  workbook saved 30 Nov 2023 - a reader that trusts it would load 2023 limits.
- In the contract file the freeze limit is `MaxTradQty`; 15 Oct 2026 values for every contract of an index were one
  number: NIFTY 3511 (4,092 rows), BANKNIFTY 1441, FINNIFTY 3241, MIDCPNIFTY 5761. Each is one more than a whole number
  of lots (3511 = 54 x 65 + 1; 1441 = 48 x 30 + 1; 3241 = 54 x 60 + 1; 5761 = 48 x 120 + 1), so the largest allowed
  order is `MaxTradQty - 1` (NIFTY 3510 units = 54 lots), agreeing with ADR-081's "about 54 lots" and F-04's 3,511 vs
  3,510 across two brokers. For lot-multiple quantities "quantity < MaxTradQty" and "quantity <= MaxTradQty - 1" agree.
- `FinInstrmId` is the exchange token: NIFTY26O1923550CE has `FinInstrmId` 47185 and Kite's `exchange_token` 47185
  (`rest-2026-10-15-order/instrument_CE.json`), so the limit joins on the contract identity (NSE_FO, token) of ADR-050.
  Dates (`XpryDt`) are seconds from 1980-01-01 (1476887400 = 2026-10-19 14:30) and `StrkPric` is in paise (2355000 =
  23,550.00); the file for a day appears after that day (16 Oct's file was 404 at 00:36 IST on 16 Oct).
- BSE (SENSEX on BFO): not yet measured; until a BSE source is read, ADR-081's warning ("Zerodha may reject a large
  order") applies to BFO legs.
- Meaning: ADR-081's "exchange's published freeze-quantity file" is, for NSE, this contract file - no decision change.
- Bears on: ADR-081, REQ-054 AC-4, F-04. Status: **measured** (built by W-076).

## F-37 - The owner's Kite access token stopped working between 04:29:48 and 04:30:48 IST the next morning, not "around 6 AM"
- Measured 2026-10-15 15:50 -> 2026-10-16 04:30 IST by `docs/research/kite-proof-2026-10-07/kite_token_watch.py`
  (token from the encrypted daily cache, `/quote/ltp?i=NSE:NIFTY+50` every 15 minutes, every minute from 04:00 to 09:00
  IST). Result file `docs/research/kite-proof-2026-10-07/token-watch-2026-10-15.json`: 74 probes, 0 network errors,
  last success 2026-10-16T04:29:48+05:30, first failure 2026-10-16T04:30:48+05:30 with HTTP 403 `TokenException`.
  One night, one account (the owner's app). Level P1.
- The common figure (the `zerodha-expert` skill and `legacy-reuse.md`: "token expiry ~6 AM") is about 1.5 hours late
  for this account. A job that runs between about 04:30 and the morning login with yesterday's token gets a 403.
- Meaning: ADR-020's "expires every day (morning)" holds; the measured cut-off is about 04:30 IST. Anything planned
  for the night with the day's token (the expiry-day settlement read, Q205's reconciliation after the session expires)
  must finish before about 04:30 or treat a 403 as "session expired" (F-07: `TokenException` (403) means the session
  expired), never as a broker error. Not yet measured: whether the cut-off is the same every day and for other
  accounts (one night is one sample; repeat the watcher on two more nights before relying on the minute).
- Bears on: ADR-020, REQ-060 (Q205), REQ-015, F-32. Status: **measured once**; no decision change.

## F-38 - Index freeze limits are revised several times a year, not once in years; the NIFTY limit changed 11 days before this was written
- Researched 2026-10-16 ~08:15 IST by the orchestrator (web search; secondary sources, the NSE circulars themselves not
  read): Zerodha Trading Q&A "NSE revises Index F&O quantity freeze limits from October 5, 2026" (citing circular
  NSE/FAOP/76693: NIFTY 1,800 -> 3,510, BANKNIFTY 1,440, FINNIFTY 3,240), the same NIFTY figure on ICICI Direct; NSE
  revision effective 2 Mar 2026 (TeamLease RegTech, Angel One); FINNIFTY cut 1,800 -> 1,200 effective 1 Dec 2025
  (Angel One); a BANKNIFTY change effective 1 Sep 2025 (Republic World; its figures conflict with the 2026 sources).
  Level P2 (secondary), raised to P1 for NIFTY by our own read: NSE's 15 Oct 2026 contract file holds `MaxTradQty`
  3511 for every NIFTY contract (F-36), which matches 3,510 as the largest order.
- Lot sizes move as well (NIFTY 75 -> 65), and the largest order is the whole-lot number below the limit (1,800 with lot
  65 gave 1,755), so a lot change alone changes what can be sent in one order.
- Meaning: a freeze limit learned once is stale within months. A missed RISE blocks orders Zerodha would take (safe,
  annoying: 27 lots refused when 54 are allowed); a missed CUT lets a leg through that Zerodha rejects while the other
  legs fill. Revisions are announced a few days ahead (the 2 Mar 2026 one on 27 Feb), so a weekly refresh is enough;
  a daily download is not needed.
- Bears on: ADR-081, ADR-091, F-36, REQ-054 AC-4. Status: **researched** (NSE circular text not read; read NSE/FAOP/76693
  before relying on the non-NIFTY figures). Led to ADR-091 (owner, 2026-10-16).

## F-39 - Kite's basket margin for an option BUY is quantity x the LOWER of the limit price and the live price, not the limit
- Measured 2026-10-16 by the orchestrator on the owner's account (`POST /margins/basket?consider_positions=true`, read
  only; LTP from `/quote/ltp` just before and after), 1 lot (65) of NIFTY26O1923550CE, BUY, NRML, LIMIT:
  - 09:06 IST (pre-open, LTP 4.05): limit 5.00 -> 263.25 (65 x 4.05); limit 10.00 -> 263.25; limit 0.50 -> 32.50.
  - 09:29 IST (market open, LTP 3.95-4.00): limit 5.00 -> 256.75 (65 x 3.95); limit 10.00 -> 256.75; limit 0.50 -> 32.50.
  - Script: the session scratchpad `live_ltp_vs_margin.py`. Level P1 for one CE buy; SELL legs, PE, futures and
    multi-leg baskets are unmeasured.
- Meaning: a BUY limit above the live price can fill at up to the limit (65 x 10.00 = Rs 650 debit) while Kite's margin
  answer is Rs 256.75. REQ-055's pre-execution margin check uses Kite's answer (ADR-016: Zerodha is the authority on
  margin), so for a buy limit above the market it can pass a basket whose real premium outflow is larger than the
  funds. Same day, live: available funds Rs -497 against required Rs 263.25 -> the check refused (MARGIN_201), as it
  should.
- 10:33 IST, a 2-leg BUY basket, limits 5.00 above live: NIFTY26O1923550CE (LTP 11.15, limit 16.15) gave
  `option_premium` 724.75 = 65 x 11.15; NIFTY26O1922750PE (LTP 20.75, limit 25.75) gave 1348.75 = 65 x 20.75;
  `final.total` 2073.50 = their sum. So the per-leg `option_premium` in the same reply is the live-price premium for a
  call and a put, in a multi-leg basket. Script: the session scratchpad `live_basket_premium.py`.
- Bears on: REQ-055, ADR-016, ADR-080 (executable price), ADR-094. Status: **measured 3 times, CE and PE, single and
  2-leg**; SELL legs, futures and limits below live in a multi-leg basket are unmeasured. Decided in ADR-094.

## F-40 - The 4b domain chain (fill ledger, reconcile, P&L) is right on the real order, but no code turns Kite's orders/trades/positions replies into its input
- Measured 2026-10-16 (GC-1 item 8) on the owner's real 1-lot order, recorded at
  `D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/real-order/` (snapshots 122104 = after entry, 151006 = after exit), by a
  throwaway script over the real `ofo.*` code; script, output and result in `docs/research/core-proof-4b-2026-10-16/`.
- With exact Decimal inputs the domain holds: both real trades (4484194, 5966618) enter the ledger once, replays are
  no-ops, the position goes 65 -> 0; reconcile gives 0 mismatches after entry (65 long NIFTY26O1923650CE) and after
  exit (flat), and flags a broker +130 and a still-active strategy against a flat broker; `position_pnl` gives exactly
  -130 (= (3.10 - 5.10) x 65), matching Kite's `pnl: -130`, but as `-130.0`, not quantized to paise.
- Every real row is refused at the boundary: `positions.py:53` refuses `average_price '5.1'` and `last_price '3.1'`
  (strings) and SDK-shaped floats 5.1 / 3.1; the flat row (`quantity 0`, `average_price 0`) is refused by
  `positions.py:44` (correct: never a 0-price holding, but the reconcile path has no flat-row rule while
  `grouping.py:295` skips `quantity == 0`); `FillEvent` refuses the trade price string (`orders/model.py:260`).
- Missing, not refused: no Kite trades-row -> `FillEvent` parser, no tradingsymbol/token -> reconcile contract key
  (issue 115), no realised P&L from the ledger, nothing moves the strategy record to exited from the ledger. `ofo_app`
  has no orders/trades/positions reader; `kite_margin.py` already parses with `parse_float=Decimal` (the pattern to reuse).
- Attack: the exit trade applied before the entry is accepted (ledger -65, then 0): the end state is right, the
  in-between state reads as a side flip.
- Does NOT prove: live JSON-number or SDK-float parsing (the recording's prices are strings written by the recorder),
  multi-leg or partial fills, out-of-order postbacks, MIS rows, charges (F-35's stamp check stays an owner item).
- Bears on: REQ-054 AC-1 (fetch positions/orders), REQ-057, REQ-060, ADR-008, ADR-016, F-33. Status: **measured once,
  one CE buy+sell**. Shapes GC-2b (Kite reply adapter, flat-row rule, contract-key mapping, trade -> fill, exit from the
  ledger). Open for owner decision only if quantizing realised P&L to paise changes what a user sees (ADR-101,
  2026-10-17, rounds Zerodha's margin and funds figures half-up to the paisa at parse - ADR-099 is the margin display;
  P&L rounding is not stated).

## F-41 - Kite returns the browser from a basket to the SAME registered redirect URL the login uses, and our login callback would show a login error
- Read 2026-10-17 (GC-2e item 6, W-105), no basket placed: https://kite.trade/docs/connect/v3/basket/ - "Once the user
  is done placing orders, the basket will redirect back to your registered `redirect_login` along with a
  `request_key`, exactly like login." and "in the end, you will receive `status` and `request_token` at your
  `redirect_url` like in the login flow." The basket form carries only `api_key` and `data` (same page;
  `backend/ofo_app/basket_post.py` sends exactly those). The publisher docs mention a `redirect_url` override on the
  same domain; a 2021 forum reply says to pass `redirect_url` in the post body - unconfirmed for a plain form POST.
- Our `kite_callback` consumes `state` first; a basket return has no state we issued, so it goes to the refusal page
  `broker_state_invalid`: the owner would see a login error right after placing real orders (REQ-073 AC-3 return).
- Unverified until GC-3's first basket: whether `state` is absent on the return, and whether a closed/cancelled basket
  returns `status=success`. The return route never reads `status` as proof of placement (it reads Zerodha's book by tag).
- Measured 2026-10-19 (GC-3L L2/L3, two real baskets, strategy 9 plans 1 and 2): after the owner pressed Place, Kite
  did NOT redirect. The basket tab stayed on `/connect/basket`, showed the order COMPLETE (order 261019170382597, BUY 65
  NIFTY26OCT24000CE filled 65/65 avg 7.00 at 10:34:26) with "Refresh order status" and "Finish" buttons; the redirect
  presumably comes only on Finish, which was not pressed (an owner-only click). The plan was closed from the Execute
  tab's Check (10:35:05 / 10:35:18 -> plan 1 `filled`, 0 mismatches; exit plan 2 the same way at 10:47:18 / 10:47:32
  -> `exited`). The no-state return page (W-105) was therefore not reached live; the return shape on Finish is still
  unmeasured.
- Bears on: REQ-073 AC-3, ADR-097 (2). Status: **measured 2026-10-19: no redirect until Finish; the Execute tab's Check
  closes the plan**. Fixed by W-105 (a no-state hit lands on a page with only "Check with Zerodha"); registry:
  `shared-callback-treats-every-return-as-login`.

## F-42 - REQ-058 and REQ-060 were Verified on domain modules the Kite-basket routes never call
- Measured 2026-10-17 (GC-3 P0 item 7, fresh Opus verifiers on main 85e38e0, current criterion text against the code
  users reach): the Execute and return routes (W-095, W-096) decide reconciliation per request with
  `ofo_app/execute_plan.strategy_blocked` and `ofo_app/execution_return.reconcile`, and partial execution as a plan state
  word; no `backend/ofo_app` module imports `ofo.reconciliation.compare`/`resolution` or `ofo.execution.partial`.
- Result: REQ-060 AC-1..AC-7 fail on the live path; REQ-058 AC-1, AC-2, AC-4, AC-6 fail (AC-3, AC-5 pass); REQ-073
  AC-5 fails (the basket form `{url, api_key, data}` is placed on whichever account is logged in on Kite's page; the
  owner-id check guards only the stored read token); REQ-057 AC-1..AC-3 pass. Real cases: broker 150 vs platform 75 on
  the strategy's own contract -> not blocked; a mismatch that later agrees -> unblocked with nothing recorded (Q222);
  a REJECTED row with `RMS:Margin Exceeds` -> `nothing_placed`, no reason.
- On the real 2026-10-16 replies the live path still closes 0 mismatches and the exit on the flat row is clean.
- Bears on: REQ-058, REQ-060, REQ-073 AC-5, ADR-106 item 3. Status: **measured**; REQ-058/REQ-060 set back to
  Approved; the drift half of REQ-060 AC-6 is W-107; the rest is open for the next contract (wire or re-specify -
  **open for owner decision** where it changes what a user sees: the four partial choices under ADR-105, a manual
  reconcile screen). Registry: `verified-on-a-module-the-product-does-not-call`.

## F-43 - On Mon 2026-10-19 the nearest NIFTY weekly contract expires the same day
- Read 2026-10-17 from the instrument subset recorded 2026-10-16 (`ofo-kite-ticks/2026-10-16/instruments.json`, the
  live recorder's NIFTY options): expiries 2026-10-19 (Mon, 208 contracts, e.g. `NIFTY26O1923000CE`) and 2026-10-27
  (Tue, 288): the weekly expiry sits on Monday ahead of the Tue 2026-10-20 holiday (ADR-050:
  "Some NIFTY expiries fall on Mondays, so expiry is read from the master, never computed from a weekday").
- Consequence for GC-3 step 5 ("the nearest-expiry NIFTY CE"): an EXIT LIMIT that does not fill by 15:30 leaves the
  leg to exchange settlement, which the live path does not handle (#279 settle-before-reconcile; an expired held leg
  blocks as a missing position, F-42) and the plan stays open into the next day (#352).
- Bears on: GC-3 step 5, ADR-097 (1), ADR-083. Status: **measured from the master; decided by ADR-108 (2)** (owner
  2026-10-17: the live test trades the 2026-10-27 expiry).

## F-44 - On Sun 2026-10-18 Kite reported zero funds on the owner's account (net, cash and opening balance all 0)
- Read 2026-10-18 ~15:10 IST, read-only, after a real login through `/broker/zerodha/login` (GC-3P item 1):
  `probe.py contract NFO:NIFTY26OCT27000CE` printed `available_funds 0.00`; the raw `GET /user/margins` `equity`
  block had `net 0`, `available.cash 0`, `available.opening_balance 0`, `live_balance 0`, every `utilised` field 0.
  The probe reads the right field (`kite_margin.fetch_available_funds` -> `equity.net`, ADR-101); the zero is Kite's.
- Planning (GC-3P contract, ADR-108 consequence example) assumed Rs 873. Unknown whether the money left the account
  or Kite zeroes the figures on a weekend: one Sunday read cannot tell the two apart.
- Consequence: a 1-lot ENTRY of 65 units at Rs 5-11 needs about Rs 325-715 plus charges; with Rs 0 the product's
  margin gate (ADR-016: "a hard execution gate") and Kite both refuse it.
- Owner, 2026-10-18 ~15:15 IST, question tool: "Re-check Mon 09:00 (Recommended)" - the GC-3L Monday timeline carries
  a hard funds gate at 09:00: `equity.net` must be at least 65 x the picked premium + Rs 100 (GC-3L L1, #338), else L1
  stops before any click and the owner adds funds. Bears on: ADR-108 (2) ("against the funds read then"), ADR-016,
  ADR-107 (#338). Status: **measured; owner-decided for the GC-3 live test** (no rule change: ADR-108 already reads
  funds at L1).
- Resolved 2026-10-19 (GC-3L L1, after the owner's Rs 1,000 deposit): `available_funds 1000.00`; the entry (BUY 65 at
  7.45, net premium -484.25, charges 23.82, margin 484.25, read 10:24:54) passed the funds gate, and after the entry the
  read was `funds 545.00` (10:35:55). Status: **resolved** - a Monday read of exactly 1000.00 after a Rs 1,000
  deposit is consistent with the Sunday zero being the real balance, not a weekend artefact (no rule change).

## F-45 - The app's database role allows 5 connections in total, while ONE API process's pool can open about 19
- Measured 2026-10-19 10:41 IST, read-only on the VPS PostgreSQL: `rolconnlimit` of role `ofo_app` = 5 (server
  `max_connections` 100); GC-3L's API alone held 3 on `ofo_dev`. `backend/ofo_app/db.py` builds the engine with
  SQLAlchemy's default pool (5 + overflow 10) and `history_store.py` adds its own (2 + 2).
- Real case (GC-5S core proof, 10:33-10:40 IST): the new Live Strategies page on a second API (:8766) loaded 13 saved
  strategies at once (13 `GET /strategies/{id}` plus a socket each); the API log shows `asyncpg TooManyConnectionsError:
  too many connections for role "ofo_app"` 11 times and an unhandled error on `GET /strategies/11`, and a plain
  one-connection read failed the same way after the browser closed, until that API was stopped.
- The limit is per ROLE across databases, so ofo_dev, ofo_test and every local API or DB test share the same 5.
- Consequence: any screen that fans out per-strategy reads, and any second API process, can refuse database work to
  another process on the role - including a live order run. Bears on: ADR-048 (the limited `ofo_app` role), REQ-050
  (shared computation and scale), REQ-049 AC-4. Status: **measured; registry `db-role-limit-below-pool-size`**; fix
  open (page: bounded concurrency; app: pool sized under the role limit), open for owner decision only if the role
  limit itself should change. Earlier sample: #370 (CI e2e), held fix #395 (pool settings, 1 + 0 in CI only).
- Also measured 2026-10-19 (GitHub CI, PR #429 and main a614b16): the e2e test `strategy-save-draft.spec.ts:71` fails on
  main itself with `FATAL: too many connections for role "ofo_app"` in the CI database log. Independent Opus review the
  same day: the defect is each API process's pool (5 kept + 10 overflow against a shared limit of 5), not the screens;
  the Live Strategies e2e visits trigger it (PR #429 red 4/4 while main 1dae5de was green). #395 (CI pools 1 + 0) merged
  2026-10-19 by GC-5S (owner decision) and #429 then passed; the per-process pool budget is open (next contract).

## F-46 - A live screen keeps showing its last answer's numbers after its own connection drops
- Measured 2026-10-19 by three GC-5S verifier rounds, each proven with a red test on the real component: the Live
  Strategies card (W-113) was not paused while reconnecting after a drop; the Underlying/index view (W-114) kept both
  index values with their "as of" time after a drop whose fallback read failed, and a read sent before a drop could
  restore a live value later; the Home strip (W-115) copied that logic before it was fixed.
- Bears on: REQ-049 AC-4 ("Screens show when data is stale or unavailable instead of presenting old numbers as live."),
  REQ-072 AC-2. Status: **measured; registry `last-live-answer-kept-after-drop`**; fixed per screen, and structurally for
  the index views (one state machine in the index composable, W-115 round 2); no repo-wide check yet for a new live
  screen.

## F-47 - The live feed carries no previous close, so the Option Chain's default Change column cannot be filled
- Read 2026-10-19 in the code on main a614b16 (GC-5S W-116): `backend/ofo/marketdata/kite_frames.py` has no `close` or
  `ohlc` field at all (Kite's packet decoder keeps LTP, depth, volume, OI and times only), and the normalised quote model
  (`backend/ofo/marketdata/quote.py`) has no close field; W-116's chain socket therefore sends `change: null` on every
  cell and computes no change from anything else.
- Bears on: REQ-029 AC-2 ("Default columns: Strike, LTP, Change, OI, Volume (Q45)"). Not a rule change: the data path is
  missing a field. Next step: the Kite full-mode packet's close price (or the instrument's previous close from a daily
  read) added to the adapter and the quote model, then the chain fills Change from the server. Status: **measured; open
  (data path work, no owner decision needed unless the source of the previous close is a choice the owner wants).**

## F-48 - A live socket's once-a-second limit guarded only its normal push, so its error path flooded the client
- Measured 2026-10-19 (GC-5S W-116 round 1, red test on the real class): with the spot missing and an unknown contract in
  the chain window, the chain socket sent an error on every poll (`[2, 30, 30]` messages per second against a limit of
  1); round 2 routes every outbound message through one gate (`[1, 1, 1]`).
- Bears on: REQ-029 AC-4 (live streaming at a bounded rate), REQ-050 (shared computation and scale). Status: **measured;
  registry `rate-gate-on-success-path-only` (guarded for the chain socket)**; the index and strategy sockets not
  re-checked yet.

## F-49 - The Strategy Builder page is built but missing from the route map, so its nav item opens the placeholder
- Read 2026-10-19 in the code on main ca60fc5: `frontend/src/pages/StrategyBuilderPage.vue` and 12 components in
  `frontend/src/components/strategy/` exist, but `REAL_PAGES` in `frontend/src/router/routes.js` (lines 9-21, 11
  entries) has no `strategies-strategy-builder` key; every nav item without a key renders `PlaceholderPage.vue`. About 14
  menu items still open the placeholder (My Strategies, Create Strategy, Strategy Builder, the 4 Positions and 4
  Orders items, Adjustments, the Settings pages).
- Bears on: REQ-009 AC-2 (the navigation items open their screens), REQ-034 (the outcome view the Builder shows).
  Not a rule change: the product's main screen is unreachable from the menu. Status: **measured; open (screen S1 wires
  the key and a test asserts every built page is keyed)**.

## F-50 - Kite's basket page shows Required margin and Final margin; order sequence changes the required one, not the final one; for F&O, buy options first
- Read 2026-10-19 from Kite's support article
  https://support.zerodha.com/category/trading-and-markets/kite-features/basket-order/articles/kite-basket-orders
  (from a search summary, not a logged-in session): the basket shows "Required margin" and "Final margin" (its example
  50,343.68 vs 38,913.68); orders are placed in basket sequence; the sequence changes the required margin but not the
  final margin; for F&O buy options first; rejected orders are re-run by hand with no fee; "Include existing positions"
  can show a required margin of 0. Partial-failure handling: not stated on that page.
- Bears on: REQ-055 AC-1, AC-3 (margin required versus available, Zerodha's figure authoritative), REQ-056 AC-3
  (protective buys before the sells that depend on them). Consistent with F-39 (the basket margin of an option BUY).
  Status: **read once from a vendor page; not measured on the owner's account** - the Execute screen labels our
  figure an estimate and Zerodha's the authority.

## F-51 - No studied app shows a guided objective, market-view and range flow; ours rests on the spec alone
- Read 2026-10-19 on public pages only (not logged in): Sensibull, Upstox, Quantsapp, Stockmock and Opstra show no
  objective / market-view / expected-range wizard in what was found; Angel One has predefined and custom tabs with
  setups described as bullish, bearish or neutral; Dhan and AlgoTest list templates
  (docs/design/screens-research-2026-10-19-part2.md section Create Strategy). Absence on public pages is not proof of
  absence in the logged-in apps.
- Bears on: REQ-024 (AC-3, AC-4, AC-7), REQ-026. Consequence: there is no competitor layout to copy for the Create
  Strategy screen; its design follows the requirements and the wording stays provisional until the legal review (Q211,
  Q261). Status: **read; unmeasured in logged-in apps**.

## F-52 - The generated build order and a work item still say REQ-061 AC-2 waits on OQ-7, which ADR-096 answered on 2026-10-16
- Read 2026-10-19: `views/build-order.md:56` and `work/W-083.md` (`status: blocked`, `next_action`) say AC-2 "waits on
  owner OQ-7 (build an order-free adopt-into-existing path, or defer it in REQ-061)"; ADR-096 (owner, 2026-10-16
  ~12:00 IST, with the question tool) records OQ-7 answered "(a) Build it now (Recommended)": the order-free adopt path.
- Bears on: REQ-061 AC-2. Consequence: AC-2 is buildable and is not blocked on an owner answer; the stale text hides it
  from anyone reading the build order. Status: **measured; `work/W-083.md` corrected 2026-10-19; `views/build-order.md`
  is generated and refreshes when the work item's blocked status is cleared by its builder**.

## F-53 - Every workflow runs on every PR push including drafts, and a frontend-only change also runs the API suite
- Read 2026-10-19 in `.github/workflows`: `ci.yml`, `coverage.yml` and `app-tests.yml` trigger on `pull_request` with
  no draft filter (no `ready_for_review` or `github.event.pull_request.draft` condition); `app-tests.yml` has ONE
  `pull_request.paths` list (backend/ofo, backend/ofo_app, tests_app, frontend, the workflow file) for its jobs `api`,
  `frontend` and `execute-screen-e2e`, so a change under `frontend/**` alone also starts the `api` job. `cancel-in-progress`
  is set, so a newer push cancels an older run of the same PR.
- Bears on: REQ-075 AC-7 (a docs-only PR runs only the kit checks; no API or frontend job). Not a rule change.
  `ci.yml` is kit-owned: a draft filter there is a `harvest` issue to Startup-Factory; `app-tests.yml` is
  project-owned and is split into a frontend job and an API job with their own path filters. Status: **measured; open
  (GC-6 row O0)**.

## F-54 - The legacy algochanakya 2026 holiday list is wrong: it misses Tue 2026-10-20 and lists Wed 2026-10-21
- Measured 2026-10-19 by the GC-6 MKT-HOURS builder: NSE's own holiday API (`holiday-master?type=trading`, key `FO`)
  returns 20 F&O trading holidays for 2026, including 2026-10-20 (Dussehra) and 2026-11-10 (Diwali-Balipratipada); the
  public calendars checked the same day (cleartax, Tata MF, Upstox) agree on 20 October. The hard-coded 2026 list in
  `abhayla/algochanakya@bf9faf7 backend/app/utils/market_hours.py` has no 20 October, lists 21 October (a trading day
  per NSE) and misses several other holidays.
- Bears on: ADR-119 (the holiday list is dated data with a source, never typed into code) and
  `spec/technical-design/legacy-reuse.md` row M2 (`market_hours.py` ADAPT): copy the session logic only, never its
  holiday list. The project's list is `backend/ofo/market_calendar.json` (source URL and fetch date in the file), built
  on branch gc6/mkt-hours. Not a rule change. Status: **measured; the copied list is not used (GC-6 row MKT-HOURS)**.

## F-55 - A net-only next-day read cannot see a same-day round trip: a filled-then-hand-sold entry reads "nothing placed"
- Measured 2026-10-19 by the read-only Opus review of PR #421 (#352-1, head 21ba2c389ff8), confirmed by the
  orchestrator: `backend/ofo_app/reconcile_attribution.py:35-36` on that branch documents "an ENTRY filled and sold by
  hand on Kite the same earlier day leaves the net at the base and reads `nothing_placed`". Kite's next-day positions
  give one net number per contract; a BUY 65 filled and a hand SELL 65 the same day net to 0, the same as no order.
- Bears on: ADR-111 ("the app records the resulting mismatch" for a hand close on Kite) and REQ-060. The plan closes
  with no mismatch and no P&L for a trade that happened. Fix direction (technical, GC-6 row NET-ROUNDTRIP): use the
  activity fields of the next-day positions reply, or treat an earlier-day plan whose net equals the base as
  unresolved, never `nothing_placed`, when activity cannot be ruled out. Status: **open; registry
  `net-only-read-misses-roundtrip`**.

## F-56 - Zerodha's instrument list is generated once each morning; Kite's docs say fetch it at about 08:30 IST
- Read 2026-10-20 (web): the Kite Connect v3 docs (https://kite.trade/docs/connect/v3/market-data-and-instruments/)
  say the instruments dump is best requested "once a day (ideally at around 08:30 AM)" and stored; Kite staff on the
  developer forum (https://kite.trade/forum/discussion/11793) say it refreshes around 8 AM each trading day and is not
  updated intraday (new strikes added during the day appear only in the next morning's file).
- Bears on: ADR-015 (no stale data as live) and ADR-058 (the daily list). A catalogue load before the morning file
  exists reads yesterday's list; GC-6 row INSTR-FRESH treats a list stamped before 08:30 IST as stale for that day
  (setting `INSTRUMENT_LIST_PUBLISH_IST`, backend/ofo/timeutil.py on branch gc6/instr-fresh). No exact generation time
  is published; 08:30 is the documented fetch time. Not a rule change. Status: **measured from documentation; no live
  timing captured**.
- Note 2026-10-22 (builder sequence row 5): the "not updated intraday" forum line conflicts with F-33, which MEASURED
  108 NIFTY 13-Oct strikes at 08:05 and 236 at 14:39 in Kite's own list (2026-10-08). Measured data wins: REQ-053's
  catalogue refresh keeps an hourly reload during market hours; its publish time and first load follow this finding
  (session current from 08:30 IST, first scheduled load 08:35).

## F-57 - Zerodha rule constants checked against Zerodha's current docs; a reported NIFTY freeze-limit rise to 3,510 is unconfirmed
- Fetched 2026-10-22 (builder sequence row 5, REQ-053 AC-5; WebFetch summaries, not raw page reads):
  - Matches: `QUOTE_LIMIT` 500 ("complete market data snapshot of up to 500 instruments in one go",
    https://kite.trade/docs/connect/v3/market-quotes/; `/quote/ohlc` and `/quote/ltp` allow 1000);
    `MAX_TOKENS_PER_CONNECTION` 3000 ("up to 3000 instruments on a single WebSocket connection", up to 3 connections
    per API key, https://kite.trade/docs/connect/v3/websocket/); basket tag 8 ("alphanumeric, max 8 chars",
    https://kite.trade/docs/connect/v3/publisher/); API order tag 20 ("alphanumeric, max 20 chars",
    https://kite.trade/docs/connect/v3/orders/); Publisher basket at most 10 items (publisher page); order rate limits
    400/minute, 10/second, 5000/day, 25 modifications per order (https://kite.trade/docs/connect/v3/exceptions/).
  - Not stated: the order types and products the margins call accepts (the page says "MARKET, LIMIT etc." and gives
    CNC/NRML examples; https://kite.trade/docs/connect/v3/margins/); exchange code NCO (absent from the user page).
  - Freeze limit: Zerodha's bulletin for 2026-04-01 gives NIFTY 1,800
    (https://zerodha.com/marketintel/bulletin/445684/quantity-freeze-limits-for-indices-from-april-01-2026), which the
    code's fallback `DEFAULT_FREEZE_UNITS` = 1,755 follows (27 lots x 65, the largest lot multiple under 1,800 - 1, per
    ADR-081). A third-party page (Choice India) reports NSE circular NSE/FAOP/76693 raising NIFTY to 3,510 from
    2026-10-05; not confirmed on NSE or Zerodha. The live value comes from NSE's daily contract file (ADR-081), so the
    fallback matters only when that file is missing.
  - Market orders on options: Zerodha allows them only for the current and next weekly and monthly NIFTY/BANKNIFTY
    contracts, not for deep ITM (> 5%) contracts, and on SENSEX only with OI over 500 lots
    (https://support.zerodha.com/category/trading-and-markets/trading-faqs/articles/market-orders-monthly-options).
    No source says options are limit-only.
- Bears on: REQ-053 AC-5, ADR-081, REQ-073. Status: **measured from documentation; the 3,510 freeze limit open until
  NSE's own file or circular is read** (the daily-file loader reads it live).

## F-58 - The pure-Python Redis stand-in (fakeredis 2.40.0 TcpFakeServer) does not deliver pub/sub over the network; Streams work
- Measured 2026-10-22 ~20:20 IST on the laptop (builder sequence row 9, REQ-113 AC-3 design), redis client 6.4.0:
  over `TcpFakeServer`, PING/SET/GET work and SUBSCRIBE is confirmed, but PUBLISH returns 1 subscriber and the
  subscriber's `get_message(timeout=3)` returns `None` (the message never arrives). Redis Streams work: `XADD` from a
  second connection 0.5 s after a blocking `XREAD ... BLOCK 3000` started was received, at 2.54 s (the stand-in checks
  for new data on a coarse timer; real Redis wakes at once). `srv.shutdown()` from the main thread hung past 120 s; exit
  with the process instead.
- Bears on: REQ-113 AC-3 (the bus is Redis per ADR-043) and the owner's rule that no server runtime is installed on the
  laptop. Decision (orchestrator, technical, row 9, after an independent Opus design review): the bus uses Redis
  Streams with a length cap and keys with an expiry (rebuildable state only), so the same code runs on real Redis in CI
  and on the stand-in on the laptop. Not a rule change. Status: **measured on real runs**.

## F-59 - Kite's 3-websocket limit is per API key across ALL users of one Kite Connect app, not per user
- Read 2026-10-22 ~23:20 IST (builder sequence row 9, REQ-113 AC-6; WebFetch of the pages):
  Kite docs (https://kite.trade/docs/connect/v3/websocket/): "Single API key can have upto 3 websocket connections."
  Zerodha staff on the developer forum: "The 3 connections limit is per api_key and not based on user" and "A Kite
  Connect app is enabled only for single user by default" (sujith, Sept 2021, asked whether 6 users with 6 tokens on one
  app could open 18 connections, https://kite.trade/forum/discussion/10382/limit-of-number-of-websockets); "we suggest
  not open more than 3 websocket connections per api_key" - more "will be blocked without intimation" (sujith, May 2022,
  https://kite.trade/forum/discussion/11179/how-many-websocket-connection-per-kite-connect-app); for more connections
  "create a new app and use that api_key" (sujith, Feb 2023, https://kite.trade/forum/discussion/12382/more-than-one-api-keys-in-same-subscription).
  Not found: any Zerodha arrangement for a multi-user platform's websocket count.
- Bears on: ADR-053 (each user's own feed in V1) - on ONE platform Kite Connect app, per-user sockets stop at 3 users;
  F-31 (Zerodha grants multi-user access only after a demo; the owner's limits question was not answered); REQ-113 AC-6
  (the cap is held as configuration: 3 per key). ADR-060 keeps the build on the owner's own app, so nothing breaks
  today. Owner decision 2026-10-23: ADR-170 (keep per-user feeds; ask Zerodha at the multi-user demo). Status: **measured from documentation and staff answers**.

## F-60 - Kite REST rate limits per endpoint group; a 429 starts a 10 s sliding cooldown; the scope of the read limits is unstated
- Read 2026-10-23 ~07:40 IST (builder sequence row 10, REQ-118 AC-1; WebFetch summaries, not raw page reads):
  https://kite.trade/docs/connect/v3/exceptions/ "API rate limit" table: "Quote | 1req/second", "Historical candle |
  3req/second", "Order placement | 10req/second", "All other endpoints | 10req/second"; orders also 400 per minute and
  5000 per day per user/API key, 25 modifications per order (as F-57); "429 | Too many requests to the API (rate
  limiting)". Kite forum, rakeshr (staff), Oct 2022 edited Jul 2023: "There's a cooldown period of 10s that must be
  respected whenever you receive a 429 Status Code", a sliding window, so requests during it extend it
  (https://kite.trade/forum/discussion/11971/api-rate-limits); repeated breaches may get the app blocked for longer
  (https://kite.trade/forum/discussion/11404/what-happens-after-i-hit-api-limit). Order limits are account (client ID)
  level, "regardless of the number of app" (https://kite.trade/forum/discussion/15912/...).
- Not found: whether the quote / historical / other limits count per api_key across all users or per user; the 429
  reply's `error_type` and message; any Retry-After header.
- Bears on: REQ-118 AC-1 (limits as configuration with source and date), AC-3 (bounded wait), AC-4 ("retried after the
  wait Kite indicates" - Kite indicates 10 s, no header). Orchestrator decision (technical, row 10): the unstated scope is
  taken as the stricter one, per api_key across all users (one bucket per group for the whole app), until Zerodha
  states otherwise. Not a rule change. Status: **measured from documentation and staff answers**.

## F-61 - A false "data disconnected" alarm after a reconnect comes from the SERVER's Kite feed reconnecting, not the browser's socket
- Measured 2026-10-24 (builder sequence row 24, REQ-133 AC-3) on the recorded 2026-10-08 replay frames, before the fix
  (chunk head 8f317c6f), and re-measured by an independent checker: (1) the BROWSER's strategy socket drops and
  reconnects before the next tick - the first push is `COMPUTED`, `status_label` none, every leg `health: available`
  with its LTP (39.15 / 12.95 / 82.75 / 35.8): no false alarm; (2) the SERVER's Kite feed reconnects before its first
  tick - the outcome answered `COMPUTED` with "Live market data disconnected. Last updated: 09:20:09 AM. Live strategy
  monitoring is paused." and every leg `stale since 09:20 IST` while the feed was connected: a false alarm with stale
  numbers drawn.
- Bears on: REQ-133 AC-3 (its "Why" placed the defect in "a screen that has just reconnected"; the measured cause is
  the feed connection on the server). Built: while the feed is connected, has had no price yet and is inside the
  existing staleness setting (`FEED_STALE`, ADR-015 "an implementation setting"), the outcome answers not-connected
  "Waiting for the first live price"; past it with no price, the stale alarm returns. Not a rule change.
  Status: **measured on recorded data, reproduced by the row 24 checker (3 tests red on the base, green after)**.

## F-62 - Zerodha's basket margin reply carries no buy-first figure, so REQ-142 "Funds needed" cannot be taken from it
- Measured 2026-10-28 (GC-UI step 3b, D-A38) on four recorded buy-only basket replies in the tests_app fixtures and on
  strategy 54's live outcome (NIFTY 3 Nov 22600 / 22800 CE bull call spread, 1 lot): the basket reply holds only
  `initial` and `final` totals, per-order margins and each BUY order's `option_premium`; `final.total` already
  includes the premium and the hedge benefit, and nothing in the reply depends on the ORDER the legs are placed in.
  For buy-only baskets `final.total` = `initial.total` = the sum of `option_premium` (REQ-142 AC-3 holds); for strategy
  54 our `needed` = Zerodha's `final.total` = 33,324.84 (top-up 0).
- Bears on: REQ-142 (statement: the buy-first figure "comes from the server, from Zerodha's margin reply for the same
  legs"): no field of that reply gives it. Not measured: three fresh live reads of a bull call spread, a short iron
  condor and a long straddle (REQ-142 AC-1) - the conclusion rests on the reply's structure, which a fresh read does
  not change. Nothing built; D-A38 parked in the GC-UI contract.
  Status: **decided by the owner 2026-10-28 (ADR-206): REQ-142 held**; no broker order in the current scope.

## F-63 - Sensibull's Greeks-tab Decay is the time value lost between the strategy's time and the next market open, about 0.73-0.84 of one day's theta overnight
- Measured 2026-10-28 ~20:03 IST on web.sensibull.com logged out (REQ-145 AC-1 "measure first"; study screen 015 form),
  NIFTY 3 Nov bull call spread that Sensibull loaded by default (BUY 22700 CE / SELL 22900 CE, 1 lot), its target time
  "Wed, 28 Oct 3:40 PM", the next market open Thu 29 Oct 09:15 IST (17 h 35 min = 0.733 day). Per unit, rounded to
  whole rupees by Sensibull: 22700 CE Theta -15, Decay -12; 22900 CE Theta +13, Decay +10; Total Theta -1.8, Decay -2.
  Decay / Theta lies in 0.74-0.84 on both legs (rounding bounds); 0.733 day sits at the edge, so the measurement is
  CONSISTENT with REQ-145's stated definition ("the time value change, in rupees, between now and the next market open
  if everything else stays the same") and cannot separate a full model revaluation from theta x time at this rounding.
  Columns in Sensibull order: Delta, Theta, Decay, Gamma, Vega.
- Formula adopted (REQ-145 statement, no rule change): Decay per leg = model value at the next market open (same spot,
  IV, rate, q; time to expiry shortened to that open) minus model value now, per unit, signed by the leg like theta;
  Total = sum of legs. Not measured: an iron condor (REQ-145 AC-1 names one; the definition does not depend on the
  shape) and a weekend gap (Friday -> Monday open, where the study says actual decay is 1/3 to 2/3 of the shown figure).
  Status: **measured on Sensibull logged out (form + definition only, never used to check our numbers)**.

## F-64 - Kite's historical minute candles cover the Strategy Chart's 10-day window for a leg and the future, but an option leg misses about 5% of the future's minutes and prices arrive as JSON numbers
- Measured 2026-10-28 ~21:33 IST (GC-UI step 5 core proof, after hours) on the owner's own Kite Connect session read
  from the encrypted store (`history_finalize.stored_credentials`), through the app's allow-listed door
  (`GET /instruments/historical/{token}/minute`, `oi=1`), 2026-10-14 09:15 to 2026-10-28 15:30 IST: NIFTY26N0325000CE
  (token 13908994) 3,638 candles, first `2026-10-14T09:15 5.4`, last `2026-10-28T15:29 close 0.65`; NIFTY26NOVFUT
  (token 15736578) 3,840 candles, first `2026-10-14T09:15 open 22900`, last `2026-10-28T15:29 close 22775`. 10 trading
  days. The leg lacks 202 of the future's 3,840 minutes (5.3%) and has none the future lacks; prices are JSON numbers
  (here `int` for 22900, floats elsewhere, F-33), so the server must read them through `Decimal(str(x))` (ADR-008).
- Only the `minute` interval is on the Kite allow-list (`ofo/broker/kite_endpoints.py`, `ofo_app/kite_history.py`);
  `60minute` and `day` are refused before sending. REQ-091 AC-2 allows 1-minute bars, so no allow-list change is needed.
- Bears on REQ-091 AC-2 (1-minute bars over the window), AC-4 (a minute where any leg has no candle is a gap, never
  interpolated: with one illiquid leg about 1 minute in 20 is a gap, and with four legs more), AC-5 (listing date), and
  ADR-203 (1). Status: **measured once, one leg + the future; a 4-leg strategy and a far-OTM leg not measured**.
- Addendum 2026-10-28 ~23:15 IST (route live on 699c53c3, strategy 56, NIFTY 3 Nov iron condor BUY 22400 PE / SELL
  22500 PE / SELL 22700 CE / BUY 22800 CE): all four near-the-money legs had 3,850 minute candles each (14 Oct 09:15 to
  28 Oct 15:39 IST), so the chart had 0 gaps; an independent recomputation from the raw candles matched all 3,850 route
  points to the paisa (`D:/Abhay/scratch/gcui-chart/check56.py`). Kite's minute candles run to 15:39 IST (the closing
  session), so the chart's last point (76.00) can differ from the builder's 15:30 LTP net (74.15: 22500 PE candle close
  101.80 vs LTP 99.80). Gap rate is a property of the leg's liquidity: far-out-of-the-money legs gap (5.3% for the 25000
  CE above), near-the-money legs did not. Still not measured: a 4-leg strategy with far-out legs.

## F-65 - Editing a paper-tracked strategy in the builder changes the saved plan but not the paper position, with no warning
- Measured 2026-10-29 ~10:28 IST, live, build/gcbm-must-have 5052f82a, strategy 63 (NIFTY 3 Nov short iron condor
  B 22600 PE / S 22700 PE / S 22900 CE / B 23000 CE, tracked 10:25): the short CE stepped 22900 -> 22950 and saved
  ("Expert IC test 1029 saved."); the builder legs then read 22950 while the Paper P&L panel still listed
  "65 units 3 Nov 22900 CE" (the other legs "1 x ..."), and the page's Greeks, payoff and summary described the
  22950 plan. Cause in code: tracking is pinned to the saved revision it started from (`routes/tracking.py:61-65,319`)
  and nothing links a later save to it. Class: every saved strategy with an open paper position (15 in ofo_dev on
  2026-10-29) whose plan is saved again. Bears on REQ-109, REQ-044 AC-2; decided by ADR-207 (2).
  Status: **measured once, live; defect class registered (`knowledge/findings/paper-plan-diverges-from-position.json`)**.

## F-66 - The builder prices an open paper position at the plan's entry prices, not its paper fills
- Same walk: strategy 63 reopened from its URL showed planned entry 73.90 / 103.60 / 118.65 / 78.80 and max profit
  +4,274 on them, while its paper fills were 72.60 / 102.00 / 122.25 / 80.95. Every summary figure of an open paper
  position (max profit / loss, breakevens, reward/risk) is therefore of a trade he did not make. Bears on REQ-109,
  REQ-046 AC-2; decided by ADR-207 (2). Status: **measured once, live**.

## F-67 - Paper entry is the LTP at "Start tracking", not the planned or typed entry price, and there is no confirm step
- Same walk: planned (captured 10:23:04) 73.90 / 103.60 / 118.65 / 78.80; recorded paper entry at ~10:25
  72.60 / 102.00 / 122.25 / 80.95 - all four legs differ (-1.30, -1.60, +3.65, +2.15 per unit). Code: `capture_entry`
  takes the live LTP only (`ofo/tracking/paper.py:64`). Sensibull's Add to Drafts shows a confirm list with price and
  quantity (catalogue 171-173). Bears on REQ-109, REQ-077; decided by ADR-207 (1). Status: **measured once, live**.

## F-68 - An open paper leg has no expiry settlement: after expiry it has no price and its exit is refused
- Code read 2026-10-29: an expired contract is "missing" (no price) in `ofo/tracking/paper.py:14`, and exit is refused
  with `tracking_exit_contract_not_live` (`routes/tracking.py:389`). Real cases waiting: four SENSEX 29 Oct paper
  strategies open at 10:30 IST on 2026-10-29 (GCBP P7, W2 P7, W2 P8; GCBP P8 already exited). Bears on REQ-109;
  decided by ADR-207 (6). Status: **from code, NOT yet seen live (check after 15:30 IST on 2026-10-29)**.

## F-69 - The Positions screen opens on a tab that says the user holds nothing while paper positions are open
- Same walk: `/positions/current-positions` opened on "Positions": "No open positions - Zerodha shows no open
  positions, and none of your strategies holds any." with 17 paper strategies (15 with open legs) in the Paper tab; the
  just-placed strategy was 17th of 17. The menu's bare `/positions` page is a placeholder ("This page is a
  placeholder"). Bears on ADR-201 (2), REQ-044 AC-3; decided by ADR-207 (3). Status: **measured once, live**.

## F-70 - "% of funds" divides by available funds; at low cash it reads as a meaningless 1045%, and Sensibull divides by funds needed
- Same walk: max profit +4,274 "(1045% of funds)", max loss -2,226 "(544% of funds)" with margin available 409 and
  margin needed 61,163 (of margin needed: about 7.0% and 3.6%). REQ-081 AC-9 / ADR-164 take available funds and say
  "as Sensibull does", but the study records Sensibull's percent as "of funds needed" (catalogue line 42). Decided by
  ADR-207 (8) (SPEC CHANGE). Status: **measured once, live; basis read from the spec and the study**.

## F-71 - The "near a short strike" adjustment detection fires at entry for a shape whose short strike is near spot by design
- Same walk: right after tracking, "Adjustment opportunity detected: Index is near a short strike: 22900, 78.95 points
  (0.35%) away" on a fresh iron condor with spot 22,821 - where a 1-step-OTM short strike always sits. The threshold is
  fixed, not relative to the position's distance at entry. Bears on REQ-045 AC-3. Status: **measured once, live;
  deferred (outside ADR-207's eight parts)**.
