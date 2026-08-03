"""Compare MetricFlow output with the shared golden result."""

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ACTUAL = Path(__file__).resolve().parent / "device_project" / "results" / "org1001_h1_by_product.csv"
EXPECTED = ROOT / "common" / "expected" / "org1001_h1_by_product.csv"
OUTPUT = Path(__file__).resolve().parent / "device_project" / "results" / "verification.json"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    actual = rows(ACTUAL)
    for row in actual:
        row["product_l1"] = row.pop("device_order__product_l1")
    expected = rows(EXPECTED)
    result = {"actual": actual, "expected": expected, "match": actual == expected}
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["match"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
