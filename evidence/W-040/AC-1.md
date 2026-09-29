---
work_item: W-040
ac: AC-1
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "Round 1 (2e141fe): python -m pytest -q -p no:cacheprovider tests/orchestrator/test_check_brief.py; ~25 crafted briefs through scripts/orchestrator/check_brief.py [--strict]; full suite. Round 2 (6bd0932): python -m pytest -q -p no:cacheprovider tests/orchestrator; check_brief.py [--strict] on crafted briefs b/1..b/10; python -m pytest -q -p no:cacheprovider"
---

AC: AC-1
result: pass
commands: Round 1 (2e141fe): python -m pytest -q -p no:cacheprovider tests/orchestrator/test_check_brief.py; ~25 crafted briefs through scripts/orchestrator/check_brief.py [--strict]; full suite. Round 2 (6bd0932): python -m pytest -q -p no:cacheprovider tests/orchestrator; check_brief.py [--strict] on crafted briefs b/1..b/10; python -m pytest -q -p no:cacheprovider
observed: Round 1: 9 passed; 1304 passed; exact REQ-058 AC-6, REQ-056 AC-10, REQ-035 AC-7 and ADR-003 quotes exit 0; one-word change, wrong AC, REQ-999, AC-99, fake ADR text exit 1; found false-FAIL for 'REQ-058 AC-6 (Q193): ...' and for Q-id quotes whose text lives in an ADR; weak passes for 1-char and reversed '...' quotes. Round 2: 13 passed; 1330 passed; REQ-058 AC-6 (Q193) quote OK; Q230 quote from ADR-003 OK; 'a' TOO-SHORT (exit 0; exit 1 with --strict); reversed '...' FAIL; one-word change FAIL.
attack: Remaining limits (recorded): a Q-id-cited quote passes if its text appears anywhere in a file that mentions the id (catches invented text, not text misattributed within the same ADR); quotes containing inner quote characters are split and FAIL; paraphrases without quotes are invisible.

Recorded by the orchestrator from the verifier's returned block.
