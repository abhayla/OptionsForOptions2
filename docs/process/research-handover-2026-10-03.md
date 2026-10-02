# Handover: end-to-end research of comparable apps (architecture, compliance, multi-broker), 2026-10-03

Written at the end of the 2026-10-02/03 session for a NEW session. The owner wants a detailed, end-to-end study of
apps like ours so "nothing comes as a surprise later", planned in detail first, with every result written into the
spec and the requirements so implementation follows the findings.

## 1. Where the project stands (verify each line yourself before relying on it)
- Main at `e201b6e` (kit 1.6.0 merged as #119). Read `docs/HANDOVER.md` first (status block 2026-10-02 15:42 IST).
- Built and verified: domain layer (`backend/ofo/`, ~1,430 tests); database foundation (trusted clock, audit store,
  instrument catalogue, entitlements; `backend/ofo_app/`, 475 PostgreSQL tests in CI); website skeleton (`frontend/`).
- Contract identity is (exchange segment, exchange token) with each broker's own code in `broker_instruments`
  (ADR-050, W-056 #114). Example: NIFTY 06-Oct-2026 20050 CE = `NSE_FO` 40559 at Zerodha, Angel One, Upstox, Dhan,
  Fyers.
- NOT started: user accounts / sign-up (build-plan label "P2b"), live Zerodha data and the order path (blocked on
  Zerodha's written answer, ADR-034, and on Q258).
- Requirements REQ-002, REQ-003, REQ-012, REQ-013, REQ-014 were approved by the owner on 2026-10-02 (#118).

## 2. What already exists on this subject (read before researching; do not redo it)
- `docs/research/broker-architecture-2026-10-02.md` - first research pass (5 broker instrument files, OpenAlgo,
  NautilusTrader, LEAN, CCXT, Kite docs, SEBI via secondary sources, algochanakya).
- `spec/findings.md` F-01..F-10 (F-06 SEBI static IP / algo ID, F-07/F-08 architecture lessons, F-10 Zerodha segment).
- `spec/decisions/ADR-050.md` (identity, per-broker table, eight order-path safeguards, OpenAlgo reference only).
- Open questions: Q258 (is our SaaS an "algo provider"; static IP), Q211 (legal review), Q204/Q205 (Zerodha feed model).
- Deferred issues: #115 (order path still links by Zerodha symbol), #116 (can an expired contract's exchange number be
  reused - unverified).
- Gaps the first pass admitted and never closed: Sensibull, Streak, Tradetron, Dhan/Upstox API docs, the SEBI circular
  PDF itself (regulation rested on news articles and Zerodha's blog), the OpenAlgo licence (believed AGPL, unchecked).

## 3. The research to plan (owner's scope, plus additions marked [added])
Plan it in detail FIRST, get the owner's approval, then research. For each app or rule, cover:

A. **Comparable apps.** Sensibull, Streak, Tradetron, Opstra, Quantsapp, AlgoTest, Dhan Options Trader, Upstox/Angel
   One option tools, OpenAlgo [added: the last five]. For each: what users can do, how orders reach the broker (whose
   API key, whose login, daily re-login), single or multi broker, how they map one option across brokers, where their
   market data comes from, pricing, and their stated regulatory status (SEBI RA/IA registration, algo-provider
   empanelment, exchange approvals).
B. **Architecture.** Broker connection model (each user's own Kite Connect app vs one platform app), order path,
   reconciliation, market-data fan-out, multi-tenant isolation, failure handling, kill switch.
C. **Compliance, from primary sources only.** SEBI retail-algo circular (4 Feb 2025) and any extension; NSE and BSE
   implementation circulars (algo ID, static IP, empanelment, 10 orders/second threshold) [added: BSE explicitly,
   since SENSEX trades there]; [added] SEBI Research Analyst / Investment Adviser rules, because showing strategies can
   count as advice (our wording rule is ADR-003); [added] SEBI rules on association with unregistered entities and
   finfluencers (2024); [added] exchange market-data redistribution licences (can we show live prices to users at
   all?); [added] Digital Personal Data Protection Act 2023; [added] Zerodha Kite Connect terms and pricing for a
   multi-user platform.
D. **Multiple brokers.** How each broker codes options, lot/tick/freeze per broker, symbol formats, order and error
   differences, rate limits; whether an expired contract's exchange number is ever reused (closes #116).

[added] Deliverables beyond findings:
- a **comparison matrix** (apps x the questions above), with a source per cell or "unknown";
- a **surprise register**: every risk that could block or reshape the product (e.g. "a market-data licence is needed
  to show live prices"), each with source, impact, and "owner decision needed: yes/no";
- one **architecture diagram** of our system (browser, API, database, broker adapter, market data, Notifier) as a
  shareable page; the owner asked for one and none was ever made.

## 4. Documentation rules (owner's condition: nothing lives only in chat)
Kit rules `.claude/rules/kit/spec-first.md` R1-R6 and `learning.md` apply. In the SAME turn a fact is proven:
1. **Finding** in `spec/findings.md` as F-11 onward: real values, source URL or document page, date read, status
   (decided / open for owner decision / recorded / unverified). A secondary source only = "unverified", with what
   would verify it.
2. **Cite the F-id** in every spec section, ADR and requirement it bears on. Run `python tools/spec_similar.py . "<text>"`
   before writing any new spec line; extend a match rather than restate it.
3. **Defect or risk classes** also go to `knowledge/findings/<slug>.json`, then regenerate the index with
   `python scripts/orchestrator/aregen.py` or `python tools/build_findings_index.py .`.
4. **New questions** go to `spec/open-questions.md` as Q259 onward. A finding never changes a decision by itself.
5. **Owner decisions** become decision rows: ADR-051 onward in `spec/decisions/`, or an amendment to an existing ADR with
   its pins re-checked. Requirements are then added or updated with acceptance criteria that cite the ADR and F-ids.
6. Long write-ups go in `docs/research/<topic>-2026-10-xx.md`; they are the narrative, and the spec is the record.
7. Only after that: work items and builds, each brief citing the findings and requirements (`check_brief.py`).
Batch spec/findings edits into one docs PR per research batch (run-discipline C5); run `python tools/ci_local.py`
before pushing; merge only with `python tools/merge_when_green.py <pr>`.

## 5. How the owner wants to work (from memory and corrections this session)
- Plain words. No unexplained labels ("P2b" was a build-plan code; say "user accounts" instead).
- Plan first: a full plan, an independent reviewer checks it, then ONE owner approval, then work (memory
  `plan-review-then-approval`).
- Questions one at a time with the question tool, each with a `Spec basis:` line and a recommended option.
- Do not ask for credentials (Google, APIs, VPS) until testing or deployment needs them (memory
  `credentials-at-test-time`).
- Honest answers: name gaps and costs, give a real example per claim, end done-claims with an evidence table.
- Research subagents: say which model and why, give a Budget line, ask for sources per claim.

## 6. Suggested first steps for the new session
1. Read this file, `docs/HANDOVER.md`, `views/spec-digest.md`, ADR-050, F-01..F-10, Q258.
2. Draft the research plan (sections 3A-3D + deliverables): sources per item, how each fact gets proven, which go to
   parallel research agents, time box per stream, and how results map into spec/requirements.
3. Get it independently reviewed, revise, and show the owner for one approval.
4. Run the research; record findings the same turn; produce the matrix, surprise register and diagram.
5. Bring the owner the decisions the findings need (one question at a time), write each answer into the spec, then
   update the requirements and the build plan.
