"""ADR-220 (1) role ``liveprices``: ``python -m ofo_app.liveprices`` starts the market-data process (REQ-113). It
holds the only Kite live connections and passes the frames to the other roles through Redis. All logic lives in
``feed_main``; this module only names the role and delegates (``--help`` prints this and exits without starting).
"""
from __future__ import annotations

import argparse
import sys

from ofo_app import feed_main, roles


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"python -m {roles.LIVEPRICES.start_module}",
        description=f"Start the {roles.LIVEPRICES.name} role (REQ-113 market-data process).")
    parser.parse_args(sys.argv[1:] if argv is None else argv)
    return feed_main.main()


if __name__ == "__main__":
    raise SystemExit(main())
