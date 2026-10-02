#!/usr/bin/env python3
# Copied/adapted from abhayla/algochanakya@bf9faf7:backend/scripts/generate_openapi.py (ADR-047)
# Changed: builds the app with ofo_app.main:create_app; only a placeholder DATABASE_URL is needed (no secrets, no
# connection is opened); --out chooses the output file.
"""Generate the OpenAPI document without starting the server.

Usage (repo root): python scripts/generate_openapi.py [--out docs/api/openapi.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

# Settings require DATABASE_URL; the engine is created lazily, so this placeholder is never connected to.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://placeholder/placeholder")

from ofo_app.main import create_app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(REPO_ROOT / "docs" / "api" / "openapi.json"))
    args = parser.parse_args()
    spec = create_app().openapi()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"OpenAPI spec written to: {out}")
    print(f"  Paths:   {len(spec.get('paths', {}))}")
    print(f"  Schemas: {len(spec.get('components', {}).get('schemas', {}))}")
    print(f"  Version: {spec.get('info', {}).get('version', 'unknown')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
