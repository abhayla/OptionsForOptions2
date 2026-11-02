# ruff: noqa: E501
"""REQ-167 AC-6 guard: a business number moved to a setting must not come back into code, and no setting may be unread.

Spec basis: REQ-167 AC-6 "A guard test fails when a module wired to settings holds a business literal again, and when
a registry key has no reader."; ADR-222 (1) "No rupee amount, rate, percentage or threshold that changes a figure a
user sees is typed in code".

Reads source as text / AST only (this tree never imports ofo_app).

1. Reader check: every key of ``backend/ofo/settings/registry.json`` appears by its exact string in ``backend/`` or
   ``frontend/src/`` (outside the registry), or is built by a key pattern of ``backend/ofo/settings/calc.py`` that is
   expanded here explicitly. A key the scan cannot resolve FAILS with "no reader found for <key>".
2. Literal check: the registry ``source`` ("was <file> <NAME>") names the old home. ``OLD_HOMES`` is the explicit table
   {file -> [(old constant name, key)]}; the old NAME must not be defined again in that file, and no module-level
   assignment of a Python file may bind the exact fractional default (``Decimal("0.065")`` / ``0.065``) again.
   Fail closed: a source whose file is in neither ``OLD_HOMES`` nor ``RETIRED_HOMES``, a table file that is gone or
   cannot be parsed, or a table name that no registry source mentions, fails with its key.
3. ``KNOWN_LEFTOVERS``: gaps found by the scan, listed so the guard is green but the gaps stay visible; each is
   re-checked (its marker must still be in the file), so a fixed or moved leftover fails until its row is removed.
"""
from __future__ import annotations

import ast
import contextlib
import json
import pathlib
import re
from decimal import Decimal, InvalidOperation

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend" / "src"
REGISTRY = BACKEND / "ofo" / "settings" / "registry.json"
CALC = BACKEND / "ofo" / "settings" / "calc.py"

# {file under backend/ or frontend/src/ -> [(old constant name, key it became)]}  (from the registry ``source`` fields)
OLD_HOMES: dict[str, list[tuple[str, str]]] = {
    "ofo_app/live_market.py": [("LIVE_RATE", "pricing.risk_free_rate")],
    "ofo/marketdata/forward.py": [("QUALITY_WIDTH", "pricing.forward_quality_width"),
                                  ("STRIKES_NEAR", "pricing.forward_strikes_near"),
                                  ("MIN_STRIKES", "pricing.forward_min_strikes")],
    "ofo/scenario/config.py": [("DEFAULT_CONFIGS", "scenarios.nifty_step_points")],
    "ofo/strategy/placement.py": [("QUICK_PICK_DISTANCES", "scenarios.strangle_quick_pick_nifty_1")],
    "ofo/engine/target.py": [("TARGET_SPAN", "scenarios.target_span")],
    "ofo/outcome/service.py": [("PAYOFF_TABLE_STEPS", "scenarios.payoff_step_1"),
                               ("PAYOFF_TABLE_DEFAULT_STEPS", "scenarios.payoff_default_step_nifty"),
                               ("SD_HORIZON_DAYS", "scenarios.sd_horizon_days")],
    "ofo_app/live_push.py": [("MIN_PUSH_INTERVAL", "speeds.open_strategy_seconds")],
    "ofo_app/calc_speeds.py": [("_STAND_IN", "speeds.per_option_seconds")],  # GC-MU stand-in, swapped at the integration
    "ofo/marketdata/feed_health.py": [("FEED_STALE", "detection.feed_stale_seconds"),
                                      ("RECONNECT_WINDOW", "detection.feed_reconnect_window_seconds")],
    "ofo/entitlements/engine.py": [("TRIAL_DAYS_DEFAULT", "billing.trial_days"),
                                   ("REFERRAL_DAYS_DEFAULT", "billing.referral_days")],
    "ofo/execution/freeze.py": [("STALE_AFTER_DAYS", "data.freeze_file_stale_days")],
    "ofo_app/chain_push.py": [("MAX_STRIKES_EACH_SIDE", "limits.chain_strikes_each_side")],
    "ofo_app/strategy_price_history.py": [("MAX_DAYS", "limits.history_max_days")],
    "ofo_app/routes/leg_picker.py": [("WIDTHS", "limits.leg_picker_width_1")],
    "lib/legPicker.js": [("LOT_CHOICES", "limits.lot_choices")],
    "lib/guided.js": [("RANGE_STEP", "limits.range_step"), ("RANGE_CAP", "limits.range_cap_nifty")],
    "pages/OptionChainPage.vue": [("UNDO_MS", "other.undo_one_leg_seconds")],
    "lib/legEdit.js": [("CLEAR_UNDO_MS", "other.undo_clear_all_seconds"), ("MULTIPLIER_MAX", "limits.multiplier_max")],
    "stores/chainSelection.js": [("MAX_LOTS", "limits.max_lots")],
    "ofo_app/paper_settlement.py": [("SETTLE_FROM", "facts.paper_settle_from"),
                                    ("RETRY_UNTIL", "facts.paper_retry_until")],
    "ofo/adjustment/detection.py": [("NEAR_LEVEL_THRESHOLD_PERCENT", "adjustments.near_level_percent")],
    "ofo/adjustment/playbook_eval.py": [("_GAP_UNTIL", "adjustments.gap_at_open_until")],
    "ofo/adjustment/compare.py": [("CURVE_RANGE", "adjustments.compare_range_percent"),
                                  ("CURVE_STEPS", "adjustments.compare_steps"),
                                  ("MOVES", "adjustments.compare_move_small")],
    "ofo_app/catalogue_picker.py": [("_PUBLISH_TIME", "facts.contract_list_publish_time")],
    "ofo/broker/session.py": [("KITE_EXPIRY_TIME_IST", "facts.kite_session_expiry")],
}
# Old homes that are legitimately gone: the file must stay absent (a data file the values were read from).
RETIRED_HOMES = {"ofo/adjustment/approach_config.json": "adjustments.short_delta_weekly"}
# Old homes that are not a file constant: the exact text that must not be read in backend code again.
RETIRED_ENV = {"CATALOGUE_MAX_DELIST_PERCENT": "data.max_delist_percent"}
# Registry sources whose "was <file>" token is in none of the above only because the file is a second home of the
# same value as another row (listed so the cross-check is explicit, not silent).
SECOND_HOMES = {"ofo_app/routes/outcome.py": "limits.max_lots",  # LegIn.lots le=10000, not a constant
                # REQ-170 table presets: the reference ofo/adjustment/alert_presets.preset_for is tested equal to
                "ofo/adjustment/alert_gate.py": "alerts.intraday.daily_cap"}

# Gaps the scan found and this round does not fix. {id: (file, marker text still present, reason, follow-up)}
KNOWN_LEFTOVERS: dict[str, tuple[str, str, str, str]] = {
    "alert_gate_presets": (
        "ofo/adjustment/alert_gate.py", "INTRADAY = Preset(",
        "the gate's INTRADAY / WEEKLY / MONTHLY stay as the REQ-170 table the settings resolver is tested equal to; "
        "no caller may build a Preset other than alert_presets.preset_for",
        "follow-up: GC-ALERT1 worker step reads preset_for; then move the presets into the gate's tests"),
    "broker_session_trigger_0600": (
        "ofo_app/alembic/versions/0007_broker_sessions.py", "06:00",
        "the broker_sessions DB trigger stamps expected_expiry at 06:00 IST (a migration; settings cannot reach it)",
        "follow-up: a new migration that drops the stamp and lets the app write facts.kite_session_expiry"),
    "market_hours_timeutil": (
        "ofo/timeutil.py", "SESSION_OPEN",
        "market hours and expiry close are typed in timeutil and not yet wired to settings",
        "follow-up: wire to a facts.* group"),
}


# ---- helpers (text / AST only) ---------------------------------------------------------------------------------
def _code_files() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for base, exts in ((BACKEND, {".py", ".js", ".json"}), (FRONTEND, {".js", ".vue", ".ts"})):
        out.extend(p for p in base.rglob("*")
                   if p.is_file() and p.suffix in exts and "node_modules" not in p.parts and "__pycache__" not in p.parts)
    return out


def _load_keys() -> list[dict]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["settings"]


def _calc_consts(calc_text: str) -> dict:
    """Module-level literal constants of calc.py (string key names and counts) by AST."""
    out = {}
    for node in ast.parse(calc_text).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            with contextlib.suppress(ValueError, SyntaxError):
                out[node.targets[0].id] = ast.literal_eval(node.value)
    return out


def expand_patterns(calc_text: str) -> set[str]:
    """Keys the key-building patterns of calc.py produce, resolved explicitly; a pattern that is missing fails."""
    c = _calc_consts(calc_text)
    idx = [i.lower() for i in c["INDEXES"]]
    keys: set[str] = set()
    for tmpl, n in (("PAYOFF_STEP_KEY", "PAYOFF_STEP_COUNT"), ("LEG_PICKER_WIDTH_KEY", "LEG_PICKER_WIDTH_COUNT")):
        keys |= {c[tmpl].format(i) for i in range(1, c[n] + 1)}
    keys |= {c["PAYOFF_DEFAULT_STEP_KEY"].format(i) for i in idx}
    keys |= {c["RANGE_CAP_KEY"].format(i) for i in idx}
    keys |= {c["QUICK_PICK_KEY"].format(i, n) for i in idx for n in range(1, c["QUICK_PICK_COUNT"] + 1)}
    # f"scenarios.{index.lower()}_{f}" over INDEXES x SCENARIO_FIELDS: the f-string itself must still be there
    if 'f"scenarios.{index.lower()}_{f}"' not in calc_text:
        raise AssertionError("the scenario key f-string in calc.py changed shape: the scan cannot resolve it")
    keys |= {f"scenarios.{i}_{f}" for i in idx for f in c["SCENARIO_FIELDS"]}
    return keys


def keys_without_reader(keys: list[str], corpus: dict[str, str], patterns: set[str]) -> list[str]:
    """Keys read nowhere: not an exact quoted string in any file of ``corpus`` and not a resolved pattern key."""
    def read(k: str) -> bool:
        quoted = re.compile(r"""["'`]""" + re.escape(k) + r"""["'`]""")
        return k in patterns or any(quoted.search(t) for t in corpus.values())

    return [f"no reader found for {k}" for k in keys if not read(k)]


def _py_module_names(text: str) -> set[str]:
    names = set()
    for node in ast.parse(text).body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        for t in targets:
            for n in ast.walk(t):
                if isinstance(n, ast.Name):
                    names.add(n.id)
    return names


def _js_names(text: str) -> set[str]:
    return set(re.findall(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\b", text, re.M))


def _py_fraction_literals(text: str) -> list[tuple[int, Decimal]]:
    """Fractional number literals (Decimal("0.065"), 0.065) inside module-level assignments."""
    out = []
    for node in ast.parse(text).body:
        if not isinstance(node, ast.Assign | ast.AnnAssign) or node.value is None:
            continue
        for n in ast.walk(node.value):
            raw = None
            if isinstance(n, ast.Constant) and isinstance(n.value, float):
                raw = repr(n.value)
            elif (isinstance(n, ast.Call) and getattr(n.func, "id", None) == "Decimal" and n.args
                  and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                raw = n.args[0].value
            if raw and "." in raw:
                with contextlib.suppress(InvalidOperation):
                    out.append((n.lineno, Decimal(raw)))
    return out


def literal_violations(rel: str, text: str, entries: list[tuple[str, str]], defaults: dict[str, str]) -> list[str]:
    """What brings an old literal back into ``rel``; an unparsable Python file fails closed."""
    bad = []
    if rel.endswith(".py"):
        try:
            names = _py_module_names(text)
            fractions = _py_fraction_literals(text)
        except SyntaxError as e:
            return [f"{rel}: cannot parse ({e.msg}) for {', '.join(k for _, k in entries)}"]
    else:
        names, fractions = _js_names(text), []
    for name, key in entries:
        if name in names:
            bad.append(f"{rel}: {name} is defined again (was moved to setting {key})")
        d = Decimal(defaults[key])
        if "." in defaults[key]:
            bad.extend(f"{rel}:{ln}: literal {d} is typed again (setting {key})" for ln, v in fractions if v == d)
    return bad


def _missing_homes() -> list[str]:
    bad: list[str] = []
    for rel in OLD_HOMES:
        p = (FRONTEND if rel.endswith((".js", ".vue")) else BACKEND) / rel
        if not p.is_file():
            bad.append(f"{OLD_HOMES[rel][0][1]}: old home {rel} no longer exists (move it to RETIRED_HOMES only if the file is gone on purpose)")
    for rel, key in RETIRED_HOMES.items():
        if (BACKEND / rel).exists():
            bad.append(f"{key}: retired home {rel} is back")
    return bad


def unresolved_sources(settings: list[dict], root: pathlib.Path) -> list[str]:
    """Registry sources whose old home is unknown to the tables, or a table file that is gone."""
    bad = []
    file_re = re.compile(r"[\w./-]+\.(?:py|json|js|vue)")
    known = {pathlib.PurePosixPath(f).name: f for f in (*OLD_HOMES, *RETIRED_HOMES, *SECOND_HOMES)}
    for s in settings:
        if "was " not in s["source"]:
            bad.append(f"{s['key']}: source names no old home: {s['source']!r}")
            continue
        was = s["source"].rsplit("was ", 1)[1]
        was = re.sub(r"\(.*?\)", "", was)
        if was.strip().startswith("env "):
            if was.split()[1] not in RETIRED_ENV:
                bad.append(f"{s['key']}: env home {was!r} not in RETIRED_ENV")
            continue
        bad.extend(f"{s['key']}: old home {tok} is in no table" for tok in file_re.findall(was)
                   if pathlib.PurePosixPath(tok).name not in known)
    return bad + _missing_homes()


# ---- the checks on the real tree ---------------------------------------------------------------------------------
def test_every_registry_key_has_a_reader():
    reg = REGISTRY.resolve()
    corpus = {str(p): p.read_text(encoding="utf-8", errors="replace") for p in _code_files() if p.resolve() != reg}
    patterns = expand_patterns(CALC.read_text(encoding="utf-8"))
    assert keys_without_reader([s["key"] for s in _load_keys()], corpus, patterns) == []


def test_range_keys_are_read_by_the_browser_and_the_pick_list_module():
    """limits.range_step / range_cap_* have two readers: the browser (lib/guided.js) and ofo/range/pick_lists.py,
    which takes them from settings (no typed default, so no KNOWN_LEFTOVERS row for it)."""
    guided = (FRONTEND / "lib" / "guided.js").read_text(encoding="utf-8")
    assert "'limits.range_step'" in guided and "limits.range_cap_${" in guided
    module = (BACKEND / "ofo" / "range" / "pick_lists.py").read_text(encoding="utf-8")
    assert "range_cap(" in module and "from ofo.settings.calc import" in module
    assert not any(v[0].endswith("pick_lists.py") for v in KNOWN_LEFTOVERS.values())
    assert not _py_module_names(module) & {"STEP", "DEFAULT_CAPS"}


def test_no_old_literal_is_back_in_its_old_home():
    settings = _load_keys()
    defaults = {s["key"]: s["default"] for s in settings}
    bad = unresolved_sources(settings, ROOT)
    for rel, entries in OLD_HOMES.items():
        p = (FRONTEND if rel.endswith((".js", ".vue")) else BACKEND) / rel
        if p.is_file():
            bad += literal_violations(rel, p.read_text(encoding="utf-8"), entries, defaults)
    for env, key in RETIRED_ENV.items():
        for p in BACKEND.rglob("*.py"):
            t = p.read_text(encoding="utf-8", errors="replace")
            if re.search(r"""environ.*["']""" + env + r"""["']|getenv\(["']""" + env, t):
                bad.append(f"{p.relative_to(ROOT)}: reads env {env} again (setting {key})")
    assert bad == []


def test_table_names_are_all_mentioned_by_a_registry_source():
    sources = " ".join(s["source"] for s in _load_keys())
    missing = [f"{rel} {name}" for rel, es in OLD_HOMES.items() for name, _ in es
               if pathlib.PurePosixPath(rel).name not in sources or not re.search(r"\b" + re.escape(name), sources)]
    assert missing == [], f"table rows no registry source names (stale or mistyped): {missing}"


def test_known_leftovers_are_still_there_and_each_has_a_reason():
    stale = []
    for lid, (rel, marker, reason, follow) in KNOWN_LEFTOVERS.items():
        p = BACKEND / rel
        assert reason and follow.startswith("follow-up:"), lid
        if not p.is_file() or marker not in p.read_text(encoding="utf-8"):
            stale.append(f"{lid}: {rel} no longer holds {marker!r} (fixed or moved: drop the row)")
    assert stale == []


# ---- self-tests on strings: the guard must fail when it should ------------------------------------------------
_DEFAULTS = {"pricing.risk_free_rate": "0.065", "pricing.forward_min_strikes": "3"}


def test_self_live_rate_literal_back_in_live_market_fails():
    snippet = 'from decimal import Decimal\n\nLIVE_RATE = Decimal("0.065")\n'
    got = literal_violations("ofo_app/live_market.py", snippet, [("LIVE_RATE", "pricing.risk_free_rate")], _DEFAULTS)
    assert any("LIVE_RATE is defined again" in g for g in got)
    assert any(g.startswith("ofo_app/live_market.py:3: literal 0.065") for g in got)


def test_self_renamed_constant_with_same_literal_still_fails():
    got = literal_violations("ofo_app/live_market.py", 'from decimal import Decimal\nRATE = Decimal("0.065")\n',
                             [("LIVE_RATE", "pricing.risk_free_rate")], _DEFAULTS)
    assert got and "literal 0.065 is typed again" in got[0]


def test_self_clean_module_passes_and_unparsable_fails_closed():
    ok = literal_violations("ofo_app/live_market.py", "def rate(values):\n    return values['x']\n",
                            [("LIVE_RATE", "pricing.risk_free_rate")], _DEFAULTS)
    assert ok == []
    bad = literal_violations("ofo_app/live_market.py", "LIVE_RATE = (\n", [("LIVE_RATE", "pricing.risk_free_rate")], _DEFAULTS)
    assert bad and "cannot parse" in bad[0] and "pricing.risk_free_rate" in bad[0]


def test_self_js_constant_back_fails():
    got = literal_violations("lib/legEdit.js", "export const MULTIPLIER_MAX = 50\n",
                             [("MULTIPLIER_MAX", "limits.multiplier_max")], {"limits.multiplier_max": "50"})
    assert got and "MULTIPLIER_MAX is defined again" in got[0]


def test_self_key_with_no_reader_fails():
    corpus = {"a.py": 'x = "pricing.risk_free_rate"\n', "registry": "irrelevant"}
    got = keys_without_reader(["pricing.risk_free_rate", "limits.orphan_key"], corpus, set())
    assert got == ["no reader found for limits.orphan_key"]
    assert keys_without_reader(["scenarios.a_1"], {}, {"scenarios.a_1"}) == []


def test_self_unresolvable_source_fails():
    got = unresolved_sources([{"key": "x.y", "source": "ADR-1; was ofo/nowhere/gone_module.py SOME_CONST"},
                              {"key": "x.z", "source": "ADR-1; typed nowhere"},
                              {"key": "x.e", "source": "ADR-1; was env SOME_OTHER_ENV"}], ROOT)
    assert any(g.startswith("x.y: old home ofo/nowhere/gone_module.py is in no table") for g in got)
    assert any(g.startswith("x.z: source names no old home") for g in got)
    assert any(g.startswith("x.e: env home") for g in got)


def test_self_pattern_expansion_covers_built_keys_and_fails_on_a_changed_pattern():
    text = CALC.read_text(encoding="utf-8")
    keys = expand_patterns(text)
    assert {"scenarios.nifty_step_points", "scenarios.payoff_step_4", "limits.range_cap_sensex",
            "scenarios.strangle_quick_pick_sensex_4", "limits.leg_picker_width_3"} <= keys
    with pytest.raises(AssertionError):
        expand_patterns(text.replace('f"scenarios.{index.lower()}_{f}"', 'f"scenarios.{index}-{f}"'))
