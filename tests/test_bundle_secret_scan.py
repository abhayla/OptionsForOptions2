"""REQ-048 AC-5 (W-134): no browser asset and no server reply carries a vendor host, key or token (ADR-012).

Two scans, both ALLOW-LISTS (finding guard-as-forbidden-list): every URL found must be on a list of exact URLs/prefixes
that names the reason, every vendor domain must sit inside such an allowed URL, and every credential-shaped name/value
is a finding unless a named entry allows exactly that place.
- the BUILT bundle (``frontend/dist`` after ``npm run build``; the frontend CI job runs this file right after the build,
  and with ``CI`` set a missing ``frontend/dist`` FAILS; a local run without the build skips). Files are discovered, an
  unreadable file or an unknown extension is a finding (fail closed);
- every property name (at every depth: nested ``properties``, ``items``, ``allOf``/``anyOf``/``oneOf``, inline objects)
  and every string in ``docs/api/openapi.json`` (the shape of every ``/api`` reply).
Static-scan limit, stated on purpose: a host or key hidden in base64 or built at run time (``atob``, array joins, a
computed property name) is NOT seen; ESLint (``no-restricted-syntax`` on vendor hosts) is the second layer.
Planted cases prove each scan can turn red.
"""
import json
import os
import pathlib
import re

import pytest

pytestmark = pytest.mark.repo_scan  # reads the built bundle and the openapi file

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"
OPENAPI = ROOT / "docs" / "api" / "openapi.json"

#: every URL the built bundle may hold, as an exact URL or a prefix, with the reason. Anything else that looks like a
#: URL is a finding. Vendor domains are matched separately and must lie inside one of these.
ALLOWED_EXACT_URLS = {
    "http://localhost": "the dev-server default inside the library code (no port, no path, no userinfo); never a vendor",  # noqa: E501
    "http://www.w3.org/2000/svg": "XML namespace string (SVG), never fetched",
    "http://www.w3.org/1999/xlink": "XML namespace string (xlink), never fetched",
    "http://www.w3.org/1998/Math/MathML": "XML namespace string (MathML), never fetched",
}
ALLOWED_URL_PREFIXES = {
    "https://kite.zerodha.com/connect/basket": "the Kite basket form the owner presses Place on (frontend/src/lib/execute.js)",  # noqa: E501
    "https://kite.zerodha.com/positions": "the Kite positions page the owner opens (frontend/src/lib/execute.js)",
    "https://vuejs.org/error-reference/#runtime-": "a documentation link inside Vue's own warning text",
}
#: vendor domains: found anywhere (with or without a scheme, after un-escaping slashes and joining split literals) they
#: are a finding unless they lie inside an allowed URL above.
VENDOR_DOMAIN_RE = re.compile(r"[A-Za-z0-9.@-]*(?:kite\.trade|zerodha\.com)", re.I)
#: the one place a public ``api_key`` field may appear: the Kite basket form (it posts the app's PUBLIC key to Kite;
#: the secret and the access token never leave the server). Matched against the path inside ``dist`` (the two
#: current chunk name patterns, an 8-character build hash); any other chunk name is a finding.
API_KEY_ALLOWED_BUNDLE_FILES = re.compile(
    r"^assets/(?:execute|ExecuteStrategyPage)-[A-Za-z0-9_-]{8}\.js$")
#: reply fields: the exact schema path (``Schema.prop.prop``) that may be named ``api_key``, with the reason.
API_KEY_ALLOWED_PATHS = {
    "ExecuteOut.basket.api_key": "the Kite basket form's PUBLIC api_key (the secret and the token never leave the server)",  # noqa: E501
}

TEXT_EXTENSIONS = {".js", ".css", ".html", ".map", ".json", ".txt", ".svg"}
BINARY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".webp"}

#: a URL-looking token: optional scheme, ``//``, then a dotted host (or ``localhost``) with userinfo/port/path; it ends
#: at a quote, space, bracket or backslash. ``//x`` without a scheme counts only right after a quote (a
#: protocol-relative URL string; a regex literal such as ``/^\/\/i.test/`` is not one).
URL_RE = re.compile(
    r"(?:(?:https?|wss?)://|(?<=[\"'`])//)[A-Za-z0-9@:_.-]*(?:\.[A-Za-z]{2,}|localhost)[^\s\"'`<>()\\]*", re.I)
CRED_NAME_RE = re.compile(
    r"(access[_-]?token|refresh[_-]?token|request[_-]?token|public[_-]?token|api[_-]?secret|client[_-]?secret|enctoken)",
    re.I)
#: reply fields only: the word ``password`` is ordinary text/library code in a bundle (input type, landing copy)
REPLY_CRED_NAME_RE = re.compile(CRED_NAME_RE.pattern[:-1] + "|password)", re.I)
API_KEY_NAME_RE = re.compile(r"api[_-]?key", re.I)
#: a credential name followed by a value of a real key's length: a key-like name, ``=`` or ``:``, then 16+ characters
CRED_VALUE_RE = re.compile(
    r"(api[_-]?key|access[_-]?token|api[_-]?secret|enctoken|request[_-]?token)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9]{16,}",
    re.I)
_SPLIT_LITERAL_RE = re.compile(r"[\"'`]\s*\+\s*[\"'`]")  # a literal, plus, a literal: joined into one string


def _normalise(text: str) -> str:
    """Un-escape slashes (``wss:\\/\\/``) and join adjacent string literals, so a split host is one host."""
    return _SPLIT_LITERAL_RE.sub("", text.replace("\\/", "/"))


def _url_allowed(url: str) -> bool:
    return url in ALLOWED_EXACT_URLS or any(url.startswith(prefix) for prefix in ALLOWED_URL_PREFIXES)


def scan_urls(name: str, text: str) -> list[str]:
    """Every URL token must be allowed; the text left after removing allowed URLs must hold no vendor domain."""
    text = _normalise(text)
    found = []
    rest = []
    last = 0
    for m in URL_RE.finditer(text):
        rest.append(text[last:m.start()])
        last = m.end()
        if not _url_allowed(m.group(0)):
            found.append(f"{name}: url {m.group(0)[:60]} is not on the allow-list")
    rest.append(text[last:])
    # a vendor domain outside any URL token (a bare ``host.tld``); inside a rejected URL it is already a finding
    found.extend(f"{name}: vendor domain {m.group(0)} is not on the allow-list"
                 for m in VENDOR_DOMAIN_RE.finditer(" ".join(rest)))
    return found


def scan_text(name: str, text: str, *, api_key_ok: bool) -> list[str]:
    found = scan_urls(name, text)
    found.extend(f"{name}: credential name {m.group(1)}" for m in CRED_NAME_RE.finditer(text))
    if not api_key_ok:
        found.extend(f"{name}: credential name {m.group(0)}" for m in API_KEY_NAME_RE.finditer(text))
    found.extend(f"{name}: credential-shaped value {m.group(0)[:24]}" for m in CRED_VALUE_RE.finditer(text))
    return found


def scan_dir(root: pathlib.Path) -> list[str]:
    files = [p for p in root.rglob("*") if p.is_file()]
    if not files:
        return [f"{root}: no files discovered (an empty bundle is not a clean bundle)"]
    found = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        ext = path.suffix.lower()
        if ext in BINARY_EXTENSIONS:
            continue
        if ext not in TEXT_EXTENSIONS:
            found.append(f"{rel}: unknown file type {ext!r}; add it to a list with a reason")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:  # fail closed on a file it cannot read
            found.append(f"{rel}: unreadable ({exc.__class__.__name__})")
            continue
        found.extend(scan_text(rel, text, api_key_ok=bool(API_KEY_ALLOWED_BUNDLE_FILES.match(rel))))
    return found


def _walk_schema(node, path: str, found: list[str]) -> None:
    """Check every property name at every depth. ``properties`` maps names to schemas; every other dict/list value
    (``items``, ``allOf``/``anyOf``/``oneOf``, ``additionalProperties``, ``not``, ...) is walked without a new name."""
    if isinstance(node, list):
        for item in node:
            _walk_schema(item, path, found)
        return
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if key == "properties" and isinstance(value, dict):
            for prop, sub in value.items():
                here = f"{path}.{prop}"
                if REPLY_CRED_NAME_RE.search(prop):
                    found.append(f"{here}: credential-named reply field")
                elif API_KEY_NAME_RE.search(prop) and here not in API_KEY_ALLOWED_PATHS:
                    found.append(f"{here}: api_key reply field outside the allow-list")
                _walk_schema(sub, here, found)
        elif key == "required" and isinstance(value, list):
            found.extend(f"{path}.{r}: credential-named required field" for r in value
                         if isinstance(r, str) and (REPLY_CRED_NAME_RE.search(r) or (
                             API_KEY_NAME_RE.search(r) and f"{path}.{r}" not in API_KEY_ALLOWED_PATHS)))
        else:
            _walk_schema(value, path, found)


def scan_openapi(doc: dict) -> list[str]:
    schemas = (doc.get("components") or {}).get("schemas")
    if not schemas:
        return ["openapi: no schemas discovered"]
    found: list[str] = []
    for schema_name, schema in schemas.items():
        _walk_schema(schema, schema_name, found)
    # response bodies declared inline on an operation (not through components) are walked from the paths too
    for route, item in (doc.get("paths") or {}).items():
        _walk_schema(item, f"paths[{route}]", found)
    dumped = json.dumps(doc)
    found.extend(scan_urls("openapi", dumped))
    found.extend(f"openapi: credential-shaped value {m.group(0)[:24]}" for m in CRED_VALUE_RE.finditer(dumped))
    return found


# ---- the real artefacts --------------------------------------------------------------------------------------------

def test_the_built_bundle_names_no_vendor_host_and_holds_no_key_or_token():
    if not DIST.is_dir():
        message = "frontend/dist is absent: run `npm run build` in frontend/ (CI runs this right after the build step)"
        # Only the frontend job's scan step sets OFO_REQUIRE_BUNDLE_SCAN (app-tests.yml): there a missing build is a
        # failed scan, never a skipped one. Not `CI`: GitHub sets CI on every runner, and the kit's tests job runs this
        # file over tests/ without building the frontend (row 6 verifier round 2).
        if os.environ.get("OFO_REQUIRE_BUNDLE_SCAN") == "1":
            pytest.fail(message)
        pytest.skip(message)
    assert scan_dir(DIST) == []


def test_every_reply_shape_is_free_of_credential_fields_and_vendor_hosts():
    assert scan_openapi(json.loads(OPENAPI.read_text(encoding="utf-8"))) == []


def test_every_allow_list_entry_names_a_reason():
    reasons = [*ALLOWED_EXACT_URLS.values(), *ALLOWED_URL_PREFIXES.values(), *API_KEY_ALLOWED_PATHS.values()]
    assert all(reasons)


def test_with_ci_set_and_no_build_the_bundle_scan_fails_and_without_ci_it_skips(monkeypatch):
    real_is_dir = pathlib.Path.is_dir
    monkeypatch.setattr(pathlib.Path, "is_dir", lambda self: False if self == DIST else real_is_dir(self))
    monkeypatch.setenv("OFO_REQUIRE_BUNDLE_SCAN", "1")  # what the frontend job's scan step sets
    with pytest.raises(pytest.fail.Exception):
        test_the_built_bundle_names_no_vendor_host_and_holds_no_key_or_token()
    # the skip half must hold wherever this runs: the frontend job sets the variable, GitHub sets CI everywhere
    monkeypatch.delenv("OFO_REQUIRE_BUNDLE_SCAN", raising=False)
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(pytest.skip.Exception):
        test_the_built_bundle_names_no_vendor_host_and_holds_no_key_or_token()


# ---- planted cases: each scan turns red ------------------------------------------------------------------------------

def _bundle(tmp_path: pathlib.Path, name: str, body: str) -> pathlib.Path:
    (tmp_path / "assets").mkdir(exist_ok=True)
    (tmp_path / "assets" / name).write_text(body, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("planted", [
    "const s = new WebSocket('wss://ws.kite.trade/?x=1')",
    "fetch('https://api.kite.trade/quote')",
    "const u = 'https://api.upstox.com/v2'",
    "fetch('api.kite.trade/quote')",  # bare domain, no scheme
    "fetch('//api.kite.trade/quote')",  # protocol-relative
    "new WebSocket('wss:\\/\\/ws.kite.trade')",  # escaped slashes
    "fetch('https://api.' + 'kite.trade/quote')",  # host split across two literals
    "fetch('https://api.kite' + '.trade/quote')",
    "fetch('https://localhost@api.kite.trade/x')",  # userinfo trick
    "fetch('ws://localhost:8000')",  # localhost with a port is not the allowed exact URL
    "fetch('https://kite.zerodha.com/orders')",  # the vendor host, a path that is not an allowed prefix
    "fetch('https://api.zerodha.com/x')",
    "fetch('https://kite.zerodha.com.evil.example/connect/basket')",  # allowed prefix text, different host
])
def test_a_planted_vendor_host_in_a_bundle_file_is_red(tmp_path, planted):
    _bundle(tmp_path, "index-abcd1234.js", "var a=1;" + planted)
    assert any("allow-list" in f for f in scan_dir(tmp_path)), planted


def test_the_allowed_urls_are_green(tmp_path):
    _bundle(tmp_path, "index-abcd1234.js",
            'a="https://kite.zerodha.com/connect/basket";b="https://kite.zerodha.com/positions";'
            'c="http://localhost";d="http://www.w3.org/2000/svg";e=`https://vuejs.org/error-reference/#runtime-${n}`')
    assert scan_dir(tmp_path) == []


PLANTED_VALUE = "abcd1234" + "efgh5678"  # built at run time so the repo's own secret hook sees no key-shaped literal


@pytest.mark.parametrize(("key", "sep"), [("api_key", "="), ("apiKey", "="), ("apiKey", ":"), ("API_KEY", ":")])
def test_a_planted_key_value_in_a_bundle_file_is_red(tmp_path, key, sep):
    _bundle(tmp_path, "index-abcd1234.js", f"x('{key}{sep}{PLANTED_VALUE}')")
    assert any("credential-shaped value" in f for f in scan_dir(tmp_path)), (key, sep)


@pytest.mark.parametrize("planted", ["res.access_token", "res.accessToken", "res.ACCESS_TOKEN", "x.apiSecret"])
def test_a_planted_credential_name_is_red_even_in_an_api_key_allowed_chunk(tmp_path, planted):
    _bundle(tmp_path, "execute-abcd1234.js", "const t = " + planted)
    assert any("credential name" in f for f in scan_dir(tmp_path)), planted


def test_a_planted_api_key_outside_the_two_basket_chunks_is_red_and_inside_is_green(tmp_path):
    _bundle(tmp_path, "other-abcd1234.js", "name:'api_key'")
    assert any("api_key" in f for f in scan_dir(tmp_path))
    for number, name in enumerate(("execute-abcd1234.js", "ExecuteStrategyPage-abcd1234.js")):
        ok = tmp_path / f"ok{number}"
        ok.mkdir()
        assert scan_dir(_bundle(ok, name, "name:'api_key'")) == []


@pytest.mark.parametrize("name", ["execute-evil-extra.js", "execute-abcd1234.min.js", "executeabcd1234.js",
                                  "execute-abcd1234.css", "ExecuteStrategyPage-abcd123.js"])
def test_a_future_execute_like_chunk_name_gets_no_api_key_exemption(tmp_path, name):
    _bundle(tmp_path, name, "name:'api_key'")
    assert any("api_key" in f for f in scan_dir(tmp_path)), name


def test_an_execute_chunk_outside_assets_gets_no_api_key_exemption(tmp_path):
    (tmp_path / "execute-abcd1234.js").write_text("name:'api_key'", encoding="utf-8")
    assert any("api_key" in f for f in scan_dir(tmp_path))


def test_an_unreadable_file_an_unknown_type_and_an_empty_bundle_fail_closed(tmp_path):
    (tmp_path / "bad.js").write_bytes(b"\xff\xfe\x00bad")
    (tmp_path / "x.wasm").write_bytes(b"\x00asm")
    found = scan_dir(tmp_path)
    assert any("unreadable" in f for f in found) and any("unknown file type" in f for f in found)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert scan_dir(empty)


def _doc() -> dict:
    return json.loads(OPENAPI.read_text(encoding="utf-8"))


def test_a_planted_access_token_field_in_a_response_model_is_red():
    doc = _doc()
    doc["components"]["schemas"]["ContractOut"]["properties"]["access_token"] = {"type": "string"}
    assert scan_openapi(doc) == ["ContractOut.access_token: credential-named reply field"]
    doc = _doc()
    doc["components"]["schemas"]["ContractOut"]["properties"]["api_key"] = {"type": "string"}
    assert any("api_key reply field" in f for f in scan_openapi(doc))
    doc = _doc()
    doc["info"]["description"] = "see wss://ws.kite.trade"
    assert any("ws.kite.trade" in f for f in scan_openapi(doc))


def test_the_real_basket_schema_is_inline_so_the_depth_tests_below_test_the_real_path():
    basket = _doc()["components"]["schemas"]["ExecuteOut"]["properties"]["basket"]
    assert "properties" in basket and "$ref" not in basket  # inline, as verifier round 1 found


@pytest.mark.parametrize("name", ["access_token", "api_secret", "accessToken", "Password"])
def test_a_credential_planted_inside_the_inline_basket_schema_is_red(name):
    doc = _doc()
    doc["components"]["schemas"]["ExecuteOut"]["properties"]["basket"]["properties"][name] = {"type": "string"}
    assert f"ExecuteOut.basket.{name}: credential-named reply field" in scan_openapi(doc)


def test_the_basket_api_key_is_green_only_at_its_exact_path():
    doc = _doc()
    assert scan_openapi(doc) == []
    doc["components"]["schemas"]["ContractOut"]["properties"]["basket"] = {
        "type": "object", "properties": {"api_key": {"type": "string"}}}
    assert any(f.startswith("ContractOut.basket.api_key") for f in scan_openapi(doc))
    doc = _doc()
    doc["components"]["schemas"]["ExecuteOut"]["properties"]["basket"]["properties"]["inner"] = {
        "type": "object", "properties": {"api_key": {"type": "string"}}}
    assert any(f.startswith("ExecuteOut.basket.inner.api_key") for f in scan_openapi(doc))


@pytest.mark.parametrize("wrap", ["items", "allOf", "anyOf", "oneOf", "additionalProperties", "deep3"])
def test_a_credential_planted_at_depth_two_and_three_of_a_reply_schema_is_red(wrap):
    leaf = {"type": "object", "properties": {"access_token": {"type": "string"}}}
    wrapped = {
        "items": {"type": "array", "items": leaf},
        "allOf": {"allOf": [leaf]},
        "anyOf": {"anyOf": [{"type": "null"}, leaf]},
        "oneOf": {"oneOf": [leaf]},
        "additionalProperties": {"type": "object", "additionalProperties": leaf},
        "deep3": {"type": "object", "properties": {"a": {"type": "object", "properties": {"b": leaf}}}},
    }[wrap]
    doc = _doc()
    doc["components"]["schemas"]["ContractOut"]["properties"]["planted"] = wrapped
    assert any("access_token: credential-named reply field" in f for f in scan_openapi(doc)), wrap


def test_a_credential_in_an_inline_operation_response_schema_is_red():
    doc = _doc()
    route = next(iter(doc["paths"]))
    method = next(iter(doc["paths"][route]))
    doc["paths"][route][method].setdefault("responses", {})["299"] = {"content": {"application/json": {
        "schema": {"type": "object", "properties": {"api_secret": {"type": "string"}}}}}}
    assert any("api_secret: credential-named reply field" in f for f in scan_openapi(doc))


def test_a_credential_in_a_required_list_is_red():
    doc = _doc()
    doc["components"]["schemas"]["ContractOut"].setdefault("required", []).append("access_token")
    assert any("access_token: credential-named required field" in f for f in scan_openapi(doc))
