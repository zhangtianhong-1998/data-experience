"""Build the shared synthetic DuckDB and verify the golden result."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "demo.duckdb"


def read_expected() -> list[dict[str, str]]:
    with (ROOT / "expected" / "org1001_h1_by_product.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        return list(csv.DictReader(handle))


def normalize(rows: list[tuple[object, ...]]) -> list[dict[str, str]]:
    return [
        {
            "product_l1": str(product),
            "device_order_amount": str(int(order_amount)),
            "device_profit_amount": str(int(profit_amount)),
        }
        for product, order_amount, profit_amount in rows
    ]


def main() -> None:
    if DATABASE.exists():
        DATABASE.unlink()
    connection = duckdb.connect(str(DATABASE))
    create_sql = (ROOT / "sql" / "create_demo_duckdb.sql").read_text(encoding="utf-8")
    baseline_sql = (ROOT / "sql" / "baseline.sql").read_text(encoding="utf-8")
    connection.execute(create_sql)
    rows = connection.execute(baseline_sql).fetchall()
    actual = normalize(rows)
    expected = read_expected()
    result = {
        "database": str(DATABASE),
        "source_row_counts": {
            "device_orders": connection.execute("select count(*) from device_orders").fetchone()[0],
            "product_master": connection.execute("select count(*) from product_master").fetchone()[0],
            "sales_orders": connection.execute("select count(*) from sales_orders").fetchone()[0],
        },
        "actual": actual,
        "expected": expected,
        "match": actual == expected,
    }
    connection.close()
    output = ROOT / "expected" / "baseline_verification.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["match"]:
        raise SystemExit("baseline result did not match the golden file")


if __name__ == "__main__":
    main()
