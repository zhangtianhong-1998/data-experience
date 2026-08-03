"""Add governed business context and a synthetic BI dependency via DataHub SDK."""

import json
from pathlib import Path

from datahub.sdk import Chart, Dashboard, DataHubClient, Dataset, GlossaryTerm, Tag


ROOT = Path(__file__).resolve().parent


def main() -> None:
    client = DataHubClient(server="http://localhost:8080")
    client.test_connection()
    tag = Tag(
        name="CertifiedDeviceMetric",
        display_name="已认证设备指标",
        description="仅用于合成 Demo 的治理标签。",
    )
    term = GlossaryTerm(
        id="device_order_amount",
        display_name="设备订货金额",
        definition="confirmed 设备订货单的 order_amount 合计；必须限定 org_code，单位 CNY。",
    )
    client.entities.upsert(tag)
    client.entities.upsert(term)

    dataset = Dataset(
        platform="sqlite",
        name="main.device_orders",
        display_name="设备订货事实表",
        description="合成 Demo。每行一张设备订货单；取消单不得计入指标。",
        subtype="Table",
        owners=["urn:li:corpuser:device_analytics"],
        tags=["urn:li:tag:CertifiedDeviceMetric"],
        terms=["urn:li:glossaryTerm:device_order_amount"],
        custom_properties={
            "certification": "demo_certified",
            "required_filter": "status=confirmed and explicit org_code",
            "unit": "CNY",
        },
    )
    client.entities.upsert(dataset)
    chart = Chart(
        name="device_orders_by_product",
        platform="powerbi",
        display_name="各产品设备订货金额",
        chart_type="BAR",
        input_datasets=[dataset],
        owners=["urn:li:corpuser:device_analytics"],
    )
    client.entities.upsert(chart)
    dashboard = Dashboard(
        name="device_business_h1_2026",
        platform="powerbi",
        display_name="2026 上半年设备经营看板",
        charts=[chart],
        input_datasets=[dataset],
        owners=["urn:li:corpuser:device_analytics"],
    )
    client.entities.upsert(dashboard)
    result = {
        "dataset": str(dataset.urn),
        "chart": str(chart.urn),
        "dashboard": str(dashboard.urn),
    }
    (ROOT / "results" / "sdk_upsert.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

