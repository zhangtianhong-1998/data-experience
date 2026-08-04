# WrenAI 最终输入到 LLM 的是什么？

## 先区分三个容易混在一起的东西

我们本机实际安装和测试的是 **Wren CLI 0.13.2**。在这个版本里：

1. `wren ask` 只负责把用户问题包进一段提示词并打印出来，它自己不调用 LLM，也不执行查询。
2. `wren serve mcp` 把 Schema、业务规则、历史查询和查询执行能力注册成 MCP 工具。
3. Claude、Codex 或其他 MCP Host 才真正调用 LLM。Host 自己的系统提示词、模型名称和消息编排不归 Wren 控制。

所以“Wren 最终给 LLM 一个完整字符串”并不是最准确的理解。在 MCP 模式下，LLM 会分多轮看到：用户问题、Wren 工作流、可用工具定义，以及工具调用返回的语义上下文。

还有一个实验边界必须提前说明：当前 [`invoke_mcp.py`](../../demos/route1/wrenai/invoke_mcp.py) 是测试脚本，它直接调用了 `get_context` 和 `query_cube`，中间没有 LLM。下面的提示词来自已安装包的真实模板；工具返回来自本机真实 MCP 调用，但“由模型自动选出查询参数”尚未在当前 Demo 中发生。

## 第一种接法：`wren ask --guided` 实际打印什么？

我在本机执行了：

```bash
wren ask \
  "ORG_1001 在 2026 年上半年，按产品一级分类统计设备订货金额和利润" \
  --guided
```

Wren 0.13.2 实际输出如下。这里保留英文原文，因为这正是交给 Agent 的真实模板，不做中文改写：

```text
You are an agent helping a user with Wren CLI.
Identify the task type, then follow the matching flow:

TASK TYPE A — data question:
  1. wren context show [--path <project>]   # see MDL models
  2. wren memory recall -q "<keywords>"  # similar past queries (skip if no memory)
  3. write SQL using model names (not raw tables)
  4. wren dry-plan --sql '...'              # validate non-trivial SQL
  5. wren query --sql '...'                 # execute
  6. answer in natural language

TASK TYPE B — explore / understand the project:
  1. wren skills list
  2. wren skills get <name> [--full]
  3. follow the markdown

Constraints:
- use model names, never invent column names (verify via wren context show)
- never ask for credentials in chat — they go through .env

User question: ORG_1001 在 2026 年上半年，按产品一级分类统计设备订货金额和利润
```

`--direct` 模式更短，实际输出是：

```text
You have access to Wren CLI for semantic SQL queries.
Run `wren skills list` or `wren --help` to discover capabilities.

User question: ORG_1001 在 2026 年上半年，按产品一级分类统计设备订货金额和利润
```

这两段都只是 Prompt 包装器。Wren 源码中的 `ask.py` 也明确写着：它不执行查询，只产生一份让 Agent 消费的提示词。

## 第二种接法：通过 MCP 时，LLM 第一轮看到什么？

MCP Server 公开了一份名为 `wren_workflow` 的 Prompt。以“数据库连接可用、写入历史记忆关闭”的通常配置为例，把本问题代入后，Wren 生成的工作流正文是：

```text
The user asked: "ORG_1001 在 2026 年上半年，按产品一级分类统计设备订货金额和利润"

Follow this workflow to answer a data question:
1. Read the `wren://mdl` resource and use `list_models` / `describe_model` to understand the schema; for schema, read `wren://mdl` or use `get_context` / `describe_schema`; browse project knowledge via `list_knowledge` + the `wren://knowledge/{path}` resource.
2. Call `get_instructions` for business rules that affect how to interpret the data.
3. Call `recall_queries` for proven NL->SQL exemplars similar to the question, or `list_stored_queries` to browse all of them.
4. Write SQL in the project's dialect, validate it with `dry_run`, then execute it with `run_sql`.
5. For named metrics, prefer `query_cube` over hand-written aggregate SQL.
```

但 LLM 收到的不只是这段文字。MCP Host 还会把工具定义作为结构化参数一同交给模型。与本例最相关的三个工具，精简后是：

```json
[
  {
    "name": "get_context",
    "parameters": {
      "question": "string, required",
      "limit": "integer, default 5",
      "item_type": "string or null",
      "model_name": "string or null"
    }
  },
  {
    "name": "recall_queries",
    "parameters": {
      "question": "string, required",
      "limit": "integer, default 3"
    }
  },
  {
    "name": "query_cube",
    "parameters": {
      "cube": "string or null",
      "measures": "string[] or null",
      "dimensions": "string[] or null",
      "time_dimension": "string or null",
      "filters": "string[] or null",
      "limit": "integer or null",
      "offset": "integer or null",
      "sql_only": "boolean, default false"
    }
  }
]
```

完整工具 JSON Schema 已保存在本机实测日志 [`mcp_calls.json`](../../demos/route1/wrenai/device_project/results/mcp_calls.json) 的第一条记录中。

这里最重要的是：工具定义不是普通提示词段落，而是 LLM API 请求中的 `tools`。模型不能随意发明工具参数字段，但当前 `measures` 和 `dimensions` 仍然只是字符串数组，并没有动态 `enum` 限制。因此它仍需要先读 Schema，再由程序校验名称。

## LLM 调用 `get_context` 后，第二轮实际会增加什么？

对于本问题，测试脚本实际发出的 MCP 调用是：

```json
{
  "name": "get_context",
  "arguments": {
    "question": "ORG_1001 在 2026 上半年按产品一级分类的设备订货金额"
  }
}
```

本机 MCP 实际返回的是下面这段文本：

```text
Catalog: wren, Schema: public

### Model: device_orders — 合成设备订货事实表。每行一张订货单，取消单不得计入指标。
  Columns:
    - order_id (VARCHAR) PRIMARY KEY
    - order_date (DATE)
    - year_month (INTEGER)
    - org_code (VARCHAR) — 组织编码；分析必须显式限定。
    - product_code (VARCHAR)
    - product_l1 (VARCHAR) — 产品一级分类。
    - order_amount (DOUBLE)
    - profit_amount (DOUBLE)
    - country (VARCHAR)
    - status (VARCHAR)

### Cube: device_business (base: device_orders)
  Measures:
    - device_order_amount (DOUBLE): SUM(CASE WHEN status = 'confirmed' THEN order_amount ELSE 0 END)
    - device_profit_amount (DOUBLE): SUM(CASE WHEN status = 'confirmed' THEN profit_amount ELSE 0 END)
  Dimensions:
    - product_l1 (VARCHAR)
    - org_code (VARCHAR)
    - year_month (INTEGER)
    - status (VARCHAR)
```

返回对象还明确标记：

```json
{
  "strategy": "full"
}
```

也就是说，本例没有做 Top-K。完整 Schema 文本不足 30,000 字符，所以 Wren 把整个结构放进第二轮 LLM 上下文。Schema 变大以后，`strategy` 才会变成 `search`，并默认返回 5 条向量检索结果。

如果 Host 严格遵循 `wren_workflow`，它还会调用 `get_instructions`。本项目的真实业务规则文件会返回：

```text
- device_order_amount 只合计 status = 'confirmed' 的 order_amount。
- 查询必须显式给出 org_code，不得默认跨组织汇总。
- 演示金额单位为 CNY。
- “销售金额”属于 sales_orders，不能代替设备订货金额。
```

当前测试脚本没有调用 `get_instructions`，所以这段规则**存在于项目中，但没有出现在当前 `mcp_calls.json` 的真实调用轨迹里**。这一点不能混写成已经发生。

## 把多轮消息摊平后，所谓“最终输入”是什么样？

不同 LLM API 的字段名略有区别，但语义上相当于下面这个消息包：

```json
{
  "system": "MCP Host 自己的系统提示词；不由 Wren 公开或控制",
  "messages": [
    {
      "role": "user",
      "content": "ORG_1001 在 2026 年上半年，按产品一级分类统计设备订货金额和利润"
    },
    {
      "role": "user",
      "content": "Follow this workflow ... For named metrics, prefer query_cube ..."
    },
    {
      "role": "assistant",
      "tool_call": {
        "name": "get_context",
        "arguments": {
          "question": "ORG_1001 在 2026 年上半年，按产品一级分类统计设备订货金额和利润"
        }
      }
    },
    {
      "role": "tool",
      "name": "get_context",
      "content": {
        "strategy": "full",
        "schema": "### Model: device_orders ... ### Cube: device_business ..."
      }
    }
  ],
  "tools": [
    "get_context JSON Schema",
    "recall_queries JSON Schema",
    "query_cube JSON Schema",
    "其他 Wren MCP 工具"
  ]
}
```

这不是从运行日志里截获的某家模型供应商原始 HTTP 请求，而是把 Wren 可核验的 Prompt、工具 Schema 和工具结果按 MCP/LLM 通用消息结构摊平，帮助人看懂“第二轮模型实际多看见了什么”。Host 的私有系统提示词不能由 Wren 给出。

## 希望 LLM 下一步产生什么？

读完上述上下文后，模型应选择 `query_cube`，并产生：

```json
{
  "cube": "device_business",
  "measures": [
    "device_order_amount",
    "device_profit_amount"
  ],
  "dimensions": ["product_l1"],
  "filters": [
    "org_code:eq:ORG_1001",
    "year_month:gte:202601",
    "year_month:lte:202606"
  ]
}
```

在当前 Demo 中，这些参数是我们预先写进脚本的，不是 LLM 自动生成的。MCP 工具收到它以后，真实返回：

```json
{
  "columns": [
    "product_l1",
    "device_order_amount",
    "device_profit_amount"
  ],
  "rows": [
    {
      "product_l1": "Compute",
      "device_order_amount": 7500.0,
      "device_profit_amount": 1560.0
    },
    {
      "product_l1": "Network",
      "device_order_amount": 3800.0,
      "device_profit_amount": 730.0
    },
    {
      "product_l1": "IoT",
      "device_order_amount": 3400.0,
      "device_profit_amount": 650.0
    }
  ],
  "row_count": 3,
  "truncated": false
}
```

随后这个工具结果会再次进入 LLM 上下文，LLM 才把三行数据组织成给人的中文答案。

## 一句话理解

Wren 没有把“全部 MDL + 问题 + SQL 指令”永远塞进同一个静态大 Prompt。它把能力拆成 MCP 工具，让模型先取 Schema 和规则，再产生查询调用，再读取结果。小 Schema 会完整进入上下文；大 Schema 才检索少量对象。

## 可核对的文件和官方资料

- 本机 Prompt 模板：`runtime/wren-venv/lib/python3.12/site-packages/wren/ask_templates/`
- 本机 MCP 实测日志：[mcp_calls.json](../../demos/route1/wrenai/device_project/results/mcp_calls.json)
- 本机业务规则：[device_metrics.md](../../demos/route1/wrenai/device_project/knowledge/rules/device_metrics.md)
- 本机 Wren Cube 查询对象：[cube_query.json](../../demos/route1/wrenai/device_project/cube_query.json)
- 本次两种 Prompt 的实际运行记录：[20260804-prompt-inspection](../../runs/20260804-prompt-inspection/README.md)
- [Wren MCP Server 暴露的工具、资源和 Prompt](https://docs.getwren.ai/oss/guides/mcp)
- [Wren memory fetch 的 30,000 字符阈值和默认 Top 5](https://docs.getwren.ai/oss/reference/cli)
- [Wren Memory 的 Schema 与历史查询召回机制](https://docs.getwren.ai/oss/concepts/memory_system)
