"""Generate the reply-field inventory (GC-MU step 2, issue #517, REQ-048 AC-5).

Every field path a reply can carry, read from the LIVE app: ``create_app().routes`` (each ``ClosedRoute`` and its
response model, each ``ClosedWebSocketRoute`` and its message models), the error body (the catalogue message's
parts), every header name the door may write and every cookie name the app constructs. The output
``tests_app/reply_inventory.py`` is checked in; ``tests_app/test_reply_inventory.py`` asserts it equals a fresh run
both ways, so a new field cannot leave the server without a reviewed line.

Answer states (fail closed): a model route, a socket route, a framework docs route (by exact name and class), a sealed
leaf (``BasketPost`` expanded to its form keys), an opaque leaf (``PlaybookBody``), a header, a cookie. A route class,
an annotation or a cookie-name expression it does not know RAISES ``InventoryError``: it never skips.

Reviewer notes: every string-capable leaf (Identifier, InstrumentId, CatalogueText, a sealed leaf's text, PlaybookBody)
is owned by ``DeclaringModel.field``; each owner carries a note in ``NOTES``. A regeneration keeps existing notes and
writes ``UNREVIEWED`` for a new owner, which the test refuses until a person writes the note.

Known bypass (verifier round 1, minor 3): the tests prove a note was WRITTEN, not that a person REVIEWED the field.
The first-round notes were written by rule (leaf kind and field-name family, seven template texts), so pasting one of
those templates onto a new owner passes. The review is the diff of this file in the pull request; the value canary at
the door (``ofo_app/secret_values.py``) is the guard that does not depend on a note being true.

Usage: ``python scripts/reply_inventory.py`` (write) or ``python scripts/reply_inventory.py --check`` (exit 1 on drift).
"""
from __future__ import annotations

import ast
import base64
import datetime
import os
import pathlib
import sys
import types
import typing
from decimal import Decimal
from typing import Any, Literal

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OUTPUT = ROOT / "tests_app" / "reply_inventory.py"
UNREVIEWED = "UNREVIEWED"

#: FastAPI's own documentation routes, by exact name (they carry the schema, never a domain value).
FRAMEWORK_ROUTES = frozenset({"openapi", "swagger_ui_html", "swagger_ui_redirect", "redoc_html"})
#: The keys ``BasketPost.as_form`` writes (basket_post.py); test_reply_inventory checks a real BasketPost against it.
BASKET_KEYS = ("api_key", "data", "url")
#: The one ``RedirectCookie(...)`` call that is not a minting site: the door reading back a header it already minted
#: (errors.py ``_cookie_from_header``), so its name is any name the builder wrote. (module, function) exactly.
COOKIE_READBACK = {("ofo_app/errors.py", "_cookie_from_header")}
STRING_KINDS = frozenset({"Identifier", "InstrumentId", "CatalogueText", "BasketPost.text", "PlaybookBody"})


class InventoryError(Exception):
    """The generator met a shape it does not know: fail closed."""


def _placeholder_env() -> None:
    """The broker config refuses to start without these; the inventory needs the routes, never a real value."""
    for name, value in (("KITE_API_KEY", "inventory_placeholder"), ("KITE_API_SECRET", "inventory_placeholder"),
                        ("KITE_REDIRECT_URL", "http://127.0.0.1:8000/kite/callback"),
                        ("FRONTEND_ORIGIN", "http://127.0.0.1:4173"), ("KITE_EXPECTED_USER_ID", "ZZ0000"),
                        ("BROKER_TOKEN_KEY", base64.urlsafe_b64encode(bytes(32)).decode("ascii"))):
        os.environ.setdefault(name, value)


def _leaf_kinds() -> list[tuple[Any, str]]:
    from ofo_app import api_models  # noqa: PLC0415

    return [(api_models.CatalogueText, "CatalogueText"), (api_models.Identifier, "Identifier"),
            (api_models.InstrumentId, "InstrumentId"), (api_models.Money, "Money")]


def _walk(tp: Any, path: str, owner: str, out: set[tuple[str, str, str]],  # noqa: C901, PLR0911, PLR0912
          stack: tuple[type, ...]) -> None:
    """Add (path, leaf kind, owner) for every leaf under annotation ``tp``; raise on anything unknown."""
    from ofo_app.api_models import ApiModel, _field_type  # noqa: PLC0415
    from ofo_app.basket_post import BasketPost  # noqa: PLC0415
    from ofo_app.playbook_body_out import PlaybookBody  # noqa: PLC0415

    for kind_tp, kind in _leaf_kinds():
        if tp == kind_tp:
            out.add((path, kind, owner))
            return
    if tp is BasketPost:  # sealed leaf: written as exactly its form keys
        for key in BASKET_KEYS:
            out.add((f"{path}.{key}", "BasketPost.text", f"BasketPost.{key}"))
        return
    if tp is PlaybookBody:  # opaque leaf (D1): a user-saved playbook body; the value canary covers it
        out.add((path, "PlaybookBody", owner))
        return
    origin = typing.get_origin(tp)
    if origin is Literal:
        out.add((path, "Literal[" + ",".join(repr(a) for a in typing.get_args(tp)) + "]", owner))
        return
    if origin in (list, tuple):
        args = typing.get_args(tp)
        if origin is tuple and args[-1] is not Ellipsis:  # a fixed-length tuple
            for index, arg in enumerate(args):
                _walk(arg, f"{path}[{index}]", owner, out, stack)
            return
        _walk(args[0], f"{path}[]", owner, out, stack)
        return
    if origin in (typing.Union, types.UnionType):
        for arg in typing.get_args(tp):
            if arg is type(None):
                out.add((path, "None", owner))
            else:
                _walk(arg, path, owner, out, stack)
        return
    if origin is dict:
        _walk(typing.get_args(tp)[1], f"{path}{{}}", owner, out, stack)
        return
    if tp in (bool, int, Decimal, datetime.datetime, datetime.date):
        out.add((path, tp.__name__, owner))
        return
    if isinstance(tp, type) and issubclass(tp, ApiModel):
        if tp in stack:
            raise InventoryError(f"{path}: {tp.__name__} contains itself; the inventory needs a finite tree")
        for name, info in tp.model_fields.items():
            _walk(_field_type(info), f"{path}.{name}", f"{tp.__name__}.{name}", out, (*stack, tp))
        return
    raise InventoryError(f"{path}: annotation {tp!r} is not a shape the inventory knows")


def model_leaves(model: type) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    _walk(model, model.__name__, model.__name__, out, ())
    return out


def _route_roots(app: Any) -> tuple[list[str], list[type]]:
    from fastapi.routing import APIRoute  # noqa: PLC0415
    from ofo_app.api_models import ApiModel  # noqa: PLC0415
    from ofo_app.errors import ClosedRoute, ClosedWebSocketRoute  # noqa: PLC0415
    from starlette.routing import Route  # noqa: PLC0415

    lines: list[str] = []
    roots: list[type] = []
    for route in app.routes:
        if type(route) is ClosedWebSocketRoute:
            models = route.message_models
            if not models or not all(isinstance(m, type) and issubclass(m, ApiModel) for m in models):
                raise InventoryError(f"{route.path}: socket message models {models!r}")
            lines.extend(f"SOCKET {route.path} -> {m.__name__}" for m in models)
            roots.extend(models)
        elif type(route) is ClosedRoute:
            model = route.response_model
            if not (isinstance(model, type) and issubclass(model, ApiModel)):
                raise InventoryError(f"{route.path}: response model {model!r}")
            lines.extend(f"ROUTE {method} {route.path} -> {model.__name__}" for method in sorted(route.methods))
            roots.append(model)
        elif type(route) is Route and not isinstance(route, APIRoute) and route.name in FRAMEWORK_ROUTES:
            lines.append(f"FRAMEWORK {route.path} {route.name}")
        else:
            raise InventoryError(f"{getattr(route, 'path', route)!r}: route class {type(route).__name__} is unknown")
    return lines, roots


def _cookie_names() -> list[str]:
    """Every name a ``RedirectCookie(...)`` call in the app constructs: a literal, or a module-level str constant."""
    names: set[str] = set()
    package = BACKEND / "ofo_app"
    for path in sorted(package.rglob("*.py")):
        rel = path.relative_to(BACKEND).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = {t.id: node.value.value for node in tree.body if isinstance(node, ast.Assign)
                     for t in node.targets if isinstance(t, ast.Name)
                     and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)}
        enclosing: dict[int, str] = {}  # call node id -> the innermost function holding it
        for func in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
            for inner in ast.walk(func):
                enclosing[id(inner)] = func.name  # later (inner) functions overwrite outer ones
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "RedirectCookie"):
                continue
            where = (rel, enclosing.get(id(node), "<module>"))
            first = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "name"), None)
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                names.add(first.value)
            elif isinstance(first, ast.Name) and first.id in constants:
                names.add(constants[first.id])
            elif where in COOKIE_READBACK:
                continue
            else:
                raise InventoryError(f"{rel}:{node.lineno}: a cookie name the inventory cannot resolve")
    return sorted(names)


def generate(app: Any) -> tuple[list[str], set[str]]:
    """(inventory lines, string-capable leaf owners) of ``app``."""
    from ofo.errors import render  # noqa: PLC0415
    from ofo_app.errors import _DOOR_HEADERS  # noqa: PLC0415

    route_lines, roots = _route_roots(app)
    leaves: set[tuple[str, str, str]] = set()
    for model in set(roots):
        leaves |= model_leaves(model)
    lines = set(route_lines)
    lines |= {f"FIELD {path}: {kind}" for path, kind, _ in leaves}
    lines |= {f"ERROR {key}: CatalogueText" for key in render("user_input_request_invalid").as_dict()}
    lines |= {f"HEADER {name}" for name in _DOOR_HEADERS}
    lines |= {f"COOKIE {name}" for name in _cookie_names()}
    owners = {owner for _, kind, owner in leaves if kind in STRING_KINDS}
    owners |= {f"ERROR.{key}" for key in render("user_input_request_invalid").as_dict()}
    return sorted(lines), owners


def render_file(lines: list[str], owners: set[str], notes: dict[str, str]) -> str:
    out = ["# ruff: noqa: E501",
           '"""GENERATED by scripts/reply_inventory.py: do not hand-edit INVENTORY; run the script, review the diff.',
           "",
           "INVENTORY: every reply field path, route, socket, header and cookie name the live app can send",
           "(REQ-048 AC-5).",
           f"NOTES: one reviewer note per string-capable leaf owner; a new owner is written as {UNREVIEWED!r} and",
           "the test refuses it until a person replaces it with what the field holds and why it is never a credential.",
           '"""', "", "INVENTORY = ("]
    out += [f"    {line!r}," for line in lines]
    out += [")", "", "NOTES = {"]
    out += [f"    {owner!r}: {notes.get(owner, UNREVIEWED)!r}," for owner in sorted(owners)]
    out += ["}", ""]
    return "\n".join(out)


def existing_notes() -> dict[str, str]:
    if not OUTPUT.exists():
        return {}
    for node in ast.parse(OUTPUT.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NOTES" for t in node.targets):
            return ast.literal_eval(node.value)
    return {}


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(BACKEND))
    _placeholder_env()
    from ofo_app.main import create_app  # noqa: PLC0415

    lines, owners = generate(create_app())
    text = render_file(lines, owners, existing_notes())
    if "--check" in argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print("tests_app/reply_inventory.py is stale: run python scripts/reply_inventory.py and review the diff")
            return 1
        return 0
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(lines)} lines, {len(owners)} reviewed owners -> {OUTPUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
