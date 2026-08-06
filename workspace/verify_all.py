#!/usr/bin/env python3
"""Validate both reproductions using only their saved, auditable artifacts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_json(relative_path: str) -> dict:
    path = ROOT / relative_path
    if not path.exists():
        raise AssertionError(f"missing artifact: {relative_path}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_dbcc() -> dict:
    summary = load_json("dbcc/outputs/reproduction_summary.json")
    official = load_json("dbcc/outputs/official_preprocessor_summary.json")

    assert summary["lossless_schema_recovery"] is True
    assert summary["factorization"]["estimated_units"] < summary["raw"]["estimated_units"]
    assert summary["evidence_purification"]["selected_count"] < summary["evidence_purification"]["source_count"]
    assert official["source_commit"] == "8b44e971756e421ade723442dafd17513fd70e1a"
    assert official["factorization"]["context_chars"] < official["raw"]["context_chars"]

    return {
        "lossless_recovery": True,
        "raw_units": summary["raw"]["estimated_units"],
        "factorized_units": summary["factorization"]["estimated_units"],
        "official_source_commit": official["source_commit"],
    }


def verify_csr_rag() -> dict:
    summary = load_json("csr_rag/outputs/summary.json")
    cases = load_json("csr_rag/outputs/cases.json")

    assert summary["case_count"] == len(cases) >= 4
    assert summary["backend"] in {"sentence-transformer", "tfidf"}
    assert 0.0 <= summary["macro_precision"] <= 1.0
    assert 0.0 <= summary["macro_recall"] <= 1.0
    assert summary["median_latency_ms"] >= 0.0
    for case in cases:
        assert case["contextual"]["tables"]
        assert case["structural"]["triplets"]
        assert case["relational"]["ranked_columns"]
        assert set(case["prediction"]["tables"]).issubset(
            set(case["candidate_union_before_relational_rag"])
        )

    return {
        "backend": summary["backend"],
        "macro_precision": summary["macro_precision"],
        "macro_recall": summary["macro_recall"],
        "median_latency_ms": summary["median_latency_ms"],
    }


def main() -> None:
    result = {
        "status": "pass",
        "dbcc": verify_dbcc(),
        "csr_rag": verify_csr_rag(),
    }
    output = ROOT / "verification.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
