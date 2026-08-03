from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EXCEL_LINE_BREAK = re.compile(r"_x000D_\s*", re.IGNORECASE)
MULTI_SPACE = re.compile(r"[ \t]+")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def clean_sql(value: Any) -> str | None:
    text = text_or_none(value)
    if text is None:
        return None
    text = EXCEL_LINE_BREAK.sub("\n", text)
    lines = [MULTI_SPACE.sub(" ", line).strip() for line in text.splitlines()]
    result = "\n".join(line for line in lines if line).strip()
    return result or None


def split_path(value: Any) -> tuple[str | None, list[str], list[int]]:
    """Return canonical path, non-empty segments and 1-based empty positions."""
    text = text_or_none(value)
    if text is None:
        return None, [], []
    raw_segments = text.replace("\\", "/").strip().split("/")
    stripped = [segment.strip() for segment in raw_segments]
    empty_positions = [
        index for index, segment in enumerate(stripped, start=1) if not segment
    ]
    segments = [segment for segment in stripped if segment]
    return "/".join(segments) or None, segments, empty_positions


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def fingerprint_json(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return sha256_text(payload)


def short_hash(value: Any, length: int = 12) -> str:
    return fingerprint_json(value)[:length]


def make_ref(kind: str, *parts: Any) -> str:
    body = "/".join(str(part).strip("/") for part in parts if part is not None)
    return f"{kind}://{body}"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    for key in ["THIRD_PARTY_API_KEY", "THIRD_PARTY_BASE_URL", "THIRD_PARTY_MODEL"]:
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def file_record(path: Path, row_count: int | None = None) -> dict[str, Any]:
    payload = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "sha256": sha256_bytes(payload),
        "size_bytes": len(payload),
        "row_count": row_count,
    }

