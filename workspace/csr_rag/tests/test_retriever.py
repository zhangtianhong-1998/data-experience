from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from retriever import CSRRAGRetriever, RetrievalConfig, TfidfEncoder, precision_recall  # noqa: E402


class RetrieverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schema = json.loads((ROOT / "data" / "schema.json").read_text(encoding="utf-8"))
        history = json.loads((ROOT / "data" / "history.json").read_text(encoding="utf-8"))
        cls.retriever = CSRRAGRetriever(schema, history, TfidfEncoder())

    def test_contextual_rag_returns_known_table_set(self) -> None:
        result = self.retriever.contextual_rag("net sales by sales region", k=1)
        self.assertIn("fact_orders", result["tables"])
        self.assertIn("dim_region", result["tables"])

    def test_structural_rag_returns_triplets(self) -> None:
        result = self.retriever.structural_rag("refund amount for returned orders", l=5)
        names = {f"{item['table']}.{item['field']}" for item in result["triplets"]}
        self.assertIn("fact_returns.refund_amount", names)

    def test_relational_stage_never_introduces_out_of_scope_table(self) -> None:
        scope = ["fact_orders", "fact_returns", "dim_region"]
        result = self.retriever.relational_rag("net revenue by region", scope, h=8)
        self.assertTrue(set(result["predicted_tables"]).issubset(set(scope)))

    def test_precision_recall(self) -> None:
        precision, recall = precision_recall(["a", "b"], ["b", "c"])
        self.assertEqual((precision, recall), (0.5, 0.5))


if __name__ == "__main__":
    unittest.main()
