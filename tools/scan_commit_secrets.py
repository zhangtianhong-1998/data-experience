"""Scan files eligible for commit without printing any matched secret value."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT.parent / "data-ex" / ".env"


def candidates() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT
    )
    return [ROOT / os.fsdecode(item) for item in output.split(b"\0") if item]


configured = dotenv_values(ENV) if ENV.exists() else {}
exact_values = {
    name: str(value).encode()
    for name, value in configured.items()
    if value and len(str(value)) >= 8
}

patterns = {
    "jwt_like": re.compile(rb"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    "openai_key_like": re.compile(rb"\bsk-[A-Za-z0-9_-]{16,}"),
    "private_key_block": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}

findings: list[tuple[str, str]] = []
scanned = 0
for path in candidates():
    if not path.is_file():
        continue
    try:
        data = path.read_bytes()
    except OSError:
        continue
    if b"\0" in data[:8192]:
        continue
    scanned += 1
    relative = str(path.relative_to(ROOT))
    for name, value in exact_values.items():
        if value in data:
            findings.append((f"configured_value:{name}", relative))
    for name, pattern in patterns.items():
        if pattern.search(data):
            findings.append((name, relative))

print(f"candidate_text_files_scanned={scanned}")
print(f"finding_count={len(findings)}")
for kind, relative in findings:
    print(f"{kind}\t{relative}")
raise SystemExit(1 if findings else 0)
