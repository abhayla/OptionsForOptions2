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
  conflicting, unverified), 25 modifications per order; autoslice returns mixed success and failure per slice, at most
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
- Bears on: Q258, REQ-042, REQ-054, REQ-063, REQ-066, ADR-009, ADR-050 item 4. Status: **open for owner decision**.
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
- Bears on: Q258, Q205 (daily session end), REQ-015 AC-7, REQ-054, REQ-063. Status: **open for owner decision**.
