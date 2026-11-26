"""gate_equivalence.py: prove a changed pre-push gate gives the same per-step verdict as the old one (lane G).

  seeds   --base SHA --out MANIFEST [--prove] [--node-modules DIR]
          one sibling commit per seed on the local branch equiv/<seed> (never pushed), each directly on SHA
  run     --gate PREPUSH.py --manifest M --label old|new --out RESULTS.json [--worktree DIR] [--only a,b]
          [--timeout S] [--extra-args="..."]  (the = form: argparse reads a value starting with -- as an option)
          Serial: two gates at once share merge_preflight's mypy cache.
  compare OLD.json NEW.json [--allow-skip REGEX ...]   markdown table; exit 0 only with no MISMATCH / SEED-INVALID

The gate is never run by `seeds`; `run` runs whatever gate file it is given, one seed at a time, in one worktree.
Every external command goes through an injected runner(cmd, cwd, timeout=None) -> (rc, combined output). The child
environment never carries a database URL or PREPUSH_GATE_ALLOW (this host's PostgreSQL serves production).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

MARKER_DIR = "ofo-prepush"  # same name as prepush.MARKER_DIR; prepush.py is not imported (it is the thing under test)
SCRUBBED_ENV = ("TEST_DATABASE_URL", "TEST_ADMIN_DATABASE_URL", "ALEMBIC_DATABASE_URL", "PREPUSH_GATE_ALLOW")
RAN = ("PASS", "FAIL")
DEFAULT_WORKTREE = os.path.join(".claude", "worktrees", "equiv-1126")
GIT_ID = ["-c", "user.name=gate-equivalence", "-c", "user.email=gate-equivalence@invalid"]

STEP_RE = re.compile(r"^(PASS|FAIL) (\S+) ([\d.]+)s (.*)$")
TOTAL_RE = re.compile(r"^TOTAL (PASS|FAIL) ([\d.]+)s ?(.*)$")
SKIP_RE = re.compile(r"^SKIP (\S+)\s*(.*)$")


def parse_gate_output(text: str) -> dict:
    """Per-step verdicts, the TOTAL verdict and note, skip reasons and STOP lines of one gate run."""
    out = {"steps": {}, "total": None, "total_note": "", "skip_reasons": {}, "stops": []}
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if m := STEP_RE.match(line):
            out["steps"][m.group(2)] = m.group(1)
        elif m := TOTAL_RE.match(line):
            out["total"], out["total_note"] = m.group(1), m.group(3)
        elif m := SKIP_RE.match(line):
            out["steps"][m.group(1)] = "SKIP"
            out["skip_reasons"][m.group(1)] = m.group(2)
        elif line.startswith("STOP"):
            out["stops"].append(line)
    return out


# ---- compare ----

def compare_seed(name: str, old: dict, new: dict, allow=()) -> tuple[list[dict], list[tuple[str, str]]]:
    """(rows, problems) for one seed. problems are (kind, text); kinds: VERDICT, TOTAL, MARKER, MARKER-NEW, MISSING,
    SKIP-NOT-ALLOWED, SEED-INVALID."""
    rows, problems = [], []
    os_, ns = old["steps"], new["steps"]
    for step in [*os_, *(s for s in ns if s not in os_)]:
        o, n = os_.get(step, "-"), ns.get(step, "-")
        status = "ok"
        if step not in os_:
            status = "new-only"
        elif o == "SKIP":
            status = "old-skip"
        elif step not in ns:
            status = "MISMATCH"
            problems.append(("MISSING", f"{step}: old ran ({o}) and new did not run or skip it"))
        elif n == "SKIP":
            reason = new.get("skip_reasons", {}).get(step, "")
            if any(re.search(rx, reason) for rx in allow):
                status = "skip-allowed"
            else:
                status = "MISMATCH"
                problems.append(("SKIP-NOT-ALLOWED", f"{step}: new skipped ({reason!r}), reason not allowed"))
        elif o != n:
            status = "MISMATCH"
            problems.append(("VERDICT", f"{step}: old {o}, new {n}"))
        rows.append({"seed": name, "step": step, "old": o, "new": n, "status": status})
    problems += _total_and_marker(old, new)
    rows.append({"seed": name, "step": "TOTAL", "old": f"{old['total']} marker={_yn(old['marker'])}",
                 "new": f"{new['total']} marker={_yn(new['marker'])}",
                 "status": "MISMATCH" if any(k in ("TOTAL", "MARKER", "MARKER-NEW") for k, _ in problems) else "ok"})
    problems += _seed_invalid(old)
    return rows, problems


def _total_and_marker(old: dict, new: dict) -> list[tuple[str, str]]:
    found = []
    if old["total"] != new["total"]:
        found.append(("TOTAL", f"TOTAL old {old['total']}, new {new['total']}"))
    if new["marker"] and not old["marker"]:
        found.append(("MARKER-NEW", "FATAL: new gate wrote a marker where old did not"))
    elif old["marker"] != new["marker"]:
        found.append(("MARKER", f"marker old {old['marker']}, new {new['marker']}"))
    return found


def _yn(flag) -> str:
    return "yes" if flag else "no"


def _seed_invalid(old: dict) -> list[tuple[str, str]]:
    """The seed must really be red (or green with a marker) in the OLD gate."""
    expect = old.get("expect_red") or []
    steps, bad = old["steps"], []
    for step in expect:
        if steps.get(step) == "FAIL":
            continue
        if step not in steps and steps.get("preflight") == "FAIL" and "preflight" in expect:
            continue  # a red preflight stopped the run before this step: the preflight is where it shows
        bad.append(("SEED-INVALID", f"expected {step} red in old, got {steps.get(step, 'not run')}"))
    if expect and old["total"] != "FAIL":
        bad.append(("SEED-INVALID", f"expected TOTAL FAIL in old, got {old['total']}"))
    if not expect and (old["total"] != "PASS" or not old["marker"]):
        bad.append(("SEED-INVALID", f"clean seed: expected TOTAL PASS and a marker in old, got {old['total']}, "
                                    f"marker {_yn(old['marker'])}"))
    return bad


def compare_results(old: dict, new: dict, allow=()) -> tuple[list[dict], list[tuple[str, str, str]]]:
    rows, problems = [], []
    for seed, o in old["seeds"].items():
        n = new["seeds"].get(seed)
        if n is None:
            problems.append((seed, "MISSING", "seed absent from the new results"))
            rows.append({"seed": seed, "step": "-", "old": "ran", "new": "absent", "status": "MISMATCH"})
            continue
        r, p = compare_seed(seed, o, n, allow)
        rows += r
        problems += [(seed, k, t) for k, t in p]
    return rows, problems


def render_markdown(rows, problems) -> str:
    lines = ["| seed | step | old | new | status |", "|---|---|---|---|---|"]
    lines += [f"| {r['seed']} | {r['step']} | {r['old']} | {r['new']} | {r['status']} |" for r in rows]
    lines.append("")
    for seed, kind, text in problems:
        label = "SEED-INVALID" if kind == "SEED-INVALID" else "MISMATCH"
        lines.append(f"- {label} [{seed}] {kind}: {text}")
    lines.append("")
    lines.append(f"Result: {'EQUIVALENT' if not problems else 'NOT EQUIVALENT'} ({len(problems)} problem(s))")
    return "\n".join(lines)


def cmd_compare(a) -> int:
    old, new = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (a.old, a.new))
    rows, problems = compare_results(old, new, a.allow_skip or [])
    print(render_markdown(rows, problems))
    return 0 if not problems else 1


# ---- runner ----

def child_env() -> dict:
    env = dict(os.environ)
    for key in SCRUBBED_ENV:
        env.pop(key, None)
    return env


def real_runner(cmd, cwd, timeout=None):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="replace",  # noqa: S603
                           env=child_env(), timeout=timeout, check=False)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return 124, out + f"\nTIMEOUT after {timeout}s\n"
    except OSError as exc:
        return 127, f"could not start {cmd[0]}: {exc!r}\n"


# ---- seeds ----

def _append(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n" + text, encoding="utf-8", newline="\n")


def _replace(root: Path, rel: str, old: str, new: str) -> None:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise ValueError(f"{rel}: seed anchor not found: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def _create(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


STRATEGY_TYPE = "backend/ofo/adjustment/strategy_type.py"
FAIL_TEST = "\n\ndef test_equiv_seed_fail():\n    assert 1 == 2, 'equivalence seed: deliberately red'\n"
VITEST_FILE = "frontend/tests/compare-url-callers.test.js"
ALEMBIC_SEED = "backend/ofo_app/alembic/versions/0054_equiv_seed_second_head.py"


@dataclass
class Seed:
    name: str
    expect_red: list
    note: str
    touches: list
    mutate: object
    proof: list = field(default_factory=list)  # argv, run at the seed commit
    proof_cwd: str = ""
    proof_want: str = "red"  # "red": rc != 0, "green": rc == 0


def _m_clean(r):
    end = "never a guessed type."
    _replace(r, STRATEGY_TYPE, end + '\n"""', end + ' (equiv seed: docstring only)\n"""')


def _m_ruff(r):
    _append(r, "scripts/orchestrator/gate_env.py", "# " + "x" * 200 + "  (equiv seed: one E501)\n")


def _m_cov(r):
    _replace(r, "docs/process/coverage-stages.yaml", "decisions:\n  ADR-001: all\n",
             "decisions:\n  ADR-001: all\n  ADR-9999: all\n")


def _m_money(r):
    _append(r, STRATEGY_TYPE, "\n\ndef _equiv_seed_money(premium, price):\n    return premium * price\n")


def _m_domain(r):
    _append(r, "tests/orchestrator/test_brief_path.py", FAIL_TEST)


def _m_app(r):
    _append(r, "tests_app/test_abs_delta_intrinsic.py", FAIL_TEST)


def _m_vitest(r):
    _append(r, VITEST_FILE, "\nimport { expect as equivExpect, it as equivIt } from 'vitest'\n"
                            "equivIt('equiv seed: deliberately red', () => {\n  equivExpect(1).toBe(2)\n})\n")


def _m_lint(r):
    _create(r, "frontend/src/equivSeedLint.js", "export const equivSeed = () => equivSeedUndefined()\n")


def _m_alembic(r):
    _create(r, ALEMBIC_SEED, '"""Equivalence seed (scratch, never pushed): a second head with an empty upgrade.\n\n'
                             'Revision ID: 0054_equiv_seed_second_head\nRevises: 0051_trigger_label_words\n"""\n'
                             'revision = "0054_equiv_seed_second_head"\ndown_revision = "0051_trigger_label_words"\n'
                             'branch_labels = None\ndepends_on = None\n\n\ndef upgrade():\n    pass\n\n\n'
                             'def downgrade():\n    pass\n')


def _m_docs_clean(r):
    _append(r, "docs/process/runbook.md", "\nEquivalence seed note: a docs-only sentence, no checked content.\n")


def _m_docs_break(r):
    _replace(r, "spec/requirements/REQ-001.md", "title: 'V1 scope: underlyings, leg types, broker'",
             "title: 'V1 scope: underlyings, leg types, broker (equiv seed)'")


PY = "python"
SEEDS = [
    Seed("clean_code", [], "docstring line in a backend/ofo module a test names; all green + marker",
         [STRATEGY_TYPE], _m_clean,
         [PY, "-c", "import sys,pathlib;sys.path.insert(0,'tools');import ci_local;"
                    "p,why=ci_local.select_tests(pathlib.Path('.'),'origin/main');print('selected',p);"
                    "sys.exit(0 if p else 1)"], "", "green"),
    Seed("ruff", ["preflight", "ruff_ratchet"], "one new E501 line", ["scripts/orchestrator/gate_env.py"], _m_ruff,
         [PY, "scripts/ruff_ratchet.py"]),
    Seed("coverage", ["preflight", "coverage"], "coverage-stages.yaml names ADR-9999, which is not discovered",
         ["docs/process/coverage-stages.yaml"], _m_cov,
         [PY, "scripts/orchestrator/coverage.py", ".", "--check", "--no-gh"]),
    Seed("money_scan", ["preflight"], "money arithmetic outside the engine (tests/test_money_outside_engine.py; "
                                      "preflight runs the tests -m repo_scan subset)", [STRATEGY_TYPE], _m_money,
         [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_money_outside_engine.py", "-k",
          "only_in_allowed_homes"]),
    Seed("domain_fail", ["domain_tests"], "a failing test appended to tests/orchestrator/test_brief_path.py",
         ["tests/orchestrator/test_brief_path.py"], _m_domain,
         [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/orchestrator/test_brief_path.py", "-k",
          "equiv_seed"]),
    Seed("app_fail", ["app_tests"], "a failing non-DB test appended to tests_app/test_abs_delta_intrinsic.py",
         ["tests_app/test_abs_delta_intrinsic.py"], _m_app,
         [PY, "-m", "pytest", "-c", "pytest-app.ini", "-q", "-p", "no:cacheprovider",
          "tests_app/test_abs_delta_intrinsic.py", "-k", "equiv_seed"]),
    Seed("vitest_fail", ["frontend_unit"], "a failing expect in frontend/tests/compare-url-callers.test.js",
         [VITEST_FILE], _m_vitest, ["npx", "vitest", "run", "tests/compare-url-callers.test.js"], "frontend"),
    Seed("lint_fail", ["frontend_lint"], "no-undef error in a new frontend/src file", ["frontend/src/equivSeedLint.js"],
         _m_lint, ["npx", "eslint", "src/equivSeedLint.js"], "frontend"),
    Seed("alembic_heads", ["preflight", "alembic_guard"],
         "second head off 0051 (scratch); the guard reads the empty upgrade() of the new revision", [ALEMBIC_SEED],
         _m_alembic, [PY, "scripts/alembic_migration_guard.py"]),
    Seed("docs_clean", [], "a sentence in docs/process/runbook.md; all green + marker", ["docs/process/runbook.md"],
         _m_docs_clean, [PY, "tools/build_spec_index.py", ".", "--check"], "", "green"),
    Seed("docs_spec_break", ["preflight", "ci_checks"],
         "REQ-001 title edited, so spec/requirements/INDEX.md is stale (build_spec_index --check)",
         ["spec/requirements/REQ-001.md"], _m_docs_break, [PY, "tools/build_spec_index.py", ".", "--check"]),
]


def _git(runner, cwd, *args):
    return runner(["git", *args], cwd)


def cmd_seeds(a, runner=real_runner) -> int:
    top = os.getcwd()
    rc, base = _git(runner, top, "rev-parse", a.base + "^{commit}")
    base = base.strip()
    if rc != 0 or len(base) != 40:  # noqa: PLR2004
        print(f"cannot resolve base {a.base}: {base}")
        return 2
    node_modules = a.node_modules or os.path.join(top, "frontend", "node_modules")
    tmp = tempfile.mkdtemp(prefix="equiv-seeds-")
    wt = os.path.join(tmp, "wt")
    rc, out = _git(runner, top, "worktree", "add", "--detach", wt, base)
    if rc != 0:
        print("worktree add failed: " + out)
        return 2
    manifest = []
    try:
        for seed in SEEDS:
            _git(runner, wt, "checkout", "-f", "--detach", base)
            seed.mutate(Path(wt))
            _git(runner, wt, "add", "-A")
            rc, out = _git(runner, wt, *GIT_ID, "commit", "--no-verify", "-q", "-m",
                           f"equiv seed {seed.name} (local scratch, never push)")
            if rc != 0:
                print(f"commit failed for {seed.name}: {out}")
                return 2
            _, sha = _git(runner, wt, "rev-parse", "HEAD")
            _git(runner, wt, "branch", "-f", f"equiv/{seed.name}", "HEAD")
            entry = {"name": seed.name, "sha": sha.strip(), "base": base, "expect_red": seed.expect_red,
                     "note": seed.note, "proof_cmd": " ".join(seed.proof)}
            if a.prove:
                entry["proof_result"] = _prove(seed, wt, node_modules, runner)
                print(f"{seed.name}: {entry['proof_result']}")
            manifest.append(entry)
    finally:
        _git(runner, top, "worktree", "remove", "--force", wt)
        shutil.rmtree(tmp, ignore_errors=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"wrote {len(manifest)} seeds to {a.out}")
    return 0


def _prove(seed: Seed, wt: str, node_modules: str, runner) -> str:
    """Run ONLY the seed's one targeted check at the seed commit; the result line says whether it matched."""
    cwd = os.path.join(wt, seed.proof_cwd) if seed.proof_cwd else wt
    link = os.path.join(wt, "frontend", "node_modules")
    linked = seed.proof_cwd == "frontend" and os.path.isdir(node_modules) and not os.path.exists(link)
    if linked:
        os.symlink(node_modules, link)  # after the commit, so the symlink is never committed
    try:
        rc, out = runner(seed.proof, cwd, 900)
    finally:
        if linked:
            os.unlink(link)
    tail = [ln for ln in out.strip().splitlines() if ln.strip()][-1:] or ["(no output)"]
    ok = (rc != 0) if seed.proof_want == "red" else (rc == 0)
    return f"{'AS-INTENDED' if ok else 'NOT-AS-INTENDED'} rc={rc} want={seed.proof_want}: {tail[0][:200]}"


# ---- run ----

def cmd_run(a, runner=real_runner, clock=time.monotonic) -> int:
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    if a.only:
        wanted = set(a.only.split(","))
        manifest = [s for s in manifest if s["name"] in wanted]
    wt = os.path.abspath(a.worktree)
    if not os.path.isdir(wt):
        rc, out = _git(runner, os.getcwd(), "worktree", "add", "--detach", wt, manifest[0]["sha"])
        if rc != 0:
            print("worktree add failed: " + out)
            return 2
    if not os.path.isdir(os.path.join(wt, "frontend", "node_modules")):
        rc, out = runner(["npm", "ci"], os.path.join(wt, "frontend"), 1800)
        print(f"npm ci in {wt}/frontend: rc={rc}")
    _, common = _git(runner, wt, "rev-parse", "--git-common-dir")
    marker_dir = os.path.join(wt, common.strip(), MARKER_DIR)
    out_dir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(out_dir, exist_ok=True)
    extra = a.extra_args.split() if a.extra_args else []
    results = {"label": a.label, "gate": a.gate, "extra_args": extra, "seeds": {}}
    for seed in manifest:
        marker = os.path.join(marker_dir, seed["sha"] + ".json")
        if os.path.exists(marker):
            os.unlink(marker)
        rc, out = _git(runner, wt, "checkout", "-f", "--detach", seed["sha"])
        if rc != 0:
            print(f"{seed['name']}: checkout failed: {out}")
            return 2
        t0 = clock()
        rc, out = runner([sys.executable, a.gate, "--repo", wt, *extra], os.getcwd(), a.timeout)
        seconds = round(clock() - t0, 1)
        raw = os.path.join(out_dir, f"{a.label}-{seed['name']}.txt")
        Path(raw).write_text(out, encoding="utf-8")
        parsed = parse_gate_output(out)
        results["seeds"][seed["name"]] = {
            "steps": parsed["steps"], "total": parsed["total"], "total_note": parsed["total_note"],
            "marker": os.path.exists(marker), "seconds": seconds, "raw_path": raw, "rc": rc,
            "skip_reasons": parsed["skip_reasons"], "stops": parsed["stops"],
            "expect_red": seed.get("expect_red", [])}
        print(f"{seed['name']}: total={parsed['total']} marker={_yn(os.path.exists(marker))} {seconds}s")
        Path(a.out).write_text(json.dumps(results, indent=1), encoding="utf-8")  # partial results survive a stop
    return 0


def main(argv=None, runner=real_runner) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seeds")
    s.add_argument("--base", default="origin/main")
    s.add_argument("--out", required=True)
    s.add_argument("--prove", action="store_true", help="run each seed's one targeted check (seconds, never the gate)")
    s.add_argument("--node-modules", default=None, help="frontend/node_modules to link for the frontend proofs")
    r = sub.add_parser("run")
    r.add_argument("--gate", required=True)
    r.add_argument("--manifest", required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--worktree", default=DEFAULT_WORKTREE)
    r.add_argument("--extra-args", default="")
    r.add_argument("--only", default="")
    r.add_argument("--timeout", type=int, default=4 * 3600)
    c = sub.add_parser("compare")
    c.add_argument("old")
    c.add_argument("new")
    c.add_argument("--allow-skip", action="append", default=[], metavar="REGEX")
    a = ap.parse_args(argv)
    if a.cmd == "seeds":
        return cmd_seeds(a, runner)
    if a.cmd == "run":
        return cmd_run(a, runner)
    return cmd_compare(a)


if __name__ == "__main__":
    sys.exit(main())
