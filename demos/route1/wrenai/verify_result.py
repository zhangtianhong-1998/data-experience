"""Parse Wren JSON output and compare it with the shared golden result."""

from __future__ import annotations

import csv
import json
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent / "device_project" / "results" / "verification.json"


def expected_rows() -> list[dict[str, str]]:
    path = ROOT / "common" / "expected" / "org1001_h1_by_product.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    raw = args.input.read_text(encoding="utf-8").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if isinstance(payload, dict) and "data" in payload:
        payload = payload["data"]
    actual = [
        {
            "product_l1": str(row["product_l1"]),
            "device_order_amount": str(int(float(row["device_order_amount"]))),
            "device_profit_amount": str(int(float(row["device_profit_amount"]))),
        }
        for row in payload
    ]
    actual.sort(key=lambda row: row["product_l1"])
    expected = expected_rows()
    result = {"actual": actual, "expected": expected, "match": actual == expected}
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["match"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
