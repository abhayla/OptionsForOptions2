"""safety_set.py: the files whose change makes a brief Tier A (ADR-178 safety set; builder-brief.md "Safety set").

One home: make_brief.py imports from here. Moved verbatim from the retired measure_process.py (ADR-189).
"""
from __future__ import annotations

SAFETY_SET = (  # the files whose change makes a checker Opus (ADR-178; builder-brief.md "Safety set"); matched as a
    # path tail, so `ofo/broker/kite_http.py` in a brief counts like `backend/ofo/broker/kite_http.py`
    # (briefs name files as `outcome/service.py` or `kite_ws.py`, so the tails are module-level)
    "engine/", "scenario/", "table/", "outcome/", "marketdata/", "feed_", "feed/", "kite_ws", "broker/", "kite_",
    "routes/auth", "broker_sessions", "orders/", "execution/", "reconciliation/", "alembic/", "scripts/hooks/",
)


def names_safety_file(text: str) -> bool:
    return any(p in text.replace("\\", "/") for p in SAFETY_SET)
