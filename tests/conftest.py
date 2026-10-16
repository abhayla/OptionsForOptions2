"""Puts tests/ on sys.path so every test folder can import the shared helper ``work_count``.

Also puts the runtime egress gate (``ofo.broker.egress``, REQ-073 AC-4) in TEST mode for this suite only: some tests
run a hook or script as a child process (this Python, or git). Every other program stays refused, and connects are
not affected at all. Production never enters test mode.
"""
import sys

from ofo.broker import egress as _egress

_egress._enter_test_mode([sys.executable, "git", "git.exe"])
