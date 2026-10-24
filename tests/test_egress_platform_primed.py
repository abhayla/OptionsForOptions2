"""Finding local-pytest-plugin-not-in-ci: on Windows the first platform.uname()/win32_ver() call starts a process
(``_syscmd_ver``); the conftests prime those caches before the no-process audit hook goes in, so a later first call
(a plugin's summary, a test module's import) is not refused by test order."""

import importlib
import platform
import subprocess

import pytest
from ofo.broker import egress

# What the conftest left in platform's own cache before ANY test module ran (read at import, i.e. at collection).
CACHE_AT_COLLECTION = getattr(platform, "_uname_cache", "no such cache in this Python")

PLATFORM_CALLS = (
    platform.uname,
    platform.win32_ver,
    platform.platform,
    platform.system,
    platform.release,
    platform.version,
    platform.machine,
    platform.python_implementation,
)


@pytest.mark.parametrize("call", PLATFORM_CALLS, ids=[c.__name__ for c in PLATFORM_CALLS])
def test_platform_calls_do_not_start_a_process_under_the_installed_hook(call):
    call()  # would raise EgressRefused if the cache were cold and the hook installed
    importlib.import_module("platform")
    call()


def test_the_conftest_filled_the_platform_cache_before_the_hook_was_installed():
    """On Windows a cold cache means the first call starts `ver` (platform._syscmd_ver), which the hook refuses."""
    if isinstance(CACHE_AT_COLLECTION, str):
        pytest.skip(CACHE_AT_COLLECTION)
    assert CACHE_AT_COLLECTION is not None


def test_the_hook_is_still_installed_and_still_refuses_a_new_process():
    """Priming must not loosen the gate: an unlisted program is still refused (the hook is the test's own session's)."""
    with pytest.raises(egress.EgressRefused):
        subprocess.run(["definitely-not-a-listed-program"], check=False)  # noqa: S607
