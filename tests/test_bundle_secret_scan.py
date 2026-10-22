"""REQ-048 AC-5 (W-134): no browser asset and no server reply carries a vendor host, key or token (ADR-012).

Two scans, both ALLOW-LISTS (finding guard-as-forbidden-list): every host found must be on a list that names the
reason, and every credential-shaped name/value is a finding unless a named entry allows exactly that place.
- the BUILT bundle (``frontend/dist`` after ``npm run build``; CI builds first, a local run without the build skips
  with the reason below); files are discovered, an unreadable file or an unknown extension is a finding (fail closed);
- every property name and every string in ``docs/api/openapi.json`` (the shape of every ``/api`` reply).
Planted cases prove each scan can turn red.
"""
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"
OPENAPI = ROOT / "docs" / "api" / "openapi.json"

#: every host the built bundle may name, with the reason (anything else is a vendor host / unknown host: a finding)
ALLOWED_HOSTS = {
    "kite.zerodha.com": "the Kite basket/orders/positions pages the owner presses Place on (frontend/src/lib/execute.js)",  # noqa: E501
    "localhost": "the dev-server default inside the library code; never a vendor",
    "vuejs.org": "a documentation link inside Vue's own warning text",
    "www.w3.org": "XML namespace strings (SVG/MathML), never fetched",
}
#: the one place a public ``api_key`` field may appear: the Kite basket form (it posts the app's PUBLIC key to Kite;
#: the secret and the access token never leave the server). Bundle files are named by their built-chunk prefix.
API_KEY_ALLOWED_BUNDLE_PREFIXES = ("execute-", "ExecuteStrategyPage-")
API_KEY_ALLOWED_SCHEMAS = {"Basket": "ExecuteOut.basket: the Kite basket form's public api_key, url and data"}

TEXT_EXTENSIONS = {".js", ".css", ".html", ".map", ".json", ".txt", ".svg"}
BINARY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".webp"}

HOST_RE = re.compile(r"(?:https?|wss?)://([A-Za-z0-9.\-]+)", re.I)
CRED_NAME_RE = re.compile(
    r"(access_token|refresh_token|request_token|public_token|api_secret|client_secret|enctoken)", re.I)
#: reply fields only: the word ``password`` is ordinary text/library code in a bundle (input type, landing copy)
REPLY_CRED_NAME_RE = re.compile(CRED_NAME_RE.pattern[:-2] + "|password)", re.I)
API_KEY_NAME_RE = re.compile(r"api_key", re.I)
#: a credential name followed by a value of a real key's length: ``api_key=abcd...`` / ``"access_token":"..."``
CRED_VALUE_RE = re.compile(
    r"(api_key|access_token|api_secret|enctoken|request_token)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9]{16,}", re.I)


def scan_text(name: str, text: str, *, api_key_ok: bool) -> list[str]:
    found = []
    for m in HOST_RE.finditer(text):
        if m.group(1).lower() not in ALLOWED_HOSTS:
            found.append(f"{name}: host {m.group(1)} is not on the allow-list")  # noqa: PERF401
    for m in CRED_NAME_RE.finditer(text):
        found.append(f"{name}: credential name {m.group(1)}")  # noqa: PERF401
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
        found.extend(scan_text(rel, text, api_key_ok=path.name.startswith(API_KEY_ALLOWED_BUNDLE_PREFIXES)))
    return found


def scan_openapi(doc: dict) -> list[str]:
    found = []
    schemas = (doc.get("components") or {}).get("schemas")
    if not schemas:
        return ["openapi: no schemas discovered"]
    for schema_name, schema in schemas.items():
        for prop in (schema.get("properties") or {}):
            if REPLY_CRED_NAME_RE.search(prop):
                found.append(f"{schema_name}.{prop}: credential-named reply field")
            elif API_KEY_NAME_RE.search(prop) and schema_name not in API_KEY_ALLOWED_SCHEMAS:
                found.append(f"{schema_name}.{prop}: api_key reply field outside the allow-list")
    for m in HOST_RE.finditer(json.dumps(doc)):
        if m.group(1).lower() not in ALLOWED_HOSTS:
            found.append(f"openapi: host {m.group(1)} is not on the allow-list")  # noqa: PERF401
    for m in CRED_VALUE_RE.finditer(json.dumps(doc)):
        found.append(f"openapi: credential-shaped value {m.group(0)[:24]}")  # noqa: PERF401
    return found


# ---- the real artefacts --------------------------------------------------------------------------------------------

def test_the_built_bundle_names_no_vendor_host_and_holds_no_key_or_token():
    if not DIST.is_dir():
        pytest.skip("frontend/dist is absent: run `npm run build` in frontend/ (CI runs this after the build step)")
    assert scan_dir(DIST) == []


def test_every_reply_shape_is_free_of_credential_fields_and_vendor_hosts():
    assert scan_openapi(json.loads(OPENAPI.read_text(encoding="utf-8"))) == []


def test_every_allow_list_entry_names_a_reason():
    assert all(ALLOWED_HOSTS.values()) and all(API_KEY_ALLOWED_SCHEMAS.values())


# ---- planted cases: each scan turns red ------------------------------------------------------------------------------

@pytest.mark.parametrize("planted", [
    "const s = new WebSocket('wss://ws.kite.trade/?api_key=x')",
    "fetch('https://api.kite.trade/quote')",
    "const u = 'https://api.upstox.com/v2'",
])
def test_a_planted_vendor_host_in_a_bundle_file_is_red(tmp_path, planted):
    (tmp_path / "index-abc.js").write_text("var a=1;" + planted, encoding="utf-8")
    assert any("not on the allow-list" in f for f in scan_dir(tmp_path))


def test_a_planted_key_value_in_a_bundle_file_is_red(tmp_path):
    (tmp_path / "index-abc.js").write_text("x('api_key=abcd1234efgh5678')", encoding="utf-8")
    assert any("credential" in f for f in scan_dir(tmp_path))


def test_a_planted_access_token_name_is_red_even_in_an_api_key_allowed_chunk(tmp_path):
    (tmp_path / "execute-abc.js").write_text("const t = res.access_token", encoding="utf-8")
    assert any("access_token" in f for f in scan_dir(tmp_path))


def test_a_planted_api_key_outside_the_basket_chunks_is_red_and_inside_is_green(tmp_path):
    (tmp_path / "other-abc.js").write_text("name:'api_key'", encoding="utf-8")
    assert any("api_key" in f for f in scan_dir(tmp_path))
    ok = tmp_path / "ok"
    ok.mkdir()
    (ok / "execute-abc.js").write_text("name:'api_key'", encoding="utf-8")
    assert scan_dir(ok) == []


def test_an_unreadable_file_an_unknown_type_and_an_empty_bundle_fail_closed(tmp_path):
    (tmp_path / "bad.js").write_bytes(b"\xff\xfe\x00bad")
    (tmp_path / "x.wasm").write_bytes(b"\x00asm")
    found = scan_dir(tmp_path)
    assert any("unreadable" in f for f in found) and any("unknown file type" in f for f in found)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert scan_dir(empty)


def test_a_planted_access_token_field_in_a_response_model_is_red():
    doc = json.loads(OPENAPI.read_text(encoding="utf-8"))
    doc["components"]["schemas"]["ContractOut"]["properties"]["access_token"] = {"type": "string"}
    assert scan_openapi(doc) == ["ContractOut.access_token: credential-named reply field"]
    doc = json.loads(OPENAPI.read_text(encoding="utf-8"))
    doc["components"]["schemas"]["ContractOut"]["properties"]["api_key"] = {"type": "string"}
    assert any("api_key reply field" in f for f in scan_openapi(doc))
    doc = json.loads(OPENAPI.read_text(encoding="utf-8"))
    doc["info"]["description"] = "see wss://ws.kite.trade"
    assert any("ws.kite.trade" in f for f in scan_openapi(doc))
