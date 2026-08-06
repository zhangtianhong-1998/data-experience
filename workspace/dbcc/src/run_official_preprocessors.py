#!/usr/bin/env python3
"""Exercise the official repository's three publicly shipped preprocessors."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
OFFICIAL = ROOT / "official-source"
EXPECTED_COMMIT = "8b44e971756e421ade723442dafd17513fd70e1a"


def main() -> None:
    if not (OFFICIAL / ".git").exists():
        raise SystemExit("official source missing; run ./fetch_official_source.sh first")

    source_commit = subprocess.check_output(
        ["git", "-C", str(OFFICIAL), "rev-parse", "HEAD"], text=True
    ).strip()
    if source_commit != EXPECTED_COMMIT:
        raise SystemExit(f"official source commit mismatch: {source_commit}")

    sys.path.insert(0, str(OFFICIAL))
    from src.core.domain import Column, Database, Table  # type: ignore
    from src.preprocessor.strategies.factorizer import FactorizationStrategy  # type: ignore
    from src.preprocessor.strategies.inheritance import InheritanceStrategy  # type: ignore
    from src.preprocessor.strategies.raw import RawStrategy  # type: ignore

    payload = json.loads((ROOT / "data" / "database.json").read_text(encoding="utf-8"))
    tables = []
    for raw_table in payload["tables"]:
        columns = [
            Column(
                name=raw_column["name"],
                original_type=raw_column["type"],
                description=raw_column.get("description"),
                metadata={"tags": raw_column.get("tags", [])},
            )
            for raw_column in raw_table["columns"]
        ]
        tables.append(Table(name=raw_table["name"], columns=columns))
    database = Database(id=payload["id"], tables=tables)

    strategies = {
        "raw": RawStrategy(enable_column_description=True, enable_column_type=True),
        "factorization": FactorizationStrategy(
            min_support=2,
            min_cols=2,
            min_gain=1,
            enable_column_description=True,
            enable_column_type=True,
        ),
        "inheritance": InheritanceStrategy(
            min_parent_cols=3,
            min_gain=2,
            max_delta_ratio=0.45,
            enable_column_description=True,
            enable_column_type=True,
        ),
    }

    output_dir = ROOT / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "official_repository": "https://github.com/MrBlankness/SchemaCompression",
        "source_commit": source_commit,
        "scope": "public preprocessor classes only; no paper benchmark or LLM call",
    }
    for name, strategy in strategies.items():
        context = strategy.compress(database)
        (output_dir / f"official_{name}_context.txt").write_text(context, encoding="utf-8")
        summary[name] = {
            "context_chars": len(context),
            "context_lines": len(context.splitlines()),
        }

    (output_dir / "official_preprocessor_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
