# Handover

Updated 2026-09-28 (spec import from the owner's ChatGPT handoffs).

## DONE
- Project created from Factory kit 1.2.0 with the production seatbelt; CI green on the first push.
- 2026-09-28: five ChatGPT handoff files and two chat transcripts (Chat1, Chat2) imported unchanged into `docs/reference/chatgpt/` (SHA-256 verified), and
  turned into the spec: 31 decision records (`spec/decisions/ADR-001`–`ADR-031`), `spec/vision/vision.md`,
  `spec/business-rules/scenario-calculations.md` (Iron Condor example recomputed: 0 mismatches),
  `spec/data/domain-model.md`, `spec/testing/core-invariants.md`, `spec/open-questions.md`,
  `spec/traceability/source-map.md`, `spec/traceability/question-register.md` (Q1–Q203, 44 missing), and 67
  requirements (`spec/requirements/REQ-001`–`REQ-067`, 322 acceptance criteria, status Specified).

## PENDING (owner)
Open questions in `spec/open-questions.md`, asked one per turn, most important first:
1. **Q204** shared data feed vs per-user Zerodha data (a real conflict between two locked decisions).
2. Q210 how users connect Zerodha · Q205 monitoring when the session expires · Q206 prices without Zerodha.
3. Q207 futures formula · Q208 SENSEX step · Q33A scenario columns · Q81 confirm Home · Q209 referral proof.
4. Q211 is a legal review, not an owner preference; it gates production of advice-like features and billing.

## NEXT
1. Ask Q204 (one question per turn); write each answer as the next ADR the same turn.
2. **Core proof** (kit rule E3), before any product code:
   `Core: a Zerodha Kite Connect login from the platform returns live NIFTY (NSE) and SENSEX (BSE) option quotes and
   the user's available margin.` `Proof: one throwaway script, the owner's real Zerodha login, 3 real option
   contracts per index, quotes + margin printed and recorded.` Needs the owner's Kite Connect credentials. Also read
   Zerodha's current Kite Connect terms (answers Q204/Q210 with facts, not guesses).
3. Then requirements (`spec/requirements/REQ-###.md`) for the first vertical slice (ADR-030), then work items.

## BLOCKED
- Core proof needs the owner's Kite Connect API key/secret and a login (owner-only credential).

## Legacy code (reference only)
- `abhayla/OptionsForOptions` (private, 2021, last pushed July 2025): an older ASP.NET WebForms + MySQL options app
  with a `Strategy` folder. The owner chose (2026-09-28) to leave it untouched. Read-only reference; anything reused
  is rewritten here under the spec, naming the legacy file it came from.
- `D:\Abhay\Ventures\OptionsForOptions` locally holds only a `.remember/` folder; leave it alone.
