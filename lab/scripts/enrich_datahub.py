"""用 DataHub 官方 SDK v2 补充业务上下文和 BI 资产关系。"""

from datahub.sdk import Chart, Dashboard, DataHubClient, Dataset, GlossaryTerm, Tag


SERVER = "http://localhost:8080"


def main() -> None:
    client = DataHubClient(server=SERVER)
    client.test_connection()

    financial = Tag(
        name="FinancialMetricCandidate",
        display_name="财务指标候选",
        description="来自历史 BI 资产、尚需核验统计口径的候选指标。",
    )
    order_term = GlossaryTerm(
        id="device_order_amount",
        display_name="设备订货金额",
        definition="设备订货金额候选术语；当前实验只记录 SUM(c27) 的历史使用事实。",
    )
    client.entities.upsert(financial)
    client.entities.upsert(order_term)

    fact_table = Dataset(
        platform="sqlite",
        name="main.device_order_profit",
        display_name="设备订货与利润事实表",
        description=(
            "实验资产：字段来自 BI 中间表头，不含业务行数据。"
            "c27、c28 的中文含义来自历史 SQL 别名，尚不能据此认定正式口径。"
        ),
        subtype="Table",
        schema=[
            ("c0", "TEXT", "历史 SQL 中的必填过滤字段；业务含义待确认。"),
            ("c2", "TEXT", "历史 SQL 中常被别名为“年月”；格式待确认。"),
            ("c7", "TEXT", "历史 SQL 中常被别名为“产品LV1”。"),
            ("c27", "NUMERIC", "历史 SQL 中常以 SUM(c27) 命名为设备订货。"),
            ("c28", "NUMERIC", "历史 SQL 中常以 SUM(c28) 命名为设备利润。"),
        ],
        owners=["urn:li:corpuser:zhangsan"],
        tags=["urn:li:tag:FinancialMetricCandidate"],
        terms=["urn:li:glossaryTerm:device_order_amount"],
        custom_properties={
            "evidence_status": "observed_not_certified",
            "source_kind": "BI_SQL_and_physical_header",
        },
    )
    client.entities.upsert(fact_table)

    chart = Chart(
        name="device_order_profit_by_product",
        platform="powerbi",
        display_name="各产品设备订货与利润",
        description="按产品一级分类和年月汇总设备订货及利润。",
        chart_type="BAR",
        input_datasets=[fact_table],
        owners=["urn:li:corpuser:zhangsan"],
    )
    client.entities.upsert(chart)

    dashboard = Dashboard(
        name="device_business_overview",
        platform="powerbi",
        display_name="设备业务经营看板",
        description="实验用 BI 看板资产，只包含元数据关系。",
        charts=[chart],
        input_datasets=[fact_table],
        owners=["urn:li:corpuser:zhangsan"],
    )
    client.entities.upsert(dashboard)

    print(f"dataset={fact_table.urn}")
    print(f"chart={chart.urn}")
    print(f"dashboard={dashboard.urn}")


if __name__ == "__main__":
    main()
