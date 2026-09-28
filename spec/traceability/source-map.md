# Source map: ChatGPT sources → spec

All sources are in `docs/reference/chatgpt/`, kept unchanged. Updated 2026-09-28.

## Which source is primary
1. **Full chat transcripts (primary)** — every question, every option offered, every owner answer:
   - **T1** `OFO_chat_full_transcript_2026-09-14_to_16.txt` — first ChatGPT account, 284 messages, Q1–Q97, the
     identity spec (T1 #272).
   - **T2** `OFO_chat2_second_account_full_transcript_2026-09-16_to_28.txt` — second account, 138 messages, Q81,
     Q98–Q203, vendor research and emails, the Zerodha interim decision, the hand-over to Claude Code.
   Both were read in full via the owner's logged-in browser on 2026-09-28 (one thread each, no branches).
2. **Handoff summaries (secondary)** — written by ChatGPT from memory; lossy:
   `Indian_Index_Options_Platform_Master_Handoff-1.md` (15 Sep), `…Latest_Handoff…-3(1).md`,
   `CLAUDE_CODE_MASTER_HANDOFF_COMPREHENSIVE_Q1-Q203.md`, `CLAUDE_CODE_Q102-Q203_QUESTION_DECISION_CONTINUATION.md`,
   `CLAUDE_CODE_IMPLEMENTATION_CONTROL.md`.
3. **Chat excerpts** `Chat1`, `Chat2` — pasted fragments of T1 and T2; superseded by the full transcripts.

## What the full chats corrected in the handoffs
| Item | Handoffs said | Full chat shows |
|---|---|---|
| Q35 | A (Buy/Sell in chain) | **C** — both; Builder default (T1 #121) |
| Q33A | never answered | **C** — both views, Expiry default (T1 #111); Q33B–Q33D also answered |
| Q81 | proposed, unconfirmed | **C** — hybrid dashboard (T2 #3) |
| Q1–Q32, Q60–Q71 | no record | all answered (register) |
| Q102–Q148 | "reconstructed" topics (e.g. Q102 = market-data architecture) | real topics are the Guided Builder, setups, preferences, history, rules (e.g. Q102 = two-path Create Strategy) |
| Data source | Q175 "interim Zerodha" as if settled | owner first chose a licensed vendor (T2 #107), then Zerodha interim (T2 #121), which ChatGPT flagged as needing Zerodha's written approval (T2 #122) |
| Exit plan | Q153 = "NO" (optional) | same — confirmed: owner chose C, both optional (T2 #89) |

## Where each part of the chats went
- Q-by-Q: `spec/traceability/question-register.md` (every Q1–Q203 + Q33A–D → answer, who, message, ADR).
- Decisions: `spec/decisions/ADR-001`–`ADR-032` (each lists its questions and the message numbers).
- Requirements: `spec/requirements/REQ-001`–`REQ-071`.
- Unanswered / external: `spec/open-questions.md`.
- Owner statements outside numbered questions (e.g. T1 #1 vision, #57 margin gate, #69 Zerodha filtering, #73
  positioning, #175 data first + adjustment solutions, #177 configurable adjustments, #183/#189/#191 commercial model,
  #235 anti-abuse, #265 daily session; T2 #93 video, #101 scale, #107/#121 data source, #119 BSE, #131 core first):
  cited in the ADRs by message number.

## Not carried (with reason)
- ChatGPT's *"What should I do now?"* section (T1 #42) and *"Suggested action: Move Call Spread"* mock-up (T1 #28):
  conflict with the wording rules (ADR-003) and Q159.
- Process text for ChatGPT sessions (continuation prompts, export discussions, rate-limit messages): not product
  requirements; the repo's kit rules govern how work is done here.
