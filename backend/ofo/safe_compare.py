"""The one place a secret or identity is compared in constant time (#174).

``secrets.compare_digest`` on two ``str`` raises ``TypeError`` when either holds a non-ASCII character, and the
values compared here can be attacker-controlled (a cookie nonce, an acknowledgement) or come from a third party
(a Kite user id). A raise is a 500; the right answer is "not equal" and the caller's existing refusal path.
Comparing the UTF-8 bytes never raises. Every ``compare_digest`` call in ``backend/`` goes through this helper
(``tests/test_compare_digest_guard.py``).
"""

from __future__ import annotations

import hmac


def equal_secret(a: str, b: str) -> bool:
    """True when ``a`` and ``b`` are the same text; constant time over the UTF-8 bytes; never raises on a str."""
    if not isinstance(a, str) or not isinstance(b, str):
        raise TypeError("equal_secret compares two str values")
    return hmac.compare_digest(a.encode("utf-8", "surrogatepass"), b.encode("utf-8", "surrogatepass"))
