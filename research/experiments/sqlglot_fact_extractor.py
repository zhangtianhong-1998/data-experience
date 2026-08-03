#!/usr/bin/env python3
"""Evaluate AST-based SQL fact extraction against pipeline facts.

This is intentionally an experiment, not a replacement for the production
pipeline.  It consumes the pipeline's facts.json so the SQL parser can be
evaluated independently from workbook ingestion.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


EXCEL_LINE_BREAK = re.compile(r"_x000D_\s*", re.IGNORECASE)
WHITESPACE = re.compile(r"[ \t]+")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def clean_sql(value: str) -> str:
    value = EXCEL_LINE_BREAK.sub("\n", value or "")
    lines = [WHITESPACE.sub(" ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def iter_queries(facts: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for report_id, report in facts.get("reports", {}).items():
        for component in report.get("components", []):
            dataset = component.get("dataset", {})
            for sql_index, query in enumerate(dataset.get("sql_list", []), start=1):
                yield {
                    "report_id": report_id,
                    "report_path": report.get("report_path", ""),
                    "component_no": component.get("component_no"),
                    "component_name": component.get("component_name", ""),
                    "dataset_path": dataset.get("dataset_path", ""),
                    "sql_index": sql_index,
                    "occurrence_count": query.get("occurrence_count", 1),
                    "regex_physical_tables": query.get("physical_tables", []),
                    "sql": query.get("sql", ""),
                }


def qualified_table_name(table: exp.Table) -> str:
    parts = [table.catalog, table.db, table.name]
    return ".".join(part for part in parts if part)


def column_ref(column: exp.Column, table_aliases: dict[str, str] | None = None) -> dict[str, str]:
    table_aliases = table_aliases or {}
    resolved_table = table_aliases.get(column.table, column.table)
    return {
        "sql": column.sql(),
        "table": column.table,
        "resolved_table": resolved_table,
        "name": column.name,
    }


def projection_fact(
    projection: exp.Expression, table_aliases: dict[str, str]
) -> dict[str, Any]:
    expression = projection.this if isinstance(projection, exp.Alias) else projection
    aggregate_functions = sorted(
        {node.key.upper() for node in expression.find_all(exp.AggFunc)}
    )
    window_functions = sorted(
        {node.this.key.upper() if isinstance(node.this, exp.Expression) else str(node.this)
         for node in expression.find_all(exp.Window)}
    )
    columns = sorted(
        (column_ref(column, table_aliases) for column in expression.find_all(exp.Column)),
        key=lambda item: item["sql"],
    )
    if aggregate_functions or window_functions:
        role = "measure_candidate"
    elif isinstance(expression, exp.Star):
        role = "wildcard"
    else:
        role = "dimension_candidate"
    return {
        "output_name": projection.alias_or_name,
        "expression": expression.sql(),
        "projection_sql": projection.sql(),
        "role_heuristic": role,
        "aggregate_functions": aggregate_functions,
        "window_functions": window_functions,
        "source_columns": columns,
        "dependency_signature": sorted(
            f"{item['resolved_table']}.{item['name']}".lstrip(".") for item in columns
        ),
    }


def parameterize_literals(tree: exp.Expression) -> exp.Expression:
    result = copy.deepcopy(tree)

    def replace(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.Literal):
            return exp.Placeholder()
        return node

    return result.transform(replace)


def parse_query(record: dict[str, Any], dialect: str | None) -> dict[str, Any]:
    sql = clean_sql(record["sql"])
    base = {key: value for key, value in record.items() if key != "sql"}
    base["clean_sql"] = sql
    base["exact_fingerprint"] = sha256_text(sql)
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except (ParseError, ValueError) as exc:
        return {
            **base,
            "parse_status": "failed",
            "parse_error": str(exc),
        }

    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    tables = sorted({qualified_table_name(table) for table in tree.find_all(exp.Table)})
    joins = []
    for join in tree.find_all(exp.Join):
        target = join.this
        joins.append(
            {
                "kind": (join.args.get("kind") or "INNER").upper(),
                "side": (join.args.get("side") or "").upper(),
                "target": qualified_table_name(target) if isinstance(target, exp.Table) else target.sql(),
                "condition": join.args["on"].sql() if join.args.get("on") else None,
                "using": [item.sql() for item in join.args.get("using") or []],
            }
        )

    table_aliases = {
        table.alias_or_name: qualified_table_name(table) for table in tree.find_all(exp.Table)
    }
    projections = [
        projection_fact(item, table_aliases) for item in (select.expressions if select else [])
    ]
    where = tree.args.get("where") if isinstance(tree, exp.Select) else tree.find(exp.Where)
    group = select.args.get("group") if select else None
    order = select.args.get("order") if select else None
    limit = select.args.get("limit") if select else None
    normalized = tree.sql(pretty=False)
    parameterized = parameterize_literals(tree).sql(pretty=False)
    all_columns = sorted(
        (column_ref(column, table_aliases) for column in tree.find_all(exp.Column)),
        key=lambda item: item["sql"],
    )
    function_counts = Counter(node.sql_name() for node in tree.find_all(exp.Func))
    placeholder_count = sum(1 for _ in tree.find_all(exp.Placeholder))
    literal_count = sum(1 for _ in tree.find_all(exp.Literal))

    regex_tables = sorted(set(record.get("regex_physical_tables", [])))
    ast_table_leaves = sorted({table.rsplit(".", 1)[-1] for table in tables})
    regex_table_leaves = sorted({table.rsplit(".", 1)[-1] for table in regex_tables})
    return {
        **base,
        "parse_status": "parsed",
        "parse_error": None,
        "normalized_sql": normalized,
        "ast_fingerprint": sha256_text(normalized),
        "structural_fingerprint": sha256_text(parameterized),
        "parameterized_sql": parameterized,
        "statement_type": tree.key.upper(),
        "tables": tables,
        "table_aliases": dict(sorted(table_aliases.items())),
        "regex_table_agreement": tables == regex_tables,
        "regex_table_leaf_agreement": ast_table_leaves == regex_table_leaves,
        "projections": projections,
        "joins": joins,
        "where": where.this.sql() if isinstance(where, exp.Where) else None,
        "group_by": [item.sql() for item in group.expressions] if group else [],
        "order_by": [item.sql() for item in order.expressions] if order else [],
        "limit": limit.expression.sql() if limit and limit.expression else None,
        "all_columns": all_columns,
        "functions": dict(sorted(function_counts.items())),
        "placeholder_count": placeholder_count,
        "literal_count": literal_count,
    }


def build_summary(records: list[dict[str, Any]], sqlglot_version: str) -> dict[str, Any]:
    parsed = [record for record in records if record["parse_status"] == "parsed"]
    failed = [record for record in records if record["parse_status"] == "failed"]
    projections = [item for record in parsed for item in record.get("projections", [])]
    role_counts = Counter(item["role_heuristic"] for item in projections)
    aliases = Counter(
        item["output_name"]
        for item in projections
        if item.get("output_name") and item["output_name"] != "*"
    )
    exact_groups = Counter(record["exact_fingerprint"] for record in records)
    structural_groups = Counter(
        record["structural_fingerprint"] for record in parsed if record.get("structural_fingerprint")
    )
    return {
        "sqlglot_version": sqlglot_version,
        "query_count": len(records),
        "parsed_count": len(parsed),
        "failed_count": len(failed),
        "parse_coverage": round(len(parsed) / len(records), 4) if records else 0,
        "regex_table_agreement_count": sum(record.get("regex_table_agreement", False) for record in parsed),
        "regex_table_leaf_agreement_count": sum(
            record.get("regex_table_leaf_agreement", False) for record in parsed
        ),
        "projection_count": len(projections),
        "projection_role_counts": dict(sorted(role_counts.items())),
        "distinct_alias_count": len(aliases),
        "aliases": dict(sorted(aliases.items())),
        "exact_duplicate_group_count": sum(count > 1 for count in exact_groups.values()),
        "structural_duplicate_group_count": sum(count > 1 for count in structural_groups.values()),
        "failures": [
            {
                "report_id": item["report_id"],
                "component_no": item["component_no"],
                "sql_index": item["sql_index"],
                "error": item["parse_error"],
            }
            for item in failed
        ],
    }


def render_markdown(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    lines = [
        "# SQLGlot 事实抽取实验",
        "",
        f"- SQLGlot 版本：`{summary['sqlglot_version']}`",
        f"- 查询总数：{summary['query_count']}",
        f"- 成功解析：{summary['parsed_count']}（覆盖率 {summary['parse_coverage']:.1%}）",
        f"- 失败解析：{summary['failed_count']}",
        f"- 与原正则表名完全一致：{summary['regex_table_agreement_count']} / {summary['parsed_count']}",
        f"- 忽略 schema 后与原正则一致：{summary['regex_table_leaf_agreement_count']} / {summary['parsed_count']}",
        f"- 投影字段：{summary['projection_count']}；候选角色：{summary['projection_role_counts']}",
        f"- 不同输出别名：{summary['distinct_alias_count']}",
        f"- 精确重复组：{summary['exact_duplicate_group_count']}；参数化结构重复组：{summary['structural_duplicate_group_count']}",
        "",
        "## 输出别名",
        "",
    ]
    for alias, count in summary["aliases"].items():
        lines.append(f"- `{alias}`：{count}")
    lines.extend(["", "## 失败样例", ""])
    if not summary["failures"]:
        lines.append("无。")
    else:
        for item in summary["failures"]:
            lines.append(
                f"- {item['report_id']} / 组件 {item['component_no']} / SQL {item['sql_index']}：`{item['error']}`"
            )
    lines.extend(["", "## 结论", ""])
    if summary["parse_coverage"] == 1:
        lines.append(
            "当前样例可全部转为 AST。AST 可稳定提供投影表达式、聚合、字段依赖、过滤、分组、排序、连接和参数占位符等可验证事实；这些事实应先于 LLM 进入证据层。"
        )
    else:
        lines.append(
            "AST 覆盖尚不完整，应保留原始 SQL、解析错误和正则降级路径，并按来源系统维护方言路由。"
        )
    lines.append(
        "输出的 `dimension_candidate` / `measure_candidate` 只是结构角色，不等价于已确认的业务维度或指标；业务命名、口径与同义关系仍需多证据融合。"
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("facts", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dialect", default=None)
    args = parser.parse_args()

    facts = json.loads(args.facts.read_text(encoding="utf-8"))
    records = [parse_query(item, args.dialect) for item in iter_queries(facts)]
    version = getattr(sqlglot, "__version__", "unknown")
    summary = build_summary(records, version)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "ast_facts.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "report.md").write_text(
        render_markdown(summary, records), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
