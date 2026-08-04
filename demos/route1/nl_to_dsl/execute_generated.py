"""Execute validated LLM-generated Cube and Wren query objects."""

from __future__ import annotations

import csv
import json
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[2]
RESULTS = ROOT / "results"
COMMON = ROOT.parents[1] / "common"
CUBE_API = "http://127.0.0.1:4000/cubejs-api/v1"
WREN_PROJECT = ROOT.parent / "wrenai" / "device_project"
WREN = WORKSPACE / "runtime" / "wren-venv" / "bin" / "wren"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def get_json(url: str) -> dict:
    with urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_cube() -> None:
    last_error = None
    for _ in range(60):
        try:
            get_json(f"{CUBE_API}/meta")
            return
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Cube did not become ready: {last_error}")


def golden_rows() -> list[dict[str, str]]:
    with (COMMON / "expected" / "org1001_h1_by_product.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        return sorted(list(csv.DictReader(handle)), key=lambda row: row["product_l1"])


def normalized_rows(rows: list[dict], framework: str) -> list[dict[str, str]]:
    if framework == "cube":
        result = [
            {
                "product_l1": str(row["DeviceOrders.productL1"]),
                "device_order_amount": str(int(float(row["DeviceOrders.deviceOrderAmount"]))),
                "device_profit_amount": str(int(float(row["DeviceOrders.deviceProfitAmount"]))),
            }
            for row in rows
        ]
    else:
        result = [
            {
                "product_l1": str(row["product_l1"]),
                "device_order_amount": str(int(float(row["device_order_amount"]))),
                "device_profit_amount": str(int(float(row["device_profit_amount"]))),
            }
            for row in rows
        ]
    return sorted(result, key=lambda row: row["product_l1"])


def execute_cube(path: Path, expected: list[dict[str, str]]) -> dict:
    query = load_json(path)
    encoded = quote(json.dumps(query, ensure_ascii=False, separators=(",", ":")))
    sql = get_json(f"{CUBE_API}/sql?query={encoded}")
    load = get_json(f"{CUBE_API}/load?query={encoded}")
    actual = normalized_rows(load["data"], "cube")
    return {
        "generated_query_path": str(path.relative_to(WORKSPACE)),
        "query": query,
        "engine_sql_response": sql,
        "engine_load_response": load,
        "actual": actual,
        "expected": expected,
        "match": actual == expected,
    }


def wren_cli_query(query: dict) -> dict:
    filters = []
    for value in query.get("filters", []):
        dimension, operator, raw_value = value.split(":", 2)
        typed_value: str | int = int(raw_value) if raw_value.isdigit() else raw_value
        filters.append(
            {"dimension": dimension, "operator": operator, "value": typed_value}
        )
    return {
        "cube": query["cube"],
        "measures": query["measures"],
        "dimensions": query.get("dimensions", []),
        "filters": filters,
    }


def run_wren(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(WREN), *args],
        cwd=WREN_PROJECT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def execute_wren(path: Path, expected: list[dict[str, str]]) -> dict:
    tool_query = load_json(path)
    cli_query = wren_cli_query(tool_query)
    out_dir = RESULTS / "execution" / "wren"
    cli_path = out_dir / f"{path.stem}_cli_query.json"
    dump_json(cli_path, cli_query)
    common_args = [
        "cube",
        "query",
        "--from",
        str(cli_path),
        "--connection-file",
        "connection.json",
    ]
    sql_run = run_wren([*common_args, "--sql-only"])
    data_run = run_wren([*common_args, "--output", "json"])
    if sql_run.returncode != 0 or data_run.returncode != 0:
        raise RuntimeError(
            f"Wren execution failed: sql={sql_run.stderr!r}, data={data_run.stderr!r}"
        )
    rows = [json.loads(line) for line in data_run.stdout.splitlines() if line.strip()]
    actual = normalized_rows(rows, "wren")
    return {
        "generated_tool_query_path": str(path.relative_to(WORKSPACE)),
        "tool_query": tool_query,
        "deterministic_mcp_to_cli_transformation": cli_query,
        "generated_sql": sql_run.stdout.strip(),
        "engine_stderr": data_run.stderr,
        "actual": actual,
        "expected": expected,
        "match": actual == expected,
    }


def main() -> None:
    wait_for_cube()
    expected = golden_rows()
    records = []
    for framework in ("cube", "wren"):
        for path in sorted((RESULTS / "generated" / framework).glob("*.json")):
            result = (
                execute_cube(path, expected)
                if framework == "cube"
                else execute_wren(path, expected)
            )
            result["framework"] = framework
            result["case_id"] = path.stem
            dump_json(
                RESULTS / "execution" / framework / f"{path.stem}.json", result
            )
            records.append(result)
    summary = {
        "executed_queries": len(records),
        "matched": sum(item["match"] for item in records),
        "all_match": bool(records) and all(item["match"] for item in records),
        "results": [
            {
                "framework": item["framework"],
                "case_id": item["case_id"],
                "match": item["match"],
            }
            for item in records
        ],
    }
    dump_json(RESULTS / "execution_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["all_match"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
