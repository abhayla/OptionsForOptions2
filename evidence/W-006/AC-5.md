---
work_item: W-006
ac: AC-5
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/instruments/test_sources.py; python - (validate_source attacks); grep -rni 'limit.only|LIMIT' backend/"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/instruments/test_sources.py; python - (validate_source attacks); grep -rni 'limit.only|LIMIT' backend/
observed: 5 passed; REJECT 2026-99-99, 2026-02-30, empty date, http://, ftp://, empty url, datetime string; KeyError for unregistered rule; no limit-only hard-coding
attack: bad dates and non-https URLs rejected. Residual (deferred): a bare 'https://' with no host is accepted; no Zerodha-domain or date-age check. The only registered rule is correctly cited.

Recorded by the orchestrator from the verifier's returned block.
