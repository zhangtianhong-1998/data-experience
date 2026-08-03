from __future__ import annotations

import copy
import re
from collections import Counter, defaultdict
from typing import Any, Iterable

from .utils import make_ref, sha256_text


TABLE_FALLBACK = re.compile(
    r"\b(?:FROM|JOIN)\s+([`\"\[]?[A-Za-z_][\w$]*[`\"\]]?(?:\s*\.\s*[`\"\[]?[A-Za-z_][\w$]*[`\"\]]?){0,2})",
    re.IGNORECASE,
)


def _clean_identifier(value: str) -> str:
    return value.strip().strip('`"[]').strip()


def fallback_tables(sql: str) -> list[str]:
    result: list[str] = []
    for match in TABLE_FALLBACK.finditer(sql or ""):
        name = ".".join(
            _clean_identifier(part) for part in re.split(r"\s*\.\s*", match.group(1))
        )
        if name and name not in result:
            result.append(name)
    return result


def _metadata_indexes(metadata: dict[str, Any]) -> tuple[dict[str, str], dict[str, list[str]]]:
    exact: dict[str, str] = {}
    leaf: dict[str, list[str]] = defaultdict(list)
    for name in metadata:
        exact[name.lower()] = name
        leaf[name.lower().rsplit(".", 1)[-1]].append(name)
    return exact, leaf


def resolve_metadata_table(
    name: str, exact: dict[str, str], leaf: dict[str, list[str]]
) -> tuple[str, str]:
    key = name.lower()
    if key in exact:
        return exact[key], "matched_exact"
    matches = leaf.get(key.rsplit(".", 1)[-1], [])
    if len(matches) == 1:
        return matches[0], "matched_unique_leaf"
    if len(matches) > 1:
        return name, "ambiguous_leaf"
    return name, "metadata_unmatched"


def _qualified_table_name(table: Any) -> str:
    parts = [table.catalog, table.db, table.name]
    return ".".join(part for part in parts if part)


def _parameterize_literals(tree: Any, exp: Any) -> Any:
    result = copy.deepcopy(tree)

    def replace(node: Any) -> Any:
        if isinstance(node, exp.Literal):
            return exp.Placeholder()
        return node

    return result.transform(replace)


def _column_fact(
    column: Any,
    table_aliases: dict[str, str],
    sole_table: str | None,
    exact: dict[str, str],
    leaf: dict[str, list[str]],
) -> dict[str, Any]:
    raw_table = table_aliases.get(column.table, column.table) or sole_table or ""
    resolved_table, table_match = (
        resolve_metadata_table(raw_table, exact, leaf)
        if raw_table
        else ("", "unqualified_ambiguous")
    )
    field_ref = (
        make_ref("field", resolved_table, column.name) if resolved_table else None
    )
    return {
        "sql": column.sql(),
        "raw_table": column.table or None,
        "resolved_table": resolved_table or None,
        "table_match": table_match,
        "field_name": column.name,
        "field_ref": field_ref,
    }


def parse_query_fact(
    query: dict[str, Any],
    report_ref: str,
    component_ref: str,
    dataset_ref: str,
    metadata: dict[str, Any],
    dialect: str | None = None,
) -> dict[str, Any]:
    sql = query.get("sql") or ""
    base = {
        "query_ref": query["query_ref"],
        "report_ref": report_ref,
        "component_ref": component_ref,
        "dataset_ref": dataset_ref,
        "sql": sql,
        "occurrence_count": query.get("occurrence_count", 1),
        "source_refs": query.get("source_refs", []),
        "exact_fingerprint": sha256_text(sql),
        "dialect": dialect,
        "fallback_tables": fallback_tables(sql),
    }
    if not re.match(r"^\s*(?:SELECT|WITH)\b", sql, flags=re.IGNORECASE):
        return {
            **base,
            "parse_status": "failed",
            "parse_error": "SQL不是SELECT/WITH查询或为空",
            "tables": [],
            "projections": [],
            "joins": [],
            "filters": None,
            "group_by": [],
            "order_by": [],
            "all_fields": [],
        }
    try:
        import sqlglot
        from sqlglot import exp
        from sqlglot.errors import ParseError
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("缺少 sqlglot，请先安装 requirements.txt") from exc

    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except (ParseError, ValueError) as exc:
        return {
            **base,
            "parse_status": "failed",
            "parse_error": str(exc),
            "tables": [],
            "projections": [],
            "joins": [],
            "filters": None,
            "group_by": [],
            "order_by": [],
            "all_fields": [],
        }

    exact, leaf = _metadata_indexes(metadata)
    table_nodes = list(tree.find_all(exp.Table))
    raw_tables = sorted({_qualified_table_name(table) for table in table_nodes})
    resolved_tables = []
    for name in raw_tables:
        resolved, status = resolve_metadata_table(name, exact, leaf)
        resolved_tables.append(
            {
                "raw_name": name,
                "table_name": resolved,
                "table_ref": make_ref("table", resolved),
                "metadata_match": status,
            }
        )
    table_aliases = {
        table.alias_or_name: _qualified_table_name(table) for table in table_nodes
    }
    sole_table = raw_tables[0] if len(raw_tables) == 1 else None
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    projections = []
    for index, projection in enumerate(select.expressions if select else [], start=1):
        expression = projection.this if isinstance(projection, exp.Alias) else projection
        aggregates = sorted(
            {node.sql_name().upper() for node in expression.find_all(exp.AggFunc)}
        )
        windows = sorted(
            {node.this.sql_name().upper() for node in expression.find_all(exp.Window)}
        )
        columns = [
            _column_fact(column, table_aliases, sole_table, exact, leaf)
            for column in expression.find_all(exp.Column)
        ]
        role = "measure_candidate" if aggregates or windows else "dimension_candidate"
        projections.append(
            {
                "projection_no": index,
                "output_name": projection.alias_or_name or None,
                "expression": expression.sql(),
                "projection_sql": projection.sql(),
                "structural_role": role,
                "aggregate_functions": aggregates,
                "window_functions": windows,
                "source_fields": columns,
                "implementation_signature": sha256_text(
                    str(
                        {
                            "role": role,
                            "aggregates": aggregates,
                            "fields": sorted(
                                item["field_ref"] for item in columns if item["field_ref"]
                            ),
                        }
                    )
                )[:20],
            }
        )
    joins = []
    for join in tree.find_all(exp.Join):
        target = join.this
        joins.append(
            {
                "kind": (join.args.get("kind") or "INNER").upper(),
                "side": (join.args.get("side") or "").upper(),
                "target": _qualified_table_name(target)
                if isinstance(target, exp.Table)
                else target.sql(),
                "condition": join.args["on"].sql() if join.args.get("on") else None,
            }
        )
    all_fields = [
        _column_fact(column, table_aliases, sole_table, exact, leaf)
        for column in tree.find_all(exp.Column)
    ]
    where = tree.find(exp.Where)
    group = select.args.get("group") if select else None
    order = select.args.get("order") if select else None
    normalized = tree.sql(pretty=False)
    parameterized = _parameterize_literals(tree, exp).sql(pretty=False)
    functions = Counter(node.sql_name().upper() for node in tree.find_all(exp.Func))
    return {
        **base,
        "parse_status": "parsed",
        "parse_error": None,
        "statement_type": tree.key.upper(),
        "normalized_sql": normalized,
        "structural_signature": sha256_text(parameterized),
        "parameterized_sql": parameterized,
        "tables": resolved_tables,
        "table_aliases": dict(sorted(table_aliases.items())),
        "projections": projections,
        "joins": joins,
        "filters": where.this.sql() if isinstance(where, exp.Where) else None,
        "group_by": [item.sql() for item in group.expressions] if group else [],
        "order_by": [item.sql() for item in order.expressions] if order else [],
        "all_fields": all_fields,
        "function_counts": dict(sorted(functions.items())),
    }


def iter_queries(asset_graph: dict[str, Any]) -> Iterable[tuple[str, str, str, dict[str, Any]]]:
    for report_ref, report in asset_graph.get("reports", {}).items():
        for component in report.get("components", []):
            dataset = component.get("dataset", {})
            for query in dataset.get("queries", []):
                yield (
                    report_ref,
                    component["component_ref"],
                    dataset["dataset_ref"],
                    query,
                )


def build_sql_facts(
    asset_graph: dict[str, Any], dialect: str | None = None
) -> list[dict[str, Any]]:
    metadata = asset_graph.get("physical_metadata", {})
    return [
        parse_query_fact(
            query,
            report_ref,
            component_ref,
            dataset_ref,
            metadata,
            dialect=dialect,
        )
        for report_ref, component_ref, dataset_ref, query in iter_queries(asset_graph)
    ]

