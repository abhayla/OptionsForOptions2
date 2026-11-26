"""D-01 reproduction (read-only, fakes + the recorded 2026-10-08 Kite frames; no DB, no network).

The API process's KiteProvider books a tick only for tokens THIS process holds (kite_provider.py on_frame: a token not
in _wanted is dropped). _already_crossed reads the index WITHOUT holding it. So the guard's answer depends on whether
some other consumer in the same process (the paper monitor's watch, a screen's push) happens to hold the index.
"""
import asyncio
import os
import sys
from decimal import Decimal

REPO = r"D:\Abhay\Ventures\OptionsForOptions2"
sys.path[:0] = [os.path.join(REPO, "backend"), os.path.join(REPO, "tests", "marketdata")]
os.environ.setdefault("APP_ENV", "test")

from _kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402

from ofo_app import paper_trigger_store, tracked_contracts  # noqa: E402
from ofo_app.routes import paper as paper_routes  # noqa: E402
from ofo_app.routes.outcome import MarketContext  # noqa: E402


async def _no_db_resolve(db, ids):
    assert not ids, "conditional exit only: no contract to resolve"
    return ()


tracked_contracts.resolve = _no_db_resolve  # the guard's only DB touch; empty for a conditional exit


def run(hold_index: bool, hold_legs: bool):
    provider, clock, items = new_provider()
    ids = all_instrument_ids(items)
    index_id = provider.index_id("NIFTY")
    legs = [i for i in ids if i.startswith("NSE_FO:")]
    if hold_index:
        provider.subscribe([index_id])
    if hold_legs:
        provider.subscribe(legs)
    replay(provider, clock)
    ctx = MarketContext(provider, clock, Decimal("0.065"))
    spot = provider.underlying_quote("NIFTY")
    level = Decimal("22500")  # NIFTY in the recording ends at 22533.25: "above 22500" is ALREADY crossed
    new = [paper_trigger_store.NewTrigger("conditional_exit", "above", level, underlying="NIFTY")]
    code = asyncio.run(paper_routes._already_crossed(None, ctx, "NIFTY", new))
    print(f"hold_index={hold_index!s:5} hold_legs={hold_legs!s:5} spot={None if spot is None else spot.ltp} "
          f"unwanted_tick={provider.counters['unwanted_tick']:5} -> guard={code!r}")
    return code


if __name__ == "__main__":
    a = run(hold_index=False, hold_legs=False)  # 15:02: fresh API, nothing holds NIFTY in this process
    b = run(hold_index=False, hold_legs=True)   # a screen holds the legs, not the index (12:53 leg-stop alert case)
    c = run(hold_index=True, hold_legs=False)   # 15:11: something (monitor watch / push) holds NIFTY
    assert a is None and b is None and c == "paper_trigger_already_crossed", (a, b, c)
    print("REPRODUCED: same price, same level; the save is accepted unless another consumer holds the index")
