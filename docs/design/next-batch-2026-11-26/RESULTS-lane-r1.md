STATUS 21:10 | stage 1: built, full check running | next push 22:30 (stage 1) | blocker: none (replies to the coordinator are refused: device trust; this line is the report)

# Lane R1: real positions get the same screens, backend (round 3)

Spec basis: ADR-330 (73) (the decision this lane implements; (64) withdrawn), (58); ADR-281; ADR-016 to ADR-019; ADR-292 (4), (5); ADR-003; ADR-008; ADR-002.
Base: origin/integration/weekend-r3-1129 (a1d70422, wave 0; alembic head was 0062_order_request_keys_expiry). Branch: feat/real-same-screens-be-1128. Status ceiling: Fixed, not tested.

## The field contract (frozen 28 Nov 19:25 IST; Lane R2 codes against it)
Every body that carries a strategy's order, trigger or alert (paper book order rows, order answers, trigger rows and
answers, alert rows, strategy list rows) carries, with these exact names:

| Field | Type | Meaning |
|---|---|---|
| `position_kind` | `"paper"` \| `"real"` \| `"unknown"` \| `"none"` | the STORED tag (strategies.position_tag); `none` = no order yet; `unknown` = tag NULL or unreadable (fail closed) |
| `position_kind_text` | string \| null | the one sentence of the row (catalogue `position_kind_real` / `position_kind_unknown`); null for paper and none |
| `stored_not_sent` | `true` \| absent | present and `true` ONLY when the answer is about a REAL position: the action was stored in the app and nothing was sent to Zerodha |
| `record` | object \| null | `{"action": "open"\|"add"\|"exit"\|"stop"\|"stop_fired", "stored_at": ISO-8601 with offset, "price": Decimal text}` of the latest stored record the body is about; null when none |

Rules for the frontend: `stored_not_sent: true` means show the catalogue line "Not sent to Zerodha. Place it in Kite.";
never show a P&L "as if filled" from `record.price`; a real row's quantity and P&L stay the Zerodha figure. Paper bodies
never carry `stored_not_sent` and carry `"record": null`.

## For the owner lane
(none yet)

## Decided for the owner
1. The tag is stored in a NEW insert-only table `strategy_position_tags` (strategy_id PK, tag paper|real), not a column on
   `strategies`: the strategies guard trigger is pinned in the app-role allow-list (a column would mean rewriting that
   pinned chain). Same meaning as the brief's `strategies.position_tag`: written once, never updated (guard OF063
   refuses UPDATE and DELETE, even for the owner role). Migration `0063_position_tags` (next after 0062 on the build).
2. No trigger writes the tag: the allow-list refuses an unexpected trigger on paper_orders, execution_plans and
   strategy_held_entries (found by running the migration). The code writes it once, first write wins:
   `paper_store.place` (under the strategy lock, at the first paper order -> paper) and `strategy_store.claim_tag` for a
   basket sent by Execute (stored on the first read of its kind -> real). I could not hook Execute's own insert (Lane B2's
   file). Effect: between an Execute and the first read the tag may be absent, and an absent tag with an order reads
   `unknown` (fail closed) only if the claim itself fails; otherwise the read stores `real` first.
3. A held entry (ADR-292) stays real whatever is stored: its basket is stored first (tag paper, same transaction), the held
   row after it, and routes/paper stores them in that order. `kind_of` therefore reads: held -> real; else the stored
   tag. The stored row is untouched (guard test pins it).
4. n7 (`test_exit_door_real_fd3`): the kind is read ONCE, BEFORE the commit (the door's check); that read decides and the
   answer after the commit reuses it. Pinned as `calls == 1` (was `>= 2`, the old FD5 expectation).
5. Backfill: held -> real; else a paper order -> paper; else an execution plan -> real; no order -> no row.

## Question for the owner
(none yet)

## New wording for the owner to read
(none yet)

## New test files
- tests_app/test_position_tag_r1_1128.py (tag never flips for every order kind and record action; claim rules; migration round trip and refusal; insert-only guards)
- rewritten: tests_app/test_position_kind_adr330_64.py (kind_of takes the stored tag), tests_app/test_exit_door_real_fd3.py n7 (one read)

## Not done
Stage 2 (record store and door), stage 3 (worker, alerts, catalogue sentences), the section-6 database test, reply fields `stored_not_sent` and `record`.

| task / model / minutes |
|---|
| lane build / Sonnet / running |
