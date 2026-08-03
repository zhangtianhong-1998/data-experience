"""Call DataHub MCP search/detail/schema/lineage/query tools."""

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Any

from fastmcp import Client


ROOT = Path(__file__).resolve().parent
URN = "urn:li:dataset:(urn:li:dataPlatform:sqlite,main.device_orders,PROD)"


def serializable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return serializable(value.model_dump(mode="json"))
    if dataclasses.is_dataclass(value):
        return {field.name: serializable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, list):
        return [serializable(item) for item in value]
    if isinstance(value, dict):
        return {key: serializable(item) for key, item in value.items()}
    return value


async def main() -> None:
    captured = []
    async with Client("http://127.0.0.1:8000/mcp") as client:
        tools = await client.list_tools()
        captured.append({"operation": "tools/list", "tool_names": [tool.name for tool in tools]})
        calls = [
            ("search", {"query": "/q device+orders", "filter": "entity_type = dataset", "num_results": 5}),
            ("get_entities", {"urns": URN}),
            ("list_schema_fields", {"urn": URN, "limit": 30}),
            ("get_dataset_queries", {"urn": URN, "count": 10}),
            ("get_lineage", {"urn": URN, "upstream": False, "max_hops": 2}),
        ]
        for name, arguments in calls:
            result = await client.call_tool(name, arguments)
            captured.append(
                {"operation": "tools/call", "tool": name, "arguments": arguments, "result": serializable(result)}
            )
    output = ROOT / "results" / "mcp_calls.json"
    output.write_text(json.dumps(captured, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(captured, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
