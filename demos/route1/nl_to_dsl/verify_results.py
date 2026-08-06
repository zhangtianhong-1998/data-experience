"""Verify the retained NL-to-DSL research evidence without calling an LLM."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    attempt1 = load(
        RESULTS
        / "attempts"
        / "01_before_cube_ambiguity_context"
        / "llm_summary.json"
    )
    attempt2 = load(
        RESULTS
        / "attempts"
        / "02_after_cube_context_before_planner_rule"
        / "llm_summary.json"
    )
    final = load(RESULTS / "llm_summary.json")
    execution = load(RESULTS / "execution_summary.json")

    final_calls = sorted((RESULTS / "calls").glob("*/*.json"))
    final_generated = sorted((RESULTS / "generated").glob("*/*.json"))
    final_execution = sorted(
        path
        for path in (RESULTS / "execution").glob("*/*.json")
        if not path.name.endswith("_cli_query.json")
    )
    call_checks = []
    for path in final_calls:
        call = load(path)
        request = call["llm"]["successful_request"]
        call_checks.append(
            {
                "path": str(path.relative_to(ROOT)),
                "validation_passed": call["validation"]["passed"],
                "api_key_logged": request["api_key_included_in_record"],
                "base_url_logged": request["base_url_included_in_record"],
            }
        )

    checks = {
        "attempt_01_is_retained_failure": attempt1["passed"] == 9
        and attempt1["failed"] == 1,
        "attempt_02_is_retained_failure": attempt2["passed"] == 8
        and attempt2["failed"] == 2,
        "final_llm_is_10_of_10": final["all_passed"]
        and final["passed"] == 10
        and final["failed"] == 0,
        "no_fallback_results": final["fallback_results"] == 0,
        "ten_final_call_records": len(final_calls) == 10,
        "all_final_call_validations_pass": all(
            item["validation_passed"] for item in call_checks
        ),
        "no_secret_locations_logged": all(
            not item["api_key_logged"] and not item["base_url_logged"]
            for item in call_checks
        ),
        "only_four_ready_queries_generated": len(final_generated) == 4,
        "four_engine_records": len(final_execution) == 4,
        "four_engine_results_match": execution["all_match"]
        and execution["matched"] == 4,
    }
    verification = {
        "checks": checks,
        "all_passed": all(checks.values()),
        "attempts": {
            "01": {"passed": attempt1["passed"], "failed": attempt1["failed"]},
            "02": {"passed": attempt2["passed"], "failed": attempt2["failed"]},
            "final": {"passed": final["passed"], "failed": final["failed"]},
        },
        "execution": execution,
        "final_calls": call_checks,
    }
    path = RESULTS / "verification.json"
    path.write_text(
        json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    if not verification["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
