"""`UserFacing`: the marker for exceptions and results whose message IS shown to a user (W-024 round 9 part 6).

REQ-065 AC-2 / ADR-003 Q226: a user sees only a four-part `UserFacingError` from `render()`. The guarantee sits at the
one boundary users see (the API, `backend/ofo_app/errors.py`): an exception that is a `UserFacing` shows its
`user_message`; ANY other exception shows the INTERNAL_SYSTEM template, and its own text goes only to the log. So text
in any other exception is developer detail by construction, and the producer inventory
(tests/errors/test_producer_inventory.py) counts sentence-shaped text only where it can flow into a `UserFacing` type,
a label table or an explanation.

A subclass implements `user_message`, returning the `UserFacingError` it carries (from `render()`), or None when this
instance carries none (an optional `message=`, e.g. `TemplateError`): the boundary then shows the internal message.
"""

from __future__ import annotations

from ofo.errors.model import UserFacingError


class UserFacing:
    """Mixin marker: the instance's `user_message` is what a user is shown. Holds no state (``__slots__ = ()``), so it
    mixes into exceptions, frozen dataclasses and slotted classes alike."""

    __slots__ = ()

    @property
    def user_message(self) -> UserFacingError | None:
        """Default: the instance's `message` attribute (every marked class keeps its render() result there).
        A class keeping it elsewhere overrides this property."""
        return getattr(self, "message", None)


def user_message_of(obj: object) -> UserFacingError | None:
    """The message a user may be shown for `obj`, or None (fail closed): only a `UserFacing` whose `user_message` is
    a genuine `render()` result counts. Anything else, or a `user_message` that raises, is None."""
    if not isinstance(obj, UserFacing):
        return None
    try:
        message = obj.user_message
    except Exception:  # a broken marker never shows text: the boundary falls back to the internal message
        return None
    return message if type(message) is UserFacingError else None
