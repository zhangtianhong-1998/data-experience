"""Run one demo step and persist a secret-safe execution record."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Sequence


SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def redact_arg(value: str) -> str:
    upper = value.upper()
    if any(marker in upper for marker in SECRET_MARKERS) and "=" in value:
        return value.split("=", 1)[0] + "=<redacted>"
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--step", required=True)
    parser.add_argument("--cwd", required=True, type=Path)
    parser.add_argument("--output", action="append", default=[], type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after --")

    step_dir = args.run_dir / "steps" / args.step
    step_dir.mkdir(parents=True, exist_ok=False)
    stdout_path = step_dir / "stdout.txt"
    stderr_path = step_dir / "stderr.txt"
    started = time.time()

    environment_names = sorted(
        name
        for name in os.environ
        if not any(marker in name.upper() for marker in SECRET_MARKERS)
        and name in {"PATH", "LANG", "LC_ALL", "TZ", "PYTHONPATH", "NODE_ENV"}
    )
    write_json(
        step_dir / "request.json",
        {
            "step": args.step,
            "cwd": str(args.cwd.resolve()),
            "argv": [redact_arg(item) for item in command],
            "environment_names_recorded": environment_names,
            "secret_values_recorded": False,
            "host": {
                "system": platform.system(),
                "machine": platform.machine(),
                "python": sys.version.split()[0],
            },
            "started_epoch": started,
        },
    )

    launch_error = None
    try:
        process = subprocess.run(
            command,
            cwd=args.cwd,
            env=os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        exit_code = process.returncode
        stdout = process.stdout
        stderr = process.stderr
    except OSError as error:
        launch_error = f"{type(error).__name__}: {error}"
        exit_code = 127
        stdout = ""
        stderr = launch_error + "\n"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    if stdout:
        print(stdout, end="")
    if stderr:
        print(stderr, end="", file=sys.stderr)

    outputs = []
    for output in args.output:
        resolved = output if output.is_absolute() else args.cwd / output
        item = {"path": str(resolved.resolve()), "exists": resolved.exists()}
        if resolved.is_file():
            item.update({"size": resolved.stat().st_size, "sha256": sha256(resolved)})
        outputs.append(item)

    write_json(
        step_dir / "result.json",
        {
            "exit_code": exit_code,
            "launch_error": launch_error,
            "duration_seconds": round(time.time() - started, 3),
            "stdout_sha256": sha256(stdout_path),
            "stderr_sha256": sha256(stderr_path),
            "outputs": outputs,
        },
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
