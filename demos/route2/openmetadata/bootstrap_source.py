"""Wait for OpenMetadata, then build the synthetic MySQL source from scratch."""

import json
import subprocess
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
health_url = "http://127.0.0.1:8586/healthcheck"
last_error = None
for _ in range(120):
    try:
        with urllib.request.urlopen(health_url, timeout=2) as response:
            if response.status == 200:
                break
    except Exception as exc:  # startup polling deliberately records only the final error
        last_error = str(exc)
        time.sleep(2)
else:
    raise RuntimeError(f"OpenMetadata did not become healthy: {last_error}")

csv_path = ROOT.parents[1] / "common" / "data" / "device_orders.csv"
sql_path = ROOT / "input" / "create_demo.sql"
subprocess.run(
    ["docker", "cp", str(csv_path), "openmetadata_mysql:/tmp/device_orders.csv"],
    check=True,
)
sql = sql_path.read_bytes()
loaded = subprocess.run(
    [
        "docker", "exec", "-i", "openmetadata_mysql", "mysql",
        "--local-infile=1", "--default-character-set=utf8mb4", "-uroot", "-ppassword",
    ],
    input=sql,
    check=True,
    capture_output=True,
)
query = (
    "SELECT 'device_orders' AS asset, COUNT(*) AS rows_count FROM enterprise_demo.device_orders "
    "UNION ALL SELECT 'device_orders_by_product', COUNT(*) FROM enterprise_demo.device_orders_by_product "
    "UNION ALL SELECT 'sales_orders', COUNT(*) FROM enterprise_demo.sales_orders;"
)
checked = subprocess.run(
    ["docker", "exec", "openmetadata_mysql", "mysql", "-N", "-uroot", "-ppassword", "-e", query],
    check=True,
    capture_output=True,
    text=True,
)
counts = {}
for line in checked.stdout.strip().splitlines():
    name, count = line.split("\t")
    counts[name] = int(count)

report = {
    "openmetadata_health": "healthy",
    "source_container": "openmetadata_mysql",
    "source_database": "enterprise_demo",
    "row_counts": counts,
    "expected": {"device_orders": 16, "device_orders_by_product": 3, "sales_orders": 3},
    "passed": counts == {"device_orders": 16, "device_orders_by_product": 3, "sales_orders": 3},
}
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results" / "source_build.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["passed"] else 1)
