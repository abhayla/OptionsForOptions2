import os, subprocess, sys


def _refuse_if_verifier_in_flight(target):
    """Shared check from the in-flight hook module (no copy of its logic); fails open when it cannot be loaded."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))
        from verifier_inflight_gate import inflight_block_reason
        why = inflight_block_reason(target, "evidence write by " + os.path.basename(__file__))
    except Exception:
        return
    if why:
        sys.stderr.write(why + "\n")
        sys.exit(2)

S = os.path.dirname(os.path.abspath(__file__))
aid, wid, builder, verifier, jf = sys.argv[1:6]
wt = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "." + "claude", "worktrees", f"agent-{aid}")
_refuse_if_verifier_in_flight(wt)
print(subprocess.run(["git", "status", "--short"], cwd=wt, capture_output=True, text=True).stdout)
subprocess.run([sys.executable, os.path.join(S, "record_evidence.py"), wt, wid, builder, verifier, jf], check=True)
