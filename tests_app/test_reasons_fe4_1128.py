"""Lane FE4 (28 Nov 2026), review finding N2: the reader's sentence must follow what the worker published.

Real case, 28 Nov, the owner's PC, market closed: every running trade read "the worker does not list this trade".
Lane FE3 made the worker publish ``market_closed``; the route then still worded only ``e.reason``, so the monitor's
``why`` codes (``index_not_live``, ``leg_not_live``, ``exit_not_priced``, ``index_exits_not_run``,
``exits_not_checked_yet``, ``book_not_read``, ``exit_not_applicable``) all read "The last price is too old". One
function, ``monitoring_state.sentence_code``, names the catalogue key for an entry; every code the worker or monitor
publishes reaches the reader unchanged, and an unknown one reads ``unknown`` (never blank, never another reason's).
Spec basis: REQ-115 AC-4 (the pause names its true reason), REQ-049, ADR-330 (44), (64).
"""
from __future__ import annotations

import datetime

import pytest
from ofo.errors.explanations import EXPLANATIONS
from ofo_app import monitoring_state as ms
from ofo_app.background import PriceState
from test_background_cycle import FIRST_ID, Calls, Prov, _watched, _worker, scn  # noqa: F401
from test_monitoring_state import _Client, _fresh

NOW = datetime.datetime(2026, 11, 27, 9, 30, tzinfo=datetime.UTC)


async def test_core_the_worker_publishes_market_closed_and_the_reader_carries_it(scn):  # noqa: F811
    client, prov, now = _Client(), Prov(scn), [scn.clock_at]
    prov.closed = True
    w = _worker(prov, _watched(scn), now, Calls(), settings=None, want_client=client)

    async def no_wants(*_a, **_k):
        return None
    w._write_wants = no_wants
    await w.cycle()
    await ms.ExitsPublisher(client, "m").publish([], {}, now[0])
    got = (await ms.read_states(client, [FIRST_ID], now[0], heartbeat=_fresh))[FIRST_ID]
    assert (got.status, got.reason) == (ms.PAUSED, "market_closed"), got
    assert ms.sentence_code(got) == "market_closed"


_REASONS = [s.value for s in PriceState if s is not PriceState.FRESH]
_REASONS += [ms.WORKERS_DOWN, ms.STATE_UNREADABLE, ms.NOT_LISTED]
_WHYS = [ms.INDEX_NOT_LIVE, ms.LEG_NOT_LIVE, ms.EXIT_NOT_PRICED, ms.INDEX_EXITS_NOT_RUN, ms.EXITS_NOT_CHECKED_YET,
         ms.BOOK_NOT_READ, ms.EXIT_NOT_APPLICABLE]


@pytest.mark.parametrize("reason", _REASONS)
def test_every_reason_the_worker_publishes_is_carried_through_the_snapshot_unchanged(reason):
    entry = ms.Entry(1, ms.PAUSED, reason, "", NOW)
    got = ms.decode(ms.encode([entry], NOW), NOW)[1]
    assert got.reason == reason
    assert ms.sentence_code(got) == reason
    assert f"monitoring_why_{reason}" in EXPLANATIONS


@pytest.mark.parametrize("why", _WHYS)
def test_every_why_the_monitor_publishes_is_carried_and_wins_over_the_generic_stale_reason(why):
    entry = ms.Entry(1, ms.PAUSED, "stale", why, NOW)
    got = ms.decode(ms.encode([entry], NOW), NOW)[1]
    assert (got.reason, got.why) == ("stale", why)
    assert ms.sentence_code(got) == why
    assert f"monitoring_why_{why}" in EXPLANATIONS


@pytest.mark.parametrize(("reason", "why", "want"), [
    ("stale", "", "stale"),  # no why: the reason's own sentence
    ("stale", "rest_stale", "stale"),  # the worker's own free-text why is not a sentence key: the reason stands
    ("stale", "no such code", "stale"),
    ("future_reason", "", "unknown"),  # a code nobody wrote a sentence for: plain fallback
    ("", "", "unknown"),  # never blank
    ("Stale", "", "unknown"),  # not a catalogue key (case)
    ("../x", "also bad", "unknown"),
])
def test_an_unknown_reason_or_why_gives_the_plain_fallback_never_a_blank_or_another_reason(reason, why, want):
    assert ms.sentence_code(ms.Entry(1, ms.PAUSED, reason, why, None)) == want


def test_every_code_sentence_sentence_key_exists_in_the_catalogue():
    for code in set(_REASONS) | set(_WHYS) | {"unknown"}:
        assert f"monitoring_why_{code}" in EXPLANATIONS, code


def test_every_why_sentence_in_the_catalogue_is_known_to_sentence_code():
    """Review F4: a new ``monitoring_why_*`` sentence nobody listed would fall back to the generic reason."""
    known = ms.SENTENCE_WHYS | ms.SENTENCE_REASONS | {"unknown"}
    for key in EXPLANATIONS:
        if key.startswith("monitoring_why_"):
            assert key.removeprefix("monitoring_why_") in known, key
