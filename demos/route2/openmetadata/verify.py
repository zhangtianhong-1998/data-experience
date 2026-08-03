"""Verify OpenMetadata connector, SDK enrichment, and embedded MCP evidence."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
source = json.loads((ROOT / "results" / "source_build.json").read_text(encoding="utf-8"))
sdk = json.loads((ROOT / "results" / "sdk_context.json").read_text(encoding="utf-8"))
mcp = json.loads((ROOT / "results" / "mcp_calls.json").read_text(encoding="utf-8"))
by_tool = {item.get("tool"): item for item in mcp if item.get("tool")}


def text_result(tool: str):
    return json.loads(by_tool[tool]["result"]["content"][0]["text"])


search = text_result("search_metadata")
details = text_result("get_entity_details")
checks = {
    "clean_source_counts": source["passed"],
    "connector_discovered_three_assets": len(sdk["tables_discovered"]) == 3,
    "sdk_business_rule_persisted": "取消单不得计入" in sdk["description_after_patch"],
    "chinese_column_comments_preserved": sdk["columns"][0]["description"] == "设备订货单唯一编号",
    "embedded_mcp_exposes_sixteen_tools": len(mcp[0]["tool_names"]) == 16,
    "mcp_search_returns_only_two_matching_tables": search["totalFound"] == 2,
    "mcp_details_returns_ten_columns": len(details["columns"]) == 10,
    "mcp_returns_permission_rule": any(
        column["name"] == "org_code" and "必须显式限定" in column["description"]
        for column in details["columns"]
    ),
}
report = {
    "passed": all(checks.values()),
    "checks": checks,
    "evidence": {
        "server_version": sdk["server_version"],
        "selected_fqn": sdk["selected_fqn"],
        "mcp_tool_count": len(mcp[0]["tool_names"]),
        "mcp_search_total": search["totalFound"],
        "mcp_column_count": len(details["columns"]),
    },
}
(ROOT / "results" / "verification.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["passed"] else 1)
