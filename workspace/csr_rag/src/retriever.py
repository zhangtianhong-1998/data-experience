"""A transparent implementation of CSR-RAG's three-stage retrieval pipeline.

The paper leaves its exact embedding checkpoint and Relational-RAG operator weights private.
This implementation makes those choices explicit instead of pretending they were specified.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple
import time

import numpy as np


@dataclass(frozen=True)
class RetrievalConfig:
    contextual_k: int = 2
    structural_l: int = 12
    relational_h: int = 14


class TextEncoder:
    """Minimal interface shared by a neural encoder and a TF-IDF fallback."""

    name: str

    def fit(self, documents: Sequence[str]) -> None:
        raise NotImplementedError

    def encode(self, documents: Sequence[str]) -> np.ndarray:
        raise NotImplementedError


class SentenceTransformerEncoder(TextEncoder):
    def __init__(self, model_name: str, cache_dir: Path, revision: str | None = None):
        from sentence_transformers import SentenceTransformer

        self.name = model_name
        self.revision = revision
        self._model = SentenceTransformer(
            model_name,
            cache_folder=str(cache_dir),
            revision=revision,
        )

    def fit(self, documents: Sequence[str]) -> None:
        return None

    def encode(self, documents: Sequence[str]) -> np.ndarray:
        values = self._model.encode(
            list(documents),
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return np.asarray(values, dtype=np.float32)


class TfidfEncoder(TextEncoder):
    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.name = "tfidf-word-bigram-fallback"
        self._vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)

    def fit(self, documents: Sequence[str]) -> None:
        self._vectorizer.fit(documents)

    def encode(self, documents: Sequence[str]) -> np.ndarray:
        return self._vectorizer.transform(documents).toarray().astype(np.float32)


def cosine_scores(query_vector: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    # Use float64 for the tiny demo as a guard against platform-specific float32 BLAS
    # warnings observed on Apple Silicon.  This does not change the ranking semantics.
    safe_query = np.asarray(query_vector, dtype=np.float64)
    safe_matrix = np.asarray(matrix, dtype=np.float64)
    query_norm = np.linalg.norm(safe_query)
    row_norms = np.linalg.norm(safe_matrix, axis=1)
    denominator = np.maximum(row_norms * query_norm, 1e-12)
    # `einsum` avoids spurious Apple Accelerate `matmul` overflow warnings seen with
    # small, finite normalized vectors on this machine.
    numerator = np.einsum("ij,j->i", safe_matrix, safe_query, optimize=True)
    return numerator / denominator


class CSRRAGRetriever:
    def __init__(
        self,
        schema: Mapping[str, Any],
        history: Sequence[Mapping[str, Any]],
        encoder: TextEncoder,
    ):
        start = time.perf_counter()
        self.schema = schema
        self.history = list(history)
        self.encoder = encoder
        self.table_by_name = {table["name"]: table for table in schema["tables"]}

        self.history_records = self._build_history_records()
        self.triplets = self._build_schema_triplets()
        self.column_records = self._build_column_records()
        all_documents = (
            [record["text"] for record in self.history_records]
            + [record["text"] for record in self.triplets]
            + [record["text"] for record in self.column_records]
        )
        self.encoder.fit(all_documents)
        self.history_vectors = self.encoder.encode([record["text"] for record in self.history_records])
        self.triplet_vectors = self.encoder.encode([record["text"] for record in self.triplets])
        self.column_vectors = self.encoder.encode([record["text"] for record in self.column_records])
        self.index_build_ms = (time.perf_counter() - start) * 1000

    def _table_description(self, table_name: str) -> str:
        table = self.table_by_name[table_name]
        columns = ", ".join(
            f"{column['name']} {column['description']}" for column in table["columns"]
        )
        return f"{table_name}: {table['description']}; columns: {columns}"

    def _build_history_records(self) -> List[Dict[str, Any]]:
        records = []
        for item in self.history:
            schema_context = " | ".join(self._table_description(name) for name in item["tables"])
            records.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "tables": list(item["tables"]),
                    "text": f"question: {item['question']} | known relevant schema: {schema_context}",
                }
            )
        return records

    def _build_schema_triplets(self) -> List[Dict[str, Any]]:
        records = []
        for table in self.schema["tables"]:
            for column in table["columns"]:
                records.append(
                    {
                        "field": column["name"],
                        "relation": "column_of",
                        "table": table["name"],
                        "description": column["description"],
                        "text": (
                            f"field {column['name']} is a column of table {table['name']}; "
                            f"table purpose: {table['description']}; field meaning: {column['description']}"
                        ),
                    }
                )
        return records

    def _build_column_records(self) -> List[Dict[str, Any]]:
        records = []
        for table in self.schema["tables"]:
            for column in table["columns"]:
                records.append(
                    {
                        "qualified_name": f"{table['name']}.{column['name']}",
                        "table": table["name"],
                        "column": column["name"],
                        "text": (
                            f"table {table['name']} {table['description']}; "
                            f"column {column['name']} {column['description']}"
                        ),
                    }
                )
        return records

    def contextual_rag(self, question: str, k: int) -> Dict[str, Any]:
        query_vector = self.encoder.encode([question])[0]
        scores = cosine_scores(query_vector, self.history_vectors)
        top_indices = np.argsort(-scores)[:k]
        matches = []
        tables: List[str] = []
        for index in top_indices:
            record = self.history_records[int(index)]
            matches.append(
                {
                    "history_id": record["id"],
                    "question": record["question"],
                    "score": round(float(scores[index]), 6),
                    "tables": record["tables"],
                }
            )
            tables.extend(record["tables"])
        return {"k": k, "matches": matches, "tables": sorted(set(tables))}

    def structural_rag(self, question: str, l: int) -> Dict[str, Any]:
        query_vector = self.encoder.encode([question])[0]
        scores = cosine_scores(query_vector, self.triplet_vectors)
        top_indices = np.argsort(-scores)[:l]
        triplets = []
        for index in top_indices:
            record = self.triplets[int(index)]
            triplets.append(
                {
                    "field": record["field"],
                    "relation": record["relation"],
                    "table": record["table"],
                    "description": record["description"],
                    "score": round(float(scores[index]), 6),
                }
            )
        return {
            "l": l,
            "triplets": triplets,
            "tables": sorted({item["table"] for item in triplets}),
        }

    def relational_rag(self, question: str, candidate_tables: Sequence[str], h: int) -> Dict[str, Any]:
        """Rank columns inside the narrowed table scope and expose valid joins.

        The paper's operator/metadata/weights are not disclosed.  Here the operator is the
        explicit string `table purpose + column name + column description`; cosine similarity
        supplies the score.  Foreign-key endpoints are appended when both tables survived the
        first two retrieval stages.
        """

        allowed = set(candidate_tables)
        candidate_indices = [
            index for index, record in enumerate(self.column_records) if record["table"] in allowed
        ]
        query_vector = self.encoder.encode([question])[0]
        candidate_matrix = self.column_vectors[candidate_indices]
        scores = cosine_scores(query_vector, candidate_matrix)
        ranked_local_indices = np.argsort(-scores)[:h]

        ranked_columns = []
        for local_index in ranked_local_indices:
            global_index = candidate_indices[int(local_index)]
            record = self.column_records[global_index]
            ranked_columns.append(
                {
                    "qualified_name": record["qualified_name"],
                    "table": record["table"],
                    "column": record["column"],
                    "score": round(float(scores[local_index]), 6),
                }
            )

        valid_join_edges = []
        for edge in self.schema["foreign_keys"]:
            left_table = edge["left"].split(".", 1)[0]
            right_table = edge["right"].split(".", 1)[0]
            if left_table in allowed and right_table in allowed:
                valid_join_edges.append(edge)

        predicted_columns = {item["qualified_name"] for item in ranked_columns}
        selected_tables = {item["table"] for item in ranked_columns}
        used_join_edges = []
        for edge in valid_join_edges:
            left_table = edge["left"].split(".", 1)[0]
            right_table = edge["right"].split(".", 1)[0]
            if left_table in selected_tables or right_table in selected_tables:
                predicted_columns.update([edge["left"], edge["right"]])
                selected_tables.update([left_table, right_table])
                used_join_edges.append(edge)

        return {
            "h": h,
            "operator": "cosine(question, table purpose + column name + column description)",
            "ranked_columns": ranked_columns,
            "valid_join_edges_in_scope": valid_join_edges,
            "join_edges_added_to_prediction": used_join_edges,
            "predicted_columns": sorted(predicted_columns),
            "predicted_tables": sorted(selected_tables),
        }

    def retrieve(self, question: str, config: RetrievalConfig) -> Dict[str, Any]:
        start = time.perf_counter()
        contextual = self.contextual_rag(question, config.contextual_k)
        structural = self.structural_rag(question, config.structural_l)
        candidate_union = sorted(set(contextual["tables"]) | set(structural["tables"]))
        relational = self.relational_rag(question, candidate_union, config.relational_h)
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "contextual": contextual,
            "structural": structural,
            "candidate_union_before_relational_rag": candidate_union,
            "relational": relational,
            "prediction": {
                "tables": relational["predicted_tables"],
                "columns": relational["predicted_columns"],
            },
            "retrieval_latency_ms": round(latency_ms, 3),
        }

    def export_hypergraph(self) -> Dict[str, Any]:
        column_to_tables: Dict[str, List[str]] = {}
        for table in self.schema["tables"]:
            for column in table["columns"]:
                column_to_tables.setdefault(column["name"], []).append(table["name"])
        hyperedges = [
            {"column_name": column, "table_nodes": sorted(tables)}
            for column, tables in sorted(column_to_tables.items())
        ]
        return {
            "node_type": "table",
            "hyperedge_type": "column_name",
            "table_nodes": sorted(self.table_by_name),
            "column_hyperedges": hyperedges,
            "foreign_key_edges": list(self.schema["foreign_keys"]),
        }


def precision_recall(predicted: Iterable[str], gold: Iterable[str]) -> Tuple[float, float]:
    predicted_set = set(predicted)
    gold_set = set(gold)
    true_positive = len(predicted_set & gold_set)
    precision = true_positive / len(predicted_set) if predicted_set else 0.0
    recall = true_positive / len(gold_set) if gold_set else 0.0
    return precision, recall
