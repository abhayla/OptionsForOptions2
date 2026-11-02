"""#583 I-12: a futures leg no longer marks live numbers as disconnected.

RCA: issue #206's streaming rule needs every leg of a REST read held by a socket on the shared fan-out. A FUT leg that
no strategy socket carried had no holder, so the whole read fell to FROM_ENTRIES under REQ-049 AC-5's "Live market data
disconnected" label although the feed was connected. Fix: leg-edit holds the request's FUT legs itself (same ONE
fan-out). DB-free: the recorded 2026-10-08 replay (its frames carry options only, so the future is listed, unquoted).

Futures-quote answer states: quoted -> live number; held and not yet ticked -> that leg's own no-quote label, state
COMPUTED, never the feed label; not held by anyone -> the old FROM_ENTRIES (the failure this fixes, kept as a test);
feed really down (session ended) -> from-entries with the feed label; provider refuses the id -> nothing held.
"""
from __future__ import annotations

import dataclasses

import pytest
from ofo.marketdata.fanout import FanOut
from ofo.settings import defaults
from ofo_app.live_push import LiveFeed
from ofo_app.routes import leg_edit
from ofo_app.routes.outcome import MarketContext, OutcomeRequest, outcome_response
from test_outcome_route import CONDOR, RATE, VALUATION, provider_with_nifty_futures

DISCONNECTED = "Live market data disconnected"


@pytest.fixture(autouse=True)
def _release():
    yield
    leg_edit.FUTURES_LEASE.release()


def _body(provider, futures):
    fut = futures[1].contract  # NIFTY 27 Oct 2026 future (listed, no recorded quote)
    fut_id = f"{fut.exchange_segment}:{fut.exchange_token}"
    legs = [{"instrument_id": iid, "action": action, "lots": 1,
             "planned_entry": f"{provider.book.get(iid, VALUATION).ltp:f}", "captured_at": VALUATION.isoformat()}
            for iid, action in CONDOR]
    legs.append({"instrument_id": fut_id, "action": "BUY", "lots": 1, "planned_entry": "23350.00",
                 "captured_at": VALUATION.isoformat()})
    return fut_id, {"underlying": "NIFTY", "legs": legs}


def _read(provider, body, held):
    """The leg-edit outcome read with a streaming predicate that says only ``held`` ids have a socket holder."""
    ctx = MarketContext(provider, lambda: VALUATION, RATE)

    def streaming(instrument_id):
        return instrument_id in held or instrument_id == provider.index_id("NIFTY")
    streaming.ctx = ctx  # the replay predicate's shape: this context's feed owns the rule
    resp = outcome_response(OutcomeRequest.model_validate(body), ctx, streaming, settings=defaults())
    return resp.model_dump(mode="json")


def test_i12_core_a_held_future_with_the_condor_computes_live():
    provider, futures = provider_with_nifty_futures()
    fut_id, body = _body(provider, futures)
    out = _read(provider, body, held={iid for iid, _a in CONDOR} | {fut_id})
    assert out["state"] == "COMPUTED"
    assert DISCONNECTED not in str(out["status_label"])


def test_i12_a_held_but_unticked_future_names_its_own_missing_price_not_the_feed():
    provider, futures = provider_with_nifty_futures()
    fut_id, body = _body(provider, futures)
    out = _read(provider, body, held={iid for iid, _a in CONDOR} | {fut_id})
    leg = next(x for x in out["legs"] if x["instrument_id"] == fut_id)
    assert leg["ltp"] is None and leg["label"] and DISCONNECTED not in leg["label"]  # that leg's own missing price
    assert DISCONNECTED not in str(out["status_label"])


def test_i12_a_future_nobody_holds_is_the_old_not_live_answer_which_is_why_the_route_must_hold_it():
    provider, futures = provider_with_nifty_futures()
    _fut_id, body = _body(provider, futures)
    out = _read(provider, body, held={iid for iid, _a in CONDOR})
    assert out["state"] == "FROM_ENTRIES"


class _Vendor:
    def __init__(self, listed) -> None:
        self.listed, self.subscribed = listed, set()

    def live_quote_stream(self, listener) -> None:
        self._listener = listener

    def subscribe(self, ids) -> None:
        if any(i not in self.listed for i in ids):
            raise KeyError("unknown")
        self.subscribed.update(ids)

    def unsubscribe(self, ids) -> None:
        self.subscribed.difference_update(ids)


async def test_i12_the_route_helper_holds_the_future_legs_and_only_them():
    provider = _Vendor({"NSE_FO:61471", "NSE_FO:39900"})
    feed = LiveFeed(MarketContext(provider, lambda: VALUATION, RATE), FanOut(provider))
    leg_edit.hold_future_legs(feed, "u1", "NIFTY", ["NSE_FO:61471"])
    assert feed.fanout.subscriber_count("NSE_FO:61471") == 1 and "NSE_FO:61471" in provider.subscribed
    assert feed.fanout.subscriber_count("NSE_FO:39900") == 0  # option legs follow the strategy socket
    leg_edit.hold_future_legs(feed, "u1", "NIFTY", [])  # the future left the strategy: the hold ends
    assert feed.fanout.subscriber_count("NSE_FO:61471") == 0
    leg_edit.hold_future_legs(None, "u1", "NIFTY", ["NSE_FO:61471"])  # no feed: nothing to hold, no error
    leg_edit.hold_future_legs(feed, "u1", "NIFTY", ["NSE_FO:99999"])  # not listed: held by no one, no error
    assert provider.subscribed == set()


def test_i12_a_session_that_ended_keeps_the_feed_label():
    provider, futures = provider_with_nifty_futures()
    _fut_id, body = _body(provider, futures)
    status = provider.status()
    ended = dataclasses.replace(status, session_ended=True) if dataclasses.is_dataclass(status) else None
    if ended is None:
        pytest.skip("status is not a dataclass")
    provider.status = lambda: ended  # type: ignore[method-assign]
    out = _read(provider, body, held=set())
    assert out["state"] == "FROM_ENTRIES"  # the feed really is down: not COMPUTED
