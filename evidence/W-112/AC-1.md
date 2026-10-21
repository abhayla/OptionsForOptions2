---
work_item: W-112
ac: AC-1
requirement: REQ-052
ac_fp: "03e21357672e"
result: pass
verified_by: "verifier (sonnet, fresh context, GC-2g)"
builder: "builder (sonnet, GC-2g)"
date: '2026-10-18'
commands: "git rev-parse --short HEAD (9d03dd3); python -m pytest -q -p no:cacheprovider -p no:metadata tests/test_history_not_shown.py; python -m pytest -q -p no:cacheprovider -p no:metadata -c pytest-app.ini tests_app/test_kite_history.py; loose grep history|candle|ohlc|historical|intraday over backend/ofo_app/routes and frontend/src; grep of history-module importers over backend; python -c calls of import_hits() and frontend_hits() on hostile strings"
---

AC: AC-1
result: pass
commands: git rev-parse --short HEAD (9d03dd3); python -m pytest -q -p no:cacheprovider -p no:metadata tests/test_history_not_shown.py; python -m pytest -q -p no:cacheprovider -p no:metadata -c pytest-app.ini tests_app/test_kite_history.py; loose grep history|candle|ohlc|historical|intraday over backend/ofo_app/routes and frontend/src; grep of history-module importers over backend; python -c calls of import_hits() and frontend_hits() on hostile strings
observed: tests/test_history_not_shown.py: 6 passed in 0.96s. tests_app/test_kite_history.py: 4 passed in 1.08s (no database fixture). The diff adds only tests/test_history_not_shown.py and work/W-112.md. Nine backend files name a history module, all allow-listed or naming it only in a comment/string (ofo/broker/egress.py:6, ofo/broker/kite_endpoints.py:25). None of the nine routers registered in main.py imports a history module. ofo/marketdata/kite_provider.py:234-235 historical() raises NotSupported ('historical data is not offered in V1') and nothing calls .historical(.
attack: (1) Loose grep of routes and frontend/src: hits are GET /strategies/{id}/history (strategy activity log, W-061), local `history` variables of stored plans, vue-router createWebHistory, and nav labels 'Execution history' / alert History - none is market data. (2) Caught: from .. import kite_history, importlib.import_module('ofo_app.kite_history'), __import__('ofo_app.kite_history'), import ofo_app.history_store, from ofo import history, non-literal import_module args. Not caught (MINOR, deferred): from importlib import import_module as im; import_module('.kite_history', package='ofo_app'); __import__('ofo_app', fromlist=[...]); getattr(importlib,'import_module'); runpy.run_module. (3) Frontend scan covers .js .ts .vue .mjs .jsx .tsx with single, double and backtick quotes; caught `${base}/ohlc`, a Vue :url binding, imports of '@/api/candles', dynamic import; not caught (MINOR, deferred): '/api/' + 'history', api.get('candles'), '/api/intraday'. No current file uses a missed shape. (4) Self-tests in the file (planted routes in every import shape, the allow-list check, planted pages) pass.

Recorded by the orchestrator from the verifier's returned block.
