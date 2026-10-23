---
work_item: W-132
ac: AC-3
requirement: REQ-117
ac_fp: "549c38fbb072"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 2 on 23eee95b)"
builder: "builder (Sonnet, builder sequence row 4: build, finish, fix round 1)"
date: '2026-10-22'
commands: "round 2: plants.py (19 round-1 shapes + new), classify.py on all 184 allow-list entries, strip_check2.py; pytest tests/test_no_broker_name_in_feature_code.py; vitest broker-capabilities, margin-line-flag-wire, outcome-margin (35 passed)"
---

AC: AC-3
result: pass
commands: round 2: plants.py (19 round-1 shapes + new), classify.py on all 184 allow-list entries, strip_check2.py; pytest tests/test_no_broker_name_in_feature_code.py; vitest broker-capabilities, margin-line-flag-wire, outcome-margin (35 passed)
observed: repo-test part: the scan is an allow-list (any broker word in feature code is a finding unless its file + line text is a reasoned entry in tests/broker_name_allowlist.py); real tree 0 findings; all 19 round-1 bypasses red; data layer green; stale and reasonless entries red; none of the 184 entries is a comparison, branch, isinstance or condition on a broker; the status query moved to broker_token_store.active_session_status; the one real consumer (builder margin line) is hidden with 'Margin from the broker is not available for this account.' when basket_margin_quote is off. Feature part for REQ-100/102/103: deferred, those features are not built (they bind their flags when built)
attack: MINOR gaps (deferred issue): 5 allow-listed lookups keyed on ZERODHA (execute.py:418,528,638; execution_return.py:237; outcome/service.py:212); JS comment stripping can blank code when a comment opener sits inside a string; row['broker']==x, bytes literals, JS escape sequences and .cjs/.mts/.cts/.json/.html/.sql files not scanned; reasons are per file, not per entry. No real case in the tree

Recorded by the orchestrator from the verifier's returned block.
