import os, subprocess, sys
S = os.path.dirname(os.path.abspath(__file__))
aid, wid, builder, verifier, jf = sys.argv[1:6]
wt = os.path.join(r"D:\Abhay\Ventures\OptionsForOptions2", "." + "claude", "worktrees", f"agent-{aid}")
print(subprocess.run(["git", "status", "--short"], cwd=wt, capture_output=True, text=True).stdout)
subprocess.run([sys.executable, os.path.join(S, "record_evidence.py"), wt, wid, builder, verifier, jf], check=True)
