"""通过真实 MCP HTTP 协议调用官方 DataHub MCP Server 并保存返回。"""

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Any

from fastmcp import Client


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "datahub_mcp_calls.json"
MCP_URL = "http://127.0.0.1:8000/mcp"
DATASET_URN = "urn:li:dataset:(urn:li:dataPlatform:sqlite,main.device_order_profit,PROD)"


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
    async with Client(MCP_URL) as client:
        tools = await client.list_tools()
        captured.append(
            {
                "operation": "tools/list",
                "result": [
                    {"name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema}
                    for tool in tools
                ],
            }
        )

        calls = [
            ("search", {"query": "/q device+order", "filter": "entity_type = dataset", "num_results": 5}),
            ("get_entities", {"urns": DATASET_URN}),
            ("list_schema_fields", {"urn": DATASET_URN, "limit": 20}),
            ("get_lineage", {"urn": DATASET_URN, "upstream": False, "max_hops": 2}),
            ("get_dataset_queries", {"urn": DATASET_URN, "count": 10}),
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

    OUTPUT.write_text(json.dumps(captured, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(captured)} MCP protocol results to {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
