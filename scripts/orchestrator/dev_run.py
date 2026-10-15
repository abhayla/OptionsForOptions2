"""dev_run.py <cwd> <command...>: run a command with DATABASE_URL = the project .env's DEV_DATABASE_URL (ofo_dev,
ADR-078) plus the other project .env keys; prints no secret. Refuses if DEV_DATABASE_URL does not name ofo_dev."""
import os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the main checkout (.env)
env = dict(os.environ)
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env.setdefault(k.strip(), v.strip())
dev = env["DEV_DATABASE_URL"]
if not dev.rstrip("/").endswith("/ofo_dev"):
    sys.exit("REFUSED: DEV_DATABASE_URL is not ofo_dev")
env["DATABASE_URL"] = dev
env["PYTHONPATH"] = os.path.join(sys.argv[1], "backend")
sys.exit(subprocess.run(sys.argv[2:], cwd=sys.argv[1], env=env).returncode)
