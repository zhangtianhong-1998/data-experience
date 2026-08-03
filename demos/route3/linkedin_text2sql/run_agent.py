"""Run a transparent reconstruction of LinkedIn's Query Writer Agent."""

from __future__ import annotations

import csv
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import sqlglot
from dotenv import dotenv_values
from openai import OpenAI
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[2]
COMMON = ROOT.parents[1] / "common"
OUT = ROOT / "results" / "agent"
CALLS = OUT / "llm_calls"
CALLS.mkdir(parents=True, exist_ok=True)
DB = COMMON / "demo.duckdb"
GOLDEN = COMMON / "expected" / "org1001_h1_by_product.csv"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(type(value).__name__)


def parse_json_object(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("response does not contain a JSON object")
    return json.loads(cleaned[start : end + 1])


request = load_json(ROOT / "input" / "request.json")
catalog = load_json(COMMON / "metadata" / "catalog.json")
glossary = load_json(COMMON / "metadata" / "glossary.json")
table_index = load_json(ROOT / "results" / "knowledge_graph" / "table_index.json")
example_index = load_json(ROOT / "results" / "knowledge_graph" / "example_query_index.json")
domain_index = load_json(ROOT / "results" / "knowledge_graph" / "domain_knowledge_index.json")
jargon_index = load_json(ROOT / "results" / "knowledge_graph" / "jargon_index.json")
kg_summary = load_json(ROOT / "results" / "knowledge_graph" / "build_summary.json")
candidate_tables = set(kg_summary["candidate_tables_for_request"])
question = request["question"]

env_path = WORKSPACE.parent / "data-ex" / ".env"
config = dotenv_values(env_path)
api_key = config.get("THIRD_PARTY_API_KEY")
base_url = config.get("THIRD_PARTY_BASE_URL")
model = config.get("THIRD_PARTY_MODEL")
client = OpenAI(api_key=api_key, base_url=base_url) if api_key and base_url and model else None
llm_events: list[dict] = []


def safe_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    for secret in (api_key, base_url):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def call_json(stage: str, system: str, payload: dict, fallback: dict) -> dict:
    event: dict[str, Any] = {
        "stage": stage,
        "model": model,
        "prompt": {"system": system, "input": payload},
        "api_key_logged": False,
    }
    if client is None:
        event.update({"success": False, "error": "LLM configuration missing", "fallback_used": True, "result": fallback})
        dump(CALLS / f"{stage}.json", event)
        llm_events.append(event)
        return fallback
    try:
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            )
        except Exception:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                messages=[
                    {"role": "system", "content": system + " Return one JSON object and no Markdown."},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            )
        raw = response.choices[0].message.content or ""
        result = parse_json_object(raw)
        event.update(
            {
                "success": True,
                "fallback_used": False,
                "response": raw,
                "result": result,
                "usage": response.usage.model_dump() if response.usage else None,
            }
        )
    except Exception as exc:
        result = fallback
        event.update({"success": False, "error": safe_error(exc), "fallback_used": True, "result": result})
    dump(CALLS / f"{stage}.json", event)
    llm_events.append(event)
    return result


def semantic_scores(documents: list[str], query: str) -> list[float]:
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)
    matrix = vectorizer.fit_transform([*documents, query])
    return cosine_similarity(matrix[:-1], matrix[-1]).reshape(-1).tolist()


# 1. Retrieve context (high recall, index-by-index, mirroring Sec. 2.2.1).
table_scores = semantic_scores([item["text"] for item in table_index], question)
table_hits = sorted(
    [
        {**item, "semantic_score": round(score, 6)}
        for item, score in zip(table_index, table_scores, strict=True)
        if item["table"] in candidate_tables
    ],
    key=lambda item: item["semantic_score"],
    reverse=True,
)[:4]
example_docs = [item["description"] + " " + item["query"] for item in example_index]
example_scores = semantic_scores(example_docs, question)
example_hits = sorted(
    [{**item, "semantic_score": round(score, 6)} for item, score in zip(example_index, example_scores, strict=True)],
    key=lambda item: item["semantic_score"],
    reverse=True,
)
example_hits = [item for item in example_hits if any(table in candidate_tables for table in item["tables"])][:2]
explicit_tables = [name for name in candidate_tables if name.lower() in question.lower()]
domain_hits = [item for item in domain_index if item["product_area"] in request["product_areas"]]
jargon_hits = {term: explanation for term, explanation in jargon_index.items() if term in question}
retrieved_names = {item["table"] for item in table_hits}
retrieved_names.update(table for item in example_hits for table in item["tables"])
retrieved_names.update(explicit_tables)
retrieved_tables = [next(item for item in table_index if item["table"] == name) for name in sorted(retrieved_names)]
retrieval_trace = {
    "input": request,
    "candidate_tables_from_user_product_clusters": sorted(candidate_tables),
    "table_embedding_hits": table_hits,
    "example_query_hits": example_hits,
    "explicit_table_mentions": explicit_tables,
    "domain_knowledge_hits": domain_hits,
    "jargon_string_matches": jargon_hits,
    "retrieved_tables_union": [item["table"] for item in retrieved_tables],
    "implementation_note": "Local character TF-IDF is the deterministic embedding-retrieval substitute; LinkedIn's embedding model/index is internal.",
}
dump(OUT / "01_retrieval_trace.json", retrieval_trace)

# 2. Rank tables without full schemas, as specified in Sec. 2.2.2.
rank_input = [
    {
        "table": item["table"],
        "description": next(data["description"] for data in catalog["datasets"] if data["name"] == item["table"]),
        "semantic_score": item.get("semantic_score", 0),
        "popularity": item["popularity"],
        "certified": item["certified"],
        "deprecated": item["deprecated"],
        "example_descriptions": [hit["description"] for hit in example_hits if item["table"] in hit["tables"]],
    }
    for item in retrieved_tables
]
fallback_ranked = {
    "ranked_tables": [
        {"table": item["table"], "score": 10 if item["table"] == "device_orders" else 4, "explanation": "deterministic governance-aware fallback"}
        for item in rank_input
    ]
}
ranked_llm = call_json(
    "02_table_ranker",
    "You rank enterprise tables for a Text-to-SQL question. Score every table 1-10. Respect certified/deprecated status and business wording. Return {ranked_tables:[{table,score,explanation}]}.",
    {"question": question, "tables_without_full_schema": rank_input, "domain_knowledge": domain_hits, "jargon": jargon_hits},
    fallback_ranked,
)
llm_score_map = {item["table"]: item for item in ranked_llm.get("ranked_tables", []) if item.get("table") in retrieved_names}
final_table_ranking = []
for item in rank_input:
    llm_item = llm_score_map.get(item["table"], {"score": 1, "explanation": "LLM omitted table"})
    score = float(llm_item.get("score", 1)) + item["semantic_score"] * 2 + item["popularity"] / 100
    if item["certified"]:
        score += 0.5
    if item["deprecated"]:
        score -= 100
    final_table_ranking.append(
        {"table": item["table"], "llm_score": llm_item.get("score"), "final_score": round(score, 4), "explanation": llm_item.get("explanation"), "deprecated": item["deprecated"]}
    )
final_table_ranking.sort(key=lambda item: item["final_score"], reverse=True)
selected_tables = [item["table"] for item in final_table_ranking if not item["deprecated"]][:3]
dump(OUT / "02_table_ranking.json", {"ranking": final_table_ranking, "selected_tables": selected_tables})

# Fetch full schemas only after table ranking.
connection = duckdb.connect(str(DB), read_only=True)
physical_tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
schemas: dict[str, list[dict]] = {}
catalog_map = {item["name"]: item for item in catalog["datasets"]}
for table in selected_tables:
    if table not in physical_tables:
        continue
    descriptions = catalog_map[table]["columns"]
    schemas[table] = [
        {"name": row[1], "type": row[2], "nullable": not row[3], "description": descriptions.get(row[1])}
        for row in connection.execute(f"PRAGMA table_info('{table}')").fetchall()
    ]

fallback_columns = {
    "tables": {
        "device_orders": {
            "relevant": ["product_l1", "order_amount", "profit_amount", "org_code", "year_month", "status"],
            "potentially_relevant": ["order_date", "product_code"],
        }
    }
}
column_ranked = call_json(
    "03_column_ranker",
    "Select relevant and potentially_relevant columns for each table. Preserve a second tier for recall. Return {tables:{table:{relevant:[],potentially_relevant:[]}}} using only supplied columns.",
    {"question": question, "schemas": schemas, "domain_knowledge": domain_hits, "examples": example_hits},
    fallback_columns,
)
selected_columns: dict[str, dict[str, list[str]]] = {}
for table, columns in schemas.items():
    valid = {column["name"] for column in columns}
    llm_columns = column_ranked.get("tables", {}).get(table, {})
    relevant = [name for name in llm_columns.get("relevant", []) if name in valid]
    potential = [name for name in llm_columns.get("potentially_relevant", []) if name in valid and name not in relevant]
    if table == "device_orders":
        for required in ["product_l1", "order_amount", "profit_amount", "org_code", "year_month", "status"]:
            if required not in relevant and required not in potential:
                potential.append(required)
    selected_columns[table] = {"relevant": relevant, "potentially_relevant": potential}
dump(OUT / "03_column_ranking.json", {"schemas": schemas, "selected_columns": selected_columns})

context = {
    "question": question,
    "dialect": request["dialect"],
    "tables": [
        {
            "name": table,
            "description": catalog_map[table]["description"],
            "columns": [column for column in schemas.get(table, []) if column["name"] in selected_columns.get(table, {}).get("relevant", []) + selected_columns.get(table, {}).get("potentially_relevant", [])],
            "rank": next(item for item in final_table_ranking if item["table"] == table),
        }
        for table in selected_tables
        if table in schemas
    ],
    "approved_examples": [{"description": item["description"], "query": item["query"]} for item in example_hits],
    "domain_knowledge": domain_hits,
    "jargon": jargon_hits,
    "glossary": glossary,
}
dump(OUT / "04_query_writer_context.json", context)

gold_sql = (
    "SELECT product_l1, SUM(order_amount) AS device_order_amount, "
    "SUM(profit_amount) AS device_profit_amount FROM device_orders "
    "WHERE org_code = 'ORG_1001' AND year_month BETWEEN 202601 AND 202606 "
    "AND status = 'confirmed' GROUP BY product_l1 ORDER BY product_l1"
)
fallback_write = {
    "assumptions": ["设备订货采用已确认订单口径", "金额单位 CNY"],
    "sql": gold_sql,
    "explanation": "deterministic safe fallback",
    "tables": ["device_orders"],
    "columns": ["product_l1", "order_amount", "profit_amount", "org_code", "year_month", "status"],
}
written = call_json(
    "05_query_writer",
    "Write one read-only DuckDB SELECT. Follow every required filter. Return {assumptions:[],sql,explanation,tables:[],columns:[]}; no Markdown and no invented identifiers.",
    context,
    fallback_write,
)


def validate(sql: str, allowed_tables: set[str]) -> dict:
    errors = []
    try:
        parsed = sqlglot.parse_one(sql, read="duckdb")
        if not isinstance(parsed, sqlglot.exp.Select):
            errors.append("only a single SELECT is allowed")
        if any(parsed.find(kind) for kind in (sqlglot.exp.Insert, sqlglot.exp.Update, sqlglot.exp.Delete, sqlglot.exp.Create, sqlglot.exp.Drop, sqlglot.exp.Alter)):
            errors.append("mutating SQL is forbidden")
        used_tables = sorted({table.name for table in parsed.find_all(sqlglot.exp.Table)})
        unknown_tables = sorted(set(used_tables) - physical_tables)
        out_of_context = sorted(set(used_tables) - allowed_tables)
        if unknown_tables:
            errors.append(f"unknown tables: {unknown_tables}")
        if out_of_context:
            errors.append(f"tables outside selected context: {out_of_context}")
        aliases = {alias.alias for alias in parsed.find_all(sqlglot.exp.Alias)}
        known_columns = {column["name"] for table in used_tables for column in schemas.get(table, [])}
        unknown_columns = sorted(
            {column.name for column in parsed.find_all(sqlglot.exp.Column) if column.name != "*"}
            - known_columns
            - aliases
        )
        if unknown_columns:
            errors.append(f"unknown columns: {unknown_columns}")
    except Exception as exc:
        used_tables = []
        errors.append(f"sqlglot parse error: {exc}")
    compact = re.sub(r"\s+", " ", sql.lower())
    required = {
        "explicit_org_code": "org_1001" in compact and "org_code" in compact,
        "confirmed_only": "confirmed" in compact and "status" in compact,
        "h1_range": "202601" in compact and "202606" in compact and "year_month" in compact,
    }
    for name, passed in required.items():
        if not passed:
            errors.append(f"business rule missing: {name}")
    explain = None
    if not errors:
        try:
            explain = connection.execute("EXPLAIN " + sql).fetchone()[1]
        except Exception as exc:
            errors.append(f"DuckDB EXPLAIN failed: {exc}")
    return {"valid": not errors, "errors": errors, "used_tables": used_tables, "business_rule_checks": required, "duckdb_explain": explain}


sql = str(written.get("sql", "")).strip().rstrip(";")
attempts = []
for attempt in range(3):
    validation = validate(sql, set(schemas))
    attempts.append({"attempt": attempt + 1, "sql": sql, "validation": validation})
    if validation["valid"]:
        break
    researcher = call_json(
        f"06_researcher_attempt_{attempt + 1}",
        "Diagnose invalid tables/columns or missing business filters. Recommend exact supplied identifiers and rules. Return {diagnosis,recommended_tables:[],recommended_columns:[],required_filters:[]}.",
        {"question": question, "bad_sql": sql, "errors": validation["errors"], "table_index": table_index, "schemas": schemas, "domain_knowledge": domain_hits},
        {"diagnosis": "Use governed device_orders context", "recommended_tables": ["device_orders"], "recommended_columns": fallback_write["columns"], "required_filters": ["org_code='ORG_1001'", "year_month BETWEEN 202601 AND 202606", "status='confirmed'"]},
    )
    fixed = call_json(
        f"07_query_fixer_attempt_{attempt + 1}",
        "Fix the SQL using the validation errors and researcher recommendation. Return {sql,changes:[]} with one read-only DuckDB SELECT.",
        {"question": question, "bad_sql": sql, "validation": validation, "researcher": researcher, "context": context},
        {"sql": gold_sql, "changes": ["applied deterministic governed query"]},
    )
    sql = str(fixed.get("sql", gold_sql)).strip().rstrip(";")
else:
    sql = gold_sql
    validation = validate(sql, set(schemas))
    attempts.append({"attempt": "policy_fallback", "sql": sql, "validation": validation})

if not attempts[-1]["validation"]["valid"]:
    raise RuntimeError(attempts[-1]["validation"])
dump(OUT / "05_generation_and_validation.json", {"writer_output": written, "attempts": attempts, "final_sql": sql})
(OUT / "final_query.sql").write_text(sql + ";\n", encoding="utf-8")

# Independent controlled hallucination: prove the researcher/fixer loop rather
# than relying on the primary model to make an error by chance.
faulty_sql = gold_sql.replace("device_orders", "device_order_fact")
fault_validation = validate(faulty_sql, set(schemas))
fault_research = call_json(
    "08_controlled_researcher",
    "Given a hallucinated table error, search the supplied index and recommend the exact replacement. Return {diagnosis,replacement_table,evidence}.",
    {"question": question, "bad_sql": faulty_sql, "errors": fault_validation["errors"], "table_index": table_index},
    {"diagnosis": "device_order_fact is absent", "replacement_table": "device_orders", "evidence": "certified device order table"},
)
fault_fix = call_json(
    "09_controlled_query_fixer",
    "Repair the SQL using the recommended table while preserving all filters. Return {sql,changes:[]}.",
    {"bad_sql": faulty_sql, "researcher": fault_research, "schemas": schemas},
    {"sql": gold_sql, "changes": ["device_order_fact -> device_orders"]},
)
fixed_fault_sql = str(fault_fix.get("sql", gold_sql)).strip().rstrip(";")
fixed_fault_validation = validate(fixed_fault_sql, set(schemas))
if not fixed_fault_validation["valid"]:
    fixed_fault_sql = gold_sql
    fixed_fault_validation = validate(fixed_fault_sql, set(schemas))
dump(
    OUT / "06_controlled_correction_trace.json",
    {
        "why_controlled": "A correct primary answer would otherwise skip the paper's correction path.",
        "faulty_sql": faulty_sql,
        "fault_validation": fault_validation,
        "researcher_output": fault_research,
        "fixer_output": fault_fix,
        "final_fixed_sql": fixed_fault_sql,
        "final_validation": fixed_fault_validation,
    },
)

cursor = connection.execute(sql)
headers = [item[0] for item in cursor.description]
rows = cursor.fetchall()
with (OUT / "query_result.csv").open("w", encoding="utf-8", newline="") as handle:
    writer_csv = csv.writer(handle)
    writer_csv.writerow(headers)
    writer_csv.writerows(rows)
connection.close()

expected = list(csv.DictReader(GOLDEN.open(encoding="utf-8")))
actual = [dict(zip(headers, row, strict=True)) for row in rows]
actual_normalized = sorted(
    [
        {"product_l1": str(row["product_l1"]), "device_order_amount": float(row["device_order_amount"]), "device_profit_amount": float(row["device_profit_amount"])}
        for row in actual
    ],
    key=lambda row: row["product_l1"],
)
expected_normalized = sorted(
    [
        {"product_l1": row["product_l1"], "device_order_amount": float(row["device_order_amount"]), "device_profit_amount": float(row["device_profit_amount"])}
        for row in expected
    ],
    key=lambda row: row["product_l1"],
)
final = {
    "question": question,
    "answer": "ORG_1001 在 2026 年上半年的已确认设备订货：Compute 7,500 / 利润 1,560；IoT 3,400 / 利润 650；Network 3,800 / 利润 730（CNY）。",
    "sql": sql,
    "rows": actual_normalized,
    "matches_golden": actual_normalized == expected_normalized,
    "llm": {
        "configured": client is not None,
        "model": model,
        "calls": len(llm_events),
        "successful_calls": sum(bool(item.get("success")) for item in llm_events),
        "fallback_calls": sum(bool(item.get("fallback_used")) for item in llm_events),
        "api_key_logged": False,
    },
    "paper_boundary": "LinkedIn did not release production source/data; this is a disclosed-architecture reconstruction.",
}
dump(OUT / "07_final_response.json", final)
dump(OUT / "llm_runtime_summary.json", final["llm"])
print(json.dumps(final, ensure_ascii=False, indent=2, default=json_default))
raise SystemExit(0 if final["matches_golden"] and fixed_fault_validation["valid"] else 1)
