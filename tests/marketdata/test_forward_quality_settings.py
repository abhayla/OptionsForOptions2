# ruff: noqa: E501, PLR2004
"""GC-SET forward step (REQ-167 AC-4, AC-5 Pricing group): the forward's three quality settings are read per request,
and a changed value can never be served from a cache entry computed with the old value.

Spec basis: REQ-167 AC-5 "forward quality width, strikes near, minimum strikes"; AC-4 "each wired calculation reads the
value in force when it runs"; ADR-061 (the method), ADR-053 (the shared compute-cache key); ADR-222 (1).
Core proof (real 2026-10-08 recording): the same chain gives a different quality figure at width 5% vs 2%, and two
reads of one feed snapshot with different settings make two cache entries (never a shared one).
"""
import datetime
from collections import Counter
from decimal import Decimal

import ofo.outcome.snapshot as snapshot_module
import pytest
from _kite_fixture import all_instrument_ids, new_provider, replay
from ofo.marketdata.forward import PARITY, SPOT_FALLBACK, ForwardQuality, parity_forward
from ofo.marketdata.kite_provider import IST
from ofo.marketdata.shared_compute import FeedScope, SharedCompute
from ofo.outcome import read_snapshot
from ofo.settings import calc, defaults, registry

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = Decimal("0.065")
EXPIRY = datetime.date(2026, 10, 13)
STRADDLE = ("NSE_FO:44614", "NSE_FO:44615")
KEYS = (calc.FORWARD_QUALITY_WIDTH, calc.FORWARD_STRIKES_NEAR, calc.FORWARD_MIN_STRIKES)


def _with(**changes) -> dict[str, Decimal]:
    values = defaults()
    for key, value in changes.items():
        assert key in values, key
        values[key] = Decimal(value)
    return values


@pytest.fixture(scope="module")
def feed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    return provider, replay(provider, clock)


def _forward(provider, quality):
    return parity_forward(provider.option_chain_snapshot("NIFTY", EXPIRY), provider.underlying_quote("NIFTY"), EXPIRY,
                          VALUATION, RATE, quality)


def test_defaults_are_exactly_the_values_the_code_had():
    assert (defaults()[calc.FORWARD_QUALITY_WIDTH], defaults()[calc.FORWARD_STRIKES_NEAR],
            defaults()[calc.FORWARD_MIN_STRIKES]) == (Decimal("0.05"), Decimal(21), Decimal(3))
    assert calc.forward_quality(defaults()) == ForwardQuality(Decimal("0.05"), 21, 3)
    assert all(registry()[k].group == "Pricing" for k in KEYS)


def test_core_width_5_percent_vs_2_percent_gives_a_different_quality_answer(feed):
    """Core: the same real SENSEX 15-Oct chain, one setting changed (width): the quality figure differs (a narrower
    width keeps fewer strikes, so a smaller spread: 9.98 at 5%, 4.13 at 2%, measured on the recording), while the
    forward itself is unchanged (the width never moves F)."""
    provider, _ = feed
    expiry = datetime.date(2026, 10, 15)

    def at(width):
        return parity_forward(provider.option_chain_snapshot("SENSEX", expiry), provider.underlying_quote("SENSEX"),
                              expiry, VALUATION, RATE, calc.forward_quality(_with(**{calc.FORWARD_QUALITY_WIDTH: width})))

    wide, narrow = at("0.05"), at("0.02")
    assert (wide.quality_spread, narrow.quality_spread) == (Decimal("9.98"), Decimal("4.13"))
    assert wide.forward == narrow.forward and wide.strikes_used == narrow.strikes_used


def test_setting_forward_quality_width_changes_quality_figure_on_a_tight_value(feed):
    """A width so tight that no strike passes: no quality figure at all (None), not the default's figure."""
    provider, _ = feed
    assert _forward(provider, calc.forward_quality(defaults())).quality_spread is not None
    assert _forward(provider, calc.forward_quality(_with(**{calc.FORWARD_QUALITY_WIDTH: "0.001"}))).quality_spread is None


def test_setting_forward_strikes_near_changes_the_strikes_read(feed):
    provider, _ = feed
    default = _forward(provider, calc.forward_quality(defaults()))
    few = _forward(provider, calc.forward_quality(_with(**{calc.FORWARD_STRIKES_NEAR: "5"})))
    assert default.strikes_considered == 21 and few.strikes_considered == 5
    assert few.strikes_used < default.strikes_used and few.source == PARITY


def test_setting_forward_min_strikes_changes_when_the_forward_falls_back_to_spot(feed):
    provider, _ = feed
    default = _forward(provider, calc.forward_quality(defaults()))
    assert default.source == PARITY and default.strikes_used >= 3
    strict = _forward(provider, calc.forward_quality(_with(**{calc.FORWARD_MIN_STRIKES: str(default.strikes_used + 1)})))
    assert strict.source == SPOT_FALLBACK and strict.label is not None and strict.strikes_used == default.strikes_used


def test_parity_forward_has_no_fallback_for_the_quality_parameter(feed):
    provider, _ = feed
    chain, spot = provider.option_chain_snapshot("NIFTY", EXPIRY), provider.underlying_quote("NIFTY")
    with pytest.raises(TypeError):
        parity_forward(chain, spot, EXPIRY, VALUATION, RATE)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="ForwardQuality"):
        parity_forward(chain, spot, EXPIRY, VALUATION, RATE, defaults())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="ForwardQuality"):
        parity_forward(chain, spot, EXPIRY, VALUATION, RATE, None)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [
    {"width": Decimal(0), "strikes_near": 21, "min_strikes": 3}, {"width": 0.05, "strikes_near": 21, "min_strikes": 3},
    {"width": Decimal("0.05"), "strikes_near": 0, "min_strikes": 3}, {"width": Decimal("0.05"), "strikes_near": 21, "min_strikes": True},
    {"width": Decimal("0.05"), "strikes_near": 21.0, "min_strikes": 3},
])
def test_forward_quality_refuses_a_value_the_method_cannot_use(bad):
    with pytest.raises(ValueError):
        ForwardQuality(**bad)


def test_the_value_read_from_a_mapping_missing_a_key_is_an_error_not_a_default():
    values = defaults()
    del values[calc.FORWARD_MIN_STRIKES]
    with pytest.raises(KeyError):
        calc.forward_quality(values)


def _counting(monkeypatch):
    calls: Counter = Counter()
    real = snapshot_module.parity_forward

    def counted(chain, spot, expiry, valuation, rate, quality):  # noqa: PLR0913
        calls[(expiry, quality)] += 1
        return real(chain, spot, expiry, valuation, rate, quality)

    monkeypatch.setattr(snapshot_module, "parity_forward", counted)
    return calls


def test_core_cache_two_reads_with_different_settings_make_two_entries_never_a_shared_one(feed, monkeypatch):
    """Core: ONE feed snapshot, ONE shared cache; read with the default settings, then with strikes-near 5. The second
    read computes its own forward (it is not served the first one), the answers differ, and each setting then reads back
    from its own entry (no further compute)."""
    provider, at = feed
    calls = _counting(monkeypatch)
    scope = FeedScope(SharedCompute(), "user-1")
    default_q, near5_q = calc.forward_quality(defaults()), calc.forward_quality(_with(**{calc.FORWARD_STRIKES_NEAR: "5"}))
    first = read_snapshot(provider, "NIFTY", list(STRADDLE), at, RATE, scope, quality=default_q)
    second = read_snapshot(provider, "NIFTY", list(STRADDLE), at, RATE, scope, quality=near5_q)
    assert first.forwards[EXPIRY].strikes_considered == 21 and second.forwards[EXPIRY].strikes_considered == 5
    assert calls[(EXPIRY, default_q)] == 1 and calls[(EXPIRY, near5_q)] == 1
    read_snapshot(provider, "NIFTY", list(STRADDLE), at, RATE, scope, quality=default_q)
    read_snapshot(provider, "NIFTY", list(STRADDLE), at, RATE, scope, quality=near5_q)
    assert calls[(EXPIRY, default_q)] == 1 and calls[(EXPIRY, near5_q)] == 1  # each setting reads its own entry


@pytest.mark.parametrize("key,value", [(calc.FORWARD_QUALITY_WIDTH, "0.02"), (calc.FORWARD_STRIKES_NEAR, "9"),
                                       (calc.FORWARD_MIN_STRIKES, "4")])
def test_each_forward_key_is_part_of_the_cache_key(feed, monkeypatch, key, value):
    """One test per key: changing only that key never reads the entry made with the old value."""
    provider, at = feed
    calls = _counting(monkeypatch)
    scope = FeedScope(SharedCompute(), "user-1")
    old, new = calc.forward_quality(defaults()), calc.forward_quality(_with(**{key: value}))
    assert old != new
    read_snapshot(provider, "NIFTY", list(STRADDLE), at, RATE, scope, quality=old)
    read_snapshot(provider, "NIFTY", list(STRADDLE), at, RATE, scope, quality=new)
    assert calls[(EXPIRY, old)] == 1 and calls[(EXPIRY, new)] == 1


def test_read_snapshot_requires_the_quality_keyword(feed):
    provider, at = feed
    with pytest.raises(TypeError):
        read_snapshot(provider, "NIFTY", list(STRADDLE), at, RATE)  # type: ignore[call-arg]
