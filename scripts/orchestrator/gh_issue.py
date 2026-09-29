"""gh_issue.py <repo-key> <label> <title> <body-file>  (repo-key 'kit' = the kit repo; 'app' = this repo)"""
import subprocess, sys
repos = {"kit": "abhayla/Startup-" + "Factory", "app": "abhayla/OptionsForOptions2"}
key, label, title, body = sys.argv[1:5]
r = subprocess.run(["gh", "issue", "create", "-R", repos[key], "--label", label, "--title", title, "--body-file", body],
                   capture_output=True, text=True)
print(r.stdout, r.stderr)
sys.exit(r.returncode)
