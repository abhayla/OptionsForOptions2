# Source map: ChatGPT handoffs → spec

Every section of the imported files and where it now lives. "Not carried" rows say why. Files are in
`docs/reference/chatgpt/`. M = comprehensive master handoff (Q1–Q203); C = Q102–Q203 continuation;
IC = implementation control; H1 = 15 Sep master handoff; H2 = "Latest" handoff.

## Handoff history (oldest first)
1. **H1**, 15 Sep 2026: stopped at unanswered Q33A.
2. **H2**, undated: says H1 is out of date; records Q43–Q97; continuation point Q81.
3. **M + C + IC**, 28 Sep 2026: consolidated through Q203; implementation starts.
Where they differ, the later file wins (M §101), and the change is written into the ADR ("Superseded" /
"Direction changed").

## M (comprehensive master handoff)
| Section | Goes to |
|---|---|
| §0 How to use | ADR-031 |
| §1 Vision, §4 Product shape, §94 Non-goals | ADR-001, spec/vision/vision.md |
| §2 Philosophy and language | ADR-003 |
| §3 Users, UX levels | ADR-004 |
| §5 Core domain, §9 Strategy-only, §10 Modification | ADR-002, spec/data/domain-model.md |
| §6 Creation, §8 Discovery, §16 Strikes, §17 Expected range, §18 Preferences | ADR-005 |
| §7 Strategy engine | ADR-006 |
| §11 Definition vs live state, §12 Active vs proposed | ADR-019, spec/data/domain-model.md |
| §13 Automation, §14 Rule engine, §15 Exit | ADR-009 |
| §19 Option Chain Q43–Q57, §20 Chain role | ADR-007 |
| §21–§27 Calculation, outcome view, table, formulas, Iron Condor, live pricing, Greeks | ADR-008, spec/business-rules/scenario-calculations.md |
| §28 Risk UX | ADR-017 (risk UX section) |
| §29 Monitoring, §30 Positions, §55 Control center | ADR-010 |
| §31–§33 Adjustments | ADR-011 |
| §34–§36 Adjustment data, feasibility, storage tiers; §72 Simulation | ADR-013 |
| §37, §40, §73, §74, §84, §85 Market-data architecture, scale | ADR-012 |
| §38, §39, §71 Data provider, Zerodha interim, vendors | ADR-014 |
| §41 Q58/Q59, §57 Home, §58 Navigation | ADR-027 |
| §42–§44, §76 Broker boundary, restrictions, margin, adapter | ADR-016 |
| §45–§48, §79 Execution, order lifecycle, partial, retry, safety | ADR-017 |
| §49, §50, §78 Reconciliation, existing positions | ADR-018 |
| §51–§54, §97 State machine, exceptions, timeline, trigger audit | ADR-019, spec/data/domain-model.md |
| §56 Notifications | ADR-028 |
| §59, §60, §82 Zerodha connection, drafts, disconnect | ADR-020 |
| §61 Identity, registration | ADR-021 |
| §62 Q82–Q97 | ADR-021 (Q85, Q86), ADR-022, ADR-023 |
| §63, §64, §83 Commercial model, entitlement, access states | ADR-023, spec/data/domain-model.md §5 |
| §65, §66 Complimentary customers, admin eligibility | ADR-024 |
| §67, §69 Referral, eligibility loop | ADR-025 |
| §68 Paid Pro | ADR-026 |
| §70, §86, §87 Security, audit, errors | ADR-029 |
| §75 Entities | spec/data/domain-model.md §4 |
| §77 Market-data abstraction | ADR-012, ADR-014 |
| §80 Validation, §81 No silent substitution | ADR-016, ADR-017, ADR-019 |
| §88 Engineering principles, §92 Order, §98–§100 Operating mode, first action | ADR-030 |
| §89 Factory/legacy migration, §90 Resource efficiency, §91 Control center | ADR-030 (kit rules already cover these: run-discipline, status-artifact) |
| §93 Invariants | spec/testing/core-invariants.md |
| §95 Open areas | spec/open-questions.md |
| §96 Traceability, §101 Source-of-truth order | this file, ADR-031 |
| §99 Production rule | ADR-030, .claude/rules/kit/deployment.md |

## C (Q102–Q203)
Q102–Q109, Q170 → ADR-012 · Q110–Q113, Q161–Q169, Q177, Q183 → ADR-013 · Q114–Q123 → ADR-008 · Q124 (risk UX:
explain / warn / explicit acknowledgement; execution review contents) → ADR-017 ·
Q125, Q134 → ADR-002 · Q126 → ADR-007 · Q127 → ADR-016 · Q128–Q137 → ADR-005 (Q128 also ADR-003) · Q138–Q142 →
ADR-009 · Q143–Q146 → ADR-010 · Q147 → ADR-017 · Q148 → ADR-016 · Q149–Q160 → ADR-011 · Q171–Q176, Q178 →
ADR-014 · Q179–Q181 → ADR-016 · Q182 → ADR-012 · Q184 → ADR-015 · Q185–Q188 → ADR-020 · Q189–Q191, Q200–Q203 →
ADR-019 · Q192–Q195 → ADR-017 · Q196–Q199 → ADR-018.

## IC (implementation control)
§1–§10, §13–§20, §22 → ADR-030 · §11, §12 → spec/testing/core-invariants.md §2–§3 · §21 Definition of done →
ADR-030.

## H1 (15 Sep master handoff) — only what M does not already carry
§8–§9 own account only, no pooled money/copy trading/discretionary/shared credentials → ADR-001 · §14 "every
strategy has an explicit exit plan" → superseded by Q153 (ADR-009) · §16 simulation metrics → ADR-013 · §17
licensed-provider preference → ADR-014 "Direction changed" · §18 builder avoids unplaceable contracts → ADR-016 · §21
protective-first default; protective fail blocks dependent sell → ADR-017 · §24 "What should I do now?" → **not
carried** (conflicts with ADR-003 wording) · §25 information density → ADR-004 · §33 per-leg scenario numbers →
scenario-calculations.md §6 (verified) · §37 open list → spec/open-questions.md (items since decided are dropped) ·
§38 Q33A → spec/open-questions.md Q33A · §0/§39 ChatGPT continuation rules → **not carried** (process for ChatGPT
sessions; this repo's kit rules govern).

## H2 (Latest handoff) — only what M does not already carry
§5 "do not rely on Zerodha as sole public data source" → ADR-014 "Direction changed" · §8 "user's separate OTP
system" → ADR-021 · §12 Q81 not confirmed → ADR-027, spec/open-questions.md Q81 · §15 "explicit exit plan" →
superseded (ADR-009) · §26 Q72–Q77 map → ADR-021.

## Chat1 (owner's own replies, excerpts)
Q8 = Yes, public SaaS = B, Q14 = B → ADR-001 · Q29 = A → ADR-002 · template list, beginner/advanced paths →
ADR-006 · chain as supporting tool + multi-select import, Q35 = A, Q55 = A → ADR-007 · unavailable legs cannot be
added → ADR-016 · Q66 → ADR-026 · Q67 = A, Q90 = A, Q91 = A, active-strategy monitoring exception → ADR-023 ·
simple action-oriented home = B → ADR-027 · never ask for Zerodha password/PIN/OTP → ADR-020 · "Suggested action:
Move Call Spread" mock-up → **not carried** (ADR-003) · handoff-creation and continuation-prompt text → process, not
carried (kit rules govern).

## Chat2 (process)
Operating model (known decision → implement … production → wait) and solo-founder maintainability → ADR-030 ·
confirms the provenance limits recorded in `docs/reference/chatgpt/README.md` · the rest is the continuation prompt
(already in Chat1) and file-delivery chatter → not carried.

## Question numbers with no record in any file
Q1–Q7, Q9–Q13, Q15–Q28, Q30–Q34, Q36–Q42 (except Q33A) — outcomes survive only in H1's unnumbered sections — and
Q60, Q62, Q65, Q68, Q69, Q71. Chat1 shows three answers ("B") whose question numbers are cut off: the simple home
screen, public SaaS, and the Option Chain role. Answer letters exist for Q58–Q97 in H2 (e.g. Q82 = C, Q83 = D,
Q63 = C); none for Q72–Q77, Q81.
