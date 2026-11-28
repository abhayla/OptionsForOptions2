STATUS 05:50 | item 1 (cancelled_stops, F4): Passed in cloud; item 2 (client_request_id): Passed in cloud; items 3-5: not started | next push: after the gate | blocker: none

# Lane FD2: backend replies, fields and closed-market reads

Branch fix/r2-backend-2-1128 (from origin/fix/r2-backend-1128-fd). Paper only; no broker call was made.

## Per item
| Item | State | Test (count) |
|---|---|---|
| 1 `cancelled_stops` on the order reply | Passed in cloud | tests_app/test_paper_orders_r2_fd2.py (4) |
| 1 F4 orphan leg stop revival | Passed in cloud (red first: the stop stayed armed) | test_an_orphan_leg_stop_on_a_flat_contract_does_not_revive_... |
| 2 `client_request_id`, paper door | Passed in cloud | tests_app/test_order_request_key_r2_fd2.py (10 on the paper door and the store) |
| 2 `client_request_id`, real door | Passed in cloud | same file, 2 real-door tests |

## For the owner lane
- `client_request_id` (UUID, optional) on POST /paper/strategies/{id}/orders and POST /strategies/{id}/execute.
- Durable key store needs a migration (Lane FD): the key lives in Redis for 600 s (longer than the 120 s unknown window). A crash between the order commit and the key write (a few milliseconds) can still let one resend through; a table `order_request_keys(user_ref, key, strategy_id, body_sha256, result jsonb, created_at)` closes it.

## Decided for the owner
(filled in as items are done)

## New wording for the owner to read
(filled in as items are done)

## Not done
Items 3 to 5.

## PC steps
Market closed and live: none for items 1 and 2.
