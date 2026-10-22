"""REQ-050 AC-3 (W-136): concurrent first requests for one key run one computation; one key's failure or slowness never
touches another key. Proven with counters and events, never with timing."""
import datetime
import threading
import time

import pytest
from ofo.marketdata.shared_compute import SharedCompute, SharedKey

T0 = datetime.datetime(2026, 10, 8, 9, 20, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
READERS = 100
SETTLE_SECONDS = 1.0  # how long the readers get to pile up on the one key before the computation is released


def key(instrument="X", owner="u1"):
    return SharedKey(owner, "NIFTY", datetime.date(2026, 10, 13), T0, "leg_iv", instrument, (1,))


def run_threads(targets):
    threads = [threading.Thread(target=t) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads)


def test_100_concurrent_first_requests_for_one_key_run_one_computation():
    """The computation blocks until every one of the 100 readers has started, so all 100 are inside get_or_compute
    together: without the per-key lock each of them would run it (the settle wait ends at once when they all do)."""
    cache, calls, results = SharedCompute(), [], []
    release, started, count_lock = threading.Event(), [], threading.Lock()

    def compute():
        with count_lock:
            calls.append(1)
        assert release.wait(timeout=30)
        return "figure"

    def reader():
        with count_lock:
            started.append(1)
        results.append(cache.get_or_compute(key(), compute))

    threads = [threading.Thread(target=reader) for _ in range(READERS)]
    for t in threads:
        t.start()
    deadline = time.monotonic() + SETTLE_SECONDS
    while time.monotonic() < deadline:  # a wait bound, never an assertion on time
        with count_lock:
            if len(started) == READERS and len(calls) == READERS:
                break
        time.sleep(0.01)
    release.set()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads)
    assert len(calls) == 1 and cache.computations == 1
    assert results == ["figure"] * READERS


def test_a_computation_that_raises_is_not_cached_and_other_keys_are_unaffected():
    cache, calls = SharedCompute(), []

    def boom():
        calls.append("boom")
        raise RuntimeError("engine failed")

    assert cache.get_or_compute(key("OK"), lambda: "fine") == "fine"
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cache.get_or_compute(key("BAD"), boom)
    assert calls == ["boom", "boom"]  # the next request computed again
    assert len(cache) == 1  # nothing cached for the failed key
    assert cache.get_or_compute(key("BAD"), lambda: "recovered") == "recovered"
    assert cache.get_or_compute(key("OK"), lambda: "never") == "fine"  # the other key is untouched


def test_concurrent_requests_to_a_failing_key_each_get_an_answer_or_the_error_and_none_hang():
    cache, outcomes = SharedCompute(), []
    first = threading.Event()

    def compute():
        if not first.is_set():
            first.set()
            raise RuntimeError("first attempt fails")
        return "second attempt"

    def reader():
        try:
            outcomes.append(cache.get_or_compute(key(), compute))
        except RuntimeError:
            outcomes.append("error")

    run_threads([reader] * 20)
    assert outcomes.count("error") == 1  # only the first attempt failed; the failure was not served to the others
    assert outcomes.count("second attempt") == 19


def test_a_slow_computation_for_one_key_does_not_block_reads_of_other_keys():
    cache = SharedCompute()
    started, release, done = threading.Event(), threading.Event(), []

    def slow():
        started.set()
        assert release.wait(timeout=30)
        return "slow figure"

    slow_reader = threading.Thread(target=lambda: done.append(cache.get_or_compute(key("SLOW"), slow)))
    slow_reader.start()
    assert started.wait(timeout=30)  # the slow computation is running now and holds its key
    fast = []

    def fast_reads():
        fast.append(cache.get_or_compute(key("FAST"), lambda: "fast figure"))  # a new key computes
        fast.append(cache.get_or_compute(key("FAST"), lambda: "never"))  # and an existing one reads

    fast_reader = threading.Thread(target=fast_reads, daemon=True)
    fast_reader.start()
    fast_reader.join(timeout=2)  # a blocked reader fails the test here, fast, instead of hanging it
    finished_while_slow_ran = not fast_reader.is_alive()
    release.set()
    slow_reader.join(timeout=30)
    assert finished_while_slow_ran, "a slow computation for one key blocked another key"
    assert fast == ["fast figure", "fast figure"]
    assert done == ["slow figure"]
