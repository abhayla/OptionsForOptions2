"""gh_issue.py <repo-key> <label> <title> <body-file> [--stage <stage>]
(repo-key 'kit' = the kit repo; 'app' = this repo)

--stage (app only): after the issue is created, append `  "#N": <stage>  # <title>` under `issues:` in
docs/process/coverage-stages.yaml, because the coverage check fails CI on an open issue with no stage.
"""
import os
import re
import subprocess
import sys

repos = {"kit": "abhayla/Startup-" + "Factory", "app": "abhayla/OptionsForOptions2"}
STAGES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "docs", "process", "coverage-stages.yaml")


def _refuse_if_verifier_in_flight(target):
    """Shared check from the in-flight hook module (no copy of its logic); fails open when it cannot be loaded."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))
        from verifier_inflight_gate import inflight_block_reason  # noqa: PLC0415 - path is set just above
        why = inflight_block_reason(target, "--stage write by " + os.path.basename(__file__))
    except Exception:  # noqa: BLE001 - a missing or broken hook module fails open
        return
    if why:
        sys.stderr.write(why + "\n")
        sys.exit(2)


def add_stage(number, stage, title, path=STAGES_FILE):
    """Insert the issue line after the last entry of the `issues:` block (other blocks follow it)."""
    with open(path, encoding="utf-8", newline="") as handle:
        text = handle.read()
    if re.search(rf'^\s+"#{number}":', text, re.MULTILINE):
        return False
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    start = next((i for i, line in enumerate(lines) if line.rstrip() == "issues:"), None)
    if start is None:
        raise ValueError("no `issues:` block in " + path)
    end = start
    for i in range(start + 1, len(lines)):
        if lines[i].startswith(" "):
            end = i
        elif lines[i].strip() and not lines[i].lstrip().startswith("#"):
            break
    note = " ".join(title.split())
    lines.insert(end + 1, f'  "#{number}": {stage}  # {note}')
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(nl.join(lines))
    return True


def create_cmd(key, label, title, body, stage=None):
    """The `gh issue create` argument list; a staged issue also gets the `staged` label (24 h coverage grace)."""
    cmd = ["gh", "issue", "create", "-R", repos[key], "--label", label]
    if stage:
        cmd += ["--label", "staged"]
    return [*cmd, "--title", title, "--body-file", body]


def main(argv):
    args = list(argv)
    stage = None
    if "--stage" in args:
        i = args.index("--stage")
        stage = args[i + 1]
        del args[i:i + 2]
    key, label, title, body = args[:4]
    if stage:
        _refuse_if_verifier_in_flight(os.path.dirname(STAGES_FILE))
    if stage and key != "app":
        print("--stage only applies to the app repo")
        return 2
    r = subprocess.run(create_cmd(key, label, title, body, stage), capture_output=True, text=True)
    print(r.stdout, r.stderr)
    if r.returncode == 0 and stage:
        tail = r.stdout.strip().rsplit("/", 1)[-1]
        if not tail.isdigit():
            print("could not read the issue number; stage it by hand")
            return 1
        add_stage(tail, stage, title)
        print(f"staged #{tail} as {stage} in docs/process/coverage-stages.yaml")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
