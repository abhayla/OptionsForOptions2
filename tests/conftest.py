"""Puts tests/ on sys.path so every test folder can import the shared helper ``work_count``.

Also installs the runtime egress gate (``ofo.broker.egress``, REQ-073 AC-4) for this whole suite, with the same call
the API's ``create_app`` makes (importing ``ofo`` no longer installs it), and puts it in TEST mode for this suite only:
some tests run a hook or script as a child process (this Python, git, or the ruff / node binaries the edit-lint hook
runs). Every other program stays refused, and connects are not widened at all. Production never enters test mode.
"""
import sys

from ofo.broker import egress as _egress

_egress.install()
_egress._enter_test_mode([sys.executable, "git", "git.exe", "ruff", "ruff.exe", "node", "node.exe"])
