"""Puts tests/ on sys.path so every test folder can import the shared helper ``work_count``.

Also installs the runtime egress gate (``ofo.broker.egress``, REQ-073 AC-4) for this whole suite, with the same call
the API's ``create_app`` makes (importing ``ofo`` no longer installs it), and puts it in TEST mode for this suite only:
some tests run a hook or script as a child process (this Python, git, or the ruff / node binaries the edit-lint hook
runs, by resolved full path). Every other program stays refused, and connects are not widened at all. Production
never enters test mode.
"""
import contextlib
import platform
import shutil
import sys

from ofo.broker import egress as _egress


def _resolved_programs() -> list[str]:
    """The ruff and node binaries by RESOLVED full path (never a bare name, which any file so named would match):
    the packaged ruff binary the edit-lint hook runs, and whatever PATH resolves for ruff and node."""
    found = [shutil.which(name) for name in ("ruff", "node")]
    with contextlib.suppress(Exception):  # ruff not installed: the hook test skips itself
        from ruff.__main__ import find_ruff_bin  # noqa: PLC0415 - optional dependency
        found.append(str(find_ruff_bin()))
    return [p for p in found if p]


# finding local-pytest-plugin-not-in-ci: on Windows the first platform.uname()/win32_ver() call starts a process
# (platform._syscmd_ver), which the no-process hook below refuses if the first call comes later; prime the caches now.
for _name in ("uname", "win32_ver", "platform", "system", "release", "version", "machine", "python_implementation"):
    getattr(platform, _name)()
_egress.install()
_egress._enter_test_mode([sys.executable, "git", "git.exe", *_resolved_programs()])
