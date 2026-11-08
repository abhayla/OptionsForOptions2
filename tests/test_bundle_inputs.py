"""GC-MU step 2 item 2 (#517, REQ-048 AC-5): the bundle's build inputs are an allow-list.

Vite inlines ``import.meta.env.<NAME>`` into the built bundle. A backend credential reaches the browser through the
build only if (a) its variable carries the exposed prefix, (b) the config injects it (``define``/``loadEnv``), or (c) a
``.env*`` file holding it sits where Vite reads it. So:
- ``envPrefix: 'VITE_'`` is stated explicitly in ``frontend/vite.config.js`` (a changed default cannot widen it);
- every ``import.meta.env`` use in ``frontend/src`` names a REVIEWED variable or a Vite built-in, by a plain member
  access (a computed ``import.meta.env[x]`` or a destructure is refused: it could read anything);
- ``process.env`` never appears in ``frontend/src``; the config has no ``define`` and no ``loadEnv``;
- no ``.env*`` file is tracked under ``frontend/``.
Known limit: a variable read through a dependency's code is not seen here; the bundle value canary (item 3) is the
layer that sees the built output.
"""
import pathlib
import re
import subprocess

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

#: the reviewed build variables: name -> why the browser may hold it. A new name fails until it is listed here.
REVIEWED_VITE_VARS = {
    "VITE_ZERODHA_OPEN_ACCOUNT_URL": "the account-opening link (REQ-015 AC-11, ADR-175): a public signup page with the "
                                     "partner code in its query; navigation, never a connection (D2)",
}
#: Vite's own values (https://vite.dev/guide/env-and-mode): never a variable of ours.
VITE_BUILTINS = frozenset({"MODE", "BASE_URL", "PROD", "DEV", "SSR"})
SOURCE_SUFFIXES = {".js", ".ts", ".vue", ".mjs", ".jsx", ".tsx"}

ENV_USE_RE = re.compile(r"import\s*\.\s*meta\s*\.\s*env")
ENV_MEMBER_RE = re.compile(r"import\s*\.\s*meta\s*\.\s*env\s*\.\s*([A-Za-z_$][A-Za-z0-9_$]*)")


def scan_env_uses(name: str, text: str) -> list[str]:
    """Every ``import.meta.env`` must be followed by ``.NAME`` with NAME reviewed or built in."""
    found = []
    members = {m.start(): m.group(1) for m in ENV_MEMBER_RE.finditer(text)}
    for use in ENV_USE_RE.finditer(text):
        member = members.get(use.start())
        if member is None:
            found.append(f"{name}: import.meta.env used without a plain .NAME (computed or destructured)")
        elif member not in REVIEWED_VITE_VARS and member not in VITE_BUILTINS:
            found.append(f"{name}: import.meta.env.{member} is not on the reviewed list")
    if "process.env" in re.sub(r"\s+", "", text):
        found.append(f"{name}: process.env in browser code")
    return found


def scan_src(src: pathlib.Path) -> list[str]:
    files = [p for p in src.rglob("*") if p.is_file() and p.suffix in SOURCE_SUFFIXES]
    if not files:
        return [f"{src}: no source files discovered"]
    found = []
    for path in files:
        found.extend(scan_env_uses(path.relative_to(src).as_posix(), path.read_text(encoding="utf-8")))
    return found


def scan_config(text: str) -> list[str]:
    found = []
    if len(re.findall(r"\benvPrefix\b", text)) != 1 or not re.search(r"^\s*envPrefix:\s*'VITE_',\s*$", text, re.M):
        found.append("vite.config.js: envPrefix: 'VITE_' is not stated exactly once")
    if re.search(r"\bdefine\s*:", text):
        found.append("vite.config.js: a define block injects values into the bundle")
    if re.search(r"\bloadEnv\b", text):
        found.append("vite.config.js: loadEnv reads env files into the config")
    return found


def tracked_env_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--", "frontend"], cwd=ROOT,  # noqa: S607 - git from PATH
                         capture_output=True, text=True, check=True)
    return [f for f in out.stdout.splitlines() if pathlib.PurePosixPath(f).name.startswith(".env")]


# ---- the real tree ---------------------------------------------------------------------------------------------------

def test_every_env_use_in_frontend_src_is_reviewed_and_process_env_never_appears():
    assert scan_src(FRONTEND / "src") == []


def test_the_vite_config_states_the_prefix_and_injects_nothing():
    assert scan_config((FRONTEND / "vite.config.js").read_text(encoding="utf-8")) == []


def test_no_env_file_is_tracked_under_frontend():
    assert tracked_env_files() == []


def test_every_reviewed_variable_names_a_reason_and_carries_the_prefix():
    assert all(reason and name.startswith("VITE_") for name, reason in REVIEWED_VITE_VARS.items())


# ---- planted cases: each turns red -----------------------------------------------------------------------------------

@pytest.mark.parametrize(("planted", "expect"), [
    ("const k = import.meta.env.VITE_KITE_API_SECRET", "not on the reviewed list"),
    ("const k = import.meta.env.VITE_ENC_TOKEN", "not on the reviewed list"),
    ("const k = import.meta.env['VITE_X']", "without a plain .NAME"),
    ("const { VITE_X } = import.meta.env", "without a plain .NAME"),
    ("const k = import.meta . env . KITE_API_SECRET", "not on the reviewed list"),
    ("const k = process.env.KITE_API_SECRET", "process.env"),
    ("const k = process .env.X", "process.env"),
])
def test_a_planted_build_input_in_src_is_red(tmp_path, planted, expect):
    (tmp_path / "x.js").write_text(planted, encoding="utf-8")
    assert any(expect in f for f in scan_src(tmp_path)), planted


def test_the_reviewed_and_builtin_uses_are_green(tmp_path):
    (tmp_path / "x.js").write_text("a = import.meta.env.VITE_ZERODHA_OPEN_ACCOUNT_URL; b = import.meta.env.DEV",
                                   encoding="utf-8")
    assert scan_src(tmp_path) == []


@pytest.mark.parametrize(("config", "expect"), [
    ("export default { plugins: [] }", "envPrefix"),
    ("  envPrefix: 'VITE_',\n  envPrefix: 'KITE_',\n", "envPrefix"),
    ("  envPrefix: ['VITE_', 'KITE_'],\n", "envPrefix"),
    ("  envPrefix: 'VITE_',\n  define: { X: 1 },\n", "define"),
    ("  envPrefix: 'VITE_',\nconst e = loadEnv(mode, '.')\n", "loadEnv"),
])
def test_a_planted_config_input_is_red(config, expect):
    assert any(expect in f for f in scan_config(config)), config
