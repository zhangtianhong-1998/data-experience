#!/usr/bin/env python3
"""Audit why labels and SQL fingerprints must not be used as entity IDs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


AGG_PREFIX = re.compile(r"^(?:sum|avg|average|max|min|count)[_\-\s]+", re.IGNORECASE)
GENERIC_LABEL = re.compile(r"^(?:long_col_?\d+|col_?\d+|c\d+|图表\d*)$", re.IGNORECASE)


def stable_key(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def normalize_label(label: str) -> str:
    value = AGG_PREFIX.sub("", (label or "").strip())
    return re.sub(r"[_\-\s]+", "", value).lower()


def implementation_key(projection: dict[str, Any]) -> str:
    return stable_key(
        {
            "role": projection.get("role_heuristic"),
            "aggregates": projection.get("aggregate_functions", []),
            "windows": projection.get("window_functions", []),
            "dependencies": projection.get("dependency_signature", []),
        }
    )


def collect(paths: list[Path]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for path in paths:
        records = json.loads(path.read_text(encoding="utf-8"))
        for record in records:
            if record.get("parse_status") != "parsed":
                continue
            for projection in record.get("projections", []):
                label = projection.get("output_name") or ""
                if not label or label == "*":
                    continue
                claims.append(
                    {
                        "source_file": str(path),
                        "report_id": record.get("report_id"),
                        "component_no": record.get("component_no"),
                        "dataset_path": record.get("dataset_path"),
                        "label": label,
                        "normalized_label": normalize_label(label),
                        "is_generic_label": bool(GENERIC_LABEL.match(label.strip())),
                        "implementation_key": implementation_key(projection),
                        "role": projection.get("role_heuristic"),
                        "aggregates": projection.get("aggregate_functions", []),
                        "dependencies": projection.get("dependency_signature", []),
                        "query_tables": record.get("tables", []),
                    }
                )
    return claims


def audit(claims: list[dict[str, Any]]) -> dict[str, Any]:
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_impl: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        by_label[claim["normalized_label"]].append(claim)
        by_impl[claim["implementation_key"]].append(claim)

    ambiguous = []
    consistent = []
    generic = []
    for label, items in sorted(by_label.items()):
        impls = sorted({item["implementation_key"] for item in items})
        labels = sorted({item["label"] for item in items})
        entry = {
            "normalized_label": label,
            "surface_labels": labels,
            "observation_count": len(items),
            "implementation_count": len(impls),
            "implementations": [
                {
                    "implementation_key": key,
                    "examples": [
                        {
                            "label": item["label"],
                            "aggregates": item["aggregates"],
                            "dependencies": item["dependencies"],
                            "dataset_path": item["dataset_path"],
                        }
                        for item in items
                        if item["implementation_key"] == key
                    ][:3],
                }
                for key in impls
            ],
        }
        if any(item["is_generic_label"] for item in items):
            generic.append(entry)
        elif len(impls) > 1:
            ambiguous.append(entry)
        elif len(items) > 1:
            consistent.append(entry)

    cross_label = []
    for key, items in sorted(by_impl.items()):
        labels = sorted({item["normalized_label"] for item in items if not item["is_generic_label"]})
        if len(labels) > 1:
            cross_label.append(
                {
                    "implementation_key": key,
                    "normalized_labels": labels,
                    "examples": [
                        {
                            "label": item["label"],
                            "aggregates": item["aggregates"],
                            "dependencies": item["dependencies"],
                        }
                        for item in items
                    ][:5],
                    "decision": "synonym_candidate_only",
                }
            )

    return {
        "claim_count": len(claims),
        "normalized_label_count": len(by_label),
        "implementation_count": len(by_impl),
        "ambiguous_non_generic_labels": ambiguous,
        "generic_label_groups": generic,
        "repeated_consistent_labels": consistent,
        "cross_label_same_implementation_candidates": cross_label,
        "policy": {
            "auto_merge": "仅在非通用标签、规范标签相同、实现签名相同且来源边界兼容时合并局部 claim。",
            "keep_separate": "同名但实现签名不同；通用系统别名；过滤/粒度/权限边界冲突。",
            "candidate_only": "实现签名相同但标签不同，只生成同义候选，不自动提升为规范概念。",
        },
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Claim 消歧审计",
        "",
        f"- 投影 claim：{result['claim_count']}",
        f"- 规范化标签：{result['normalized_label_count']}",
        f"- 不同实现签名：{result['implementation_count']}",
        f"- 非通用同名歧义组：{len(result['ambiguous_non_generic_labels'])}",
        f"- 通用标签组：{len(result['generic_label_groups'])}",
        f"- 同实现跨标签候选：{len(result['cross_label_same_implementation_candidates'])}",
        "",
        "## 高风险标签",
        "",
    ]
    risky = result["generic_label_groups"] + result["ambiguous_non_generic_labels"]
    if not risky:
        lines.append("当前样本未发现。")
    for group in risky:
        lines.append(
            f"- `{', '.join(group['surface_labels'])}`：{group['observation_count']} 次观察，"
            f"对应 {group['implementation_count']} 种实现。"
        )
        for impl in group["implementations"]:
            example = impl["examples"][0]
            lines.append(
                f"  - `{example['aggregates']}` ← `{example['dependencies']}`（{example['dataset_path'] or '路径缺失'}）"
            )
    lines.extend(
        [
            "",
            "## 保守融合结论",
            "",
            "- 标签不是实体 ID；系统别名尤其不能参与跨域自动融合。",
            "- 相同实现只证明计算实现相近，不证明业务口径、过滤范围、单位或权限相同。",
            "- 自动动作应止于局部 claim 去重；规范概念、同义词和企业指标需要更高等级证据或审批。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    claims = collect(args.inputs)
    result = audit(claims)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "claims.json").write_text(
        json.dumps(claims, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "report.md").write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
