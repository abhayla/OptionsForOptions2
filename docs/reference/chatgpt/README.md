# ChatGPT source documents (reference only — never edit, never delete)

The owner's product-design work was done in ChatGPT and exported as the files below. They were imported on
2026-09-28 into `spec/` (the single source of truth). **These files are kept exactly as received** (SHA-256 checked
against the originals in the owner's Downloads folder). If a file here and `spec/` disagree, `spec/` wins; the
disagreement is a defect to fix in `spec/`, never in these files.

| File (oldest first) | Dated | Lines | SHA-256 | What it is |
|---|---|---|---|---|
| `Indian_Index_Options_Platform_Master_Handoff-1.md` | 2026-09-15 | 889 | `fd6cba5b…3d82a1f` | First master handoff; stops at unanswered Q33A |
| `Indian_Index_Options_Platform_Latest_Handoff_Post_Previous_Handoff-3(1).md` | undated | 336 | `e0a8c6c3…f3e4e22` | Continuation: Q43–Q97, stops at Q81 |
| `CLAUDE_CODE_MASTER_HANDOFF_COMPREHENSIVE_Q1-Q203.md` | 2026-09-28 | 2,122 | `471c8e8c…0c77086` | WHAT the product is: all decisions through Q203 |
| `CLAUDE_CODE_Q102-Q203_QUESTION_DECISION_CONTINUATION.md` | 2026-09-28 | 413 | `aa8e178c…fe38998` | One record per question Q102–Q203 |
| `CLAUDE_CODE_IMPLEMENTATION_CONTROL.md` | 2026-09-28 | 372 | `a244b8d2…c8d1e` | HOW to build it: phases, testing, definition of done |

## Provenance limits (stated by the files themselves)
- **Q1–Q32 wording is lost**; their outcomes survive only as unnumbered sections. Q33–Q42 (except Q33A), Q60, Q62,
  Q65, Q67–Q69, Q71 have no record at all.
- **Q102–Q148 were reconstructed by ChatGPT** from the finished requirements, not the owner's verbatim answers.
- **Q149–Q203** keep the subjects and locked outcomes.
- Answer letters survive only for Q58–Q97 (in the Latest handoff).

Every ADR records which kind each of its decisions is (`provenance:`), so a reader can tell an owner-locked answer
from a reconstruction. Section-by-section mapping: `spec/traceability/source-map.md`.
