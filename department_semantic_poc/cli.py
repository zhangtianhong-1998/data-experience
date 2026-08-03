from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .alignment import (
    align_candidate_batches,
    build_alignment_candidates,
    materialize_department_semantics,
)
from .evidence import build_report_evidence_packages
from .extraction import extract_reports
from .ingest import build_asset_graph
from .llm import LLMConfig, OpenAICompatibleJSONClient
from .sql_facts import build_sql_facts
from .utils import now_iso, read_json, read_jsonl, write_json, write_jsonl


DEFAULT_INPUT_DIR = Path(
    "outputs/019fb2dd-78a1-7871-8583-6a82e72af555/simulated_inputs"
)
DEFAULT_RUN_DIR = Path(
    "outputs/019fb2dd-78a1-7871-8583-6a82e72af555/runs/department_demo_001"
)


def prepare(
    input_dir: Path,
    output_dir: Path,
    dialect: str | None = None,
) -> dict[str, Any]:
    snapshot, asset_graph = build_asset_graph(
        execution_excel=input_dir / "BI_SQL执行明细_部门实验.xlsx",
        table_metadata_path=input_dir / "数据字段信息.json",
        report_mapping_path=input_dir / "报表使用的数据映射.json",
        lineage_excel=input_dir / "报表字段血缘_部门实验.xlsx",
        scope_path=input_dir / "实验范围.json",
    )
    sql_facts = build_sql_facts(asset_graph, dialect=dialect)
    packages = build_report_evidence_packages(asset_graph, sql_facts)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "01_source_snapshot.json", snapshot)
    write_json(output_dir / "02_asset_graph.json", asset_graph)
    write_jsonl(output_dir / "03_sql_facts.jsonl", sql_facts)
    write_jsonl(output_dir / "04_report_evidence_packages.jsonl", packages)

    reports = list(asset_graph.get("reports", {}).values())
    selected_department = asset_graph.get("scope", {}).get("selected_department_ref")
    selected_reports = [
        report for report in reports if report.get("department_ref") == selected_department
    ]
    components = [
        component for report in reports for component in report.get("components", [])
    ]
    summary = {
        "schema_version": "prepare-summary-v1",
        "generated_at": now_iso(),
        "selected_department_ref": selected_department,
        "counts": {
            "reports_total": len(reports),
            "reports_selected_department": len(selected_reports),
            "components_total": len(components),
            "queries_total": len(sql_facts),
            "sql_parsed": sum(item.get("parse_status") == "parsed" for item in sql_facts),
            "sql_failed": sum(item.get("parse_status") != "parsed" for item in sql_facts),
            "evidence_packages": len(packages),
            "evidence_items": sum(len(item.get("evidences", [])) for item in packages),
            "input_issues": len(asset_graph.get("issues", [])),
            "lineage_issues": sum(
                item.get("status") != "正常"
                for item in asset_graph.get("field_lineage", [])
            ),
            "physical_metadata_issues": sum(
                payload.get("status") != "正常，未发现缺失值"
                for payload in asset_graph.get("physical_metadata", {}).values()
                if isinstance(payload, dict)
            ),
        },
        "package_statuses": {
            status: sum(item.get("status") == status for item in packages)
            for status in sorted({item.get("status") for item in packages})
        },
    }
    write_json(output_dir / "00_prepare_summary.json", summary)
    lines = [
        "# 确定性预处理摘要",
        "",
        f"- 选择部门：`{selected_department}`",
        f"- 报表：{summary['counts']['reports_total']}，其中部门内 {summary['counts']['reports_selected_department']}",
        f"- 组件：{summary['counts']['components_total']}；SQL：{summary['counts']['queries_total']}",
        f"- SQL解析：成功 {summary['counts']['sql_parsed']}，失败 {summary['counts']['sql_failed']}",
        f"- 报表证据包：{summary['counts']['evidence_packages']}；原子证据：{summary['counts']['evidence_items']}",
        f"- 输入异常：{summary['counts']['input_issues']}；血缘异常：{summary['counts']['lineage_issues']}；物理元数据异常表：{summary['counts']['physical_metadata_issues']}",
        "",
        "此阶段没有调用LLM。SQL结构、血缘和质量状态均可由程序重算。",
        "",
    ]
    (output_dir / "00_prepare_summary.md").write_text("\n".join(lines), encoding="utf-8")
    return {
        "snapshot": snapshot,
        "asset_graph": asset_graph,
        "sql_facts": sql_facts,
        "packages": packages,
        "summary": summary,
    }


def load_prepared(output_dir: Path) -> dict[str, Any]:
    return {
        "asset_graph": read_json(output_dir / "02_asset_graph.json"),
        "sql_facts": read_jsonl(output_dir / "03_sql_facts.jsonl"),
        "packages": read_jsonl(output_dir / "04_report_evidence_packages.jsonl"),
    }


def make_client(args: argparse.Namespace) -> OpenAICompatibleJSONClient:
    config = LLMConfig.from_env(
        Path(args.env_file),
        timeout_seconds=args.llm_timeout,
        max_tokens=args.llm_max_tokens,
        format_mode=args.format_mode,
        thinking_mode=args.llm_thinking,
    )
    return OpenAICompatibleJSONClient(config)


def run_extract(args: argparse.Namespace) -> list[dict[str, Any]]:
    prepared = load_prepared(Path(args.output_dir))
    return extract_reports(
        prepared["packages"],
        make_client(args),
        Path(args.output_dir) / "05_report_extractions.jsonl",
        Path(args.prompt_dir),
        max_reports=args.max_reports,
        force=args.force,
    )


def run_candidate_generation(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    prepared = load_prepared(output_dir)
    extraction_records = read_jsonl(output_dir / "05_report_extractions.jsonl")
    department_ref = prepared["asset_graph"]["scope"]["selected_department_ref"]
    configured_max = prepared["asset_graph"]["scope"].get("policy", {}).get(
        "max_alignment_candidates_per_mention", args.top_k
    )
    top_k = min(configured_max, args.top_k)
    candidates, batches, summary = build_alignment_candidates(
        extraction_records,
        prepared["packages"],
        department_ref=department_ref,
        top_k=top_k,
        batch_size=args.batch_size,
    )
    write_jsonl(output_dir / "06_department_alignment_candidates.jsonl", candidates)
    write_jsonl(output_dir / "07_department_alignment_batches.jsonl", batches)
    write_json(output_dir / "06_alignment_candidate_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return {"candidates": candidates, "batches": batches, "summary": summary}


def run_alignment(args: argparse.Namespace) -> list[dict[str, Any]]:
    output_dir = Path(args.output_dir)
    batches = read_jsonl(output_dir / "07_department_alignment_batches.jsonl")
    return align_candidate_batches(
        batches,
        make_client(args),
        output_dir / "08_department_alignment_decisions.jsonl",
        Path(args.prompt_dir),
        max_batches=args.max_batches,
        force=args.force,
    )


def run_materialize(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    asset_graph = read_json(output_dir / "02_asset_graph.json")
    candidates = read_jsonl(output_dir / "06_department_alignment_candidates.jsonl")
    decisions = read_jsonl(output_dir / "08_department_alignment_decisions.jsonl")
    result = materialize_department_semantics(
        candidates,
        decisions,
        asset_graph["scope"]["selected_department_ref"],
    )
    write_json(output_dir / "09_department_semantics.json", result)
    return result


def add_llm_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--prompt-dir", default="prompts")
    parser.add_argument("--llm-timeout", type=int, default=180)
    parser.add_argument("--llm-max-tokens", type=int, default=9000)
    parser.add_argument(
        "--llm-thinking", choices=["disabled", "auto"], default="disabled"
    )
    parser.add_argument(
        "--format-mode",
        choices=["json_object", "json_schema", "prompt_only"],
        default="json_object",
    )
    parser.add_argument("--force", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="部门级BI语义发现与Data Agent验证原型"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="确定性预处理和证据包生成")
    prepare_parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    prepare_parser.add_argument("--output-dir", default=str(DEFAULT_RUN_DIR))
    prepare_parser.add_argument("--dialect", default=None)

    extract_parser = subparsers.add_parser("extract", help="调用LLM做报表局部语义抽取")
    extract_parser.add_argument("--output-dir", default=str(DEFAULT_RUN_DIR))
    extract_parser.add_argument("--max-reports", type=int, default=None)
    add_llm_args(extract_parser)

    candidate_parser = subparsers.add_parser(
        "candidates", help="生成部门内跨报表Top-K候选"
    )
    candidate_parser.add_argument("--output-dir", default=str(DEFAULT_RUN_DIR))
    candidate_parser.add_argument("--top-k", type=int, default=3)
    candidate_parser.add_argument("--batch-size", type=int, default=12)

    align_parser = subparsers.add_parser("align", help="调用LLM判断候选语义关系")
    align_parser.add_argument("--output-dir", default=str(DEFAULT_RUN_DIR))
    align_parser.add_argument("--max-batches", type=int, default=None)
    add_llm_args(align_parser)

    materialize_parser = subparsers.add_parser(
        "materialize", help="按保守策略形成部门关系和可合并概念"
    )
    materialize_parser.add_argument("--output-dir", default=str(DEFAULT_RUN_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "prepare":
        result = prepare(Path(args.input_dir), Path(args.output_dir), dialect=args.dialect)
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    elif args.command == "extract":
        run_extract(args)
    elif args.command == "candidates":
        run_candidate_generation(args)
    elif args.command == "align":
        run_alignment(args)
    elif args.command == "materialize":
        print(json.dumps(run_materialize(args), ensure_ascii=False, indent=2))
    return 0
