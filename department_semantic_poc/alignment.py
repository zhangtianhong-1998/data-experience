from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .llm import OpenAICompatibleJSONClient, invocation_fingerprint, render_template
from .models import AlignmentBatchResult
from .utils import fingerprint_json, make_ref, now_iso, read_jsonl, short_hash
from .validation import validate_alignment_result


GENERIC_LABEL = re.compile(r"^(?:LONG_COL_?\d+|COL_?\d+|c\d+|图表\d*|组件\d*)$", re.IGNORECASE)
AGG_PREFIX = re.compile(r"^(?:sum|avg|average|max|min|count)[_\-\s]+", re.IGNORECASE)


def normalize_label(value: str) -> str:
    text = AGG_PREFIX.sub("", (value or "").strip())
    return re.sub(r"[\s_\-（）()【】\[\]]+", "", text).lower()


def char_jaccard(left: str, right: str) -> float:
    left_set = set(normalize_label(left))
    right_set = set(normalize_label(right))
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def _asset_sets(concept: dict[str, Any]) -> dict[str, set[str]]:
    result = {
        "field": set(),
        "table": set(),
        "dataset": set(),
        "query": set(),
        "component": set(),
    }
    for ref in concept.get("asset_refs", []):
        for kind in result:
            if ref.startswith(f"{kind}://"):
                result[kind].add(ref)
        if ref.startswith("field://"):
            body = ref.removeprefix("field://")
            if "/" in body:
                table_name, _ = body.rsplit("/", 1)
                result["table"].add(make_ref("table", table_name))
    return result


def _implementation_signature(concept: dict[str, Any]) -> str | None:
    if concept.get("concept_type") not in {"metric", "measure"}:
        return None
    metric = concept.get("metric_definition")
    fields = sorted(_asset_sets(concept)["field"])
    if not metric and not fields:
        return None
    return fingerprint_json({"metric": metric, "fields": fields})


def _compatible_types(left: str, right: str) -> bool:
    if left == right:
        return True
    return {left, right}.issubset({"metric", "measure"})


def collect_concepts(extraction_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    concepts: list[dict[str, Any]] = []
    seen_mentions: set[str] = set()
    for record in extraction_records:
        if record.get("run_status") not in {"completed_valid", "cache_reused"}:
            continue
        if not record.get("validation", {}).get("is_valid"):
            continue
        for concept in record.get("enriched_concepts", []):
            if concept["mention_ref"] in seen_mentions:
                continue
            seen_mentions.add(concept["mention_ref"])
            item = dict(concept)
            item["normalized_label_program"] = normalize_label(concept.get("label", ""))
            item["implementation_signature"] = _implementation_signature(concept)
            item["asset_sets"] = {
                key: sorted(value) for key, value in _asset_sets(concept).items()
            }
            concepts.append(item)
    return concepts


def build_alignment_candidates(
    extraction_records: list[dict[str, Any]],
    packages: list[dict[str, Any]],
    department_ref: str,
    top_k: int = 5,
    batch_size: int = 8,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    alignment_types = {
        "business_entity",
        "business_event",
        "metric",
        "measure",
        "dimension",
        "attribute",
        "business_term",
    }
    all_concepts = collect_concepts(extraction_records)
    concepts = [
        item
        for item in all_concepts
        if item.get("department_ref") == department_ref
        and not GENERIC_LABEL.fullmatch(item.get("label", "").strip())
        and item.get("concept_type") in alignment_types
    ]
    package_by_report = {item["report_ref"]: item for item in packages}
    evidence_by_ref = {
        evidence["evidence_ref"]: evidence
        for package in packages
        for evidence in package.get("evidences", [])
    }
    reports = {item["report_ref"] for item in concepts}
    table_report_counts: Counter[str] = Counter()
    tables_by_report: dict[str, set[str]] = defaultdict(set)
    for concept in concepts:
        tables_by_report[concept["report_ref"]].update(concept["asset_sets"]["table"])
    for tables in tables_by_report.values():
        table_report_counts.update(tables)
    common_tables = {
        table
        for table, count in table_report_counts.items()
        if re.search(r"(?:calendar|date_dim|dim_date|dim_org|permission|权限|日历|组织)", table, re.IGNORECASE)
    }

    raw_candidates: list[dict[str, Any]] = []
    for left_index, left in enumerate(concepts):
        for right in concepts[left_index + 1 :]:
            if left["report_ref"] == right["report_ref"]:
                continue
            if not _compatible_types(left["concept_type"], right["concept_type"]):
                continue
            left_sets = {key: set(value) for key, value in left["asset_sets"].items()}
            right_sets = {key: set(value) for key, value in right["asset_sets"].items()}
            signals: list[dict[str, Any]] = []
            score = 0.0
            if left["normalized_label_program"] == right["normalized_label_program"]:
                score += 5.0
                signals.append({"name": "exact_normalized_label", "weight": 5.0})
            lexical = round(char_jaccard(left["label"], right["label"]), 4)
            if lexical >= 0.5 and left["normalized_label_program"] != right["normalized_label_program"]:
                score += 2.0
                signals.append({"name": "character_overlap", "weight": 2.0, "value": lexical})
            shared_fields = sorted(left_sets["field"] & right_sets["field"])
            if shared_fields:
                score += 4.0
                signals.append({"name": "shared_physical_field", "weight": 4.0, "values": shared_fields})
            left_impl = left.get("implementation_signature")
            right_impl = right.get("implementation_signature")
            if left_impl and left_impl == right_impl:
                score += 5.0
                signals.append({"name": "same_implementation_signature", "weight": 5.0})
            shared_datasets = sorted(left_sets["dataset"] & right_sets["dataset"])
            if shared_datasets:
                score += 1.5
                signals.append({"name": "shared_dataset", "weight": 1.5, "values": shared_datasets})
            shared_business_tables = sorted(
                (left_sets["table"] & right_sets["table"]) - common_tables
            )
            if shared_business_tables:
                table_weight = round(
                    max(
                        0.2,
                        sum(
                            1 - table_report_counts[table] / max(len(reports), 1)
                            for table in shared_business_tables
                        )
                        / len(shared_business_tables),
                    ),
                    4,
                )
                score += table_weight
                signals.append(
                    {
                        "name": "shared_business_table_idf",
                        "weight": table_weight,
                        "values": shared_business_tables,
                    }
                )
            if score < 4.0:
                continue
            pair_key = sorted([left["mention_ref"], right["mention_ref"]])
            candidate_ref = make_ref("candidate", short_hash(pair_key, 18))
            evidence_refs = sorted(
                set(left.get("evidence_refs", [])) | set(right.get("evidence_refs", []))
            )
            exact_label = left["normalized_label_program"] == right["normalized_label_program"]
            grades_ok = left.get("evidence_grade") in {"A", "B"} and right.get(
                "evidence_grade"
            ) in {"A", "B"}
            same_impl = bool(left_impl and left_impl == right_impl)
            same_field = bool(shared_fields)
            deterministic_safe = (
                left["concept_type"] == right["concept_type"]
                and exact_label
                and grades_ok
                and (
                    (
                        left["concept_type"] in {"metric", "measure"}
                        and same_impl
                    )
                    or (
                        left["concept_type"] in {"dimension", "attribute"}
                        and same_field
                    )
                )
            )
            raw_candidates.append(
                {
                    "candidate_ref": candidate_ref,
                    "department_ref": department_ref,
                    "left_mention_ref": left["mention_ref"],
                    "right_mention_ref": right["mention_ref"],
                    "left_report_ref": left["report_ref"],
                    "right_report_ref": right["report_ref"],
                    "left": left,
                    "right": right,
                    "retrieval_score": round(score, 4),
                    "retrieval_signals": signals,
                    "routing": "deterministic_safe_dedup"
                    if deterministic_safe
                    else "llm_alignment_required",
                    "allowed_evidence_refs": evidence_refs,
                    "evidence_excerpt": [
                        {
                            "evidence_ref": ref,
                            "kind": evidence_by_ref[ref]["kind"],
                            "text": evidence_by_ref[ref]["text"],
                        }
                        for ref in evidence_refs
                        if ref in evidence_by_ref
                    ],
                }
            )

    by_mention: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in raw_candidates:
        by_mention[candidate["left_mention_ref"]].append(candidate)
        by_mention[candidate["right_mention_ref"]].append(candidate)
    selected_refs: set[str] = set()
    for mention_candidates in by_mention.values():
        for candidate in sorted(
            mention_candidates,
            key=lambda item: (-item["retrieval_score"], item["candidate_ref"]),
        )[:top_k]:
            selected_refs.add(candidate["candidate_ref"])
    candidates = sorted(
        [item for item in raw_candidates if item["candidate_ref"] in selected_refs],
        key=lambda item: (-item["retrieval_score"], item["candidate_ref"]),
    )

    llm_candidates = [
        item for item in candidates if item["routing"] == "llm_alignment_required"
    ]
    deterministic_candidates = [
        item for item in candidates if item["routing"] == "deterministic_safe_dedup"
    ]
    batches: list[dict[str, Any]] = []
    for offset in range(0, len(llm_candidates), batch_size):
        batch_candidates = llm_candidates[offset : offset + batch_size]
        batch_ref = make_ref(
            "alignment-batch",
            short_hash([department_ref, [item["candidate_ref"] for item in batch_candidates]], 18),
        )
        batches.append(
            {
                "schema_version": "alignment-batch-input-v1",
                "batch_ref": batch_ref,
                "department_ref": department_ref,
                "candidates": batch_candidates,
            }
        )
    all_pairs = len(concepts) * (len(concepts) - 1) // 2
    eligible_cross_report_pairs = sum(
        1
        for left_index, left in enumerate(concepts)
        for right in concepts[left_index + 1 :]
        if left["report_ref"] != right["report_ref"]
        and _compatible_types(left["concept_type"], right["concept_type"])
    )
    summary = {
        "department_ref": department_ref,
        "report_count": len(reports),
        "concept_count": len(concepts),
        "deferred_concept_count": len(
            [
                item
                for item in all_concepts
                if item.get("department_ref") == department_ref
                and item.get("concept_type") not in alignment_types
            ]
        ),
        "all_pair_count": all_pairs,
        "eligible_cross_report_pair_count": eligible_cross_report_pairs,
        "raw_candidate_count": len(raw_candidates),
        "topk_candidate_count": len(candidates),
        "deterministic_safe_dedup_count": len(deterministic_candidates),
        "llm_alignment_candidate_count": len(llm_candidates),
        "batch_count": len(batches),
        "candidate_compression_ratio_vs_all_pairs": round(len(candidates) / all_pairs, 6)
        if all_pairs
        else 0,
        "llm_compression_ratio_vs_all_pairs": round(len(llm_candidates) / all_pairs, 6)
        if all_pairs
        else 0,
        "common_tables_downweighted": sorted(common_tables),
    }
    return candidates, batches, summary


def align_candidate_batches(
    batches: list[dict[str, Any]],
    client: OpenAICompatibleJSONClient,
    output_path: Path,
    prompt_dir: Path,
    max_batches: int | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    schema = AlignmentBatchResult.model_json_schema()
    schema_text = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    system_prompt = (prompt_dir / "alignment_system.md").read_text(encoding="utf-8")
    selected = batches[:max_batches] if max_batches is not None else batches
    existing = [] if force else read_jsonl(output_path)
    cached = {
        item.get("invocation_fingerprint"): item
        for item in existing
        if item.get("run_status") in {"completed_valid", "cache_reused"}
    }
    records = list(existing)
    completed = {item.get("invocation_fingerprint") for item in records}
    for index, batch in enumerate(selected, start=1):
        user_prompt = render_template(
            prompt_dir / "department_alignment.md",
            {
                "OUTPUT_SCHEMA": schema_text,
                "BATCH_JSON": json.dumps(batch, ensure_ascii=False, separators=(",", ":")),
            },
        )
        invocation = invocation_fingerprint(
            client.config.model,
            system_prompt,
            user_prompt,
            schema,
            {
                "max_tokens": client.config.max_tokens,
                "format_mode": client.config.format_mode,
                "thinking_mode": client.config.thinking_mode,
            },
        )
        print(f"[align {index}/{len(selected)}] {batch['batch_ref']} candidates={len(batch['candidates'])}")
        if not force and invocation in cached:
            print("  cache reused")
            continue
        try:
            response = client.complete_json(
                system_prompt,
                user_prompt,
                schema,
                schema_name="department_alignment",
            )
            result, validation = validate_alignment_result(batch, response["payload"])
            record = {
                "run_ref": make_ref("alignment-run", short_hash([invocation, now_iso()], 16)),
                "operator": "department_candidate_alignment",
                "batch_ref": batch["batch_ref"],
                "department_ref": batch["department_ref"],
                "invocation_fingerprint": invocation,
                "model": client.config.model,
                "run_status": "completed_valid"
                if result is not None and validation["is_valid"]
                else "completed_validation_failed",
                "transport": response["transport"],
                "raw_text": response["raw_text"],
                "result": result.model_dump(mode="json") if result else response["payload"],
                "validation": validation,
                "created_at": now_iso(),
            }
        except Exception as exc:
            record = {
                "run_ref": make_ref("alignment-run", short_hash([invocation, now_iso()], 16)),
                "operator": "department_candidate_alignment",
                "batch_ref": batch["batch_ref"],
                "department_ref": batch["department_ref"],
                "invocation_fingerprint": invocation,
                "model": client.config.model,
                "run_status": "api_or_parse_failed",
                "error": str(exc),
                "validation": {"is_valid": False, "errors": [str(exc)]},
                "created_at": now_iso(),
            }
        if invocation not in completed:
            records.append(record)
            completed.add(invocation)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in records),
            encoding="utf-8",
        )
        print(f"  {record['run_status']}")
    return records


class _DisjointSet:
    def __init__(self, items: list[str]):
        self.parent = {item: item for item in items}

    def find(self, item: str) -> str:
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def materialize_department_semantics(
    candidates: list[dict[str, Any]],
    alignment_records: list[dict[str, Any]],
    department_ref: str,
) -> dict[str, Any]:
    candidate_by_ref = {item["candidate_ref"]: item for item in candidates}
    concepts = {
        concept["mention_ref"]: concept
        for candidate in candidates
        for concept in [candidate["left"], candidate["right"]]
    }
    decisions = []
    dsu = _DisjointSet(sorted(concepts))
    for candidate in candidates:
        if candidate.get("routing") != "deterministic_safe_dedup":
            continue
        decisions.append(
            {
                "candidate_ref": candidate["candidate_ref"],
                "relation": "equivalent",
                "explanation": "程序策略：同类型、同规范标签、A/B级证据，且指标同实现或字段概念同物理字段。",
                "matching_evidence": [item["name"] for item in candidate["retrieval_signals"]],
                "important_differences": [],
                "evidence_refs": candidate.get("allowed_evidence_refs", []),
                "recommended_action": "eligible_for_department_merge",
                "left_mention_ref": candidate["left_mention_ref"],
                "right_mention_ref": candidate["right_mention_ref"],
                "policy_merge_eligible": True,
                "decision_source": "deterministic_policy",
            }
        )
        dsu.union(candidate["left_mention_ref"], candidate["right_mention_ref"])
    for record in alignment_records:
        if record.get("run_status") not in {"completed_valid", "cache_reused"}:
            continue
        if record.get("department_ref") != department_ref:
            continue
        for decision in record.get("result", {}).get("decisions", []):
            candidate = candidate_by_ref.get(decision["candidate_ref"])
            if not candidate:
                continue
            relation = {
                **decision,
                "left_mention_ref": candidate["left_mention_ref"],
                "right_mention_ref": candidate["right_mention_ref"],
            }
            decisions.append(relation)
            left = candidate["left"]
            right = candidate["right"]
            exact_label = left["normalized_label_program"] == right["normalized_label_program"]
            same_impl = (
                left.get("implementation_signature")
                and left.get("implementation_signature") == right.get("implementation_signature")
            )
            grades_ok = left.get("evidence_grade") in {"A", "B"} and right.get(
                "evidence_grade"
            ) in {"A", "B"}
            eligible = (
                decision["relation"] == "equivalent"
                and decision["recommended_action"] == "eligible_for_department_merge"
                and exact_label
                and bool(same_impl)
                and grades_ok
                and not decision.get("important_differences")
            )
            relation["policy_merge_eligible"] = eligible
            if eligible:
                dsu.union(candidate["left_mention_ref"], candidate["right_mention_ref"])

    clusters: dict[str, list[str]] = defaultdict(list)
    for mention_ref in concepts:
        clusters[dsu.find(mention_ref)].append(mention_ref)
    department_concepts = []
    for members in sorted(clusters.values(), key=lambda items: sorted(items)[0]):
        if len(members) < 2:
            continue
        labels = [concepts[item]["label"] for item in members]
        department_concepts.append(
            {
                "department_concept_ref": make_ref(
                    "department-concept", short_hash(sorted(members), 18)
                ),
                "department_ref": department_ref,
                "preferred_label": Counter(labels).most_common(1)[0][0],
                "member_mentions": sorted(members),
                "status": "auto_exact_evidence_dedup",
            }
        )
    return {
        "schema_version": "department-semantics-v1",
        "department_ref": department_ref,
        "generated_at": now_iso(),
        "department_concepts": department_concepts,
        "alignment_relations": decisions,
        "policy": {
            "automatic_merge": "仅等价、同规范标签、同实现、A/B级证据且无重要差异",
            "all_other_decisions": "只记录关系，保留局部mention",
        },
    }
