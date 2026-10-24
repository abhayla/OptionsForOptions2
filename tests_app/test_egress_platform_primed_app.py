"""Finding local-pytest-plugin-not-in-ci, the tests_app side: tests_app/conftest.py primes platform's caches before the
no-process audit hook goes in (the root tests/ side is tests/test_egress_platform_primed.py). Database-free."""

import platform

import pytest


def test_tests_app_conftest_cached_win32_ver():
    """platform.win32_ver keeps no cache of its own; its fallback starts a process, so the conftest wraps it."""
    assert hasattr(platform.win32_ver, "cache_info")


def test_tests_app_conftest_filled_the_uname_cache():
    """The conftest called platform.uname() once, so its cache is set before any test module is imported."""
    if not hasattr(platform, "_uname_cache"):
        pytest.skip("this Python keeps no platform._uname_cache")
    assert platform._uname_cache is not None
