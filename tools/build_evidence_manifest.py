"""Build a compact, reviewable index over the clean-run evidence."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs" / "20260804-clean-verification"
OUT = ROOT / "reports" / "evidence_manifest.json"

KNOWN_DIAGNOSTIC_FAILURES = {
    "00-common-rebuild": "Wrong working directory exposed a relative CSV path assumption; retry used demos/common.",
    "11-metricflow-build": "MF_DUCKDB_PATH was intentionally absent from the clean shell; retry supplied the explicit path.",
    "22-cube-query": "Cube accepted the TCP connection before its API was ready; the readiness loop was hardened and retried.",
    "43-datahub-schema-ingest": "The executable was relative to the child cwd; retry used an absolute executable path.",
    "47-datahub-verify": "Immediate MCP read observed DataHub/OpenSearch eventual consistency: query index had not refreshed.",
    "47b-datahub-verify-after-index-refresh": "Data was present, but the original assertion assumed a fixed search rank and two lineage nodes; corrected to the API's clean-state semantics.",
    "72-linkedin-agent-real-llm": "SQL and values were correct, but the verifier treated row order as semantic; corrected to key-sorted comparison.",
    "90-build-evidence-manifest": "The manifest builder observed its own in-progress step directory before result.json existed; incomplete steps are now skipped.",
}

TERMINAL_CHECKS = {
    "common": "demos/common/expected/baseline_verification.json",
    "metricflow": "demos/route1/metricflow/device_project/results/verification.json",
    "cube": "demos/route1/cube/results/verification.json",
    "wrenai": "demos/route1/wrenai/device_project/results/verification.json",
    "datahub": "demos/route2/datahub/results/verification.json",
    "openmetadata": "demos/route2/openmetadata/results/verification.json",
    "linkedin_text2sql": "demos/route3/linkedin_text2sql/results/verification.json",
}


def read_json(relative: str | Path):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


steps = []
for step_dir in sorted((RUN / "steps").iterdir()):
    if not step_dir.is_dir():
        continue
    # The manifest can itself be executed through run_logged.  That step's
    # result.json is only written after this process exits, so omit incomplete
    # step directories and include it on the next build.
    if not (step_dir / "result.json").exists():
        continue
    result = read_json(step_dir.relative_to(ROOT) / "result.json")
    request = read_json(step_dir.relative_to(ROOT) / "request.json")
    step = {
        "step": step_dir.name,
        "exit_code": result["exit_code"],
        "duration_seconds": result["duration_seconds"],
        "request": str((step_dir / "request.json").relative_to(ROOT)),
        "stdout": str((step_dir / "stdout.txt").relative_to(ROOT)),
        "stderr": str((step_dir / "stderr.txt").relative_to(ROOT)),
        "result": str((step_dir / "result.json").relative_to(ROOT)),
        "command_recorded": bool(request.get("argv")),
        "secret_values_recorded": request.get("secret_values_recorded"),
    }
    if step_dir.name in KNOWN_DIAGNOSTIC_FAILURES:
        step["classification"] = "diagnostic_failure_retained"
        step["interpretation"] = KNOWN_DIAGNOSTIC_FAILURES[step_dir.name]
    else:
        step["classification"] = "passed" if result["exit_code"] == 0 else "unexpected_failure"
    steps.append(step)

terminal = {}
for name, path in TERMINAL_CHECKS.items():
    payload = read_json(path)
    terminal[name] = {
        "path": path,
        "passed": bool(payload.get("passed", payload.get("match"))),
    }

manifest = {
    "run_id": RUN.name,
    "purpose": "Clean, secret-safe verification of six executable demos across three public semantic-data routes.",
    "secret_policy": {
        "env_source": "Sibling data-ex/.env was read only by the LinkedIn reconstruction at runtime.",
        "values_committed": False,
        "logged_request_environment_contains_secret_values": False,
    },
    "terminal_checks": terminal,
    "all_terminal_checks_passed": all(item["passed"] for item in terminal.values()),
    "steps": steps,
    "diagnostic_failure_count": sum(item["classification"] == "diagnostic_failure_retained" for item in steps),
    "unexpected_failure_count": sum(item["classification"] == "unexpected_failure" for item in steps),
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({
    "output": str(OUT.relative_to(ROOT)),
    "step_count": len(steps),
    "terminal_checks": terminal,
    "all_terminal_checks_passed": manifest["all_terminal_checks_passed"],
    "diagnostic_failure_count": manifest["diagnostic_failure_count"],
    "unexpected_failure_count": manifest["unexpected_failure_count"],
}, ensure_ascii=False, indent=2))
