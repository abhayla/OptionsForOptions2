# Handover

Updated 2026-09-28 (spec built from the owner's full ChatGPT chats).

## DONE
- Project created from Factory kit 1.2.0 with the production seatbelt; CI green on the first push.
- 2026-09-28: all ChatGPT material imported unchanged into `docs/reference/chatgpt/`: five handoff files, two chat
  excerpts, and — read directly from the owner's two ChatGPT accounts — the two **full chat transcripts** (T1: 284
  messages, Q1–Q97; T2: 138 messages, Q81, Q98–Q203).
- Spec (PR #2): 32 decisions `spec/decisions/ADR-001`–`032`; 71 requirements `spec/requirements/REQ-001`–`071`
  (384 acceptance criteria, status Specified); `spec/traceability/question-register.md` (all 203 questions + Q33A–D:
  144 owner answers, 58 ChatGPT-delegated, 5 superseded, 0 missing); vision, scenario calculations (Iron Condor
  recomputed, 0 mismatches), domain model, core invariants, open questions, source map.
- Corrections found by reading the full chats: Q35 = C (not A); Q33A–Q33D and Q81 answered; handoff Q102–Q148 had the
  wrong topics.

## PENDING (owner / external)
`spec/open-questions.md`, most important first:
1. **Q210** — ask Zerodha's API team in writing: may our SaaS show/use Kite Connect data, and does the startup /
   mass-retail programme apply? (ChatGPT read Zerodha's docs as: free Personal plan has no live data; ₹500/month per
   API key for live data; no redistribution.) This decides whether the interim data plan works.
2. **Q204/Q205** — per-user Zerodha feed vs shared feed; monitoring when the daily Zerodha session has expired.
3. Q206 prices without Zerodha · Q207 futures formula · Q208 SENSEX step · Q209 referral proof · Q213/Q214 small UX.
4. Q211 legal review (gates production of advice-like features and billing). Q212 YouTube transcript from the owner.
5. Vendor replies: TrueData (emailed; "NSE certificate"), GFDL (drafted), NSE, BSE (not contacted).

## NEXT
1. Merge PR #2 once the owner has no more sources to add.
2. **Core proof** (kit rule E3; owner T1 #175 "data is the first goal"), before any product code:
   `Core: a Zerodha Kite Connect login from the platform returns live NIFTY (NSE) and SENSEX (BSE) option quotes and
   the user's available margin.` `Proof: one throwaway script, the owner's real Zerodha login, 3 real option contracts
   per index, quotes + margin printed and recorded.` Needs the owner's Kite Connect credentials and the Q210 answer.
3. Then work items for the first vertical slice (ADR-030), from REQs marked Approved by the owner.

## BLOCKED
- Core proof needs the owner's Kite Connect API key/secret and login (owner-only credential), and Q210's answer.

## Legacy code (reference only)
- `abhayla/OptionsForOptions` (private, 2021, last pushed July 2025): an older ASP.NET WebForms + MySQL options app
  with a `Strategy` folder. The owner chose (2026-09-28) to leave it untouched. Read-only reference; anything reused
  is rewritten here under the spec, naming the legacy file it came from.
- `D:\Abhay\Ventures\OptionsForOptions` locally holds only a `.remember/` folder; leave it alone.
