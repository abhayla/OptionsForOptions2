"""Load an NSE F&O contract file's freeze limits into the database (W-076). See ofo_app.freeze_store.

    python scripts/orchestrator/db_run.py . python scripts/load_freeze_file.py <NSE_FO_contract_ddmmyyyy.csv.gz>
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend")]

from ofo_app.freeze_store import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run(sys.argv))
