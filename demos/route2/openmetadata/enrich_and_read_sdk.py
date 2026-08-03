"""Use OpenMetadata's official Python SDK to enrich and retrieve the catalog."""

import json
from pathlib import Path

from metadata.generated.schema.entity.data.table import Table
from metadata.generated.schema.entity.services.connections.metadata.openMetadataConnection import (
    AuthProvider,
    OpenMetadataConnection,
)
from metadata.generated.schema.security.client.openMetadataJWTClientConfig import (
    OpenMetadataJWTClientConfig,
)
from metadata.ingestion.ometa.ometa_api import OpenMetadata


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[2]
token = (WORKSPACE / "runtime" / "openmetadata-1.13.0" / "admin.jwt").read_text(encoding="utf-8").strip()
client = OpenMetadata(
    OpenMetadataConnection(
        hostPort="http://127.0.0.1:8585/api",
        authProvider=AuthProvider.openmetadata,
        securityConfig=OpenMetadataJWTClientConfig(jwtToken=token),
        storeServiceConnection=False,
    )
)

listed = client.list_entities(Table, fields=["columns", "description", "service"]).entities
demo_tables = [table for table in listed if "enterprise_mysql" in str(table.fullyQualifiedName)]
by_name = {str(table.name.root): table for table in demo_tables}
device_orders = by_name["device_orders"]

governed_description = (
    "设备订货事实表。指标“设备订货金额”= confirmed 订单的 order_amount 合计；"
    "必须显式限定 org_code；单位 CNY；取消单不得计入。"
)
client.patch_description(Table, device_orders, governed_description, force=True, skip_on_failure=False)

refreshed = client.get_by_name(
    Table,
    str(device_orders.fullyQualifiedName.root),
    fields=["columns", "description", "service", "database", "databaseSchema"],
    nullable=False,
)
columns = [
    {
        "name": str(column.name.root),
        "data_type": str(column.dataType.value),
        "description": str(column.description.root) if column.description else None,
    }
    for column in refreshed.columns
]
report = {
    "sdk_package": "openmetadata-ingestion==1.13.0.0",
    "server_version": client.server_version,
    "tables_discovered": [str(table.fullyQualifiedName.root) for table in demo_tables],
    "selected_fqn": str(refreshed.fullyQualifiedName.root),
    "description_after_patch": str(refreshed.description.root),
    "columns": columns,
    "intermediate_entity_id": str(refreshed.id.root),
    "passed": (
        len(demo_tables) == 3
        and "取消单不得计入" in str(refreshed.description.root)
        and len(columns) == 10
    ),
}
(ROOT / "results" / "sdk_context.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["passed"] else 1)
