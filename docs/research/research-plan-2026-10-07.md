<!-- Approved by the owner 2026-10-07 with the master plan, docs/process/master-plan-2026-10-07.md (it is Stage 1). -->

# Part B: Research plan (Stage 1), rev 2 after review, plus option chains

Core: we can fetch the hard sources raw, without a login, and read exact text and numbers from them. The sources are
SEBI and NSE circulars, the SEBI intermediary register, a JavaScript-heavy app pricing page, and an NSE F&O daily
contract file.
Proof (step 1, about 20 min, in this session, raw files saved to the scratchpad):
1. the SEBI retail-algo circular of 4 Feb 2025 (PDF to text): quote the algo-provider paragraph with its number;
2. one NSE circular page (the INVG67858 algo circular);
3. one search on the SEBI intermediary register (Research Analysts);
4. Sensibull's pricing page;
5. one NSE F&O bhavcopy (zip, parsed with Python): show the contract-number column and the row count.

Each of these is either "fetched raw and read", or "blocked". A blocked one is retried once through the Chrome
browser tool. If any of the five still fails, I STOP and re-plan before spending on agents.

## Context
The first pass (2026-10-02, `docs/research/broker-architecture-2026-10-02.md`) proved how five brokers code the
same option (F-01..F-05, F-10) and led to ADR-050. Its regulation part rested on news articles (F-06
"unverified"). It never covered Sensibull, Streak or Tradetron, Dhan's or Upstox's API docs, or the OpenAlgo licence.

Q258 (are we an "algo provider"?) blocks the order phase. Q210/ADR-034 already verified, on Zerodha's own pages:
- the free Personal plan has no live data;
- the Connect plan costs ₹500 per app per month;
- showing Kite Connect data on another platform is refused by default.

The startup-programme question waits on Zerodha's written answer.

**Out of scope:**
- No credentials, sign-ups or logins.
- No contacting companies.
- No code.
- Not a legal opinion. Q258 and Q211 cannot be settled by public research. The outcome for them is primary-source
  **evidence** for Zerodha's answer and the legal review, not a verdict.

## 1. How a fact is proven (every stream)

| Level | Source | Status in `spec/findings.md` |
|---|---|---|
| P1 primary | SEBI / NSE / BSE circular, Act or Rules in the Gazette, the company's own terms / pricing / legal page, official API docs, a real data file we downloaded | recorded / open for owner decision |
| P2 company statement | Blog, help centre, founder post, official video | recorded, marked "company statement" |
| P3 secondary | News, forums, YouTube, AI summaries | **unverified**, naming the P1 source that would verify it |
| Inferred | Seen on a public page (e.g. a "Login with Kite" button), job posts | **inferred**, never acted on |

Every finding row carries: the real values; the URL plus the paragraph, clause or page; a quote of at most about 25
words; the date read; the level; and **"in force as of <date> / superseded by <circular>"**, checked against SEBI's
master circulars.

Regulatory status (RA/IA registration, algo-provider empanelment) is checked on the official registers, never taken
from the company's own claim.

**Raw, not summarised.** Files and PDFs are downloaded to the scratchpad, PDFs are turned into text, and data files
are parsed with Python. Quotes and counts come from the raw text.

**Agent reports are claims.** Before a fact is written into the spec, I re-read its primary source myself, from the
raw text. This covers every P1 fact that changes a status, every fact in the surprise register, and every fact cited
by a requirement or decision. Other P2 and P3 app facts are spot-checked one in three, and unchecked ones are marked
as such.

**"Same turn"** (handover §4): the turn in which I re-verify a fact is the turn it is written into the spec, stream
by stream.

When something cannot be found in time, it is written "unknown (tried: …)". Nothing is guessed.

## 2. Hypotheses to test (the likely surprises; NOT facts)
- **H1** Live-price display: 2025 SEBI price-data rules, plus exchange and index data policy, may stop us showing
  live prices to users who have not connected a broker (REQ-010, REQ-052, Q204).
- **H2** Zerodha's terms beyond Q210: is a platform-level Kite Connect app or partner agreement possible, and does
  the startup programme include data rights? Where the ADR-034 email stands is recorded.
- **H3** The SEBI RA Regulations as amended Dec 2024, plus the 2025 guidelines, may require RA registration for
  suggested setups (REQ-025/027/045/046/068/069, Q211).
- **H4** SEBI's 2024 association and finfluencer rules may limit links with the owner (an Authorised Person) and
  Zerodha.
- **H5** Algo framework: does "Alert + Prepare Orders" (ADR-009, REQ-042), with each order confirmed by the user,
  count as an algo? Also strategy registration, algo ID, static IP (Q258).
- **H6** DPDP Act 2023 / Rules 2025: consent, deletion, breach notice, retention (REQ-013, Q96).
- **H7** An expired contract's exchange number may be reused (#116).
- **H8** SEBI's F&O rules from 2024 onward: one weekly expiry per exchange, contract size, upfront premium,
  expiry-day moves, and pending limits on weeklies.
- **H9** Payments: gateway restrictions on "trading tools / tips" merchants, RBI e-mandate rules, GST (REQ-023,
  ADR-026).
- **H10** NSE Indices / Asia Index name and data licensing; CERT-In 2022 (6-hour reports, 180-day logs); Google and
  Meta financial-ads rules; PaRRVA and the ban on advertising algo returns or backtests (ADR-013, REQ-051).
- **H11** Authorised Person rules: may an AP sell a separate paid product to clients, and is free Pro (ADR-024) an
  inducement?

## 3. Research streams
Each agent:
- fetches raw files into its scratchpad and writes no repo files;
- returns a claims table (claim, value, URL plus location, quote, level, in force / superseded, date read) and an
  "unknown" list;
- has a brief that carries `Budget:`, `Report: evidence-table`, §1, its hypotheses and the facts it must not redo
  (F-01..F-10, Q210).

All streams run in parallel after the core proof.

### S1a Market and algo rules. Opus, 90 min / 100 tool calls
Why Opus: legal text, judging what a clause applies to. Covers H5, H7 (circular side), H8.
- SEBI retail-algo circular of 4 Feb 2025, every extension since, and the FAQs.
- NSE and BSE implementation circulars: empanelment SOP, algo-ID and static-IP specs, the 10 orders per second
  threshold, white-box vs black-box algos.
- Zerodha's framework pages.
- SEBI F&O measures (Oct 2024 onward) and the NSE/BSE expiry-day circulars.
- The exchange contract-file spec on token uniqueness (#116).

### S1b Advice, data, privacy, the Authorised Person, payments. Opus, 90 min / 100 tool calls
Why Opus: same reason. Covers H1, H2, H3, H4, H6, H9, H10, H11.
- SEBI RA and IA rules and the 2025 RA guidelines.
- The 2024 association and finfluencer circulars; the past-performance and price-data circulars.
- NSE and BSE market-data and index-data licence policies.
- DPDP Act and Rules, with their dates.
- CERT-In 2022.
- NSE and BSE Authorised Person rules.
- Payment-gateway prohibited lists, RBI e-mandate rules, GST for SaaS.
- Google and Meta financial-ads policy.
- Read `D:\Abhay\GLOBAL.md` and the `zerodha-ap-social-media-compliance` skill first; do not redo them.

### S2 Comparable apps. Two Sonnet agents, 75 min / 80 tool calls each
Why Sonnet: clear template, public pages.
- S2a: Sensibull, Streak, Tradetron, Opstra, Quantsapp.
- S2b: AlgoTest, Dhan Options Trader, OpenAlgo (including its LICENSE file, closing ADR-050 item 5), and the Upstox
  and Angel One option tools (cells 3, 6, 8, 9, 11 and 13 only).
- The 13 cells:
  1. features;
  2. target user level;
  3. how orders reach the broker (whose API key, whose login, how often the user logs in again);
  4. single or multiple brokers;
  5. cross-broker option mapping, if visible;
  6. data source;
  7. free vs paid and price (with the date read);
  8. stated regulatory status;
  9. register-checked status;
  10. disclaimers and wording compared with ADR-003;
  11. SEBI or exchange orders against it;
  12. what to copy and what to avoid;
  13. **option-chain screen:** which columns (OI, IV, Greeks, change, volume), how often it refreshes, whether it is
      delayed or live for signed-out users, and how a leg is picked into a strategy (REQ-029-031).
- Public pages only. Short quotes.

### S3 Brokers and option-chain data. Sonnet, 90 min / 100 tool calls
Why Sonnet: data files and documented fields.
1. Add two brokers to the F-01 table (Kotak Neo, ICICI Breeze), same two contracts. This is a light confirmation:
   V1 is Zerodha-only (REQ-001).
2. From official API docs (Zerodha, Upstox, Dhan, Angel One, Fyers): order types, products, error codes, rate
   limits, session length and re-login, order-update push. This settles F-07's daily cap (3,000 vs 5,000).
3. #116 on data: a daily series of NSE and BSE F&O contract files or bhavcopies covering at least 4 weekly expiries,
   counting numbers seen on more than one contract. Report "no reuse seen in N contracts over <dates>", never
   "disproven".
4. **Option-chain feasibility from Kite's docs:**
   - instruments per WebSocket connection, connections per API key, and the subscription modes (LTP, quote, full)
     and their fields (OI, depth);
   - quote-API limits;
   - how many strikes and expiries a full NIFTY and SENSEX chain needs today, counted from the real instrument
     file;
   - whether one user's own feed can carry a full chain plus their positions;
   - how far back Kite's historical API goes for intraday options data (decides when 4a must start recording);
   - Kite's redirect-URL and postback rules (is a local or IP-only URL allowed?), which feed D5.

   This feeds REQ-029, REQ-048, REQ-050 and Q204, and the "Zerodha rate limits for per-user WebSockets" open area.

### S4 Architecture synthesis and diagram. This session, 60 min, after the streams
Questions:
- connection model (each user's own Kite app vs a platform app);
- order path;
- reconciliation;
- market-data fan-out under the licence findings;
- option-chain data path;
- tenant isolation;
- failure handling;
- kill switch;
- where the static IP sits.

Output: our system diagram (browser, API, database, broker adapter, market data, option chain, Notifier, payments,
admin), with every arrow labelled by its F-id or ADR and open forks marked.

### Time and cost
- About 5-6 h elapsed:
  - core proof: 20 min;
  - streams: about 1.5 h;
  - my re-verification and spec writing: about 2 h for about 60-80 sources;
  - S4 and deliverables: about 1 h.
- Roughly 3-5 million tokens.
- At its time box an agent stops and reports done / not done / next step. Unfinished cells become "unknown". A
  stream is never extended silently.

## 4. Deliverables
1. Findings F-11 onward in `spec/findings.md`. F-06 is edited in place, with its history kept.
2. `docs/research/comparable-apps-2026-10-07.md`, `compliance-2026-10-07.md`, `multi-broker-2026-10-07.md`, with
   full source lists.
3. The comparison matrix: the apps × 13 cells, each a value plus its source, or "unknown (tried …)".
4. `docs/research/surprise-register.md`: SR id, risk, F-ids, impact (blocks launch / reshapes feature / adds cost /
   none), owner decision yes/no, Q-id.
5. The architecture diagram as a private, shareable artifact page, with its HTML source committed under
   `docs/research/`.

## 5. How results map into the spec (in the turn each fact is verified)
1. Run `python tools/spec_similar.py . "<text>"` before every new line, then extend or cite a match.
2. Cite the F-id in each spec item it bears on:

   | Area | Spec items |
   |---|---|
   | Algo / IP / Alert+Prepare | Q258, ADR-009, REQ-042, REQ-054, REQ-063, REQ-066, ADR-034, ADR-050 |
   | F&O market rules | REQ-001, REQ-026, ADR-042, F-05 |
   | Advice / RA | ADR-003, REQ-005, REQ-024, REQ-025, REQ-027, REQ-045, REQ-046, REQ-068, REQ-069, Q211 |
   | Data / index licence | ADR-012, ADR-014, REQ-010, REQ-029, REQ-048, REQ-052, Q204, Q205, Q210 |
   | Option chain | REQ-029, REQ-030, REQ-031, REQ-048, REQ-050 |
   | DPDP / CERT-In | REQ-013, REQ-063, REQ-064, Q96 |
   | Authorised Person / payments / GST | ADR-024, ADR-026, REQ-019, REQ-023 |
   | Notifications / ads | ADR-028, ADR-040, REQ-062, REQ-051, ADR-013 |
   | Apps | REQ-001, REQ-006, REQ-015, REQ-023, vision |
   | Brokers / #116 | REQ-053, REQ-054, REQ-056, REQ-057, F-04, F-07 |

3. Defect and risk classes go to `knowledge/findings/<slug>.json`, then the index is regenerated.
4. Anything that needs you becomes Q259 onward. A finding never changes a decision by itself. Decisions are made in
   Stage 2.
5. **In Stage 1, F-id citations go into REQ files, findings, open questions and spec sections only, never into ADR
   files.** Touching an ADR is a class-3 trigger, so ADR edits happen only in the Stage 2 decision PR. That keeps the
   research PR truly `Class: none`. `check_spec_refs` is run so that no `confirmed_against` pin breaks.

**Git:**
- Worktree `OptionsForOptions2-research-2026-10`, branch `docs/research-2026-10`, 48 h TTL.
- One commit per stream. `python tools/ci_local.py` before each push.
- One docs PR (Tier C), with Spec-deviation `Class: none`.
- Merge with `python tools/merge_when_green.py <pr>`, run as its own command.
- The worktree is removed the same session.
- The Stage 2-3 spec changes go in their own PR.

## 6. Verification (evidence table at the end of each stage)
- `ci_local.py` and GitHub CI are green: factory_lint, trace_check, check_spec_refs, the findings index `--check`,
  the pytest guards, plus `coverage.py --check`.
- Every F-11+ row has a URL, a location, a date, a level and "in force / superseded". A grep shows each F-id cited
  in at least one spec, requirement or decision file.
- Every matrix cell is sourced or "unknown (tried …)". Every surprise row has an F-id and a Q-id, or "no decision
  needed".
- H1-H11 each end proven, disproven or unknown.
- Every claim in a report sits in a `| Claim | Evidence |` table backed by commands run in that turn.
