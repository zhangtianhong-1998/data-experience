from __future__ import annotations

import re
from typing import Any

from .models import AlignmentBatchResult, AgentAnswer, ReportExtraction


GENERIC_LABEL = re.compile(r"^(?:LONG_COL_?\d+|COL_?\d+|c\d+|图表\d*|组件\d*)$", re.IGNORECASE)


def evidence_grade(evidence_kinds: set[str]) -> str:
    if "sql_projection" in evidence_kinds and (
        "physical_field_comment" in evidence_kinds or "field_lineage" in evidence_kinds
    ):
        return "A"
    deterministic = {
        "sql_projection",
        "sql_table_reference",
        "sql_filter",
        "sql_group_by",
        "field_lineage",
        "physical_field_comment",
    }
    if evidence_kinds.intersection(deterministic) and (
        len(evidence_kinds) >= 2
        or evidence_kinds.intersection(
            {"sql_filter", "field_lineage", "physical_field_comment"}
        )
    ):
        return "B"
    if evidence_kinds.intersection(
        deterministic
        | {"report_path", "report_mapping", "component_name", "dataset_path"}
    ):
        return "C"
    return "U"


def validate_report_extraction(
    package: dict[str, Any], payload: dict[str, Any]
) -> tuple[ReportExtraction | None, dict[str, Any], list[dict[str, Any]]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        result = ReportExtraction.model_validate(payload)
    except Exception as exc:
        return None, {"is_valid": False, "errors": [str(exc)], "warnings": []}, []
    if result.package_ref != package["package_ref"]:
        errors.append("package_ref 与输入证据包不一致")
    if result.report_ref != package["report_ref"]:
        errors.append("report_ref 与输入证据包不一致")
    allowed_assets = set(package.get("allowed_asset_refs", []))
    evidence_by_ref = {
        item["evidence_ref"]: item for item in package.get("evidences", [])
    }
    concept_refs: set[str] = set()
    enriched: list[dict[str, Any]] = []
    for concept in result.concepts:
        if concept.local_ref in concept_refs:
            errors.append(f"概念 local_ref 重复：{concept.local_ref}")
        concept_refs.add(concept.local_ref)
        invalid_assets = sorted(set(concept.asset_refs) - allowed_assets)
        invalid_evidence = sorted(set(concept.evidence_refs) - set(evidence_by_ref))
        if invalid_assets:
            errors.append(f"{concept.local_ref} 引用了越界资产：{invalid_assets}")
        if invalid_evidence:
            errors.append(f"{concept.local_ref} 引用了越界证据：{invalid_evidence}")
        kinds = {
            evidence_by_ref[ref]["kind"]
            for ref in concept.evidence_refs
            if ref in evidence_by_ref
        }
        grade = evidence_grade(kinds)
        if GENERIC_LABEL.fullmatch(concept.label.strip()) and not kinds.intersection(
            {"physical_field_comment", "field_lineage", "component_name", "report_mapping"}
        ):
            errors.append(f"{concept.local_ref} 仅使用技术名称生成业务概念：{concept.label}")
        if concept.metric_definition and concept.concept_type not in {"metric", "measure"}:
            warnings.append(
                f"{concept.local_ref} 类型为 {concept.concept_type} 但包含 metric_definition"
            )
        item = concept.model_dump(mode="json")
        item["evidence_grade"] = grade
        item["evidence_kinds"] = sorted(kinds)
        enriched.append(item)
    relation_refs: set[str] = set()
    for relation in result.relations:
        if relation.relation_ref in relation_refs:
            errors.append(f"关系 relation_ref 重复：{relation.relation_ref}")
        relation_refs.add(relation.relation_ref)
        if relation.subject_ref not in concept_refs or relation.object_ref not in concept_refs:
            errors.append(f"{relation.relation_ref} 引用了不存在的局部概念")
        invalid_evidence = sorted(set(relation.evidence_refs) - set(evidence_by_ref))
        if invalid_evidence:
            errors.append(f"{relation.relation_ref} 引用了越界证据：{invalid_evidence}")
    for unresolved in result.unresolved:
        invalid_assets = sorted(set(unresolved.related_asset_refs) - allowed_assets)
        invalid_evidence = sorted(set(unresolved.evidence_refs) - set(evidence_by_ref))
        if invalid_assets:
            errors.append(f"{unresolved.item_ref} 引用了越界资产：{invalid_assets}")
        if invalid_evidence:
            errors.append(f"{unresolved.item_ref} 引用了越界证据：{invalid_evidence}")
    return (
        result,
        {
            "is_valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "concept_count": len(result.concepts),
            "relation_count": len(result.relations),
            "unresolved_count": len(result.unresolved),
        },
        enriched,
    )


def validate_alignment_result(
    batch: dict[str, Any], payload: dict[str, Any]
) -> tuple[AlignmentBatchResult | None, dict[str, Any]]:
    try:
        result = AlignmentBatchResult.model_validate(payload)
    except Exception as exc:
        return None, {"is_valid": False, "errors": [str(exc)]}
    errors: list[str] = []
    if result.batch_ref != batch["batch_ref"]:
        errors.append("batch_ref 与输入不一致")
    if result.department_ref != batch["department_ref"]:
        errors.append("department_ref 与输入不一致")
    candidate_refs = {item["candidate_ref"] for item in batch.get("candidates", [])}
    evidence_refs = {
        ref
        for item in batch.get("candidates", [])
        for ref in item.get("allowed_evidence_refs", [])
    }
    seen: set[str] = set()
    for decision in result.decisions:
        if decision.candidate_ref not in candidate_refs:
            errors.append(f"越界 candidate_ref：{decision.candidate_ref}")
        if decision.candidate_ref in seen:
            errors.append(f"candidate_ref 重复：{decision.candidate_ref}")
        seen.add(decision.candidate_ref)
        invalid = sorted(set(decision.evidence_refs) - evidence_refs)
        if invalid:
            errors.append(f"{decision.candidate_ref} 引用了越界证据：{invalid}")
    missing = candidate_refs - seen
    if missing:
        errors.append(f"未返回全部候选判断：{sorted(missing)}")
    return result, {"is_valid": not errors, "errors": errors}


def validate_agent_answer(payload: dict[str, Any], question_id: str) -> tuple[AgentAnswer | None, dict[str, Any]]:
    try:
        result = AgentAnswer.model_validate(payload)
    except Exception as exc:
        return None, {"is_valid": False, "errors": [str(exc)]}
    errors = [] if result.question_id == question_id else ["question_id 与输入不一致"]
    return result, {"is_valid": not errors, "errors": errors}
