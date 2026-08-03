"""通过 DataHub 官方 SDK v2 读回同一资产，并保存可直接阅读的返回。"""

import json
from pathlib import Path
from typing import Any

from datahub.sdk import DataHubClient


SERVER = "http://localhost:8080"
DATASET_URN = "urn:li:dataset:(urn:li:dataPlatform:sqlite,main.device_order_profit,PROD)"
OUTPUT = Path(__file__).resolve().parents[1] / "output" / "datahub_sdk_readback.json"


def urn_text(value: Any) -> str:
    return str(value)


def main() -> None:
    client = DataHubClient(server=SERVER)
    client.test_connection()
    dataset = client.entities.get(DATASET_URN)

    result = {
        "python_type": f"{type(dataset).__module__}.{type(dataset).__name__}",
        "urn": urn_text(dataset.urn),
        "display_name": dataset.display_name,
        "description": dataset.description,
        "custom_properties": dataset.custom_properties,
        "owners": [
            {"owner": owner.owner, "type": owner.type}
            for owner in (dataset.owners or [])
        ],
        "tags": [tag.tag for tag in (dataset.tags or [])],
        "terms": [term.urn for term in (dataset.terms or [])],
        "schema": [
            {
                "field_path": field.field_path,
                "native_type": field.native_type,
                "description": field.description,
            }
            for field in (dataset.schema or [])
        ],
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved to {OUTPUT}")


if __name__ == "__main__":
    main()
