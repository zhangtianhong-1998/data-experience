#!/usr/bin/env python3
"""Run CSR-RAG, save per-stage traces, and sweep k/l/h trade-offs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from retriever import (  # noqa: E402
    CSRRAGRetriever,
    RetrievalConfig,
    SentenceTransformerEncoder,
    TfidfEncoder,
    precision_recall,
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def evaluate_case(retriever: CSRRAGRetriever, case: dict, config: RetrievalConfig) -> dict:
    result = retriever.retrieve(case["question"], config)
    table_precision, table_recall = precision_recall(result["prediction"]["tables"], case["gold_tables"])
    column_precision, column_recall = precision_recall(result["prediction"]["columns"], case["gold_columns"])
    result.update(
        {
            "id": case["id"],
            "question": case["question"],
            "gold": {"tables": case["gold_tables"], "columns": case["gold_columns"]},
            "metrics": {
                "table_precision": round(table_precision, 6),
                "table_recall": round(table_recall, 6),
                "column_precision": round(column_precision, 6),
                "column_recall": round(column_recall, 6),
            },
        }
    )
    return result


def aggregate(cases: list[dict]) -> dict:
    return {
        "macro_precision": round(statistics.mean(case["metrics"]["table_precision"] for case in cases), 6),
        "macro_recall": round(statistics.mean(case["metrics"]["table_recall"] for case in cases), 6),
        "macro_column_precision": round(statistics.mean(case["metrics"]["column_precision"] for case in cases), 6),
        "macro_column_recall": round(statistics.mean(case["metrics"]["column_recall"] for case in cases), 6),
        "median_latency_ms": round(statistics.median(case["retrieval_latency_ms"] for case in cases), 3),
        "p90_latency_ms": round(sorted(case["retrieval_latency_ms"] for case in cases)[max(0, int(len(cases) * 0.9) - 1)], 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["sentence-transformer", "tfidf"], default="sentence-transformer")
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--revision", default="1110a243fdf4706b3f48f1d95db1a4f5529b4d41")
    args = parser.parse_args()

    data_dir = ROOT / "data"
    output_dir = ROOT / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    schema = read_json(data_dir / "schema.json")
    history = read_json(data_dir / "history.json")
    questions = read_json(data_dir / "questions.json")

    if args.backend == "sentence-transformer":
        cache_dir = ROOT / "model-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(cache_dir))
        encoder = SentenceTransformerEncoder(args.model, cache_dir, revision=args.revision)
    else:
        encoder = TfidfEncoder()

    retriever = CSRRAGRetriever(schema, history, encoder)
    final_config = RetrievalConfig(contextual_k=1, structural_l=10, relational_h=12)
    cases = [evaluate_case(retriever, case, final_config) for case in questions]
    metrics = aggregate(cases)

    sweep_configs = [
        RetrievalConfig(1, 6, 8),
        RetrievalConfig(1, 10, 12),
        RetrievalConfig(2, 10, 12),
        RetrievalConfig(2, 18, 18),
    ]
    sweep = []
    for config in sweep_configs:
        sweep_cases = [evaluate_case(retriever, case, config) for case in questions]
        sweep.append(
            {
                "config": {
                    "contextual_k": config.contextual_k,
                    "structural_l": config.structural_l,
                    "relational_h": config.relational_h,
                },
                **aggregate(sweep_cases),
            }
        )

    write_json(output_dir / "schema_triplets.json", retriever.triplets)
    write_json(output_dir / "hypergraph.json", retriever.export_hypergraph())
    write_json(output_dir / "cases.json", cases)
    write_json(output_dir / "parameter_sweep.json", sweep)
    backend_label = args.backend.replace("-", "_")
    write_json(output_dir / f"cases_{backend_label}.json", cases)
    write_json(output_dir / f"parameter_sweep_{backend_label}.json", sweep)
    summary = {
        "backend": args.backend,
        "encoder": encoder.name,
        "encoder_revision": getattr(encoder, "revision", None),
        "case_count": len(cases),
        "schema_table_count": len(schema["tables"]),
        "schema_column_count": sum(len(table["columns"]) for table in schema["tables"]),
        "history_count": len(history),
        "index_build_ms": round(retriever.index_build_ms, 3),
        "config": {
            "contextual_k": final_config.contextual_k,
            "structural_l": final_config.structural_l,
            "relational_h": final_config.relational_h,
        },
        **metrics,
        "scope": "independent mechanism-level reproduction; not the authors' private enterprise benchmark",
        "undisclosed_paper_choices": [
            "exact BERT-like checkpoint",
            "Relational-RAG semantic operator",
            "metadata availability rules",
            "operator weights",
        ],
    }
    write_json(output_dir / "summary.json", summary)
    write_json(output_dir / f"summary_{backend_label}.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
