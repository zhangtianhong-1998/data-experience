"""Use a real LLM to turn questions into governed Cube and Wren query objects.

This is an inspectable external-agent harness. It does not claim to reproduce
Cube Cloud's or Wren Cloud's private orchestration prompt.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from openai import OpenAI


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[2]
CUBE_META = ROOT.parent / "cube" / "results" / "meta_response.json"
WREN_PROJECT = ROOT.parent / "wrenai" / "device_project"
WREN_MDL = WREN_PROJECT / "target" / "mdl.json"
WREN_RULES = WREN_PROJECT / "knowledge" / "rules" / "device_metrics.md"
RESULTS = ROOT / "results"

READY_MEASURES = {
    "cube": [
        "DeviceOrders.deviceOrderAmount",
        "DeviceOrders.deviceProfitAmount",
    ],
    "wren": ["device_order_amount", "device_profit_amount"],
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$", "", (text or "").strip(), flags=re.I | re.S
    )
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        if start < 0:
            raise ValueError("LLM response does not contain a JSON object")
        value, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    if not isinstance(value, dict):
        raise ValueError("LLM response is not a JSON object")
    return value


def safe_error(exc: Exception, secrets: list[str | None]) -> str:
    value = f"{type(exc).__name__}: {exc}"
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value


def cube_context() -> dict[str, Any]:
    raw = load_json(CUBE_META)
    cube = next(item for item in raw["cubes"] if item["name"] == "DeviceOrders")
    return {
        "source": "actual Cube Core /cubejs-api/v1/meta response",
        "scope_strategy": "full metadata after hard scoping to the device domain",
        "cube": {
            "name": cube["name"],
            "title": cube.get("title"),
            "description": cube.get("description"),
            "measures": [
                {
                    key: member.get(key)
                    for key in ("name", "title", "description", "type", "meta")
                    if member.get(key) is not None
                }
                for member in cube.get("measures", [])
            ],
            "dimensions": [
                {
                    key: member.get(key)
                    for key in ("name", "title", "description", "type", "meta")
                    if member.get(key) is not None
                }
                for member in cube.get("dimensions", [])
            ],
        },
    }


def wren_context() -> dict[str, Any]:
    mdl = load_json(WREN_MDL)
    cube = next(item for item in mdl["cubes"] if item["name"] == "device_business")
    model = next(item for item in mdl["models"] if item["name"] == cube["baseObject"])
    return {
        "source": "actual compiled Wren target/mdl.json plus knowledge/rules",
        "scope_strategy": "full context because the MDL is below Wren's 30,000-character threshold",
        "model": model,
        "cube": cube,
        "business_rules": WREN_RULES.read_text(encoding="utf-8"),
    }


SYSTEM_PROMPT = """你是企业语义查询规划器。你不写物理 SQL，只能从给定语义上下文中选择正式对象并生成结构化查询。

必须遵守：
1. 只能使用上下文出现的正式 Cube、Measure、Dimension 和操作符，绝不发明字段、指标、公式或 Join。
2. 先判断问题是否具备唯一且可执行的业务含义。只有全部指标、分组、组织和时间范围都明确时才能返回 ready。
3. 缺少必填条件或存在多个合理指标时返回 needs_clarification，并提出一个具体问题；query 必须为 null。
4. 问题明确要求语义层声明不可替代或不支持的概念时返回 unsupported；query 必须为 null。
5. 不要把“销售金额”解释成“设备订货金额”，不要把“净利润”解释成“设备利润”。
6. 时间范围必须使用闭区间：2026 年上半年是 2026-01-01 至 2026-06-30；Wren 的 year_month 范围是 202601 至 202606。
7. dimensions 只放用户明确要求的分组字段。作为过滤条件的组织和时间字段不能同时放进 dimensions，除非用户明确要求按组织或时间分组。
8. 只返回一个 JSON 对象，不要输出 Markdown。"""


def output_contract(framework: str) -> dict[str, Any]:
    common = {
        "status": "ready | needs_clarification | unsupported",
        "reason": "简洁说明为什么做出这一判断",
        "clarification_question": "需要追问时填写字符串，否则为 null",
    }
    if framework == "cube":
        common["query"] = {
            "measures": "仅允许 DeviceOrders.deviceOrderAmount、DeviceOrders.deviceProfitAmount、DeviceOrders.orderCount",
            "dimensions": "仅允许 DeviceOrders.productL1、DeviceOrders.yearMonth、DeviceOrders.orgCode、DeviceOrders.status",
            "timeDimensions": [
                {
                    "dimension": "仅允许 DeviceOrders.orderDate",
                    "dateRange": ["YYYY-MM-DD", "YYYY-MM-DD"],
                }
            ],
            "filters": [
                {
                    "member": "上下文中的正式 Dimension ID",
                    "operator": "equals",
                    "values": ["过滤值"],
                }
            ],
            "order": "可选；如提供，只能写 {正式 Dimension ID: asc | desc}。省略时由程序确定性排序",
        }
    else:
        common["query"] = {
            "cube": "仅允许 device_business",
            "measures": "仅允许 device_order_amount、device_profit_amount",
            "dimensions": "仅允许 product_l1、org_code、year_month、status",
            "filters": ["dimension:operator:value；操作符只允许 eq、gte、lte"],
        }
    common["query_note"] = "status 不是 ready 时，query 必须为 null"
    return common


def validate_response(
    framework: str, case: dict[str, Any], response: dict[str, Any]
) -> dict[str, Any]:
    errors: list[str] = []
    status = response.get("status")
    if status != case["expected_status"]:
        errors.append(
            f"expected status {case['expected_status']!r}, got {status!r}"
        )
    if not isinstance(response.get("reason"), str) or not response["reason"].strip():
        errors.append("reason must be a non-empty string")

    query = response.get("query")
    if status != "ready":
        if query is not None:
            errors.append("query must be null when status is not ready")
        if status == "needs_clarification" and not isinstance(
            response.get("clarification_question"), str
        ):
            errors.append("needs_clarification requires a clarification_question")
        return {"passed": not errors, "errors": errors}

    if not isinstance(query, dict):
        errors.append("ready response requires a query object")
        return {"passed": False, "errors": errors}

    if framework == "cube":
        if set(query.get("measures", [])) != set(READY_MEASURES["cube"]):
            errors.append("Cube measures do not match the governed pair")
        if query.get("dimensions") != ["DeviceOrders.productL1"]:
            errors.append("Cube dimension must be DeviceOrders.productL1")
        expected_time = [
            {
                "dimension": "DeviceOrders.orderDate",
                "dateRange": ["2026-01-01", "2026-06-30"],
            }
        ]
        if query.get("timeDimensions") != expected_time:
            errors.append("Cube timeDimensions do not represent 2026 H1")
        filters = {
            (
                item.get("member"),
                item.get("operator"),
                tuple(str(value) for value in item.get("values", [])),
            )
            for item in query.get("filters", [])
            if isinstance(item, dict)
        }
        if filters != {
            ("DeviceOrders.orgCode", "equals", ("ORG_1001",))
        }:
            errors.append("Cube filters must contain only the explicit organization")
        allowed = {
            "DeviceOrders.deviceOrderAmount",
            "DeviceOrders.deviceProfitAmount",
            "DeviceOrders.orderCount",
            "DeviceOrders.productL1",
            "DeviceOrders.yearMonth",
            "DeviceOrders.orgCode",
            "DeviceOrders.status",
            "DeviceOrders.orderDate",
        }
        used = set(query.get("measures", [])) | set(query.get("dimensions", []))
        used |= {
            item.get("member")
            for item in query.get("filters", [])
            if isinstance(item, dict)
        }
        used |= {
            item.get("dimension")
            for item in query.get("timeDimensions", [])
            if isinstance(item, dict)
        }
        invented = {item for item in used if item and item not in allowed}
        if invented:
            errors.append(f"invented Cube members: {sorted(invented)}")
    else:
        if query.get("cube") != "device_business":
            errors.append("Wren cube must be device_business")
        if set(query.get("measures", [])) != set(READY_MEASURES["wren"]):
            errors.append("Wren measures do not match the governed pair")
        if query.get("dimensions") != ["product_l1"]:
            errors.append("Wren dimension must be product_l1")
        if set(query.get("filters", [])) != {
            "org_code:eq:ORG_1001",
            "year_month:gte:202601",
            "year_month:lte:202606",
        }:
            errors.append("Wren filters do not match organization and 2026 H1")
        allowed = {
            "device_order_amount",
            "device_profit_amount",
            "product_l1",
            "org_code",
            "year_month",
            "status",
        }
        used = set(query.get("measures", [])) | set(query.get("dimensions", []))
        for value in query.get("filters", []):
            if isinstance(value, str):
                used.add(value.split(":", 1)[0])
        invented = {item for item in used if item and item not in allowed}
        if invented:
            errors.append(f"invented Wren members: {sorted(invented)}")
    return {"passed": not errors, "errors": errors}


def call_llm(
    client: OpenAI,
    model: str,
    framework: str,
    case: dict[str, Any],
    context: dict[str, Any],
    secrets: list[str | None],
) -> dict[str, Any]:
    user_payload = {
        "framework": framework,
        "question": case["question"],
        "current_date": "2026-08-04",
        "semantic_context": context,
        "required_output": output_contract(framework),
    }
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False, indent=2),
        },
    ]
    attempts: list[dict[str, Any]] = []
    for format_mode in ("json_object", "prompt_only"):
        request: dict[str, Any] = {
            "model": model,
            "temperature": 0,
            "messages": messages,
        }
        if format_mode == "json_object":
            request["response_format"] = {"type": "json_object"}
        recorded_request = {
            **request,
            "api_key_included_in_record": False,
            "base_url_included_in_record": False,
        }
        try:
            api_request = {key: value for key, value in request.items()}
            response = client.chat.completions.create(**api_request)
            raw = response.choices[0].message.content or ""
            parsed = parse_json_object(raw)
            return {
                "successful_request": recorded_request,
                "format_mode": format_mode,
                "raw_response": raw,
                "parsed_response": parsed,
                "response_metadata": {
                    "id": response.id,
                    "model": response.model,
                    "finish_reason": response.choices[0].finish_reason,
                    "usage": response.usage.model_dump() if response.usage else None,
                },
                "failed_attempts": attempts,
            }
        except Exception as exc:
            attempts.append(
                {
                    "request": recorded_request,
                    "error": safe_error(exc, secrets),
                }
            )
    raise RuntimeError(f"all LLM attempts failed: {attempts}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--env",
        type=Path,
        default=WORKSPACE.parent / "data-ex" / ".env",
        help="Path to the secret .env file; values are never persisted.",
    )
    args = parser.parse_args()
    config = dotenv_values(args.env)
    api_key = config.get("THIRD_PARTY_API_KEY")
    base_url = config.get("THIRD_PARTY_BASE_URL")
    model = config.get("THIRD_PARTY_MODEL")
    if not api_key or not base_url or not model:
        raise RuntimeError("THIRD_PARTY_API_KEY, THIRD_PARTY_BASE_URL and THIRD_PARTY_MODEL are required")

    client = OpenAI(api_key=api_key, base_url=base_url)
    contexts = {"cube": cube_context(), "wren": wren_context()}
    cases = load_json(ROOT / "cases.json")
    records = []
    for framework in ("cube", "wren"):
        for case in cases:
            call = call_llm(
                client,
                str(model),
                framework,
                case,
                contexts[framework],
                [str(api_key), str(base_url)],
            )
            validation = validate_response(
                framework, case, call["parsed_response"]
            )
            record = {
                "framework": framework,
                "case": case,
                "context_source": contexts[framework]["source"],
                "context_strategy": contexts[framework]["scope_strategy"],
                "llm": call,
                "validation": validation,
            }
            dump_json(
                RESULTS / "calls" / framework / f"{case['id']}.json", record
            )
            if (
                call["parsed_response"].get("status") == "ready"
                and validation["passed"]
            ):
                dump_json(
                    RESULTS / "generated" / framework / f"{case['id']}.json",
                    call["parsed_response"]["query"],
                )
            records.append(record)

    summary = {
        "model": model,
        "real_llm_calls": len(records),
        "fallback_results": 0,
        "api_key_logged": False,
        "base_url_logged": False,
        "passed": sum(item["validation"]["passed"] for item in records),
        "failed": sum(not item["validation"]["passed"] for item in records),
        "all_passed": all(item["validation"]["passed"] for item in records),
        "results": [
            {
                "framework": item["framework"],
                "case_id": item["case"]["id"],
                "expected_status": item["case"]["expected_status"],
                "actual_status": item["llm"]["parsed_response"].get("status"),
                "passed": item["validation"]["passed"],
                "errors": item["validation"]["errors"],
            }
            for item in records
        ],
        "scope_note": "External reproducible agent harness; not a claim about private Cube Cloud or Wren Cloud prompts.",
    }
    dump_json(RESULTS / "llm_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
