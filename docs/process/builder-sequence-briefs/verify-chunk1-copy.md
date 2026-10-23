# Verifier brief: chunk 1 reference-copy records, the one check (ADR-178 (2)) - 16 COPY records

Independent, adversarial verifier; you built none of it. READ-ONLY: never edit, create, commit or delete a tracked
file. Scratch only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\5db71e90-61e3-4f1b-8a6c-a0ee38c54e11\scratchpad\verify-copy`.

Code: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, current head (parts A,
B1 and B2 merged). Records: `spec/reference-diffs/RD-0NN.json` (read each: `reference_behaviour`, `ours`, `req`, `ac`,
`status`). Briefs: `docs/process/builder-sequence-briefs/chunk1-copy-part-a.md`, `chunk1-copy-part-b1.md`,
`chunk1-copy-part-b2.md`.

For each record, verdict whether OUR product now does what `reference_behaviour` describes, on the path users reach
(finding verified-on-a-module-the-product-does-not-call: name the route/component that shows it):
- Part A: RD-010 (login panel: is-it-safe explainer, partner link from its one home module per ADR-175, no-extra-charges
  line), RD-012 (Trade disabled with its reason before any click when no broker), RD-045 (a data-health state in one
  sentence with its reason), RD-048 (a missing value's reason in place).
- Part B1: RD-039, RD-046, RD-047, RD-068 (row 11 code: check the file:line each record cites), RD-057 (browser
  reconnect spread up to 1 s), RD-058 (browser never gives up, retries at the cap), RD-090 (20 shapes added as data, no
  engine code; each matches its own template only), RD-095 (display names; ids unchanged).
- Part B2: RD-013 (masked user id; margin exactly as read with its read time; reason, never 0), RD-014 (positions read at
  connect and on a 45 s period, no Execute visit), RD-025 (four new capability flags, default off), RD-063 (minimum
  read period per user inside the one limiter; a read inside the period is served from the last answer).

Attack first: RD-013 a margin read failing / empty / capability off -> never 0 and never computed (grep the route and
the component); RD-063 two users and a 429 - one user's reads never consume the other's period and the order path
(Execute, return) still gets its reads; RD-058 a socket that never opens -> retries forever, screen shows the
reconnecting text, no tight loop (the wait never drops below its floor); RD-090 build each new shape from its legs and
check it matches exactly one template; the B1 template-name scanner change (`tests/strategy/test_templates.py`): does
it still catch a backend `if template.id == "strip":` branch? Write that case in a scratch copy and run the test.
New ACs (REQ-113 AC-10/AC-11, REQ-015 AC-12/AC-13, REQ-117 AC-6, REQ-118 AC-7, REQ-015 AC-10/AC-11): each must not name
the reference product (ADR-176 (4)) and must have a test in its work item's `tests_required`.

Database: run NO database test locally; CI on PR #525 runs them. Frontend: `npx vitest run <files>` in frontend/ is
fine (known local-only failures: learn.test.js `\r`, vendor-host-lint timeout). DB-free backend tests you may run:
python -m pytest -q -p no:cacheprovider tests/strategy tests/broker tests/test_margin_from_zerodha_only.py tests/test_reference_register_real.py
Why Opus: RD-013 margin display (ADR-016) and RD-063/RD-014 live broker reads under the rate limiter (REQ-118) are in
the safety set.
BINDING: never stop a process by name. Kit guard: a shell command naming spec/, tools/, .claude, factory, views or
.github is blocked; use Read/Grep/Glob.

Return a JSON array, one object per record: `{"rd": "RD-0NN", "result": "pass" | "fail" | "partial", "observed":
"route/component file:line", "attack": "...", "evidence": "command + result line"}`, then under 250 words: each
fail/partial with severity and the smallest fix.
Budget: 25 min wall-clock, 32 tool calls (the verifier's turn limit is 40; batch commands)
Report: evidence-table
