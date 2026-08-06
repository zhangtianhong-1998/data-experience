from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from compression import (  # noqa: E402
    factorize_column_groups,
    load_database,
    original_schema,
    purify_evidence,
    recover_factorized_schema,
    sgcf_gain,
)


class CompressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads((ROOT / "data" / "database.json").read_text(encoding="utf-8"))
        cls.database = load_database(payload)

    def test_gain_is_plain_saving_minus_overhead(self) -> None:
        self.assertEqual(sgcf_gain(support=4, width=5), 11)

    def test_factorization_is_lossless(self) -> None:
        artifacts = factorize_column_groups(self.database)
        self.assertEqual(recover_factorized_schema(artifacts), original_schema(self.database))

    def test_evidence_is_question_specific(self) -> None:
        entries = json.loads((ROOT / "data" / "external_knowledge.json").read_text(encoding="utf-8"))
        result = purify_evidence("show net revenue by region", entries)
        selected = {item["id"] for item in result["selected"]}
        self.assertIn("metric.net_revenue", selected)
        self.assertIn("term.sales_region", selected)
        self.assertNotIn("metric.inventory_turnover", selected)


if __name__ == "__main__":
    unittest.main()
