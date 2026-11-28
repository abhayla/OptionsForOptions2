STATUS 19:25 | stage 1: contract written, tag column in progress | next push 22:30 (stage 1) | blocker: none

# Lane R1: real positions get the same screens, backend (round 3)

Base: origin/integration/weekend-r3-1129. Branch: feat/real-same-screens-be-1128. Status ceiling: Fixed, not tested.

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
(none yet)

## Question for the owner
(none yet)

## New wording for the owner to read
(none yet)

## New test files
(none yet)

## Not done
(everything; stage 1 in progress)

| task / model / minutes |
|---|
| lane build / Sonnet / running |
