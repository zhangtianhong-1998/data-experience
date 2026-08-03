"""Build the indexes and user-dataset clusters disclosed in LinkedIn's paper."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import sqlglot
from sklearn.decomposition import FastICA
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parent
COMMON = ROOT.parents[1] / "common"
RESULTS = ROOT / "results" / "knowledge_graph"
RESULTS.mkdir(parents=True, exist_ok=True)


def dump(name: str, value) -> None:
    (RESULTS / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


catalog = json.loads((COMMON / "metadata" / "catalog.json").read_text(encoding="utf-8"))
glossary = json.loads((COMMON / "metadata" / "glossary.json").read_text(encoding="utf-8"))
product_areas = json.loads((ROOT / "input" / "product_areas.json").read_text(encoding="utf-8"))
jargon = json.loads((ROOT / "input" / "jargon.json").read_text(encoding="utf-8"))
example_descriptions = json.loads(
    (ROOT / "input" / "example_descriptions.json").read_text(encoding="utf-8")
)
domain_records = [
    json.loads(line)
    for line in (ROOT / "input" / "domain_knowledge.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
examples = [
    json.loads(line)
    for line in (COMMON / "metadata" / "query_history.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
access_rows = list(csv.DictReader((ROOT / "input" / "user_table_access.csv").open(encoding="utf-8")))

datasets = {item["name"]: item for item in catalog["datasets"]}
users = sorted({row["user"] for row in access_rows})
tables = sorted(datasets)
access = {(row["user"], row["table"]): int(row["access_count"]) for row in access_rows}
matrix = np.array([[access.get((user, table), 0) for user in users] for table in tables], dtype=float)

# The paper standardizes across users, then applies FastICA. Its production
# constants (200 components, 20 tables/cluster) are reduced to fit four demo tables.
scaled = StandardScaler().fit_transform(matrix.T).T
n_components = min(3, len(tables), len(users))
ica = FastICA(n_components=n_components, random_state=42, max_iter=2000, whiten="unit-variance")
component_scores = ica.fit_transform(scaled)
top_tables_per_cluster = min(3, len(tables))
cluster_tables: dict[str, list[str]] = {}
extended_clusters: dict[str, list[str]] = {}
for component in range(n_components):
    cluster = f"cluster_{component}"
    ranked = sorted(
        zip(tables, component_scores[:, component], strict=True),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    cluster_tables[cluster] = [table for table, _ in ranked[:top_tables_per_cluster]]
    extended_clusters[cluster] = list(cluster_tables[cluster])
for table_idx, table in enumerate(tables):
    closest = int(np.argmax(np.abs(component_scores[table_idx, :])))
    cluster = f"cluster_{closest}"
    if table not in extended_clusters[cluster]:
        extended_clusters[cluster].append(table)

user_clusters: dict[str, list[dict]] = {}
for user in users:
    scored = []
    for cluster, cluster_dataset_names in cluster_tables.items():
        score = sum(access.get((user, table), 0) for table in cluster_dataset_names)
        if score:
            scored.append({"cluster": cluster, "access_count": score})
    user_clusters[user] = sorted(scored, key=lambda item: item["access_count"], reverse=True)[:10]

product_area_clusters: dict[str, list[dict]] = {}
for area, config in product_areas.items():
    aggregate: dict[str, dict[str, int]] = defaultdict(lambda: {"unique_users": 0, "access_count": 0})
    for user in config["representative_users"]:
        for record in user_clusters.get(user, []):
            aggregate[record["cluster"]]["unique_users"] += 1
            aggregate[record["cluster"]]["access_count"] += record["access_count"]
    ranked = [
        {"cluster": cluster, **scores}
        for cluster, scores in aggregate.items()
    ]
    product_area_clusters[area] = sorted(
        ranked,
        key=lambda item: (item["unique_users"], item["access_count"]),
        reverse=True,
    )[:3]


def candidate_tables(user: str, areas: list[str]) -> list[str]:
    clusters = {item["cluster"] for item in user_clusters.get(user, [])[:3]}
    explicit: set[str] = set()
    for area in areas:
        clusters.update(item["cluster"] for item in product_area_clusters.get(area, [])[:3])
        explicit.update(product_areas[area]["explicit_tables"])
    inferred = {table for cluster in clusters for table in extended_clusters[cluster]}
    return sorted(inferred | explicit)


nodes = []
edges = []
for table, item in datasets.items():
    nodes.append({"id": f"table:{table}", "type": "table", **item})
    for column, description in item["columns"].items():
        nodes.append(
            {"id": f"column:{table}.{column}", "type": "column", "table": table, "name": column, "description": description}
        )
        edges.append({"from": f"table:{table}", "to": f"column:{table}.{column}", "type": "contains"})
for join in catalog["joins"]:
    edges.append({"from": f"column:{join['left']}", "to": f"column:{join['right']}", "type": "joins", "usage_count": join["usage_count"]})
for idx, item in enumerate(examples):
    parsed = sqlglot.parse_one(item["query"], read="duckdb")
    used_tables = sorted({table.name for table in parsed.find_all(sqlglot.exp.Table)})
    node_id = f"example:{idx}"
    nodes.append(
        {
            "id": node_id,
            "type": "example_query",
            **item,
            "description": example_descriptions[item["user"]],
            "tables": used_tables,
        }
    )
    edges.append({"from": f"user:{item['user']}", "to": node_id, "type": "authored"})
    for table in used_tables:
        edges.append({"from": node_id, "to": f"table:{table}", "type": "uses"})
for user in users:
    nodes.append({"id": f"user:{user}", "type": "user", "clusters": user_clusters[user]})
for area, config in product_areas.items():
    nodes.append({"id": f"product_area:{area}", "type": "product_area", "clusters": product_area_clusters[area]})
    for table in config["explicit_tables"]:
        edges.append({"from": f"product_area:{area}", "to": f"table:{table}", "type": "explicit_table"})
for record in domain_records:
    nodes.append({"type": "domain_knowledge", **record})
    for table in record["tables"]:
        edges.append({"from": f"domain:{record['id']}", "to": f"table:{table}", "type": "associated_with"})
for term, definition in glossary.items():
    nodes.append({"id": f"glossary:{term}", "type": "glossary", "name": term, **definition})
for term, explanation in jargon.items():
    nodes.append({"id": f"jargon:{term}", "type": "jargon", "name": term, "explanation": explanation})

table_index = []
for table, item in datasets.items():
    extended = " ".join([table, item["description"], item["domain"], *item["columns"].keys(), *item["columns"].values()])
    table_index.append({"table": table, "text": extended, "certified": item["certified"], "deprecated": item["deprecated"], "popularity": item["popularity"]})
example_index = [node for node in nodes if node.get("type") == "example_query" and node["quality"] == "approved"]

dump("nodes.json", nodes)
dump("edges.json", edges)
dump("table_index.json", table_index)
dump("example_query_index.json", example_index)
dump("domain_knowledge_index.json", domain_records)
dump("jargon_index.json", jargon)
dump(
    "clustering.json",
    {
        "paper_algorithm": "FastICA soft clustering over user-dataset access counts",
        "production_constants_from_paper": {"n_components": 200, "tables_per_cluster": 20},
        "demo_constants": {"n_components": n_components, "tables_per_cluster": top_tables_per_cluster},
        "users": users,
        "tables": tables,
        "raw_access_matrix_table_by_user": matrix.tolist(),
        "scaled_matrix_table_by_user": scaled.round(6).tolist(),
        "component_scores_table_by_component": component_scores.round(6).tolist(),
        "clusters": cluster_tables,
        "extended_clusters": extended_clusters,
        "user_clusters": user_clusters,
        "product_area_clusters": product_area_clusters,
    },
)
request = json.loads((ROOT / "input" / "request.json").read_text(encoding="utf-8"))
candidates = candidate_tables(request["user"], request["product_areas"])
summary = {
    "node_count": len(nodes),
    "edge_count": len(edges),
    "table_index_count": len(table_index),
    "approved_example_count": len(example_index),
    "candidate_tables_for_request": candidates,
    "candidate_contains_authoritative_table": "device_orders" in candidates,
    "paper_fidelity": {
        "implemented": [
            "user-dataset access matrix",
            "FastICA soft clustering",
            "extended clusters",
            "user and product-area cluster association",
            "table/column, usage, example-query, domain-knowledge and jargon indexes",
        ],
        "scaled_down": "200 ICA components/20 tables per cluster are reduced to 3/3 for four synthetic tables",
    },
}
dump("build_summary.json", summary)
print(json.dumps(summary, ensure_ascii=False, indent=2))
