"""Run the official ingestion CLI while keeping the local JWT out of argv/logs."""

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[2]
token = (WORKSPACE / "runtime" / "openmetadata-1.13.0" / "admin.jwt").read_text(encoding="utf-8").strip()
env = os.environ.copy()
env["OM_JWT_TOKEN"] = token
command = [
    str(WORKSPACE / "runtime" / "openmetadata-venv" / "bin" / "metadata"),
    "ingest",
    "-c",
    str(ROOT / "ingest_mysql_local.yml"),
]
raise SystemExit(subprocess.run(command, cwd=ROOT, env=env, check=False).returncode)
