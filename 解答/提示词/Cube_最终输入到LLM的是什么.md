# Cube 最终输入到 LLM 的是什么？

## 先说最重要的事实

在我们本机运行的 **Cube Core Demo 中，没有调用 LLM，因此不存在一份“Cube 最终提示词”。**

这次实验的真实调用链是：

```text
我们预先写好的 query.json
        ↓
Cube Core REST API
        ↓
Cube 根据固定语义模型编译 SQL
        ↓
DuckDB 返回数据
```

也就是说，下面这份查询对象是实验的**输入**，不是大模型在实验中生成的**输出**：

```json
{
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
  ],
  "order": {"DeviceOrders.productL1": "asc"}
}
```

Cube 官方也明确区分了两种产品：

- Cube Core 是无前端的开源语义层，本身不提供 AI 问答。
- Cube Cloud 的 Analytics Chat 会使用 LLM，但它的完整系统提示词、上下文排序算法和最终模型请求没有公开。

因此，任何人如果声称下面展示的是“Cube Cloud 官方原始提示词”，都需要拿出可核验的公开源码或请求日志。我们目前没有这样的证据。

## Cube 真正能公开给智能体的是什么？

Cube Core 的 `/cubejs-api/v1/meta` 会返回当前身份可见的语义对象。为了避免只读配置文件后凭印象描述，我重新启动了本机 Cube 容器并实际调用了 `/meta`。与本问题相关的返回可以精简为：

```json
{
  "name": "DeviceOrders",
  "title": "设备订货事实",
  "description": "合成数据。每行是一张设备订货单；指标只统计 confirmed 状态。",
  "measures": [
    {
      "name": "DeviceOrders.deviceOrderAmount",
      "title": "设备订货事实 设备订货金额",
      "description": "已确认设备订货单的 order_amount 合计，演示单位 CNY.",
      "type": "number"
    },
    {
      "name": "DeviceOrders.deviceProfitAmount",
      "title": "设备订货事实 设备利润金额",
      "description": null,
      "type": "number"
    },
    {
      "name": "DeviceOrders.orderCount",
      "title": "设备订货事实 Order Count",
      "description": null,
      "type": "number"
    }
  ],
  "dimensions": [
    {"name": "DeviceOrders.orderId", "type": "string"},
    {"name": "DeviceOrders.orderDate", "type": "time"},
    {"name": "DeviceOrders.yearMonth", "type": "number"},
    {"name": "DeviceOrders.orgCode", "type": "string"},
    {
      "name": "DeviceOrders.productL1",
      "title": "设备订货事实 产品一级分类",
      "type": "string"
    },
    {"name": "DeviceOrders.status", "type": "string"}
  ]
}
```

这里有一个非常重要的设计：LLM 通常只需要知道正式成员 ID、标题、说明和类型。指标公式可以继续由 Cube 引擎保管。模型选择 `DeviceOrders.deviceOrderAmount` 后，Cube 会自动带上 `confirmed` 口径，不需要让 LLM 重写一次公式。

## 如果用自己的 LLM 接 Cube，拼装后的输入长什么样？

下面给出一份**可复现的参考拼装**。它使用了上面实际返回的 Meta 和真实问题，但这段系统指令是我们为了展示外部 Agent 怎样接 Cube 而写的，**不是 Cube Cloud 内部提示词**。

真实 LLM API 通常不会只有一个长字符串，而是由 `messages` 和一个限制输出形状的工具定义组成。为了方便人阅读，先展开成四块。

### 1. 系统指令

```text
你是企业数据分析查询规划器。

你的任务不是编写物理 SQL，而是从“可用语义对象”中选择成员，
生成 Cube REST Query。

规则：
1. measures、dimensions、timeDimensions 和 filters 只能使用上下文中出现的正式成员 ID。
2. 不得发明成员、指标公式、Join 或数据库字段。
3. 用户表达存在歧义时返回 clarification，不得猜测。
4. 必须保留用户明确给出的组织和时间范围。
5. 只输出 submit_cube_query 工具调用，不输出解释性文字。
```

### 2. 从 Meta 中筛出的语义上下文

```text
可用 Cube：DeviceOrders
标题：设备订货事实
说明：每行是一张设备订货单；指标只统计 confirmed 状态。

可用 Measures：
- DeviceOrders.deviceOrderAmount
  标题：设备订货金额
  说明：已确认设备订货单的 order_amount 合计，单位 CNY
- DeviceOrders.deviceProfitAmount
  标题：设备利润金额
- DeviceOrders.orderCount
  标题：订单数

可用 Dimensions：
- DeviceOrders.productL1，string，产品一级分类
- DeviceOrders.orderDate，time，订单日期
- DeviceOrders.yearMonth，number，年月
- DeviceOrders.orgCode，string，组织编码
- DeviceOrders.status，string，订单状态
```

### 3. 用户消息

```text
ORG_1001 在 2026 年上半年，按产品一级分类统计设备订货金额和利润。
```

### 4. 输出工具的参数约束

```json
{
  "name": "submit_cube_query",
  "parameters": {
    "type": "object",
    "properties": {
      "measures": {
        "type": "array",
        "items": {
          "enum": [
            "DeviceOrders.deviceOrderAmount",
            "DeviceOrders.deviceProfitAmount",
            "DeviceOrders.orderCount"
          ]
        }
      },
      "dimensions": {
        "type": "array",
        "items": {
          "enum": [
            "DeviceOrders.productL1",
            "DeviceOrders.yearMonth",
            "DeviceOrders.orgCode",
            "DeviceOrders.status"
          ]
        }
      },
      "timeDimensions": {"type": "array"},
      "filters": {"type": "array"},
      "order": {"type": "object"},
      "clarification": {"type": ["string", "null"]}
    },
    "required": [
      "measures",
      "dimensions",
      "timeDimensions",
      "filters",
      "clarification"
    ]
  }
}
```

工具约束中的 `enum` 很有价值：它把“不要编字段”从一句软性提醒，变成机器可以校验的封闭候选集合。真实系统还应当进一步约束过滤器结构、操作符、日期格式和成员类型；这里为了让提示词容易阅读做了精简。

## 希望 LLM 返回什么？

在本例中，LLM 应产生下面的工具参数：

```json
{
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
  ],
  "order": {"DeviceOrders.productL1": "asc"},
  "clarification": null
}
```

程序校验成员和类型后，去掉只供 Agent 使用的 `clarification` 字段，把其余对象提交给 Cube。Cube 再生成真实 SQL。

## 这份示例证明了什么，又没有证明什么？

它清楚展示了一个外部 LLM 怎样使用 Cube Meta 生成查询 DSL，也说明了最终上下文中不必包含物理表的全部字段和指标 SQL。

但它仍然只是我们根据公开接口构造的参考 Agent 输入，没有证明 Cube Cloud Analytics Chat 内部使用相同措辞、相同 JSON Schema 或相同检索顺序。要验证托管版原始请求，必须获得 Cube 官方公开源码、可观测日志或官方提供的 Prompt 调试界面。

## 可核对的文件和官方资料

- 本机 Cube 模型：[DeviceOrders.js](../../demos/route1/cube/model/DeviceOrders.js)
- 本机真实 Meta 响应：[meta_response.json](../../demos/route1/cube/results/meta_response.json)
- 本机真实查询对象：[query.json](../../demos/route1/cube/query.json)
- 本机真实编译结果：[sql_response.json](../../demos/route1/cube/results/sql_response.json)
- 本次洁净补充运行：[20260804-prompt-inspection](../../runs/20260804-prompt-inspection/README.md)
- [Cube Core 不包含 AI 功能](https://docs.cube.dev/docs/getting-started)
- [Cube View 是提供给用户和 AI 的精选语义界面](https://docs.cube.dev/docs/data-modeling/views)
- [Cube description 与 meta.ai_context 怎样供 AI 使用](https://docs.cube.dev/docs/data-modeling/ai-context)
- [Cube Agent、Space 和 accessible_views](https://docs.cube.dev/admin/ai/multi-agent)
