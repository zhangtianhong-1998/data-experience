#!/usr/bin/env python3
"""Run the four DbCC operators and save every intermediate artifact."""

from __future__ import annotations

import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from compression import (  # noqa: E402
    build_template_hierarchy,
    componentize_semantic_tags,
    factorize_column_groups,
    load_database,
    original_schema,
    purify_evidence,
    raw_schema_units,
    recover_factorized_schema,
    render_factorized,
    render_raw,
    render_semantic,
    render_templates,
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    data_dir = ROOT / "data"
    output_dir = ROOT / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    database = load_database(read_json(data_dir / "database.json"))
    question = read_json(data_dir / "question.json")["question"]
    external_entries = read_json(data_dir / "external_knowledge.json")

    raw_context = render_raw(database)
    factorized = factorize_column_groups(database)
    templates = build_template_hierarchy(database)
    semantic = componentize_semantic_tags(database)
    evidence = purify_evidence(question, external_entries)

    recovered = recover_factorized_schema(factorized)
    lossless = recovered == original_schema(database)
    if not lossless:
        raise AssertionError("factorized schema cannot be expanded back to the original schema")

    (output_dir / "01_raw_context.txt").write_text(raw_context, encoding="utf-8")
    (output_dir / "02_factorized_context.txt").write_text(render_factorized(factorized), encoding="utf-8")
    (output_dir / "03_template_context.txt").write_text(render_templates(templates), encoding="utf-8")
    (output_dir / "04_semantic_context.txt").write_text(render_semantic(semantic), encoding="utf-8")
    write_json(output_dir / "02_factorized_artifacts.json", factorized)
    write_json(output_dir / "03_template_artifacts.json", templates)
    write_json(output_dir / "04_semantic_artifacts.json", semantic)
    write_json(output_dir / "05_purified_evidence.json", evidence)

    raw_units = raw_schema_units(database)
    summary = {
        "database_id": database.database_id,
        "table_count": len(database.tables),
        "raw": {"estimated_units": raw_units, "context_chars": len(raw_context)},
        "factorization": {
            "estimated_units": factorized["estimated_units"],
            "saved_units": raw_units - factorized["estimated_units"],
            "reduction_ratio": round(1 - factorized["estimated_units"] / raw_units, 4),
            "component_count": len(factorized["components"]),
        },
        "template_hierarchy": {"template_count": len(templates["templates"])},
        "semantic_componentization": {"component_count": len(semantic["components"])},
        "evidence_purification": {
            "source_count": evidence["source_count"],
            "selected_count": evidence["selected_count"],
            "selected_types": [item["type"] for item in evidence["selected"]],
        },
        "lossless_schema_recovery": lossless,
        "scope": "mechanism-level reproduction on a synthetic enterprise-style schema",
    }
    write_json(output_dir / "reproduction_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
