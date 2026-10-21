# W-116 round 2 (last allowed round): no error storm, bid/ask live, OI slower, window follows ATM

Common brief: docs/process/builder-brief.md
Core: the chain socket never sends more than one message a second for ANY reason (push, error or refusal), and its rows track the live ATM.
Proof: the verifier's storm case as a red test first - spot missing at apply time, then a window containing a contract the provider does not know (KeyError) -> over 30 poll loops at most 1 message per second and rows appear once the spot arrives; then green.
Budget: 40 min wall-clock, 50 tool calls
Report: evidence-table
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Tier: A fix round. Findings checked: liveness-from-shared-subscribers, live-subscription-lost-on-release-reacquire, staleness-by-last-change-age
Threat model: unchanged from W-116-builder.md (push storm in scope).

## Findings (Tier A verifier, ff7cf11)
1. MAJOR - error storm: when the spot is missing at apply time and the re-picked window holds a contract the provider
   does not know (KeyError), `_maybe_push` retries the re-pick before the 1 s gate and never sets `_last_push` on that
   path: 30 errors in 30 loops (~20/s in production), rows never appear. Fix: every outbound message (push, error,
   refusal) passes the same 1 s gate; a re-pick is retried at most once a second; a contract the provider does not know
   makes THAT cell unavailable instead of failing the whole window.
2. MAJOR - REQ-029 AC-4 "LTP and bid/ask stream live; OI and IV update at a lower frequency (Q46)." Fix: each cell also
   carries `bid` and `ask` (strings from the quote, 0 -> null per F-29) at the push rate; `oi` (and `oi_change` if the
   quote has it) is refreshed at most every 5 s (orchestrator technical decision: Q46 says only "lower frequency"); IV is
   NOT added (it needs the one engine, ADR-008) - say so in the module docstring as the remaining part of AC-4.
3. MINOR - the window never re-centres: after a spot move the ATM can leave the rows. Fix: when the live ATM is outside
   the current window, re-pick around it, at most once every 5 s, releasing old contracts AFTER taking the new ones
   (same order as `StrategyPush._replace`).
4. MINOR - every invalid client message gets an error reply one-for-one: covered by fix 1's single gate.
5. Not changed: the REST read's other-context rule (inherited #206 behaviour, unreachable in production).

## Tests (add to tests_app/test_chain_live.py; fakes only)
Storm case (the Proof); 50 invalid messages in 1 s -> at most 1 reply per second; bid/ask present and 0 -> null; OI value
changes inside 5 s are not pushed until 5 s pass while LTP changes are; spot drift 25162.30 -> 25398 -> after <= 5 s the
rows contain the new ATM and the old contracts are released, the index stays held. Mutations: remove the shared gate ->
storm test red; remove the OI timer -> OI test red; remove the re-centre -> drift test red. Regenerate
`docs/api/openapi.json` (the cell model changes) and run `tests_app/test_response_door.py` and `tests_app/test_openapi_drift.py`.

## Isolation
Work ONLY in `D:\Abhay\Ventures\OptionsForOptions2-gc5s-w116` (branch `build/W-116-chain-route`). Never run git or npm in
`D:\Abhay\Ventures\OptionsForOptions2`; no database, no server; never touch `routes/outcome.py` again, execute/order
files or migrations. Commit, push; no PR. No new duplicated literal; reuse the existing helper; ruff/mypy baselines must
not rise; targeted tests only; no regenerated files in the PR except `docs/api/openapi.json`.
