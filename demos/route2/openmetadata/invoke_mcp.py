"""Call the MCP server embedded in the running OpenMetadata instance."""

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Any

from fastmcp import Client


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[2]
FQN = "enterprise_mysql.default.enterprise_demo.device_orders"


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
    token = (WORKSPACE / "runtime" / "openmetadata-1.13.0" / "admin.jwt").read_text(encoding="utf-8").strip()
    captured = []
    async with Client("http://127.0.0.1:8585/mcp", auth=token, timeout=30) as client:
        tools = await client.list_tools()
        captured.append(
            {
                "operation": "tools/list",
                "tool_names": [tool.name for tool in tools],
                "tools": [serializable(tool) for tool in tools],
            }
        )
        calls = [
            ("search_metadata", {"query": "device_orders", "entityType": "table", "size": 5}),
            ("get_entity_details", {"entityType": "table", "fqn": FQN}),
        ]
        for name, arguments in calls:
            try:
                result = await client.call_tool(name, arguments)
                captured.append(
                    {"operation": "tools/call", "tool": name, "arguments": arguments, "result": serializable(result)}
                )
            except Exception as exc:
                captured.append(
                    {"operation": "tools/call", "tool": name, "arguments": arguments, "error": str(exc)}
                )
    (ROOT / "results" / "mcp_calls.json").write_text(
        json.dumps(captured, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(captured, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
