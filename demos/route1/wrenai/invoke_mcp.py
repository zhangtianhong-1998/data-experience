"""Call the live Wren MCP server and save the exact tool results."""

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Any

from fastmcp import Client


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "device_project" / "results" / "mcp_calls.json"


def serializable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return serializable(value.model_dump(mode="json"))
    if dataclasses.is_dataclass(value):
        return {
            field.name: serializable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, list):
        return [serializable(item) for item in value]
    if isinstance(value, dict):
        return {key: serializable(item) for key, item in value.items()}
    return value


async def main() -> None:
    captured = []
    async with Client("http://127.0.0.1:8010/mcp") as client:
        tools = await client.list_tools()
        captured.append(
            {
                "operation": "tools/list",
                "tools": [
                    {"name": tool.name, "inputSchema": tool.inputSchema}
                    for tool in tools
                ],
            }
        )
        calls = [
            (
                "get_context",
                {"question": "ORG_1001 在 2026 上半年按产品一级分类的设备订货金额"},
            ),
            (
                "query_cube",
                {
                    "cube": "device_business",
                    "measures": ["device_order_amount", "device_profit_amount"],
                    "dimensions": ["product_l1"],
                    "filters": [
                        "org_code:eq:ORG_1001",
                        "year_month:gte:202601",
                        "year_month:lte:202606",
                    ],
                },
            ),
        ]
        for name, arguments in calls:
            result = await client.call_tool(name, arguments)
            captured.append(
                {
                    "operation": "tools/call",
                    "tool": name,
                    "arguments": arguments,
                    "result": serializable(result),
                }
            )
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(captured, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(captured, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
