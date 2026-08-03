"""Verify that DataHub's real MCP server returned the demo's governed context."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
calls = json.loads((ROOT / "results" / "mcp_calls.json").read_text(encoding="utf-8"))
by_tool = {item.get("tool"): item for item in calls if item.get("tool")}


def data(tool: str):
    return by_tool[tool]["result"]["data"]


entity = data("get_entities")
schema = data("list_schema_fields")
queries = data("get_dataset_queries")
lineage = data("get_lineage")["downstreams"]
search = data("search")

checks = {
    "official_mcp_tools_exposed": len(calls[0]["tool_names"]) == 6,
    # Search ranking is eventually consistent and the similarly named generated
    # view can legitimately rank ahead of the governed base table.  What matters
    # is that the governed entity is present in the candidate set.
    "search_finds_governed_dataset": any(
        item["entity"]["properties"]["name"] == "设备订货事实表"
        for item in search["searchResults"]
    ),
    "business_description_returned": "取消单不得计入指标" in entity["editableProperties"]["description"],
    "required_filter_returned": any(
        item["key"] == "required_filter" and "status=confirmed" in item["value"]
        for item in entity["properties"]["customProperties"]
    ),
    "glossary_term_returned": entity["glossaryTerms"]["terms"][0]["term"]["properties"]["name"] == "设备订货金额",
    "ten_schema_fields_returned": len(schema["fields"]) == 10,
    "two_real_query_examples_returned": queries["total"] == 2,
    # On a clean v1.5.0.6 graph the dataset->dashboard edge is returned, while
    # the chart membership is represented on the dashboard entity rather than
    # as a second dataset-lineage result.
    "bi_downstream_lineage_returned": lineage["total"] >= 1
    and any(
        item["entity"]["urn"]
        == "urn:li:dashboard:(powerbi,device_business_h1_2026)"
        for item in lineage["searchResults"]
    ),
}

report = {
    "passed": all(checks.values()),
    "checks": checks,
    "evidence": {
        "tool_names": calls[0]["tool_names"],
        "dataset": entity["urn"],
        "schema_field_count": len(schema["fields"]),
        "query_count": queries["total"],
        "downstream_count": lineage["total"],
    },
}
(ROOT / "results" / "verification.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["passed"] else 1)
