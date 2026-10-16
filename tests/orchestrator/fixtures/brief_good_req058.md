# Good brief
Rule: REQ-058 AC-6 "V1 never resubmits a failed order automatically; the failure is shown with its reason and the
user chooses the next action" (Q193).
Tests: `python -m pytest -q tests/test_*.py tests/errors/test_write_allowlist.py`
