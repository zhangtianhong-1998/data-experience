"""Build a clean SQLite source from the shared synthetic CSV files."""

import csv
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parent
COMMON = ROOT.parents[1] / "common" / "data"
DATABASE = ROOT / "input" / "datahub_demo.db"


def load_csv(connection: sqlite3.Connection, name: str, columns: list[str]) -> int:
    with (COMMON / f"{name}.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    placeholders = ",".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO {name} ({','.join(columns)}) VALUES ({placeholders})",
        [[row[column] for column in columns] for row in rows],
    )
    return len(rows)


def main() -> None:
    DATABASE.parent.mkdir(exist_ok=True)
    if DATABASE.exists():
        DATABASE.unlink()
    connection = sqlite3.connect(DATABASE)
    connection.executescript(
        """
        CREATE TABLE device_orders (
          order_id TEXT PRIMARY KEY,
          order_date TEXT NOT NULL,
          year_month INTEGER NOT NULL,
          org_code TEXT NOT NULL,
          product_code TEXT NOT NULL,
          product_l1 TEXT NOT NULL,
          order_amount NUMERIC,
          profit_amount NUMERIC,
          country TEXT,
          status TEXT NOT NULL
        );
        CREATE TABLE product_master (
          product_code TEXT PRIMARY KEY,
          product_l1 TEXT NOT NULL,
          product_name TEXT
        );
        CREATE TABLE sales_orders (
          sales_order_id TEXT PRIMARY KEY,
          order_date TEXT NOT NULL,
          org_code TEXT NOT NULL,
          product_l1 TEXT NOT NULL,
          sales_amount NUMERIC
        );
        CREATE VIEW device_orders_by_product AS
        SELECT product_l1,
               SUM(CASE WHEN status = 'confirmed' THEN order_amount ELSE 0 END) AS device_order_amount,
               SUM(CASE WHEN status = 'confirmed' THEN profit_amount ELSE 0 END) AS device_profit_amount
        FROM device_orders
        GROUP BY product_l1;
        """
    )
    counts = {
        "device_orders": load_csv(
            connection,
            "device_orders",
            [
                "order_id", "order_date", "year_month", "org_code", "product_code",
                "product_l1", "order_amount", "profit_amount", "country", "status",
            ],
        ),
        "product_master": load_csv(
            connection, "product_master", ["product_code", "product_l1", "product_name"]
        ),
        "sales_orders": load_csv(
            connection,
            "sales_orders",
            ["sales_order_id", "order_date", "org_code", "product_l1", "sales_amount"],
        ),
    }
    connection.commit()
    connection.close()
    result = {"database": str(DATABASE), "row_counts": counts, "view_count": 1}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "source_build.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

