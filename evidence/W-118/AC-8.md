---
work_item: W-118
ac: AC-8
requirement: REQ-029
ac_fp: "497ccbc6827a"
result: fail
verified_by: "verifier (sonnet, fresh context, Tier B; round 1 f6aa87e FAIL, round 2 9cf0592, 2026-10-19)"
builder: "builder (W-118, sonnet, 2 rounds)"
date: '2026-10-19'
commands: "Read OptionChainPage.vue; npx vitest run tests/option-chain.test.js; attack A4"
---

AC: AC-8
result: fail
commands: Read OptionChainPage.vue; npx vitest run tests/option-chain.test.js; attack A4
observed: ATM row highlighted from the server's atm_strike (live: exactly 1 data-atm row); underlying price shown; expiry selector on top. NOT MET AS WRITTEN: no selected-contract highlight (needs REQ-030 selection).
attack: atm '24500' vs strike '24500.00': no highlight (fails closed on string inequality, MINOR).

Recorded by the orchestrator from the verifier's returned block.
