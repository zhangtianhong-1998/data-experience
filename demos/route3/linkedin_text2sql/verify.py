"""Verify the disclosed-architecture reconstruction end to end."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
kg = json.loads((ROOT / "results" / "knowledge_graph" / "build_summary.json").read_text(encoding="utf-8"))
retrieval = json.loads((ROOT / "results" / "agent" / "01_retrieval_trace.json").read_text(encoding="utf-8"))
ranking = json.loads((ROOT / "results" / "agent" / "02_table_ranking.json").read_text(encoding="utf-8"))
columns = json.loads((ROOT / "results" / "agent" / "03_column_ranking.json").read_text(encoding="utf-8"))
generation = json.loads((ROOT / "results" / "agent" / "05_generation_and_validation.json").read_text(encoding="utf-8"))
correction = json.loads((ROOT / "results" / "agent" / "06_controlled_correction_trace.json").read_text(encoding="utf-8"))
final = json.loads((ROOT / "results" / "agent" / "07_final_response.json").read_text(encoding="utf-8"))

top_table_hits = [item["table"] for item in retrieval["table_embedding_hits"]]
selected_device_columns = columns["selected_columns"]["device_orders"]
all_device_columns = set(selected_device_columns["relevant"] + selected_device_columns["potentially_relevant"])
required_columns = {"product_l1", "order_amount", "profit_amount", "org_code", "year_month", "status"}
checks = {
    "knowledge_graph_built": kg["node_count"] == 37 and kg["edge_count"] == 25,
    "cluster_candidate_contains_authoritative_table": kg["candidate_contains_authoritative_table"],
    "multi_index_retrieval_ranks_device_orders_first": top_table_hits[0] == "device_orders",
    "examples_retrieve_two_device_queries": [item["user"] for item in retrieval["example_query_hits"]] == ["analyst_a", "analyst_b"],
    "llm_ranker_demotes_deprecated_table": ranking["ranking"][-1]["table"] == "deprecated_device_orders",
    "two_tier_column_recall_covers_required_columns": required_columns <= all_device_columns,
    "primary_query_valid_on_first_attempt": generation["attempts"][0]["validation"]["valid"],
    "controlled_hallucination_detected": not correction["fault_validation"]["valid"],
    "researcher_and_fixer_recover": correction["final_validation"]["valid"],
    "five_real_llm_calls_without_fallback": final["llm"]["successful_calls"] == 5 and final["llm"]["fallback_calls"] == 0,
    "execution_matches_golden": final["matches_golden"],
}
report = {
    "passed": all(checks.values()),
    "checks": checks,
    "evidence": {
        "candidate_tables": kg["candidate_tables_for_request"],
        "ranked_first": ranking["ranking"][0]["table"],
        "final_sql": final["sql"],
        "rows": final["rows"],
        "llm": final["llm"],
    },
}
(ROOT / "results" / "verification.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["passed"] else 1)
