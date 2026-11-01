"""REQ-048 AC-5 (W-134): no browser asset and no server reply carries a vendor host, key or token (ADR-012).

Two scans, both ALLOW-LISTS (finding guard-as-forbidden-list): every URL found must be on a list of exact URLs/prefixes
that names the reason, every vendor domain must sit inside such an allowed URL, and every credential-shaped name/value
is a finding unless a named entry allows exactly that place.
- the BUILT bundle (``frontend/dist`` after ``npm run build``; the frontend CI job runs this file right after the build,
  and with ``CI`` set a missing ``frontend/dist`` FAILS; a local run without the build skips). Files are discovered, an
  unreadable file or an unknown extension is a finding (fail closed);
- every property name (at every depth: nested ``properties``, ``items``, ``allOf``/``anyOf``/``oneOf``, inline objects)
  and every string in ``docs/api/openapi.json`` (the shape of every ``/api`` reply).
#517 (GC-MU step 2): the PRIMARY guards are allow-lists - the reply inventory (tests_app/test_reply_inventory.py), the
reviewed build variables (tests/test_bundle_inputs.py), the exact URLs below - plus value canaries (a dist built with a
canary in every backend credential variable holds none; the API door refuses a reply holding a registered credential
value). The name scans here are the second layer.
Known bypasses, stated on purpose (out of the threat model): a host or key hidden by deliberate encoding (base64,
``atob``, array joins, a computed property name or string) is NOT seen; a compromised dependency or a browser
extension is not in scope; ESLint (``no-restricted-syntax`` on vendor hosts) is a further layer.
Planted cases prove each scan can turn red.
"""
import ipaddress
import json
import os
import pathlib
import re
import urllib.parse

import pytest

pytestmark = pytest.mark.repo_scan  # reads the built bundle and the openapi file

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"
OPENAPI = ROOT / "docs" / "api" / "openapi.json"
WORKFLOW = ROOT / ".github" / "workflows" / "app-tests.yml"
ENV_EXAMPLE = ROOT / ".env.example"

#: every URL the built bundle may hold, compared EXACTLY on its parsed (scheme, host, port, path), with the reason
#: (#517: no prefixes; a query or fragment is not compared). Anything else with a ``scheme://`` is a finding, whatever
#: its host. Vendor domains are matched separately and must lie inside one of these.
ALLOWED_URLS = {
    ("http", "localhost", None, ""): "the dev-server default inside the library code (no port, no path)",
    ("http", "www.w3.org", None, "/2000/svg"): "XML namespace string (SVG), never fetched",
    ("http", "www.w3.org", None, "/1999/xlink"): "XML namespace string (xlink), never fetched",
    ("http", "www.w3.org", None, "/1998/Math/MathML"): "XML namespace string (MathML), never fetched",
    ("https", "kite.zerodha.com", None, "/connect/basket"): "the Kite basket form the owner presses Place on "
                                                           "(frontend/src/lib/execute.js; navigation, ADR-054)",
    ("https", "kite.zerodha.com", None, "/positions"): "the Kite positions page the owner opens (execute.js)",
    ("https", "kite.zerodha.com", None, "/orders"): "the Kite order book link (execute.js KITE_ORDER_BOOK_URL, used by "
                                                   "TwoBasketStepper.vue); a link, not a connection",
    ("https", "signup.zerodha.com", None, "/"): "the account-opening page (VITE_ZERODHA_OPEN_ACCOUNT_URL, D2); the "
                                               "partner code rides in the query; navigation, never a connection",
    ("https", "vuejs.org", None, "/error-reference/"): "a documentation link inside Vue's own warning text",
}
#: vendor domains: found anywhere (with or without a scheme, after un-escaping slashes and joining split literals) they
#: are a finding unless they lie inside an allowed URL above.
VENDOR_DOMAIN_RE = re.compile(r"[A-Za-z0-9.@-]*(?:kite\.trade|zerodha\.com)", re.I)
#: the source modules whose chunks may name a public ``api_key`` (the Kite basket form posts the app's PUBLIC key to
#: Kite; the secret and the access token never leave the server). #517: pinned to the SOURCE module through Vite's
#: build manifest (``dist/.vite/manifest.json``, ``build.manifest`` in vite.config.js), never to a chunk-name pattern.
#: A module that becomes a shared chunk (no ``src`` in the manifest) is matched by its chunk ``name`` AND by being
#: imported from an allowed page entry. No manifest: no exemption (fail closed).
API_KEY_SOURCES = {
    "src/pages/ExecuteStrategyPage.vue": "the Execute page; holds BasketForm.vue's hidden api_key input",
    "src/lib/execute.js": "basketFormFields: checks the reply's {url, api_key, data} shape",
}
MANIFEST = pathlib.PurePosixPath(".vite/manifest.json")
#: reply fields: the exact schema path (``Schema.prop.prop``) that may be named ``api_key``, with the reason.
API_KEY_ALLOWED_PATHS = {
    "ExecuteOut.basket.api_key": "the Kite basket form's PUBLIC api_key (the secret and the token never leave the server)",  # noqa: E501
}

TEXT_EXTENSIONS = {".js", ".css", ".html", ".map", ".json", ".txt", ".svg"}
BINARY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".webp"}

#: a URL token: ANY ``scheme://`` (#517: whatever its host, so an IP literal or a bracketed IPv6 is a URL too), or a
#: protocol-relative ``//host`` right after a quote (a regex literal such as ``/^\/\/i.test/`` is not one). It ends at
#: a quote, space, bracket or backslash. A scheme right after a backslash is a regex escape in library code (axios:
#: ``\w+:\/\/``), not a URL; a deliberately escaped URL string is out of scope (a known bypass, like encoding).
URL_RE = re.compile(r"(?:(?<![\\A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]*://|(?<=[\"'`])//(?=[A-Za-z0-9\[]))[^\s\"'`<>()\\]*")
CRED_NAME_RE = re.compile(
    r"(access[_-]?token|refresh[_-]?token|request[_-]?token|public[_-]?token|api[_-]?secret|client[_-]?secret|"
    r"enc[_-]?token|kite[_-]?session)", re.I)
#: reply fields only: the word ``password`` is ordinary text/library code in a bundle (input type, landing copy)
REPLY_CRED_NAME_RE = re.compile(CRED_NAME_RE.pattern[:-1] + "|password)", re.I)
API_KEY_NAME_RE = re.compile(r"api[_-]?key", re.I)
#: a credential name followed by a value of a real key's length: a key-like name, ``=`` or ``:``, then 16+ characters
CRED_VALUE_RE = re.compile(
    r"(api[_-]?key|access[_-]?token|api[_-]?secret|secret|enc[_-]?token|request[_-]?token)[\"']?\s*[:=]\s*[\"']?"
    r"[A-Za-z0-9]{16,}", re.I)
_SPLIT_LITERAL_RE = re.compile(r"[\"'`]\s*\+\s*[\"'`]")  # a literal, plus, a literal: joined into one string


def _normalise(text: str) -> str:
    """Un-escape slashes (``wss:\\/\\/``) and join adjacent string literals, so a split host is one host."""
    return _SPLIT_LITERAL_RE.sub("", text.replace("\\/", "/"))


def url_refusal(url: str) -> str | None:
    """None when ``url`` is on ALLOWED_URLS exactly; else the reason it is refused."""
    if url.startswith("//"):
        url = "https:" + url
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return "does not parse"
    host = (parts.hostname or "").lower()
    if "@" in parts.netloc:
        return "carries userinfo"
    if parts.netloc.startswith("[") or _is_ip(host):
        return "names an IP literal"
    if ".." in parts.path or "%" in parts.path:
        return "has '..' or '%' in its path"
    if (parts.scheme.lower(), host, port, parts.path) not in ALLOWED_URLS:
        return "is not on the exact allow-list"
    return None


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def scan_urls(name: str, text: str) -> list[str]:
    """Every URL token must be allowed exactly; the text left after removing them must hold no vendor domain."""
    text = _normalise(text)
    found = []
    rest = []
    last = 0
    for m in URL_RE.finditer(text):
        rest.append(text[last:m.start()])
        last = m.end()
        refusal = url_refusal(m.group(0))
        if refusal:
            found.append(f"{name}: url {m.group(0)[:60]} {refusal} (allow-list)")
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


def api_key_files(root: pathlib.Path) -> set[str]:
    """The dist files built from API_KEY_SOURCES, read from the build manifest; empty without one (fail closed)."""
    try:
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if not isinstance(manifest, dict):
        return set()
    files = set()
    for entry in manifest.values():
        if isinstance(entry, dict) and entry.get("src") in API_KEY_SOURCES and isinstance(entry.get("file"), str):
            files.add(entry["file"])
            for key in entry.get("imports") or ():
                shared = manifest.get(key)
                if (isinstance(shared, dict) and "src" not in shared and isinstance(shared.get("file"), str)
                        and any(shared.get("name") == pathlib.PurePosixPath(s).stem for s in API_KEY_SOURCES)):
                    files.add(shared["file"])
    return files


def canary_value(variable: str) -> str:
    """The canary the frontend CI build sets for ``variable`` (app-tests.yml Build step)."""
    return "ofocanaryexample" + re.sub(r"[^a-z0-9]", "", variable.lower())


def backend_credential_variables() -> list[str]:
    """Every backend variable named in .env.example that holds a credential or a connection string."""
    names = re.findall(r"^([A-Z][A-Z0-9_]*)=", ENV_EXAMPLE.read_text(encoding="utf-8"), re.M)
    return sorted(n for n in names if re.search(r"SECRET|KEY|TOKEN|PASSWORD|DATABASE_URL", n))


def scan_canaries(root: pathlib.Path, values: list[str]) -> list[str]:
    """A dist built with a canary in every backend credential variable holds none of them, in any file."""
    found = []
    for path in (p for p in root.rglob("*") if p.is_file()):
        data = path.read_bytes()
        found.extend(f"{path.relative_to(root).as_posix()}: holds the canary of a backend credential variable"
                     for value in values if value.encode() in data)
    return found


def scan_dir(root: pathlib.Path) -> list[str]:
    files = [p for p in root.rglob("*") if p.is_file()]
    if not files:
        return [f"{root}: no files discovered (an empty bundle is not a clean bundle)"]
    allowed = api_key_files(root)
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
        found.extend(scan_text(rel, text, api_key_ok=rel in allowed))
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

def _require_dist() -> None:
    if not DIST.is_dir():
        message = "frontend/dist is absent: run `npm run build` in frontend/ (CI runs this right after the build step)"
        # Only the frontend job's scan step sets OFO_REQUIRE_BUNDLE_SCAN (app-tests.yml): there a missing build is a
        # failed scan, never a skipped one. Not `CI`: GitHub sets CI on every runner, and the kit's tests job runs this
        # file over tests/ without building the frontend (row 6 verifier round 2).
        if os.environ.get("OFO_REQUIRE_BUNDLE_SCAN") == "1":
            pytest.fail(message)
        pytest.skip(message)


def test_the_built_bundle_names_no_vendor_host_and_holds_no_key_or_token():
    _require_dist()
    assert scan_dir(DIST) == []


def test_the_built_bundle_holds_no_canary_of_a_backend_credential_variable():
    """#517 item 3b: the CI build sets every backend credential variable to its canary (asserted below); none of them
    may reach any file of the build."""
    _require_dist()
    assert scan_canaries(DIST, [canary_value(v) for v in backend_credential_variables()]) == []


def _step_env(workflow: str, step: str) -> dict[str, str]:
    """The ``env:`` of the workflow step named ``step`` (a plain text read: the kit suite has no YAML library)."""
    lines = workflow.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == f"- name: {step}")
    indent = len(lines[start]) - len(lines[start].lstrip())
    env: dict[str, str] = {}
    in_env = False
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped.startswith("- ") and len(line) - len(line.lstrip()) <= indent:
            break
        if stripped == "env:":
            in_env = True
            continue
        if in_env and ":" in stripped and not stripped.startswith("#"):
            if len(line) - len(line.lstrip()) <= indent + 2:
                in_env = False
                continue
            name, _, value = stripped.partition(":")
            env[name.strip()] = value.split("#")[0].strip().strip("'\"")
    return env


def test_the_ci_build_sets_a_canary_in_every_backend_credential_variable():
    variables = backend_credential_variables()
    assert {"BROKER_TOKEN_KEY", "KITE_API_SECRET"} <= set(variables)
    env = _step_env(WORKFLOW.read_text(encoding="utf-8"), "Build")
    assert {v: env.get(v) for v in variables} == {v: canary_value(v) for v in variables}


def test_every_reply_shape_is_free_of_credential_fields_and_vendor_hosts():
    assert scan_openapi(json.loads(OPENAPI.read_text(encoding="utf-8"))) == []


def test_every_allow_list_entry_names_a_reason():
    reasons = [*ALLOWED_URLS.values(), *API_KEY_SOURCES.values(), *API_KEY_ALLOWED_PATHS.values()]
    assert all(reasons)


def test_with_ci_set_and_no_build_the_bundle_scan_fails_and_without_ci_it_skips(monkeypatch):
    real_is_dir = pathlib.Path.is_dir
    monkeypatch.setattr(pathlib.Path, "is_dir", lambda self: False if self == DIST else real_is_dir(self))
    monkeypatch.setenv("OFO_REQUIRE_BUNDLE_SCAN", "1")  # what the frontend job's scan step sets
    for real in (test_the_built_bundle_names_no_vendor_host_and_holds_no_key_or_token,
                 test_the_built_bundle_holds_no_canary_of_a_backend_credential_variable):
        with pytest.raises(pytest.fail.Exception):
            real()
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
    "fetch('https://kite.zerodha.com/orders/x')",  # the vendor host, a path that is not an allowed exact path
    "fetch('https://kite.zerodha.com/connect/basketx')",  # an allowed path as a PREFIX (#517: exact only)
    "fetch('https://api.zerodha.com/x')",
    "fetch('https://kite.zerodha.com.evil.example/connect/basket')",  # allowed host text, different host
    "fetch('ftp://files.example.org/a')",  # any scheme is a URL
])
def test_a_planted_vendor_host_in_a_bundle_file_is_red(tmp_path, planted):
    _bundle(tmp_path, "index-abcd1234.js", "var a=1;" + planted)
    assert any("allow-list" in f for f in scan_dir(tmp_path)), planted


#: the round-2 URL escapes (#517 Class line): each passed the prefix/dotted-host scan; each is red now
@pytest.mark.parametrize(("planted", "reason"), [
    ("fetch('http://127.0.0.1:8000/api/x')", "IP literal"),
    ("fetch('https://[::1]/x')", "IP literal"),
    ("new WebSocket('ws://[::1]:8000')", "IP literal"),
    ("fetch('https://kite.zerodha.com/connect/basket/../../oms/orders')", "'..'"),
    ("fetch('https://kite.zerodha.com/connect/basket/%2e%2e/oms')", "'%'"),
    ("fetch('https://user:pw@kite.zerodha.com/positions')", "userinfo"),
])
def test_a_round_two_url_escape_is_red(tmp_path, planted, reason):
    found = scan_dir(_bundle(tmp_path, "index-abcd1234.js", planted))
    assert any(reason in f for f in found), (planted, found)


def test_the_allowed_urls_are_green(tmp_path):
    _bundle(tmp_path, "index-abcd1234.js",
            'a="https://kite.zerodha.com/connect/basket";b="https://kite.zerodha.com/positions";'
            'c="http://localhost";d="http://www.w3.org/2000/svg";e=`https://vuejs.org/error-reference/#runtime-${n}`;'
            'f="https://kite.zerodha.com/orders";g="https://signup.zerodha.com/?c=AB1234";'
            'h=/^\\w+:\\/\\/[^/]+\\//')  # the regex literal in axios' own code (measured on the main checkout's dist)
    assert scan_dir(tmp_path) == []


def test_the_order_book_link_is_allowed_only_as_its_exact_url():
    assert url_refusal("https://kite.zerodha.com/orders") is None
    for wider in ("https://kite.zerodha.com/orders/", "https://kite.zerodha.com/ordersx", "http://kite.zerodha.com/orders",
                  "https://kite.zerodha.com:444/orders"):
        assert url_refusal(wider) == "is not on the exact allow-list", wider


PLANTED_VALUE = "abcd1234" + "efgh5678"  # built at run time so the repo's own secret hook sees no key-shaped literal


@pytest.mark.parametrize(("key", "sep"), [("api_key", "="), ("apiKey", "="), ("apiKey", ":"), ("API_KEY", ":"),
                                          ("secret", ":")])
def test_a_planted_key_value_in_a_bundle_file_is_red(tmp_path, key, sep):
    _bundle(tmp_path, "index-abcd1234.js", f"x('{key}{sep}{PLANTED_VALUE}')")
    assert any("credential-shaped value" in f for f in scan_dir(tmp_path)), (key, sep)


@pytest.mark.parametrize("planted", ["res.access_token", "res.accessToken", "res.ACCESS_TOKEN", "x.apiSecret",
                                     "res.enc_token", "s.kite_session"])
def test_a_planted_credential_name_is_red_even_in_an_api_key_allowed_chunk(tmp_path, planted):
    _manifest_dist(tmp_path, {"src/lib/execute.js": "assets/execute-abcd1234.js"})
    _bundle(tmp_path, "execute-abcd1234.js", "const t = " + planted)
    assert any("credential name" in f for f in scan_dir(tmp_path)), planted


# ---- value canaries in the bundle (#517 item 3b): the four round-2 bundle escapes are red by VALUE -------------------

CANARIES = [canary_value(v) for v in ("KITE_API_SECRET", "BROKER_TOKEN_KEY")]


@pytest.mark.parametrize("planted", [
    "const enc_token = '{c}'",  # a name no list held
    "const kite_session = '{c}'",
    "headers: {{ Authorization: 'token ' + 'k:' + '{c}' }}",  # an Authorization header built by concatenation
    "x({{secret:'{c}'}})",  # secret:value
])
def test_a_round_two_bundle_escape_is_red_by_its_canary_value(tmp_path, planted):
    _bundle(tmp_path, "index-abcd1234.js", planted.format(c=CANARIES[0]))
    assert scan_canaries(tmp_path, CANARIES) == ["assets/index-abcd1234.js: holds the canary of a backend credential "
                                                 "variable"]


def test_a_dist_without_any_canary_is_green(tmp_path):
    _bundle(tmp_path, "index-abcd1234.js", "const a = 'ofocanaryexample'")  # the prefix alone is not a canary
    assert scan_canaries(tmp_path, CANARIES) == []


def test_mutant_without_the_canary_list_the_canary_passes(tmp_path):
    _bundle(tmp_path, "index-abcd1234.js", f"const a = '{CANARIES[1]}'")
    assert scan_canaries(tmp_path, []) == []  # the guard is the values list: empty, it sees nothing
    assert scan_canaries(tmp_path, CANARIES)


# ---- the api_key exemption is pinned to its source module through the build manifest (#517) ------------------------

def _manifest_dist(tmp_path: pathlib.Path, sources: dict[str, str], shared: dict[str, str] | None = None):
    """A planted dist manifest: page entries ``src -> file`` (each importing every shared chunk) and shared chunks
    ``name -> file`` (no ``src``, as Vite writes a chunk imported by several pages)."""
    shared = shared or {}
    manifest = {src: {"file": file, "src": src, "isDynamicEntry": True,
                      "imports": [f"_{pathlib.PurePosixPath(f).name}" for f in shared.values()]}
                for src, file in sources.items()}
    manifest |= {f"_{pathlib.PurePosixPath(file).name}": {"file": file, "name": name} for name, file in shared.items()}
    (tmp_path / ".vite").mkdir(exist_ok=True)
    (tmp_path / ".vite" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_the_api_key_is_green_in_the_chunks_built_from_the_basket_modules(tmp_path):
    _manifest_dist(tmp_path, {"src/pages/ExecuteStrategyPage.vue": "assets/ExecuteStrategyPage-Q1w2E3r4.js"},
                   shared={"execute": "assets/execute-Z9y8X7w6.js"})
    _bundle(tmp_path, "ExecuteStrategyPage-Q1w2E3r4.js", "name:'api_key'")
    _bundle(tmp_path, "execute-Z9y8X7w6.js", "b.api_key")
    assert scan_dir(tmp_path) == []


@pytest.mark.parametrize("name", ["execute-abcd1234.js", "ExecuteStrategyPage-abcd1234.js", "execute-evil-extra.js",
                                  "other-abcd1234.js"])
def test_without_a_manifest_no_chunk_gets_the_api_key_exemption(tmp_path, name):
    _bundle(tmp_path, name, "name:'api_key'")
    assert any("api_key" in f for f in scan_dir(tmp_path)), name


def test_any_eight_character_suffix_chunk_not_built_from_the_modules_is_red(tmp_path):
    """The round-2 escape: ``execute-<any 8 chars>.js`` matched the name regex. Now only the manifest's file is."""
    _manifest_dist(tmp_path, {"src/pages/ExecuteStrategyPage.vue": "assets/ExecuteStrategyPage-Q1w2E3r4.js"})
    _bundle(tmp_path, "ExecuteStrategyPage-Q1w2E3r4.js", "")
    _bundle(tmp_path, "execute-AAAAAAAA.js", "name:'api_key'")  # a chunk name the old regex exempted
    _bundle(tmp_path, "ExecuteStrategyPage-BBBBBBBB.js", "name:'api_key'")
    found = scan_dir(tmp_path)
    assert {f.split(":")[0] for f in found if "api_key" in f} == {"assets/execute-AAAAAAAA.js",
                                                                  "assets/ExecuteStrategyPage-BBBBBBBB.js"}


def test_a_shared_chunk_named_like_the_module_but_not_imported_by_the_page_is_red(tmp_path):
    _manifest_dist(tmp_path, {"src/pages/OtherPage.vue": "assets/OtherPage-Q1w2E3r4.js"},
                   shared={"execute": "assets/execute-Z9y8X7w6.js"})
    _bundle(tmp_path, "execute-Z9y8X7w6.js", "b.api_key")
    assert any("api_key" in f for f in scan_dir(tmp_path))


def test_an_api_key_planted_in_the_manifest_itself_is_red(tmp_path):
    _manifest_dist(tmp_path, {"src/pages/ExecuteStrategyPage.vue": "assets/ExecuteStrategyPage-Q1w2E3r4.js"})
    (tmp_path / ".vite" / "manifest.json").write_text('{"x": {"file": "a.js", "api_key": 1}}', encoding="utf-8")
    assert any(f.startswith(".vite/manifest.json") and "api_key" in f for f in scan_dir(tmp_path))


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
