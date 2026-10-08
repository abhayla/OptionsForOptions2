# Builder brief: W-024 round 10 - structural guarantees only (restart of parked issue 30)

Core: no log record from ANY logger can carry a secret, and no API response body can carry text that did not come
from the catalogue, because each passes one structural door - not because a scanner recognised its shape.
Proof (step 1, before anything else): two tests, red on origin/build/W-024-r9 (0d2906d) and green after:
(1) `tests_app/test_redaction_root.py` logs a real-shaped Kite access token and api secret through three logger names
the code never registered (`ofo.execution.safety`, `ofo_app.routes.anything`, `zz.unrelated`) and through a child
logger created after start-up, and asserts the captured output holds the redaction marker and never the token;
(2) `tests_app/test_apimodel_closed.py` defines ApiModel subclasses using `model_construct()`, a `@computed_field`
returning `str`, and a `@field_serializer`, and asserts each is refused at class creation or at serialisation.

Why Opus: Tier A (secrets in logs, a guard meant to be hard to bypass); a redesign around an independent review after
two failed rounds on the round-9 design.
Budget: 60 min wall-clock, 90 tool calls. Commit after step 1 and after each numbered item; at budget stop after a
commit and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`).
Tier: A.
Class: text reaching a log or a response body through a path a detector did not recognise - any logger, any pydantic
serialisation hook, any exception text, any identifier carrying a secret.
Proof: the two step-1 tests above plus the full domain and app suites green (summary lines only).
Copy from: none - algochanakya has no error catalogue; rounds 1-9 built it new.

## Spec basis
- REQ-065 AC-2: "Every user-facing error states what happened, the impact, what is blocked and the next action."
- ADR-003 Q226: "every platform message comes from a
  fixed, reviewed template catalogue with typed slots"
- Core invariants: tokens never logged (spec/testing/core-invariants.md section 4, the Kite token rule).
- Issue 30, round-9 park comment (2026-10-08): the four findings and the recommended restart below. Run-discipline B8:
  prefer a structural guarantee over a detector.

## Start
Branch `build/W-024-r10` from `origin/build/W-024-r9` (0d2906d), then merge origin/main into it (37 commits behind:
W-059 kite_ws/fan-out, W-060 forward, W-056/057 catalogue). Resolve conflicts keeping main's behaviour and the
round-9 boundary; run both suites after the merge and commit before any new change.

## What to build (the issue's recommended restart, nothing else)
1. **Redaction at the root.** Replace `install_redaction()`'s fixed logger list with one hook every record passes:
   `logging.setLogRecordFactory` (preferred; covers every logger, child loggers and loggers created later) or a filter
   on every root handler PLUS a test that a handler added later is still covered. Redacts `msg`, every `args` value
   and `exc_text`/exception messages, by the secret VALUES the process holds (api key, api secret, access token,
   cache key read from config at start-up) and by the token shape Kite uses. Fail closed: if formatting the record
   raises, emit the redaction marker, never the raw args.
2. **ApiModel closed.** In `__pydantic_init_subclass__` refuse a subclass that defines `model_construct`, any
   `computed_field` or any `field_serializer`/`model_serializer`; `model_construct` called on any ApiModel raises.
   `_serialize` fails closed on any value that is not `CatalogueText` or a typed slot.
3. **Drop the exception-flow scan as a guarantee.** The boundary already hides exception text (round 9). `UserText`
   can be created only by the request-parsing layer from a request field, never from an exception: make its
   constructor private to that layer (module-level factory; a direct call raises) and test that `UserText(str(e))`
   from any other module raises. Keep the scan only as a second layer if it still passes; do not extend it.
4. **Identifier tightened and SlotType pinned.** `Identifier` accepts only a short closed pattern (no `:`, no `=`, no
   whitespace, max length stated in the code) so `access_token:...` is refused; a test pins the exact set of
   `SlotType` subclasses so a new one fails until reviewed.

## Standing items (run-discipline B4) and reviewer checklist
- (c) every guard fails closed on shapes it cannot resolve; name each guard by the structural door, not by a word list.
- Mutation tests first, one per guard: remove the record-factory hook; let one child logger bypass it; allow
  `computed_field`; let `_serialize` pass a plain `str`; allow `UserText` from an exception; allow `:` in
  `Identifier`. Each must turn a test red; list them in the report.
- No new detector (word list, shape scan, call-site list) as a guarantee - B8.
- Kit CI stays green: tests/ imports no ofo_app; app tests in tests_app/; no wall-clock asserts.

## Rules
- Do not edit kit files or spec/. Never write `evidence/`. Never mark anything verified. Targeted tests while
  building; the full domain and app suites once at the end (summary lines only, output to a log file). Run
  `python tools/ci_local.py` once before the push. Commit, push, report.
