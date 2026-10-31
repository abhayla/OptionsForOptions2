"""GC-MU step 2 (#517, REQ-048 AC-5): the reply inventory is the allow-list of every field a reply can carry, and the
door refuses a reply holding a registered credential VALUE ("Browsers never ... hold vendor credentials").

- the checked-in ``tests_app/reply_inventory.py`` equals a fresh ``scripts/reply_inventory.py`` run on ``create_app()``,
  both ways, so a new field, route, socket, header or cookie cannot leave the server without a reviewed line;
- every string-capable leaf owner carries a reviewer note;
- value canaries: a canary access token that went through the token cipher (as the token store does) is absent from
  every reply model's body (the sample harness of test_response_door) and from every header.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest
import reply_inventory as CHECKED_IN  # the checked-in output, tests_app/reply_inventory.py
from ofo_app import api_models
from ofo_app.api_models import ApiModel, DoorRefused, Identifier
from ofo_app.main import create_app

ROOT = pathlib.Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("reply_inventory_generator", ROOT / "scripts" / "reply_inventory.py")
ri = importlib.util.module_from_spec(_SPEC)  # the generator, loaded by path: it shares the output's module name
_SPEC.loader.exec_module(ri)

#: a 32-character letters-and-digits value: the shape of a Kite access token, so it fits any Identifier field. Built at
#: run time so the repo's secret hook sees no key-shaped literal.
#: the sweep must be real: the app has dozens of reply models with an Identifier, and three sockets
MIN_SWEPT_MODELS = 20
SOCKETS = 3
CANARY = "canary" + "Q7" * 13


def _fresh() -> tuple[list[str], set[str]]:
    return ri.generate(create_app())


# ---- the core: the checked-in inventory equals the live app, both ways ---------------------------------------------

def test_the_checked_in_inventory_equals_the_live_app_both_ways() -> None:
    lines, owners = _fresh()
    added = sorted(set(lines) - set(CHECKED_IN.INVENTORY))
    missing = sorted(set(CHECKED_IN.INVENTORY) - set(lines))
    assert (added, missing) == ([], []), (
        f"not in tests_app/reply_inventory.py: {added[:10]}; listed but not sent: {missing[:10]} "
        "- run python scripts/reply_inventory.py and review the diff")
    assert list(CHECKED_IN.INVENTORY) == lines  # sorted, no duplicates
    assert set(CHECKED_IN.NOTES) == owners


def test_every_string_capable_leaf_owner_carries_a_reviewed_note() -> None:
    unreviewed = sorted(o for o, note in CHECKED_IN.NOTES.items() if not note.strip() or ri.UNREVIEWED in note)
    assert unreviewed == []


def test_the_inventory_covers_every_answer_state() -> None:
    lines = set(CHECKED_IN.INVENTORY)
    kinds = {line.split(" ", 1)[0] for line in lines}
    # FRAMEWORK lines appear only where the settings serve the docs (none in this suite's settings)
    assert kinds == {"ROUTE", "SOCKET", "FIELD", "ERROR", "HEADER", "COOKIE"}
    assert {"FIELD ExecuteOut.basket.api_key: BasketPost.text", "FIELD ExecuteOut.basket.url: BasketPost.text",
            "FIELD ExecuteOut.basket.data: BasketPost.text"} <= lines  # sealed leaf, expanded to its form keys
    assert any(line.endswith(": PlaybookBody") for line in lines)  # opaque leaf (D1)
    assert "COOKIE ofo_kite_login" in lines and "HEADER set-cookie" in lines


def test_the_basket_keys_the_generator_lists_are_the_keys_a_real_basket_post_writes() -> None:
    from ofo_app.basket_post import BasketPost  # noqa: PLC0415
    from test_execute_route import _real_basket  # noqa: PLC0415

    assert tuple(sorted(BasketPost.of(_real_basket(), "kitekey").as_form())) == ri.BASKET_KEYS


# ---- planted fields: each round-2 reply escape turns the both-ways test red ------------------------------------------

def _planted_app(field: str):
    planted = type("PlantedOut", (ApiModel,), {"__annotations__": {field: Identifier}, "__module__": "planted"})
    app = create_app()

    async def endpoint():  # pragma: no cover - never called, only listed
        return None

    app.router.routes.insert(0, app.router.route_class("/api/planted", endpoint, response_model=planted,
                                                       methods=["GET"]))
    return app


@pytest.mark.parametrize("field", ["token", "auth_token", "secret", "kite_session"])
def test_a_planted_reply_field_is_red_until_listed(field: str) -> None:
    lines, owners = ri.generate(_planted_app(field))
    added = set(lines) - set(CHECKED_IN.INVENTORY)
    assert f"FIELD PlantedOut.{field}: Identifier" in added
    assert f"PlantedOut.{field}" in owners - set(CHECKED_IN.NOTES)  # and it needs a reviewer note


# ---- fail closed: the generator raises on what it does not know ------------------------------------------------------

def test_an_unknown_route_type_makes_the_generator_raise() -> None:
    from starlette.routing import Mount  # noqa: PLC0415

    app = create_app()
    app.router.routes.append(Mount("/raw", app=lambda scope, receive, send: None))
    with pytest.raises(ri.InventoryError, match="unknown"):
        ri.generate(app)


def test_an_unknown_annotation_makes_the_generator_raise() -> None:
    with pytest.raises(ri.InventoryError, match="not a shape"):
        ri._walk(bytes, "X.y", "X.y", set(), ())


def test_an_unresolvable_cookie_name_makes_the_generator_raise(tmp_path, monkeypatch) -> None:
    (tmp_path / "ofo_app").mkdir()
    (tmp_path / "ofo_app" / "x.py").write_text("def f(n):\n    return RedirectCookie(n, '/')\n", encoding="utf-8")
    monkeypatch.setattr(ri, "BACKEND", tmp_path)
    with pytest.raises(ri.InventoryError, match="cookie name"):
        ri._cookie_names()
    (tmp_path / "ofo_app" / "x.py").write_text("NAME = 'c1'\ndef f():\n    return RedirectCookie(NAME, '/')\n",
                                               encoding="utf-8")
    assert ri._cookie_names() == ["c1"]


def test_mutant_a_dropped_inventory_line_is_red() -> None:
    lines, _ = _fresh()
    assert sorted(set(lines) - set(CHECKED_IN.INVENTORY[1:])) == [CHECKED_IN.INVENTORY[0]]


# ---- value canaries --------------------------------------------------------------------------------------------------

@pytest.fixture
def canary_in_the_token_store():
    """The canary goes through the token cipher exactly as the store's write and read do (broker_token_store)."""
    import os  # noqa: PLC0415

    from ofo_app import secret_values  # noqa: PLC0415
    from ofo_app.broker_crypto import TokenCipher, associated_data  # noqa: PLC0415

    before = set(secret_values._VALUES)
    secret_values._VALUES.discard(CANARY.encode())
    cipher = TokenCipher(os.urandom(32))
    aad = associated_data("u-canary", "zerodha", 1)
    assert cipher.decrypt(cipher.encrypt(CANARY, aad), aad) == CANARY
    yield
    secret_values._VALUES.clear()
    secret_values._VALUES.update(before)


def _reply_models() -> list[type]:
    _, roots = ri._route_roots(create_app())
    return sorted(set(roots), key=lambda c: c.__name__)


def _has_identifier(model: type) -> bool:
    return any(kind == "Identifier" for _, kind, _ in ri.model_leaves(model))


def test_every_reply_model_with_the_canary_in_its_identifier_fields_is_refused(canary_in_the_token_store,
                                                                               monkeypatch) -> None:
    import test_response_door as door  # noqa: PLC0415  the existing sample harness

    real_sample = door._sample

    def canary_sample(tp, required_only=False):
        return CANARY if tp == Identifier else real_sample(tp, required_only)

    monkeypatch.setattr(door, "_sample", canary_sample)
    models = [m for m in _reply_models() if _has_identifier(m)]
    assert len(models) > MIN_SWEPT_MODELS  # the sweep is real, not empty
    leaked = []
    for model in models:
        built = door._build(model)
        try:
            body = api_models.emit(built)
        except DoorRefused:
            continue
        leaked.append(model.__name__) if CANARY.encode() in body else None
    assert leaked == []
    # and the sample values without the canary still emit: the refusal is the canary, not the harness
    monkeypatch.setattr(door, "_sample", real_sample)
    for model in models:
        assert CANARY.encode() not in api_models.emit(door._build(model))


def test_every_socket_message_with_the_canary_is_refused(canary_in_the_token_store, monkeypatch) -> None:
    import test_response_door as door  # noqa: PLC0415
    from ofo_app.errors import ClosedWebSocketRoute, socket_body  # noqa: PLC0415

    real_sample = door._sample
    monkeypatch.setattr(door, "_sample",
                        lambda tp, required_only=False: CANARY if tp == Identifier else real_sample(tp, required_only))
    sockets = [r for r in create_app().routes if type(r) is ClosedWebSocketRoute]
    assert len(sockets) == SOCKETS
    for route in sockets:
        for model in route.message_models:
            if _has_identifier(model):
                with pytest.raises(DoorRefused):
                    socket_body(door._build(model), route.message_models)


def test_a_header_holding_the_canary_is_refused(canary_in_the_token_store) -> None:
    from ofo_app.errors import RedirectCookie, _mint_headers  # noqa: PLC0415

    with pytest.raises(DoorRefused, match="credential value"):
        _mint_headers(body_length=0, content_type=False, status=302,
                      cookie=RedirectCookie("ofo_kite_login", "/kite/callback", value=CANARY))
    assert _mint_headers(body_length=0, content_type=False, status=302,
                         cookie=RedirectCookie("ofo_kite_login", "/kite/callback", value="nonce" + "1" * 20))


def test_mutant_without_the_canary_check_the_canary_leaks(canary_in_the_token_store, monkeypatch) -> None:
    import test_response_door as door  # noqa: PLC0415

    monkeypatch.setattr(api_models, "contains_secret", lambda data: False)
    real_sample = door._sample
    monkeypatch.setattr(door, "_sample",
                        lambda tp, required_only=False: CANARY if tp == Identifier else real_sample(tp, required_only))
    model = next(m for m in _reply_models() if _has_identifier(m))
    assert CANARY.encode() in api_models.emit(door._build(model))


def test_the_broker_config_registers_the_api_secret_and_the_token_key() -> None:
    import os  # noqa: PLC0415

    from ofo_app import secret_values  # noqa: PLC0415
    from ofo_app.broker_config import load_broker_config  # noqa: PLC0415

    load_broker_config()
    for name in ("KITE_API_SECRET", "BROKER_TOKEN_KEY"):
        assert os.environ[name].encode() in secret_values._VALUES, name
    assert os.environ["KITE_API_KEY"].encode() not in secret_values._VALUES  # the PUBLIC key reaches the basket form
