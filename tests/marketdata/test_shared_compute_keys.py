"""#519 / REQ-050 AC-3: a shared figure's cache key is built FROM the engine call, so it cannot drift from what the
engine reads.

Part 1, the helper: the one normaliser's answer states (kept, reduced, None, empty tuple, refused), the function
identity in the key, the refused callables, and "the function is called with exactly the keyed arguments".
Part 2, the second layer on the real 2026-10-08 recording: each engine function's inputs are changed ONE at a time at
the same snapshot instant; every change recomputes the figure (a new key) and the figure equals an unshared direct call.
"""
import dataclasses
import datetime
import functools
from decimal import Decimal

import ofo.outcome.snapshot as snapshot_module
import pytest
from _kite_fixture import all_instrument_ids, new_provider, replay
from ofo.engine.legs import Instrument
from ofo.engine.model import expiry_model
from ofo.marketdata.forward import ForwardUnavailable
from ofo.marketdata.shared_compute import FeedScope, SharedCompute, call_shared, function_identity, key_part
from ofo.outcome import read_snapshot, service
from ofo.rules.inputs import DataHealth
from ofo.scenario.spot import spot_reading
from ofo.settings import calc as settings_calc
from ofo.settings import defaults as settings_defaults

RATE = Decimal("0.065")
CE, PE = "NSE_FO:44614", "NSE_FO:44615"  # the 22550 CE and PE of the 2026-10-13 expiry
EXPIRY = datetime.date(2026, 10, 13)
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 8, 9, 20, tzinfo=IST)
SCOPE = ("NIFTY", EXPIRY, T0, "X")


@dataclasses.dataclass(frozen=True)
class Point:
    x: Decimal
    hidden: Decimal = dataclasses.field(default=Decimal(0), compare=False)


QUALITY = settings_calc.forward_quality(settings_defaults())  # the registry's forward settings, passed explicitly

def add(a, b, c=Decimal(1)):
    return a + b + c


def other_add(a, b, c=Decimal(1)):
    return a + b + c


RECEIVED = []


def record(*args, **kwargs):
    RECEIVED.append((args, kwargs))
    return len(RECEIVED)


FAILS = []


def fails(a):
    FAILS.append(a)
    raise ValueError("no answer")


# ---- part 1: the normaliser's answer states ------------------------------------------------------------------

def test_a_plain_value_is_kept_exactly_and_tagged_with_its_type():
    assert key_part(Decimal("1.0")) != key_part(Decimal("1.00"))  # exact: the exponent is part of the key
    assert key_part(True) != key_part(1) != key_part(Decimal(1))  # equal values of other types are other keys
    assert key_part("CE") == key_part("CE") and key_part(Instrument.CE) != key_part("CE")
    later = T0.astimezone(datetime.UTC)
    assert later == T0 and key_part(later) != key_part(T0)  # the same instant in another zone is another key
    hash(key_part(T0))


def test_none_is_kept_as_none():
    assert key_part(None) == ("builtins.NoneType", None)
    assert key_part((None,)) != key_part(())


def test_the_empty_tuple_is_kept():
    assert key_part(()) == ("builtins.tuple", ())


def test_a_dataclass_is_reduced_to_every_field_by_name_even_one_left_out_of_equality():
    a, b = Point(Decimal(1)), Point(Decimal(1), hidden=Decimal(9))
    assert a == b  # the dataclass's own equality ignores ``hidden``
    assert key_part(a) != key_part(b)  # the key does not
    assert key_part(Point(Decimal(1))) == key_part(a)
    assert key_part(Point(Decimal(2))) != key_part(a)


def test_a_slots_only_engine_value_is_reduced_to_every_slot(recorded):
    snap = recorded
    em = expiry_model(spot_reading(snap.spot), snap.forwards[EXPIRY], underlying="NIFTY")
    again = expiry_model(spot_reading(snap.spot), snap.forwards[EXPIRY], underlying="NIFTY")
    assert em is not again and key_part(em) == key_part(again)  # by value, never by identity
    moved = expiry_model(spot_reading(snap.spot), dataclasses.replace(snap.forwards[EXPIRY], years=Decimal("0.01")),
                         underlying="NIFTY")
    assert key_part(moved) != key_part(em)


@pytest.mark.parametrize("bad", [[1], {"a": 1}, {1}, object(), len, lambda: 1, b"x", frozenset({1})],
                         ids=["list", "dict", "set", "identity-hashed object", "builtin", "lambda", "unlisted hashable",
                              "frozenset"])
def test_anything_the_normaliser_cannot_reduce_is_refused_never_dropped(bad):
    with pytest.raises(TypeError, match="cannot be reduced"):
        key_part(bad)
    with pytest.raises(TypeError, match="cannot be reduced"):
        key_part((Decimal(1), bad))  # nested too
    with pytest.raises(TypeError):
        FeedScope(SharedCompute(), "user-1").call(SCOPE, add, Decimal(1), bad)


# ---- part 1: the call ---------------------------------------------------------------------------------------

def test_the_function_identity_is_in_the_key_so_one_name_never_serves_two_functions():
    cache = FeedScope(SharedCompute(), "user-1")
    assert cache.call(SCOPE, add, Decimal(1), Decimal(2)) == cache.call(SCOPE, other_add, Decimal(1), Decimal(2))
    assert cache.cache.computations == len((add, other_add))  # same arguments, two functions: two entries
    assert {k.figure for k in cache.cache._slots} == {f"{__name__}.add", f"{__name__}.other_add"}


def test_the_function_is_called_with_exactly_the_keyed_arguments():
    cache = FeedScope(SharedCompute(), "user-1")
    assert cache.call(SCOPE, add, Decimal(1), Decimal(2)) == Decimal(4)
    assert cache.call(SCOPE, add, Decimal(1), Decimal(2), Decimal(5)) == Decimal(8)  # one more argument: recomputed
    RECEIVED.clear()
    cache.call(SCOPE, record, Decimal(1), (Decimal(2), None))
    assert [((Decimal(1), (Decimal(2), None)), {})] == RECEIVED
    cache.call(SCOPE, record, Decimal(1), (Decimal(2), None))
    assert len(RECEIVED) == 1  # read back
    (key,) = [k for k in cache.cache._slots if k.figure.endswith(".record")]
    assert key.inputs == (key_part(Decimal(1)), key_part((Decimal(2), None)))  # every argument, in order


def test_a_keyword_argument_is_refused():
    with pytest.raises(TypeError):
        FeedScope(SharedCompute(), "user-1").call(SCOPE, add, Decimal(1), b=Decimal(2))


def test_the_gated_expiry_model_lists_every_slot(recorded):
    em = expiry_model(spot_reading(recorded.spot), recorded.forwards[EXPIRY], underlying="NIFTY")
    assert tuple(name for name, _ in em.key_fields()) == type(em).__slots__


def test_an_unshared_call_is_the_same_call():
    assert call_shared(None, SCOPE, add, Decimal(1), Decimal(2)) == Decimal(4)


def test_a_raised_error_is_never_cached_through_the_call():
    cache = FeedScope(SharedCompute(), "user-1")
    FAILS.clear()
    for _ in range(2):
        with pytest.raises(ValueError):
            cache.call(SCOPE, fails, Decimal(1))
    assert len(FAILS) == len(range(2)) and len(cache.cache) == 0


def _nested():
    def inner(a):
        return a
    return inner


def _closure(captured):
    def inner(a):
        return a + captured
    return inner


class _Holder:
    def method(self, a):
        return a


@pytest.mark.parametrize("fn", [lambda a: a, _nested(), _closure(Decimal(1)), functools.partial(add, Decimal(1)),
                                _Holder().method, _Holder, print],
                         ids=["lambda", "nested", "closure", "partial", "bound method", "class", "builtin"])
def test_a_callable_that_may_capture_inputs_outside_its_arguments_is_refused(fn):
    with pytest.raises(TypeError):
        function_identity(fn)
    with pytest.raises(TypeError):
        FeedScope(SharedCompute(), "user-1").call(SCOPE, fn, Decimal(1))


# ---- part 2: one input changed at a time, on the recorded snapshot --------------------------------------------

@pytest.fixture(scope="module")
def recorded():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    at = replay(provider, clock)
    return read_snapshot(provider, "NIFTY", [CE, PE], at, RATE, quality=QUALITY)


def _em(reading, fwd):
    return expiry_model(reading, fwd, underlying="NIFTY")


def _answer(fn, args):
    try:
        return ("value", fn(*args))
    except (ValueError, ArithmeticError, ForwardUnavailable) as exc:
        return ("raised", type(exc))


def _shared_answer(cache, fn, args):
    try:
        return ("value", cache.call(("NIFTY", EXPIRY, T0, None), fn, *args))
    except (ValueError, ArithmeticError, ForwardUnavailable) as exc:
        return ("raised", type(exc))


def _em_variants(snap):
    """Every ExpiryModel field the IV and Greeks engine calls read, moved one at a time (the level moves the forward's
    spot with it: the gate refuses a forward read on another spot)."""
    reading, fwd = spot_reading(snap.spot), snap.forwards[EXPIRY]
    level = reading.level + Decimal("25")
    return {
        "spot level": _em(dataclasses.replace(reading, level=level), dataclasses.replace(fwd, spot=level)),
        "forward": _em(reading, dataclasses.replace(fwd, forward=fwd.forward + Decimal("5"))),
        "implied yield / dividend yield": _em(reading, dataclasses.replace(fwd, implied_yield=Decimal("0.0123"))),
        "years": _em(reading, dataclasses.replace(fwd, years=fwd.years / 2)),
        "rate": _em(reading, dataclasses.replace(fwd, rate=Decimal("0.07"))),
        "days in year": _em(reading, dataclasses.replace(fwd, days_in_year=366)),
    }


def _iv_cases(snap):
    em = _em(spot_reading(snap.spot), snap.forwards[EXPIRY])
    q = snap.legs[CE].quote
    base = (em, Instrument.CE, service.iv_price(q), q.strike)
    cases = {"kind": (em, Instrument.PE, base[2], base[3]), "strike": (em, Instrument.CE, base[2], base[3] + 50),
             "price": (em, Instrument.CE, base[2] + Decimal("1.5"), base[3])}
    cases.update({name: (moved, *base[1:]) for name, moved in _em_variants(snap).items()})
    return base, cases


def _greek_cases(snap):
    em = _em(spot_reading(snap.spot), snap.forwards[EXPIRY])
    base = (em, Instrument.CE, Decimal("22550"), Decimal("0.12"))
    cases = {"kind": (em, Instrument.PE, *base[2:]), "strike": (em, Instrument.CE, Decimal("22600"), base[3]),
             "leg iv": (em, Instrument.CE, base[2], Decimal("0.13"))}
    cases.update({name: (moved, *base[1:]) for name, moved in _em_variants(snap).items()})
    return base, cases


def _forward_cases(snap):
    chain = tuple(sorted(snap.chains[EXPIRY], key=lambda q: q.instrument_id))
    spot = snap.spot
    base = (chain, spot, EXPIRY, snap.valuation, RATE, QUALITY)
    i = next(n for n, q in enumerate(chain) if q.instrument_id == CE)  # a quote the forward reads (nearest the money)

    def quote(**change):
        return ((*chain[:i], dataclasses.replace(chain[i], **change), *chain[i + 1:]), *base[1:])

    def with_spot(**change):
        return (chain, dataclasses.replace(spot, **change), *base[2:])

    q = chain[i]
    other = next(x for x in chain if x.instrument_id not in (CE, PE) and x.instrument_type is q.instrument_type)
    swapped = dataclasses.replace(q, instrument_id=other.instrument_id, instrument_type=other.instrument_type,
                                  expiry=other.expiry, strike=other.strike)  # only the contract differs
    return base, {
        "quote contract": ((*chain[:i], swapped, *chain[i + 1:]), *base[1:]),  # another contract, the same prices
        "quote bid": quote(bid=q.bid - Decimal("0.5")), "quote ask": quote(ask=q.ask + Decimal("0.5")),
        "quote timestamp": quote(timestamp=q.timestamp - datetime.timedelta(seconds=1)),
        "quote health": quote(health=DataHealth.STALE),
        "spot ltp": with_spot(ltp=spot.ltp + Decimal("7")),
        "spot timestamp": with_spot(timestamp=spot.timestamp - datetime.timedelta(seconds=1)),
        "spot health": with_spot(health=DataHealth.UNHEALTHY),
        "expiry": (chain, spot, datetime.date(2026, 10, 20), *base[3:]),
        "rate": (*base[:4], Decimal("0.07"), QUALITY),
        # REQ-167 AC-5: a changed forward setting is a new key, never served from the entry of the old one
        "forward quality": (*base[:5], dataclasses.replace(QUALITY, strikes_near=QUALITY.strikes_near + 2)),
    }


ENGINE_CALLS = {
    "iv": (service._solved_iv, _iv_cases),
    "greeks": (service._unit_greeks, _greek_cases),
    "forward": (snapshot_module._parity_forward, _forward_cases),
}
CASES = [(figure, name) for figure, names in (
    ("iv", ["kind", "strike", "price", "spot level", "forward", "implied yield / dividend yield", "years", "rate",
            "days in year"]),
    ("greeks", ["kind", "strike", "leg iv", "spot level", "forward", "implied yield / dividend yield", "years", "rate",
                "days in year"]),
    ("forward", ["quote contract", "quote bid", "quote ask", "quote timestamp", "quote health", "spot ltp",
                 "spot timestamp", "spot health", "expiry", "rate"]),
) for name in names]


@pytest.mark.parametrize(("figure", "changed"), CASES, ids=[f"{f}-{n}" for f, n in CASES])
def test_one_changed_input_at_the_same_instant_recomputes_and_equals_an_unshared_call(recorded, figure, changed):
    fn, cases = ENGINE_CALLS[figure]
    base, variants = cases(recorded)
    moved = variants[changed]
    cache = FeedScope(SharedCompute(), "user-1")
    first = _shared_answer(cache, fn, base)
    assert first == _answer(fn, base) and first[0] == "value" and first[1] is not None  # the base is a real figure
    computed = cache.cache.computations
    assert _shared_answer(cache, fn, base) == first and cache.cache.computations == computed  # read back, not redone
    again = _shared_answer(cache, fn, moved)
    assert cache.cache.computations == computed + 1, f"{figure}: a changed {changed} read the old entry"
    assert again == _answer(fn, moved)  # equals the unshared engine call to the last digit

