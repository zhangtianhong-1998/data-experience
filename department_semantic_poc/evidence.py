from __future__ import annotations

from collections import defaultdict
from typing import Any

from .utils import fingerprint_json, make_ref, short_hash


def _field_comment_index(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for table_name, payload in metadata.items():
        if not isinstance(payload, dict):
            continue
        for field in payload.get("fields") or []:
            if not isinstance(field, dict) or not field.get("field"):
                continue
            field_ref = make_ref("field", table_name, field["field"])
            result[field_ref] = {
                "table_name": table_name,
                "field_name": field["field"],
                "comment": field.get("comment"),
                "table_cn_name": payload.get("cn_name"),
            }
    return result


def build_report_evidence_packages(
    asset_graph: dict[str, Any],
    sql_facts: list[dict[str, Any]],
    selected_department_ref: str | None = None,
    max_package_chars: int = 120_000,
) -> list[dict[str, Any]]:
    selected_department_ref = selected_department_ref or asset_graph.get("scope", {}).get(
        "selected_department_ref"
    )
    facts_by_report: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in sql_facts:
        facts_by_report[fact["report_ref"]].append(fact)
    lineage_by_report: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for lineage in asset_graph.get("field_lineage", []):
        if lineage.get("report_ref"):
            lineage_by_report[lineage["report_ref"]].append(lineage)
    field_comments = _field_comment_index(asset_graph.get("physical_metadata", {}))

    packages: list[dict[str, Any]] = []
    for report_ref, report in sorted(asset_graph.get("reports", {}).items()):
        if selected_department_ref and report.get("department_ref") != selected_department_ref:
            continue
        package_ref = make_ref("package", "report", short_hash(report_ref, 16))
        evidence_prefix = package_ref.removeprefix("package://")
        evidences: list[dict[str, Any]] = []
        evidence_keys: set[str] = set()
        allowed_assets: set[str] = {report_ref}

        def add_evidence(
            kind: str,
            text: str,
            asset_refs: list[str],
            source_refs: list[str] | None = None,
            data: dict[str, Any] | None = None,
        ) -> str:
            key = fingerprint_json(
                {"kind": kind, "text": text, "asset_refs": sorted(asset_refs), "data": data}
            )
            if key in evidence_keys:
                return next(item["evidence_ref"] for item in evidences if item["fingerprint"] == key)
            evidence_keys.add(key)
            evidence_ref = make_ref(
                "evidence", evidence_prefix, f"E{len(evidences) + 1:03d}"
            )
            evidences.append(
                {
                    "evidence_ref": evidence_ref,
                    "kind": kind,
                    "text": text,
                    "asset_refs": sorted(set(asset_refs)),
                    "source_refs": sorted(set(source_refs or [])),
                    "data": data or {},
                    "fingerprint": key,
                }
            )
            allowed_assets.update(asset_refs)
            return evidence_ref

        path = report.get("report_path") or "<缺失报表路径>"
        add_evidence(
            "report_path",
            f"报表路径：{path}",
            [report_ref],
            data={"segments": report.get("report_path_segments", [])},
        )
        for index, segment in enumerate(report.get("report_path_segments", []), start=1):
            add_evidence(
                "report_path_segment",
                f"报表路径第{index}段：{segment}",
                [report_ref],
                data={"position": index, "value": segment},
            )
        mapping = report.get("mapping", {})
        if mapping.get("cn_name"):
            add_evidence(
                "report_mapping",
                f"报表映射中文名：{mapping['cn_name']}；target_dataset_id：{mapping.get('target_dataset_id')}",
                [report_ref],
                data=mapping,
            )
        if report.get("department_ref"):
            add_evidence(
                "configured_department",
                f"实验配置确认报表归属部门：{report.get('department_name')}",
                [report_ref, report["department_ref"]],
                data={
                    "department_ref": report["department_ref"],
                    "assignment_method": report.get("department_assignment_method"),
                },
            )

        component_contexts = []
        for component in report.get("components", []):
            component_ref = component["component_ref"]
            allowed_assets.add(component_ref)
            component_name = component.get("component_name") or "<组件名称缺失>"
            add_evidence(
                "component_name",
                f"组件{component['component_no']}名称：{component_name}；名称类型：{component.get('name_kind')}",
                [report_ref, component_ref],
                component.get("source_refs", []),
                data={
                    "component_no": component["component_no"],
                    "component_name": component.get("component_name"),
                    "name_kind": component.get("name_kind"),
                },
            )
            dataset = component.get("dataset", {})
            dataset_ref = dataset["dataset_ref"]
            allowed_assets.add(dataset_ref)
            add_evidence(
                "dataset_path",
                f"组件{component['component_no']}使用数据集：{dataset.get('dataset_path') or '<数据集路径缺失>'}",
                [report_ref, component_ref, dataset_ref],
                component.get("source_refs", []),
                data={"segments": dataset.get("dataset_path_segments", [])},
            )
            component_contexts.append(
                {
                    "component_ref": component_ref,
                    "component_no": component["component_no"],
                    "component_name": component.get("component_name"),
                    "name_kind": component.get("name_kind"),
                    "dataset_ref": dataset_ref,
                    "dataset_path": dataset.get("dataset_path"),
                    "query_refs": [item["query_ref"] for item in dataset.get("queries", [])],
                    "status": component.get("status"),
                }
            )

        report_sql_facts = sorted(facts_by_report.get(report_ref, []), key=lambda item: item["query_ref"])
        field_refs_used: set[str] = set()
        table_refs_used: set[str] = set()
        query_contexts = []
        for fact in report_sql_facts:
            query_ref = fact["query_ref"]
            allowed_assets.add(query_ref)
            query_assets = [report_ref, fact["component_ref"], fact["dataset_ref"], query_ref]
            add_evidence(
                "sql_query",
                f"SQL查询 {query_ref}：\n{fact.get('sql') or '<SQL缺失>'}",
                query_assets,
                fact.get("source_refs", []),
                data={
                    "parse_status": fact.get("parse_status"),
                    "occurrence_count": fact.get("occurrence_count"),
                },
            )
            if fact.get("parse_status") != "parsed":
                add_evidence(
                    "sql_parse_issue",
                    f"SQL解析失败：{fact.get('parse_error')}",
                    query_assets,
                    fact.get("source_refs", []),
                )
            for table in fact.get("tables", []):
                table_ref = table["table_ref"]
                table_refs_used.add(table_ref)
                add_evidence(
                    "sql_table_reference",
                    f"SQL引用物理表：{table['table_name']}；元数据匹配：{table['metadata_match']}",
                    query_assets + [table_ref],
                    fact.get("source_refs", []),
                    data=table,
                )
            for projection in fact.get("projections", []):
                projection_fields = [
                    item["field_ref"]
                    for item in projection.get("source_fields", [])
                    if item.get("field_ref")
                ]
                field_refs_used.update(projection_fields)
                add_evidence(
                    "sql_projection",
                    "SQL输出："
                    f"{projection.get('output_name')} = {projection.get('expression')}；"
                    f"结构角色：{projection.get('structural_role')}；"
                    f"聚合：{projection.get('aggregate_functions')}",
                    query_assets + projection_fields,
                    fact.get("source_refs", []),
                    data=projection,
                )
            if fact.get("filters"):
                filter_fields = [
                    item["field_ref"]
                    for item in fact.get("all_fields", [])
                    if item.get("field_ref")
                ]
                field_refs_used.update(filter_fields)
                add_evidence(
                    "sql_filter",
                    f"SQL过滤条件：{fact['filters']}",
                    query_assets + filter_fields,
                    fact.get("source_refs", []),
                    data={"filter": fact["filters"]},
                )
            if fact.get("group_by"):
                add_evidence(
                    "sql_group_by",
                    f"SQL分组粒度：{fact['group_by']}",
                    query_assets,
                    fact.get("source_refs", []),
                    data={"group_by": fact["group_by"]},
                )
            query_contexts.append(
                {
                    "query_ref": query_ref,
                    "component_ref": fact["component_ref"],
                    "dataset_ref": fact["dataset_ref"],
                    "parse_status": fact.get("parse_status"),
                    "tables": [item.get("table_name") for item in fact.get("tables", [])],
                    "projections": [
                        {
                            "output_name": item.get("output_name"),
                            "expression": item.get("expression"),
                            "role": item.get("structural_role"),
                            "source_fields": [
                                field.get("field_ref")
                                for field in item.get("source_fields", [])
                                if field.get("field_ref")
                            ],
                        }
                        for item in fact.get("projections", [])
                    ],
                    "filters": fact.get("filters"),
                    "group_by": fact.get("group_by", []),
                }
            )

        lineage_contexts = []
        for lineage in sorted(
            lineage_by_report.get(report_ref, []), key=lambda item: item["lineage_ref"]
        ):
            assets = [report_ref]
            if lineage.get("table_ref"):
                assets.append(lineage["table_ref"])
                table_refs_used.add(lineage["table_ref"])
            if lineage.get("field_ref"):
                assets.append(lineage["field_ref"])
                field_refs_used.add(lineage["field_ref"])
            add_evidence(
                "field_lineage",
                "字段血缘："
                f"报表绑定列 {lineage.get('bound_column_name')} → "
                f"{lineage.get('table_name')}.{lineage.get('field_name')}；"
                f"状态：{lineage.get('status')}",
                assets,
                [lineage.get("source_ref")],
                data=lineage,
            )
            lineage_contexts.append(lineage)

        for field_ref in sorted(field_refs_used):
            field = field_comments.get(field_ref)
            if not field:
                continue
            table_ref = make_ref("table", field["table_name"])
            table_refs_used.add(table_ref)
            add_evidence(
                "physical_field_comment",
                f"物理字段 {field['table_name']}.{field['field_name']}：{field.get('comment') or '<注释缺失>'}；表中文名：{field.get('table_cn_name')}",
                [table_ref, field_ref],
                data=field,
            )

        package = {
            "schema_version": "report-evidence-package-v1",
            "package_ref": package_ref,
            "report_ref": report_ref,
            "department_ref": report.get("department_ref"),
            "department_name": report.get("department_name"),
            "report": {
                "report_path": report.get("report_path"),
                "report_path_segments": report.get("report_path_segments", []),
                "mapping": report.get("mapping", {}),
                "status": report.get("status"),
            },
            "components": component_contexts,
            "queries": query_contexts,
            "lineage": lineage_contexts,
            "allowed_asset_refs": sorted(allowed_assets),
            "evidences": evidences,
        }
        package["package_fingerprint"] = fingerprint_json(package)
        package["estimated_chars"] = len(str(package))
        package["status"] = (
            "ready"
            if package["estimated_chars"] <= max_package_chars
            else "requires_component_cluster_chunking"
        )
        packages.append(package)
    return packages

