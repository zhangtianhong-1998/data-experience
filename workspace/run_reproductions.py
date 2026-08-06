#!/usr/bin/env python3
"""Clean orchestrator that records commands, durations, stdout, stderr, and exit codes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parent
LOG_ROOT = ROOT / "run_logs"


def run_step(step_id: str, command: list[str], env: dict[str, str] | None = None) -> dict:
    started = datetime.now(timezone.utc)
    start_clock = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT.parent,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    duration_ms = (time.perf_counter() - start_clock) * 1000
    stdout_path = LOG_ROOT / f"{step_id}.stdout.txt"
    stderr_path = LOG_ROOT / f"{step_id}.stderr.txt"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    result = {
        "step": step_id,
        "command": command,
        "started_at": started.isoformat(),
        "duration_ms": round(duration_ms, 3),
        "exit_code": completed.returncode,
        "stdout": str(stdout_path.relative_to(ROOT)),
        "stderr": str(stderr_path.relative_to(ROOT)),
    }
    if completed.returncode != 0:
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tfidf",
        action="store_true",
        help="skip the neural embedding run and keep only the no-network TF-IDF path",
    )
    args = parser.parse_args()

    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    python = "python3"
    csr_python = str(ROOT / "csr_rag" / ".venv" / "bin" / "python")
    if not Path(csr_python).exists():
        raise SystemExit("CSR-RAG virtualenv missing; follow csr_rag/README.md first")

    steps = [
        ("01_dbcc_tests", [python, "-m", "unittest", "discover", "-s", "workspace/dbcc/tests", "-v"], None),
        ("02_dbcc_mechanism", [python, "workspace/dbcc/src/run_demo.py"], None),
        ("03_dbcc_official", [python, "workspace/dbcc/src/run_official_preprocessors.py"], None),
        ("04_csr_tests", [csr_python, "-m", "unittest", "discover", "-s", "workspace/csr_rag/tests", "-v"], None),
        ("05_csr_tfidf", [csr_python, "workspace/csr_rag/src/run_demo.py", "--backend", "tfidf"], None),
    ]
    if not args.tfidf:
        neural_env = dict(os.environ)
        neural_env["HF_HOME"] = str(ROOT / "csr_rag" / "model-cache")
        steps.append(
            (
                "06_csr_sentence_transformer",
                [csr_python, "workspace/csr_rag/src/run_demo.py", "--backend", "sentence-transformer"],
                neural_env,
            )
        )
    steps.append(("07_verify", [python, "workspace/verify_all.py"], None))

    manifest = {
        "run_started_at": datetime.now(timezone.utc).isoformat(),
        "mode": "tfidf-only" if args.tfidf else "tfidf-and-sentence-transformer",
        "steps": [],
    }
    for step_id, command, env in steps:
        print(f"running {step_id} ...", flush=True)
        manifest["steps"].append(run_step(step_id, command, env))
    manifest["status"] = "pass"
    manifest["run_finished_at"] = datetime.now(timezone.utc).isoformat()
    (LOG_ROOT / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
