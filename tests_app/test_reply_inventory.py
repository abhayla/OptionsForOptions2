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
def registry():
    """The registry's slots, restored after the test (other tests' config values stay registered)."""
    from ofo_app import secret_values  # noqa: PLC0415

    before = dict(secret_values._BY_SLOT)
    secret_values._BY_SLOT.clear()
    yield secret_values
    secret_values._BY_SLOT.clear()
    secret_values._BY_SLOT.update(before)


def _stored_blob(key: bytes, token: str, aad: bytes) -> bytes:
    """A ciphertext as the store holds it (nonce + AES-GCM), made WITHOUT TokenCipher.encrypt: the state after a
    restart, when this process never saw the token in plain text before reading it back."""
    import os  # noqa: PLC0415

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415
    from ofo_app.broker_crypto import NONCE_BYTES  # noqa: PLC0415

    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, token.encode("utf-8"), aad)


@pytest.fixture
def canary_in_the_token_store(registry):
    """The canary is READ from a stored blob through the token cipher (the store's read path), never encrypted here."""
    import os  # noqa: PLC0415

    from ofo_app.broker_crypto import TokenCipher, associated_data  # noqa: PLC0415

    key = os.urandom(32)
    aad = associated_data("u-canary", "zerodha", 1)
    blob = _stored_blob(key, CANARY, aad)
    assert CANARY.encode() not in registry.registered_values()
    assert TokenCipher(key).decrypt(blob, aad) == CANARY
    return registry


def _route_reply(value: str):
    """A real route of the real app whose reply puts ``value`` in a reviewed Identifier field, sent through the door."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    planted = type("TokenEchoOut", (ApiModel,),
                   {"__annotations__": {"strategy_id": Identifier}, "__module__": "planted"})
    app = create_app()

    async def endpoint():
        return planted(strategy_id=value)

    app.router.routes.insert(0, app.router.route_class("/api/echo", endpoint, response_model=planted, methods=["GET"]))
    return TestClient(app, raise_server_exceptions=False).get("/api/echo")


def _assert_refused_without_the_value(response, value: str) -> None:
    assert response.status_code == 500  # noqa: PLR2004 - the door's internal failure answer
    assert value not in response.text and all(value not in v for v in response.headers.values())


def test_a_token_read_from_the_store_after_a_restart_is_refused_in_a_route_reply(canary_in_the_token_store) -> None:
    """Verifier round 1 MAJOR: no encrypt in this process; only the decrypt registers the token."""
    _assert_refused_without_the_value(_route_reply(CANARY), CANARY)


def test_a_token_stored_but_never_read_back_is_refused_in_a_route_reply(registry) -> None:
    import os  # noqa: PLC0415

    from ofo_app.broker_crypto import TokenCipher, associated_data  # noqa: PLC0415

    TokenCipher(os.urandom(32)).encrypt(CANARY, associated_data("u-canary", "zerodha", 1))
    _assert_refused_without_the_value(_route_reply(CANARY), CANARY)


def test_an_unregistered_value_passes_the_same_route(registry) -> None:
    assert _route_reply(CANARY).status_code == 200  # noqa: PLR2004 - the refusal above is the registry, not the route


@pytest.mark.parametrize("name", ["KITE_API_SECRET", "BROKER_TOKEN_KEY"])
def test_a_config_secret_is_registered_by_the_config_load_and_refused_in_a_route_reply(registry, monkeypatch,
                                                                                         name) -> None:
    from ofo_app.broker_config import load_broker_config  # noqa: PLC0415

    value = {"KITE_API_SECRET": "cfg" + "S1" * 12, "BROKER_TOKEN_KEY": None}[name]
    if value is None:  # a real 32-byte key in its urlsafe base64 text (44 characters; Identifier allows '-' and '_')
        import base64  # noqa: PLC0415

        value = base64.urlsafe_b64encode(bytes(range(1, 33))).decode("ascii").rstrip("=")
        monkeypatch.setenv(name, value + "=")
        value = value + "="
    else:
        monkeypatch.setenv(name, value)
    load_broker_config()
    assert registry.registered_values() >= {value.encode()}
    if "=" not in value:  # an Identifier cannot carry '=', so only the secret can be planted in a reply field
        _assert_refused_without_the_value(_route_reply(value), value)


def test_the_public_api_key_is_not_registered(registry) -> None:
    import os  # noqa: PLC0415

    from ofo_app.broker_config import load_broker_config  # noqa: PLC0415

    load_broker_config()
    assert os.environ["KITE_API_KEY"].encode() not in registry.registered_values()


def test_a_new_token_replaces_the_same_owners_old_one_so_the_registry_stays_bounded(registry) -> None:
    import os  # noqa: PLC0415

    from ofo_app.broker_crypto import TokenCipher, associated_data  # noqa: PLC0415

    cipher = TokenCipher(os.urandom(32))
    tokens = ["tok" + str(day) * 29 for day in range(1, 10)]
    for session_id, token in enumerate(tokens, start=1):  # nine daily logins of one user
        cipher.encrypt(token, associated_data("u-1", "zerodha", session_id))
    cipher.encrypt("other" + "9" * 27, associated_data("u-2", "zerodha", 1))
    assert registry.registered_values() == {tokens[-1].encode(), ("other" + "9" * 27).encode()}
    assert not registry.contains_secret(tokens[0].encode())  # yesterday's token is gone, today's is held
    assert registry.contains_secret(b"x" + tokens[-1].encode())



def test_tokens_read_back_after_a_restart_keep_one_value_per_owner(registry) -> None:
    """The decrypt side keys the same owner slot as the encrypt side (the session id dropped): nine sessions of one
    user read back from the store after a restart leave ONE registered value, not nine (verifier mutant 1b2)."""
    import os  # noqa: PLC0415

    from ofo_app.broker_crypto import TokenCipher, associated_data  # noqa: PLC0415

    cipher = TokenCipher(os.urandom(32))
    tokens = ["tok" + str(day) * 29 for day in range(1, 10)]
    stored = [(cipher.encrypt(t, associated_data("u-1", "zerodha", sid)), associated_data("u-1", "zerodha", sid))
              for sid, t in enumerate(tokens, start=1)]
    registry._BY_SLOT.clear()  # a restart: nothing registered until the store is read
    for blob, aad in stored:
        cipher.decrypt(blob, aad)
    assert registry.registered_values() == {tokens[-1].encode()}

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
