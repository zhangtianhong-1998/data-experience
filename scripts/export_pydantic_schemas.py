#!/usr/bin/env python
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from department_semantic_poc.models import (
    AgentAnswer,
    AlignmentBatchResult,
    ReportExtraction,
)


def main() -> None:
    output_dir = Path("schemas")
    output_dir.mkdir(parents=True, exist_ok=True)
    schemas = {
        "report_extraction.schema.json": ReportExtraction.model_json_schema(),
        "department_alignment.schema.json": AlignmentBatchResult.model_json_schema(),
        "agent_answer.schema.json": AgentAnswer.model_json_schema(),
    }
    for name, schema in schemas.items():
        (output_dir / name).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(output_dir / name)


if __name__ == "__main__":
    main()
