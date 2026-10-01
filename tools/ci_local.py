#!/usr/bin/env python3
"""ci_local.py - run every step CI runs, locally, in the foreground (REQ-046, OD-65).

Run it once per batch, before the first push. It reads .github/workflows/ci.yml at run time
(the step list is never hard-coded), runs each `run:` step through bash in the repo, writes each
step's output to a log file outside the repo, and prints one line per step plus a total.

Usage:
    python tools/ci_local.py [--list] [--repo PATH] [--workflow PATH] [--event NAME]
                             [--base REF] [--pr-body FILE]

Options:
    --list         print the plan (PLAN / SKIP lines, pytest collection included); run nothing
    --repo         repository root; default: current directory
    --workflow     workflow file; default: <repo>/.github/workflows/ci.yml
    --event        event to mirror (github.event_name); default: pull_request
    --base         base ref for `git merge-base <base> HEAD` (the PR base sha); default: origin/main
    --pr-body FILE a file holding the PR description; written into a temp event JSON and given to
                   every step as GITHUB_EVENT_PATH (tools/check_pr_spec_block.py reads it)

Plan rules (every step of every job, in file order, each accounted for):
    uses: step                      SKIP  environment setup
    same command as an earlier step SKIP  same command as step N
    pytest step covered by another  SKIP  covered by step N (a of b tests), by comparing collections
    `if:` github.event_name == 'x'  decided from --event
    `if:` github.event_name != 'x'  the exact complement: PLAN unless --event is x (no other negation)
    `if:` steps.<id>.outputs.<k> == 'v'  decided at run time from the earlier step's GITHUB_OUTPUT
    command runs a repo file that mentions GITHUB_EVENT_PATH, no --pr-body
                                    SKIP  reads GITHUB_EVENT_PATH; pass --pr-body FILE
    (no exit code is ever turned into SKIP: a non-zero exit is FAIL)
Fail closed (UNSUPPORTED, exit 2, before anything runs): any other `if:` shape, any `${{ }}` in a
command other than github.event.pull_request.base.sha / github.event.before (resolved to the
merge-base), a job-level `if:`, a step `working-directory:`, a step `shell:` or job `defaults.run.shell` other than bash.

Exit codes: 0 all steps passed or skipped (or --list); 1 at least one step failed;
2 usage error, unsupported workflow shape, or no bash.
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
from pathlib import Path

import yaml

TAIL_LINES = 30
EVENT_COND = re.compile(r"^github\.event_name\s*(==|!=)\s*'([^']*)'$")
OUTPUT_COND = re.compile(r"^steps\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)\s*==\s*'([^']*)'$")
EXPR = re.compile(r"\$\{\{(.*?)\}\}", re.S)
BASE_TERMS = {"github.event.pull_request.base.sha", "github.event.before"}


class Unsupported(Exception):
    """A workflow shape this tool cannot mirror faithfully."""


class Step:
    def __init__(self, idx: int, job: str, name: str, raw: dict, job_env: dict):
        self.idx, self.job, self.name = idx, job, name
        self.cmd = raw.get("run")
        self.uses = raw.get("uses")
        self.sid = raw.get("id")
        self.cond = None            # raw if: text
        self.runtime_cond = None    # (step_id, key, value) decided at run time
        env = dict(job_env)
        env.update(raw.get("env") or {})
        self.env = {str(k): str(v) for k, v in env.items()}
        self.status = "PLAN"        # PLAN | SKIP
        self.reason = ""

    @property
    def label(self) -> str:
        return f"{self.job}/{self.name}"


def _check_exprs(text: str, where: str) -> None:
    for m in EXPR.finditer(text):
        terms = [t.strip() for t in m.group(1).split("||")]
        if not all(t in BASE_TERMS for t in terms):
            raise Unsupported(f"{where}: unsupported expression `${{{{{m.group(1)}}}}}`")


def _resolve(text: str, base_sha: str) -> str:
    return EXPR.sub(lambda _m: base_sha, text)


def _strip_cond(cond) -> str:
    text = str(cond).strip()
    m = re.fullmatch(r"\$\{\{(.*)\}\}", text, re.S)
    return (m.group(1) if m else text).strip()


def reads_event_file(cmd: str, repo: Path) -> str | None:
    """Name of a repo file in the command whose text mentions GITHUB_EVENT_PATH, else None."""
    for tok in re.split(r"[\s;&|<>()]+", cmd):
        tok = tok.strip("\"'")
        if not tok or tok.startswith("-"):
            continue
        path = repo / tok
        try:
            if path.is_file() and "GITHUB_EVENT_PATH" in path.read_text(encoding="utf-8", errors="replace"):
                return tok
        except OSError:
            continue
    return None


def build_plan(workflow: dict, event: str, repo: Path | None = None,
               has_pr_body: bool = False) -> list[Step]:
    """Validate and plan every step. Raises Unsupported before anything runs."""
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise Unsupported("workflow has no jobs")
    steps: list[Step] = []
    idx = 0
    for job_name, job in jobs.items():
        if "if" in job:
            raise Unsupported(f"job {job_name}: job-level if: `{job['if']}` is not supported")
        job_env = job.get("env") or {}
        job_shell = ((job.get("defaults") or {}).get("run") or {}).get("shell")
        if job_shell not in (None, "bash"):
            raise Unsupported(f"job {job_name}: defaults.run.shell `{job_shell}` is not supported (bash only)")
        for v in job_env.values():
            _check_exprs(str(v), f"job {job_name} env")
        seen_ids: set[str] = set()
        for raw in job.get("steps") or []:
            idx += 1
            if "run" in raw:
                default = str(raw["run"]).strip().splitlines()[0]
            else:
                default = f"uses: {raw.get('uses')}"
            st = Step(idx, job_name, str(raw.get("name") or default), raw, job_env)
            where = f"step {idx} ({st.label})"
            if raw.get("shell") not in (None, "bash"):
                raise Unsupported(f"{where}: shell `{raw['shell']}` is not supported (bash only)")
            if raw.get("working-directory"):
                raise Unsupported(f"{where}: working-directory is not supported")
            for v in st.env.values():
                _check_exprs(v, where + " env")
            if st.cmd is not None:
                _check_exprs(str(st.cmd), where)
            if "if" in raw:
                st.cond = _strip_cond(raw["if"])
                em, om = EVENT_COND.match(st.cond), OUTPUT_COND.match(st.cond)
                if em:
                    op, name = em.groups()
                    if op == "==" and name != event:
                        st.status = "SKIP"
                        st.reason = f"event is {event}, only runs on {name} ({st.cond})"
                    elif op == "!=" and name == event:
                        st.status = "SKIP"
                        st.reason = f"event is {event}, does not run on {name} ({st.cond})"
                elif om:
                    if om.group(1) not in seen_ids:
                        raise Unsupported(
                            f"{where}: if `{st.cond}` names no earlier run step with that id in this job")
                    st.runtime_cond = om.groups()
                else:
                    raise Unsupported(f"{where}: unsupported if: `{st.cond}`")
            if st.sid and st.cmd is not None:
                seen_ids.add(str(st.sid))
            if st.status == "PLAN" and st.cmd is not None and repo is not None and not has_pr_body:
                hit = reads_event_file(str(st.cmd), repo)
                if hit:
                    st.status = "SKIP"
                    st.reason = "reads GITHUB_EVENT_PATH; pass --pr-body FILE"
            if st.status == "PLAN" and st.cmd is None:
                st.status = "SKIP"
                st.reason = f"environment setup (uses: {st.uses})"
            steps.append(st)
    # identical commands: only against earlier steps that run unconditionally
    planned: dict[str, int] = {}
    for st in steps:
        if st.status != "PLAN":
            continue
        key = str(st.cmd).strip()
        if key in planned and st.runtime_cond is None and not st.sid and not st.env:
            st.status, st.reason = "SKIP", f"same command as step {planned[key]:02d}"
        elif st.runtime_cond is None and not st.sid and not st.env:
            planned[key] = st.idx
    return steps


def find_bash() -> str | None:
    cands = []
    found = shutil.which("bash")
    if found:
        cands.append(found)
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            root = Path(git).resolve().parent.parent
            cands += [str(root / "bin" / "bash.exe"), str(root / "usr" / "bin" / "bash.exe")]
    for c in cands:
        if "system32" in c.lower().replace("/", "\\") or not Path(c).exists():
            continue  # System32 bash.exe is the WSL launcher, not a shell for this repo
        return c
    return None


def run_bash(bash: str, cmd: str, repo: Path, env: dict, log) -> int:
    return subprocess.run([bash, "-e", "-c", cmd], cwd=str(repo), env=env,
                          stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL).returncode


def collect_tests(bash: str, cmd: str, repo: Path, env: dict) -> set[str] | None:
    """Node ids a pytest command selects, or None when collection failed."""
    cmd = cmd.strip()
    extra = "--collect-only" if re.search(r"(^|\s)-q\b", cmd) else "--collect-only -q"
    proc = subprocess.run([bash, "-e", "-c", f"{cmd} {extra}"], cwd=str(repo), env=env,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        return None
    ids = {ln.strip() for ln in proc.stdout.splitlines() if "::" in ln and not ln.startswith(" ")}
    return ids or None


def dedupe_pytest(steps: list[Step], bash: str, repo: Path, env: dict) -> None:
    sets: dict[int, set[str]] = {}
    for st in steps:
        if (st.status == "PLAN" and st.runtime_cond is None
                and re.match(r"python\d*(\.\d+)?\s+-m\s+pytest\b", str(st.cmd).strip())):
            got = collect_tests(bash, str(st.cmd), repo, env)
            if got is not None:
                sets[st.idx] = got
    by_idx = {s.idx: s for s in steps}
    for i in sorted(sets):
        for j in sorted(sets):
            if i == j or by_idx[j].status != "PLAN" or by_idx[i].status != "PLAN":
                continue
            if sets[i] <= sets[j] and (sets[i] != sets[j] or j < i):
                by_idx[i].status = "SKIP"
                by_idx[i].reason = f"covered by step {j:02d} ({len(sets[i])} of {len(sets[j])} tests)"
                break


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:50] or "step"


def read_outputs(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.exists():
        for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in ln and "<<" not in ln.split("=", 1)[0]:
                k, v = ln.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def merge_base(repo: Path, base: str) -> str:
    proc = subprocess.run(["git", "merge-base", base, "HEAD"], cwd=str(repo),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git merge-base {base} HEAD failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run every CI step locally (REQ-046).")
    ap.add_argument("--list", action="store_true", help="print the plan; run nothing")
    ap.add_argument("--repo", default=".", help="repository root (default: cwd)")
    ap.add_argument("--workflow", help="workflow file (default: <repo>/.github/workflows/ci.yml)")
    ap.add_argument("--event", default="pull_request", help="event to mirror (default: pull_request)")
    ap.add_argument("--base", default="origin/main", help="base ref for the merge-base (default: origin/main)")
    ap.add_argument("--pr-body", help="file holding the PR description")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    wf_path = Path(args.workflow) if args.workflow else repo / ".github" / "workflows" / "ci.yml"
    try:
        workflow = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        print(f"ERROR: cannot read workflow {wf_path}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(workflow, dict):
        print(f"ERROR: {wf_path} is not a workflow mapping", file=sys.stderr)
        return 2
    try:
        steps = build_plan(workflow, args.event, repo, bool(args.pr_body))
    except Unsupported as exc:
        print(f"UNSUPPORTED: {exc}", file=sys.stderr)
        return 2
    body_text = None
    if args.pr_body:
        try:
            body_text = Path(args.pr_body).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: cannot read --pr-body {args.pr_body}: {exc}", file=sys.stderr)
            return 2
    bash = find_bash()
    if not bash:
        print("ERROR: bash not found on PATH (Git Bash is enough)", file=sys.stderr)
        return 2

    run_dir = None
    work = Path(tempfile.mkdtemp(prefix="ci-local-work-"))
    env = dict(os.environ)
    env["GITHUB_EVENT_NAME"] = args.event
    if body_text is not None:
        ev = work / "event.json"
        ev.write_text(json.dumps({"pull_request": {"body": body_text}}), encoding="utf-8")
        env["GITHUB_EVENT_PATH"] = ev.as_posix()

    try:
        dedupe_pytest(steps, bash, repo, env)

        if args.list:
            for st in steps:
                if st.status == "SKIP":
                    print(f"SKIP  {st.idx:02d}  {st.label}  [{st.reason}]")
                else:
                    gate = f"  [runs only if {st.cond}]" if st.runtime_cond else ""
                    first = str(st.cmd).strip().splitlines()[0]
                    print(f"PLAN  {st.idx:02d}  {st.label}  : {first}{gate}")
            return 0

        run_dir = Path(tempfile.gettempdir()) / "ci-local" / time.strftime("%Y%m%d-%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        print(f"logs: {run_dir}", flush=True)
        t_all = time.time()
        counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
        outputs_file: dict[str, Path] = {}
        base_sha: str | None = None

        for st in steps:
            def report(kind: str, secs: float, note: str = "") -> None:
                counts[kind] += 1
                extra = f"  [{note}]" if note else ""
                print(f"{kind}  {st.idx:02d}  {st.label}  ({secs:.1f}s){extra}", flush=True)

            if st.status == "SKIP":
                report("SKIP", 0.0, st.reason)
                continue
            out_path = outputs_file.setdefault(st.job, work / f"output-{slug(st.job)}.txt")
            if st.runtime_cond:
                sid, key, want = st.runtime_cond
                got = read_outputs(out_path).get(key)
                if got != want:
                    report("SKIP", 0.0, f"if {st.cond} is false (value: {got!r})")
                    continue
            cmd = str(st.cmd)
            if EXPR.search(cmd):
                try:
                    base_sha = base_sha or merge_base(repo, args.base)
                except RuntimeError as exc:
                    report("FAIL", 0.0, str(exc))
                    continue
                cmd = _resolve(cmd, base_sha)
            step_env = dict(env)
            step_env.update(st.env)
            step_env["GITHUB_OUTPUT"] = out_path.as_posix()
            log_path = run_dir / f"{st.idx:02d}-{slug(st.name)}.log"
            t0 = time.time()
            with open(log_path, "w", encoding="utf-8", errors="replace") as log:
                rc = run_bash(bash, cmd, repo, step_env, log)
            secs = time.time() - t0
            if rc == 0:
                report("PASS", secs)
            else:
                report("FAIL", secs, f"exit {rc}")
                lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                print(f"--- last {min(TAIL_LINES, len(lines))} lines of {log_path} ---")
                print("\n".join(lines[-TAIL_LINES:]))
                print("--- end ---", flush=True)

        print(f"TOTAL: {counts['PASS']} passed, {counts['FAIL']} failed, {counts['SKIP']} skipped "
              f"({time.time() - t_all:.1f}s) - logs: {run_dir}")
        return 1 if counts["FAIL"] else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
