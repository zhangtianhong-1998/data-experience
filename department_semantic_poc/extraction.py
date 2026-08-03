from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .llm import (
    OpenAICompatibleJSONClient,
    invocation_fingerprint,
    render_template,
)
from .models import ReportExtraction
from .utils import make_ref, now_iso, read_jsonl, short_hash
from .validation import validate_report_extraction


def extract_reports(
    packages: list[dict[str, Any]],
    client: OpenAICompatibleJSONClient,
    output_path: Path,
    prompt_dir: Path,
    max_reports: int | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    schema = ReportExtraction.model_json_schema()
    schema_text = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    system_prompt = (prompt_dir / "report_system.md").read_text(encoding="utf-8")
    existing = read_jsonl(output_path)
    valid_cache = {
        record.get("invocation_fingerprint"): record
        for record in existing
        if record.get("run_status") in {"completed_valid", "cache_reused"}
    }
    selected = [package for package in packages if package.get("status") == "ready"]
    if max_reports is not None:
        selected = selected[:max_reports]
    records: list[dict[str, Any]] = [] if force else list(existing)
    completed_fingerprints = {
        record.get("invocation_fingerprint") for record in records
    }
    for index, package in enumerate(selected, start=1):
        user_prompt = render_template(
            prompt_dir / "report_extraction.md",
            {
                "OUTPUT_SCHEMA": schema_text,
                "PACKAGE_JSON": json.dumps(
                    package, ensure_ascii=False, separators=(",", ":")
                ),
            },
        )
        invocation = invocation_fingerprint(
            client.config.model,
            system_prompt,
            user_prompt,
            schema,
            {
                "max_tokens": client.config.max_tokens,
                "format_mode": client.config.format_mode,
                "thinking_mode": client.config.thinking_mode,
            },
        )
        print(
            f"[extract {index}/{len(selected)}] {package['report_ref']} chars={package.get('estimated_chars')}"
        )
        if not force and invocation in valid_cache:
            cached = dict(valid_cache[invocation])
            cached_result, cached_validation, cached_enriched = validate_report_extraction(
                package, cached.get("result", {})
            )
            if cached_result is not None:
                cached["validation"] = cached_validation
                cached["enriched_concepts"] = [
                    {
                        **item,
                        "mention_ref": make_ref(
                            "mention",
                            short_hash(package["report_ref"], 12),
                            item["local_ref"],
                        ),
                        "report_ref": package["report_ref"],
                        "department_ref": package.get("department_ref"),
                    }
                    for item in cached_enriched
                ]
            cached["run_status"] = "cache_reused"
            cached["reused_at"] = now_iso()
            if invocation in completed_fingerprints:
                records = [
                    cached if item.get("invocation_fingerprint") == invocation else item
                    for item in records
                ]
                output_path.write_text(
                    "".join(
                        json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
                        for item in records
                    ),
                    encoding="utf-8",
                )
            else:
                records.append(cached)
                completed_fingerprints.add(invocation)
            print("  cache reused")
            continue
        try:
            response = client.complete_json(
                system_prompt,
                user_prompt,
                schema,
                schema_name="report_extraction",
            )
            result, validation, enriched = validate_report_extraction(
                package, response["payload"]
            )
            run_status = (
                "completed_valid"
                if result is not None and validation["is_valid"]
                else "completed_validation_failed"
            )
            record = {
                "run_ref": make_ref("extraction-run", short_hash([invocation, now_iso()], 16)),
                "operator": "report_local_semantic_extraction",
                "package_ref": package["package_ref"],
                "report_ref": package["report_ref"],
                "department_ref": package.get("department_ref"),
                "invocation_fingerprint": invocation,
                "prompt_fingerprint": short_hash(system_prompt + user_prompt, 24),
                "schema_fingerprint": short_hash(schema, 24),
                "model": client.config.model,
                "run_status": run_status,
                "transport": response["transport"],
                "raw_text": response["raw_text"],
                "result": result.model_dump(mode="json") if result else response["payload"],
                "enriched_concepts": [
                    {
                        **item,
                        "mention_ref": make_ref(
                            "mention",
                            short_hash(package["report_ref"], 12),
                            item["local_ref"],
                        ),
                        "report_ref": package["report_ref"],
                        "department_ref": package.get("department_ref"),
                    }
                    for item in enriched
                ],
                "validation": validation,
                "created_at": now_iso(),
            }
        except Exception as exc:
            record = {
                "run_ref": make_ref("extraction-run", short_hash([invocation, now_iso()], 16)),
                "operator": "report_local_semantic_extraction",
                "package_ref": package["package_ref"],
                "report_ref": package["report_ref"],
                "department_ref": package.get("department_ref"),
                "invocation_fingerprint": invocation,
                "prompt_fingerprint": short_hash(system_prompt + user_prompt, 24),
                "schema_fingerprint": short_hash(schema, 24),
                "model": client.config.model,
                "run_status": "api_or_parse_failed",
                "error": str(exc),
                "validation": {"is_valid": False, "errors": [str(exc)]},
                "created_at": now_iso(),
            }
        records.append(record)
        completed_fingerprints.add(invocation)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "".join(
                json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
                for item in records
            ),
            encoding="utf-8",
        )
        print(
            f"  {record['run_status']} concepts={record.get('validation', {}).get('concept_count', 0)}"
        )
    return records
