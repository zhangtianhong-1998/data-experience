# 真实 LLM 如何从语义上下文生成 DSL？

## 先说结果

现在不再是“假设大模型会生成正确 DSL”。我们已经让真实 LLM 分别读取 Cube 和 Wren 的语义上下文，并回答 5 类问题。

最终一轮结果是：

- Cube 5/5 判断正确；Wren 5/5 判断正确。
- 标准问题和同义词问题产生 4 份可执行查询。
- 4 份查询全部由真实 Cube/Wren 引擎编译执行，4/4 与标准答案一致。
- 歧义、缺组织、跨业务域三个问题都没有产生可执行查询。
- 没有用预写答案覆盖模型错误。

不过，真正值得读的不是最后的 10/10，而是它在前两轮为什么会失败。

## 一、人的问题是什么？

标准问题是：

> ORG_1001 在 2026 年上半年，按产品一级分类统计设备订货金额和设备利润。

另外还测试了：

| 问题 | 我们希望系统做什么 |
|---|---|
| “各产品大类的设备订货额和设备利润额” | 理解同义词，生成相同查询 |
| “按产品一级分类统计金额” | 追问是订货金额还是利润金额 |
| 没有提供组织编码 | 追问组织，不能默认跨组织汇总 |
| 询问“销售金额” | 说明设备模型不支持，不能偷换成订货金额 |

这里不是让模型一律“想办法回答”。`needs_clarification` 和 `unsupported` 都是合格结果。

## 二、Cube 的 LLM 实际看到了什么？

Cube Core 自己没有调用 LLM。我们的外部 Agent 先读取本机真实 `/meta`，再把以下内容交给模型：

```text
系统规则：
- 只能选择给出的正式成员
- 缺组织或存在歧义时必须追问
- 不得把销售金额替换成设备订货金额
- dimensions 只能放用户要求的分组字段

真实 Cube Meta：
- DeviceOrders.deviceOrderAmount
  设备订货金额；同义词包括“设备订货额”
- DeviceOrders.deviceProfitAmount
  设备利润金额；不是净利润
- DeviceOrders.productL1
  “产品大类”在本模型中指产品一级分类
- DeviceOrders.orgCode
  必填过滤维度，不得猜测

用户问题：
ORG_1001 在 2026 年上半年，按产品一级分类统计设备订货金额和设备利润

输出合同：
status + reason + clarification_question + Cube Query
```

这不是根据文档手工还原的摘要。完整的两条 LLM message、模型名、`response_format`、原始响应和 token usage 都保存在 [`cube/01_exact.json`](../demos/route1/nl_to_dsl/results/calls/cube/01_exact.json)。日志明确记录 `api_key_included_in_record=false` 和 `base_url_included_in_record=false`。

## 三、LLM 返回了什么？

真实模型返回：

```json
{
  "status": "ready",
  "reason": "组织编码、时间范围、分组字段和指标均明确且无歧义。",
  "clarification_question": null,
  "query": {
    "measures": [
      "DeviceOrders.deviceOrderAmount",
      "DeviceOrders.deviceProfitAmount"
    ],
    "dimensions": ["DeviceOrders.productL1"],
    "timeDimensions": [
      {
        "dimension": "DeviceOrders.orderDate",
        "dateRange": ["2026-01-01", "2026-06-30"]
      }
    ],
    "filters": [
      {
        "member": "DeviceOrders.orgCode",
        "operator": "equals",
        "values": ["ORG_1001"]
      }
    ]
  }
}
```

程序接下来不是直接相信它，而是检查：

- 两个指标和分组维度是否存在于 Meta。
- 是否只使用正式成员 ID。
- 时间范围是否真的是 2026 年上半年。
- 是否保留了用户明确给出的 `ORG_1001`。
- 是否把过滤字段错误地加入分组。

通过后才提交给 Cube。Cube 生成的物理 SQL 自动带上：

```sql
SUM(CASE WHEN status = 'confirmed' THEN order_amount ELSE 0 END)
SUM(CASE WHEN status = 'confirmed' THEN profit_amount ELSE 0 END)
```

注意：LLM 输出里没有 `status='confirmed'`。这条口径来自 Cube 的长期指标定义，不由 LLM 临时重写。

## 四、Wren 的输入和输出有什么不同？

Wren 的语义上下文来自真实 `target/mdl.json` 和 `knowledge/rules/device_metrics.md`。LLM 最终返回的是 MCP `query_cube` 可以使用的参数：

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

程序把 MCP 风格的过滤字符串确定性转换成 Wren CLI 的结构化过滤对象，Wren 再编译出：

```sql
SELECT
  product_l1,
  SUM(CASE WHEN status = 'confirmed' THEN order_amount ELSE 0 END)
    AS device_order_amount,
  SUM(CASE WHEN status = 'confirmed' THEN profit_amount ELSE 0 END)
    AS device_profit_amount
FROM device_orders
WHERE org_code = 'ORG_1001'
  AND year_month >= 202601
  AND year_month <= 202606
GROUP BY 1
```

完整输入和原始回答见 [`wren/01_exact.json`](../demos/route1/nl_to_dsl/results/calls/wren/01_exact.json)，实际编译与数据对账见 [`execution/wren/01_exact.json`](../demos/route1/nl_to_dsl/results/execution/wren/01_exact.json)。

## 五、系统什么时候没有生成查询？

### 只说“金额”

Cube 最终回答：

> 用户只说“金额”，语义层明确声明无法区分“设备订货金额”与“设备利润金额”，必须追问。

并生成问题：

> 您所说的“金额”是指设备订货金额还是设备利润金额？

此时 `query=null`，因此后面的执行器根本没有可执行文件可读。

### 没有组织

两个框架都返回 `needs_clarification`。它们没有猜测 `ORG_1001`，也没有默认统计全公司。

### 问销售金额

两个框架都返回 `unsupported`。Wren 的原始理由很直白：销售金额属于 `sales_orders` 业务域，当前只有 `device_business`，不能用 `device_order_amount` 替代。

## 六、第一次为什么只有 9/10？

第一轮中，Wren 面对“统计金额”会追问，Cube 却直接选择了一个指标。

原因不是 Wren 的模型更聪明，而是两边拿到的语义资产不同：

- Wren Knowledge 明确写着：“用户只说金额时，无法区分订货金额和利润金额，必须追问。”
- Cube Meta 当时只有两个指标名称和各自说明，没有写这条歧义处理规则。

我们没有修改测试期望，也没有在程序里强制把这个案例改成追问。修复方式是把同一条业务规则写进两个 Cube Measure 的 `meta.ai_context`，重新启动 Cube，再通过真实 `/meta` 读取。下一轮 Cube 才正确追问。

这次失败验证了一件很实在的事：

> 高质量语义层不仅告诉 Agent“有什么指标”，还要告诉它“什么时候不能选”和“什么时候必须问人”。

第一轮完整记录保存在 [`01_before_cube_ambiguity_context`](../demos/route1/nl_to_dsl/results/attempts/01_before_cube_ambiguity_context/llm_summary.json)。

## 七、第二轮又暴露了什么？

第二轮的歧义已经修复，但出现两个规划问题：

- Cube 省略了 `order`，旧验证器把它判错。实际上排序不改变聚合语义，程序完全可以在展示和对账时确定性排序，所以这是验证器过严。
- Wren 在同义词问题中把 `org_code`、`year_month` 同时放进 filters 和 dimensions，导致结果粒度可能被拆到月份。这是真正的查询规划错误。

因此最终系统规则增加了一条通用限制：过滤字段不能同时成为分组字段，除非用户明确要求按它分组。最终第三轮 10/10 通过。

第二轮原始记录保存在 [`02_after_cube_context_before_planner_rule`](../demos/route1/nl_to_dsl/results/attempts/02_after_cube_context_before_planner_rule/llm_summary.json)。

## 八、我们现在能下什么结论？

能下的结论是：

> 在这个受控的设备业务域中，真实 LLM 已经能够读取 Cube/Wren 语义上下文，选择正式指标和维度，生成受控查询 DSL；歧义或缺条件时不生成查询；通过校验的 DSL 能被真实引擎编译并得到正确结果。

不能下的结论是：

> 这已经证明数万张表、多业务域、多用户权限和连续对话都能达到同样准确率。

当前只有一个小型单 Cube 场景、5 类问题和一个模型。它是链路贯通实验，不是生产准确率基准。

完整实现、复跑方式和产物索引见 [`nl_to_dsl/README.md`](../demos/route1/nl_to_dsl/README.md)；三轮命令与退出码见 [`20260804-nl-to-dsl`](../runs/20260804-nl-to-dsl/README.md)。
