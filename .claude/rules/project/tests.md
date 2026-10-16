---
paths:
  - "tests/**"
  - "tests_app/**"
  - "frontend/tests/**"
  - "frontend/e2e/**"
---
# Scope: path-scoped (tests)

# Tests (REQ-075, ADR-093)

- Write the failing test first, on the real function; for a guard, show a mutation makes it fail.
- Run only the files you touched locally (`-q`, output to a log file, read the tail); the full suites run once per
  pull request in CI - never per edit.
- No wall-clock asserts (`tests/test_no_wall_clock_asserts.py`); pass dates in.
- Real Kite data only through recorded fixtures (`tests/fixtures/kite_ws/`, `tests/fixtures/kite_history/`); never a
  shape typed from memory.
- Assert exact values (rendered text, Decimal amounts), not just "no error".
- Playwright: locate by role, label or test id; never `waitForTimeout`.
