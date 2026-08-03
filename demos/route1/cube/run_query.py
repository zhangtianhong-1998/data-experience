"""Wait for Cube, call SQL and Load APIs, and verify the returned data."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import time
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
API = "http://127.0.0.1:4000/cubejs-api/v1"


def get_json(url: str) -> dict:
    with urlopen(url, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_until_ready() -> None:
    last_error = None
    for _ in range(60):
        try:
            get_json(f"{API}/meta")
            return
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(1)
    raise RuntimeError(f"Cube did not become ready: {last_error}")


def expected_rows() -> list[dict[str, str]]:
    path = ROOT.parents[1] / "common" / "expected" / "org1001_h1_by_product.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    wait_until_ready()
    query = json.loads((ROOT / "query.json").read_text(encoding="utf-8"))
    encoded = quote(json.dumps(query, separators=(",", ":")))
    sql_response = get_json(f"{API}/sql?query={encoded}")
    load_response = get_json(f"{API}/load?query={encoded}")
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "sql_response.json").write_text(
        json.dumps(sql_response, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ROOT / "results" / "load_response.json").write_text(
        json.dumps(load_response, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    actual = [
        {
            "product_l1": row["DeviceOrders.productL1"],
            "device_order_amount": str(int(float(row["DeviceOrders.deviceOrderAmount"]))),
            "device_profit_amount": str(int(float(row["DeviceOrders.deviceProfitAmount"]))),
        }
        for row in load_response["data"]
    ]
    expected = expected_rows()
    verification = {
        "actual": actual,
        "expected": expected,
        "match": actual == expected,
        "generated_sql": sql_response.get("sql", sql_response),
    }
    (ROOT / "results" / "verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    if not verification["match"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
