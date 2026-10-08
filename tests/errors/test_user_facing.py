"""W-024 round 9 part 6 (REQ-065 AC-2, ADR-003 Q226): every `ofo.errors.UserFacing` type shows a four-part render()
message, and nothing else.

The API boundary (backend/ofo_app/errors.py) shows a `UserFacing` exception's `user_message` and the INTERNAL_SYSTEM
template for any other exception. So each `UserFacing` subclass must (a) carry a genuine `render()` result in
`user_message`, with all four parts, and (b) refuse a plain string. `EXAMPLES` must name every subclass found by
importing backend/ofo: a new `UserFacing` type without an example here fails, so none ships unchecked.
"""
from __future__ import annotations

import datetime
import importlib
import pathlib
from collections.abc import Callable

import pytest

from ofo.errors import UserFacing, UserFacingError, render, user_message_of

ROOT = pathlib.Path(__file__).resolve().parents[2] / "backend" / "ofo"
PARTS = ("what_happened", "impact", "what_is_blocked", "next_action")
AT = datetime.datetime(2026, 10, 8, 10, 0, tzinfo=datetime.timezone.utc)


def _all_subclasses() -> set[type]:
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT.parent).with_suffix("").as_posix().replace("/", ".")
        importlib.import_module(rel.removesuffix(".__init__"))
    found: set[type] = set()
    stack = [UserFacing]
    while stack:
        for sub in stack.pop().__subclasses__():
            if sub not in found:
                found.add(sub)
                stack.append(sub)
    return found


def _check_failure() -> object:
    from ofo.execution.safety import CheckCode, CheckFailure

    return CheckFailure(CheckCode.UNDERLYING_UNSUPPORTED, render("gate_underlying_unsupported", symbol="BANKNIFTY"))


def _send_refused() -> object:
    from ofo.execution.send_guard import SendRefused

    return SendRefused(render("send_choice_unknown"))


def _slice_refused() -> object:
    from ofo.execution.sequence import SliceRefused

    return SliceRefused(detail="lots=0 for leg 2", message=render("send_choice_unknown"))


def _preparation() -> object:
    from ofo.execution.partial import PartialChoice, _not_prepared

    return _not_prepared(PartialChoice.REVIEW_MANUALLY, None)


def _guard_refused() -> object:
    from ofo.strategy.guard import GuardRefused

    return GuardRefused(render("guard_risk_profile_changed"))


def _template_error() -> object:
    from ofo.strategy.model import TemplateError

    return TemplateError("bad yaml at line 3", message=render("strategy_catalogue_unreadable"))


def _reconciliation_error() -> object:
    from ofo.reconciliation.compare import ReconciliationError

    return ReconciliationError("strategy s1 has exited", message=render("partial_mismatch_unresolved"))


def _mismatch() -> object:
    from ofo.reconciliation import compare

    kind = compare.MismatchKind.MISSING_PLATFORM_POSITION
    return compare.Mismatch(kind=kind, strategy_ids=("s1",), at=AT, broker_state=(), platform_state=(),
                            platform_breakdown=(), difference=(), next_action=compare._NEXT_ACTION[kind])


def _disconnect_status() -> object:
    from ofo.marketdata.disconnect import DisconnectStatus, disconnect_error

    return DisconnectStatus(error=disconnect_error(AT), last_updated=AT)


EXAMPLES: dict[str, Callable[[], object]] = {
    "ofo.marketdata.disconnect.DisconnectStatus": _disconnect_status,
    "ofo.execution.safety.CheckFailure": _check_failure,
    "ofo.execution.send_guard.SendRefused": _send_refused,
    "ofo.execution.sequence.SliceRefused": _slice_refused,
    "ofo.execution.partial.Preparation": _preparation,
    "ofo.strategy.guard.GuardRefused": _guard_refused,
    "ofo.strategy.model.TemplateError": _template_error,
    "ofo.reconciliation.compare.ReconciliationError": _reconciliation_error,
    "ofo.reconciliation.compare.Mismatch": _mismatch,
}


def _qualname(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def test_every_user_facing_subclass_has_an_example() -> None:
    names = {_qualname(c) for c in _all_subclasses() if c.__module__.startswith("ofo.")}
    assert names == set(EXAMPLES), f"missing examples: {sorted(names - set(EXAMPLES))}; " \
                                   f"stale: {sorted(set(EXAMPLES) - names)}"


@pytest.mark.parametrize("name", sorted(EXAMPLES))
def test_every_user_facing_subclass_renders_four_parts(name: str) -> None:
    obj = EXAMPLES[name]()
    assert _qualname(type(obj)) == name
    message = user_message_of(obj)
    assert type(message) is UserFacingError
    for part in PARTS:
        assert getattr(message, part).strip(), (name, part)
    assert len({getattr(message, p) for p in PARTS}) == 4


@pytest.mark.parametrize("build", [
    lambda: __import__("ofo.execution.send_guard", fromlist=["x"]).SendRefused("Leg 1 has already expired."),
    lambda: __import__("ofo.strategy.guard", fromlist=["x"]).GuardRefused("The risk changed."),
    lambda: __import__("ofo.execution.sequence", fromlist=["x"]).SliceRefused(detail="d", message="Lots wrong."),
    lambda: __import__("ofo.strategy.model", fromlist=["x"]).TemplateError("d", message="The template is bad."),
    lambda: __import__("ofo.reconciliation.compare", fromlist=["x"]).ReconciliationError("d", message="Mismatch."),
])
def test_a_plain_string_message_is_refused(build: Callable[[], object]) -> None:
    with pytest.raises(TypeError):
        build()


def test_optional_message_absent_means_no_user_message() -> None:
    from ofo.strategy.model import TemplateError

    assert user_message_of(TemplateError("developer detail only")) is None


def test_non_user_facing_objects_have_no_user_message() -> None:
    assert user_message_of(ValueError("leg expired before execution, use strike 22,550")) is None
    assert user_message_of("Leg 1 has already expired.") is None


def test_a_marker_whose_user_message_is_not_a_render_result_shows_nothing() -> None:
    """Fail closed: a UserFacing that hands out a plain string, or raises, yields None (the boundary then shows the
    INTERNAL_SYSTEM template)."""

    class Broken(UserFacing):
        @property
        def user_message(self):  # type: ignore[override]
            return "Leg 1 has already expired."

    class Raising(UserFacing):
        @property
        def user_message(self):  # type: ignore[override]
            raise RuntimeError("boom")

    assert user_message_of(Broken()) is None
    assert user_message_of(Raising()) is None
