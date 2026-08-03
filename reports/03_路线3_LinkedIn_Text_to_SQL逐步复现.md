# 路线 3：LinkedIn 企业 Text-to-SQL 从知识图谱到纠错的逐步复现

## 边界先讲清楚

LinkedIn 公开了论文和工程文章，但没有公开生产系统源码、内部数据、embedding model、向量索引、prompt 或全部基础设施。因此本目录不是“运行 LinkedIn 官方仓库”，而是：

- 严格按其公开的组件和顺序重建；
- 把每个输入、中间对象、LLM 请求/响应、校验结果都落盘；
- 对未公开部分显式使用可解释替代，并标注差异；
- 不把合成数据上的通过率冒充 LinkedIn 生产指标。

公开系统的三大部分是：知识图谱、Query Writer Agent、交互式 chatbot。论文称知识图谱索引数据库元数据、查询日志、wiki 和代码，agent 进行检索/重排/写 SQL/自动修复；论文报告其内部系统超过 300 周用户，专家评审 53% 的回答正确或接近正确。[论文](https://arxiv.org/abs/2507.14372)

本实验重点复现前两部分，因为它们正对应“怎样构建语义知识”和“构建后怎样让智能体使用”。

---

## 一、LinkedIn 公开方法到底怎样构建知识

根据论文和工程文章，生产知识来源至少包括：

1. **DataHub 元数据**：表、字段、说明、分区键、top-K 类别值、metric/dimension/attribute 分类、认证和废弃状态。
2. **查询日志**：表/字段访问频率、常见 join、成功 SQL。
3. **wiki 与 notebook/code**：经过认证或满足新鲜度/可靠性启发式的示例查询。
4. **用户贡献的 domain knowledge**：业务规则和自定义 instruction。
5. **内部 jargon**：把公司黑话解释成可检索、可用于重排的含义。
6. **用户—数据集访问矩阵**：用 Independent Component Analysis 推断业务用例簇，再按用户和产品域缩小候选表。

工程文章给出了一个很关键的尺度：先用 filtering/embedding retrieval 从数百万表缩到候选，取前 20 张；再用 LLM reranker 选前 7 张；之后才把完整 schema 交给字段 reranker 和 Query Writer。[LinkedIn 工程文章](https://www.linkedin.com/blog/engineering/ai/practical-text-to-sql-for-data-analytics)

这意味着它不是：

```text
用户问题 + 全库 schema → 一个超长 prompt → SQL
```

而是：

```text
个性化候选空间 → 多索引召回 → 表重排 → 取完整 schema → 字段重排 → 写 SQL
```

---

## 二、本次重建的输入

代码在 [`demos/route3/linkedin_text2sql`](../demos/route3/linkedin_text2sql)。

### 1. 用户请求

[`input/request.json`](../demos/route3/linkedin_text2sql/input/request.json) 包含 user identity / product areas、中文问题、DuckDB dialect 和输出期望。问题中没有出现 `device_orders`，因此系统必须先理解“设备订货”。

### 2. 表与字段元数据

公共 catalog 包含 4 个候选表：

| 表 | 状态 | 作用 |
|---|---|---|
| `device_orders` | certified、popular、未废弃 | 权威设备订货事实表 |
| `deprecated_device_orders` | 未认证、低热度、deprecated | 名称很像，但不得用于新查询 |
| `product_master` | certified | 产品主数据，可能用于 product_l1 |
| `sales_orders` | certified、popular | “销售订单”，业务概念相近但口径不同 |

### 3. 访问矩阵与产品域

[`user_table_access.csv`](../demos/route3/linkedin_text2sql/input/user_table_access.csv) 表示用户近一段时间访问各表的次数；[`product_areas.json`](../demos/route3/linkedin_text2sql/input/product_areas.json) 将当前请求绑定到 `device_business` 域。

这两类输入共同限制“这个用户在这个业务域里通常用哪些表”。它们不是最终答案，但可以把全局候选压缩到更小的局部空间。

### 4. Domain knowledge 与 jargon

[`domain_knowledge.jsonl`](../demos/route3/linkedin_text2sql/input/domain_knowledge.jsonl) 明确：

```text
设备订货金额仅统计 status='confirmed' 的 order_amount；
设备利润使用同一批订单的 profit_amount；
必须显式限定 org_code；金额单位 CNY。
```

[`jargon.json`](../demos/route3/linkedin_text2sql/input/jargon.json) 明确：

```text
设备订货 != sales_orders 中的销售收入
上半年 = year_month BETWEEN YYYY01 AND YYYY06
```

### 5. 已批准示例 SQL

[`example_descriptions.json`](../demos/route3/linkedin_text2sql/input/example_descriptions.json) 为历史 SQL 提供自然语言描述、使用者和涉及表。它们被建成单独索引，不与表描述混为一谈。

---

## 三、知识图谱构建时生成了什么

执行 [`build_knowledge_graph.py`](../demos/route3/linkedin_text2sql/build_knowledge_graph.py)，实际使用 scikit-learn FastICA 构建软聚类。

论文生产参数是 200 个 ICA components、每簇保留 20 张表；本 demo 只有 4 张表，因此缩放为 3 个 components、每簇 3 张表。缩放边界已写入构建结果，未冒充生产配置。

最终生成：

```json
{
  "node_count": 37,
  "edge_count": 25,
  "table_index_count": 4,
  "approved_example_count": 3,
  "candidate_tables_for_request": [
    "deprecated_device_orders",
    "device_orders",
    "product_master",
    "sales_orders"
  ]
}
```

主要节点包括 users、product areas、ICA table clusters、tables、columns、example queries、domain knowledge 和 jargon。主要边包括 user→cluster、product area→cluster、cluster→table、table→column、example query→table、domain knowledge→table/column。

中间产物全部可读：

- [`nodes.json`](../demos/route3/linkedin_text2sql/results/knowledge_graph/nodes.json)
- [`edges.json`](../demos/route3/linkedin_text2sql/results/knowledge_graph/edges.json)
- [`clustering.json`](../demos/route3/linkedin_text2sql/results/knowledge_graph/clustering.json)
- [`table_index.json`](../demos/route3/linkedin_text2sql/results/knowledge_graph/table_index.json)
- [`example_query_index.json`](../demos/route3/linkedin_text2sql/results/knowledge_graph/example_query_index.json)
- [`domain_knowledge_index.json`](../demos/route3/linkedin_text2sql/results/knowledge_graph/domain_knowledge_index.json)
- [`jargon_index.json`](../demos/route3/linkedin_text2sql/results/knowledge_graph/jargon_index.json)

### 未公开 embedding 的替代

LinkedIn 没有发布其 embedding model/index。本次使用确定性的中文字符 TF-IDF 2–4 gram 计算 cosine similarity。它能真实运行并展现“检索对象与分数”，但不代表 LinkedIn 生产语义召回质量。这一说明同时写进 retrieval trace。

---

## 四、一次问题进入 Agent 后，每一步具体发生什么

完整实现是 [`run_agent.py`](../demos/route3/linkedin_text2sql/run_agent.py)。

### 第 1 步：个性化候选 + 多索引召回

系统先用用户/产品域簇得到 4 张候选，再分别查表索引、示例 SQL、domain knowledge、jargon。

表 embedding 排名：

| 排名 | 表 | similarity | popularity | certified | deprecated |
|---:|---|---:|---:|---|---|
| 1 | `device_orders` | 0.095744 | 98 | 是 | 否 |
| 2 | `product_master` | 0.044331 | 76 | 是 | 否 |
| 3 | `sales_orders` | 0.036606 | 91 | 是 | 否 |
| 4 | `deprecated_device_orders` | 0.030177 | 12 | 否 | 是 |

召回两条最相关的 approved examples：

1. 按一级产品统计指定组织、月份区间、confirmed 设备订货金额。
2. 按月统计指定组织的 confirmed 设备订货金额和利润。

还命中两个 domain knowledge 和四个 jargon。完整结果在 [`01_retrieval_trace.json`](../demos/route3/linkedin_text2sql/results/agent/01_retrieval_trace.json)。

### 第 2 步：第一次 LLM 调用——表重排

送给表重排模型的不是完整 schema，而是 question、候选表名称和说明、similarity/popularity/certified/deprecated、相关 example descriptions、domain knowledge 与 jargon。

模型返回 1–10 分和解释。代码再加入确定性的治理加减分：认证加分、popular 轻量加分、deprecated 减 100。

真实最终排名：

| 表 | LLM 分 | 最终分 | 解释摘要 |
|---|---:|---:|---|
| `device_orders` | 10 | 11.48 | 权威设备订货表，包含全部所需概念 |
| `product_master` | 8 | 9.26 | 可能用于一级分类，但不是事实金额来源 |
| `sales_orders` | 2 | 3.41 | 销售额不是设备订货金额 |
| `deprecated_device_orders` | 1 | -98.88 | 已废弃，不得用于新查询 |

这里展示了结构化治理信号的作用：即使一个旧表名称很接近，也会被确定性规则压到底部，而不是只相信 LLM 的主观分数。

### 第 3 步：取完整 schema

只有完成表重排后，才对前三张未废弃表读取完整物理 schema。这是控制 token 与噪声的关键步骤。

### 第 4 步：第二次 LLM 调用——两级字段筛选

字段被分成 `relevant`（直接写 SQL 所需）和 `potentially_relevant`（保留用于消歧、连接、修复的第二级）。`device_orders` 的结果：

```json
{
  "relevant": [
    "org_code", "year_month", "status", "product_l1",
    "order_amount", "profit_amount"
  ],
  "potentially_relevant": [
    "order_date", "product_code", "country", "order_id"
  ]
}
```

代码还执行一条确定性 recall guard：六个业务必需字段若被模型漏掉，就加入第二级，而不是让下游直接失去关键过滤列。

### 第 5 步：拼装 Query Writer 上下文

[`04_query_writer_context.json`](../demos/route3/linkedin_text2sql/results/agent/04_query_writer_context.json) 是真正交给 SQL Writer 的上下文，包含：

```text
question
dialect
排过序的 3 张表及精选字段
2 条 approved historical SQL
2 条 domain knowledge
4 个 jargon 解释
glossary 指标定义与 required_filters
```

知识图谱本身不直接“回答”；它先被检索、筛选、排序和压缩，才成为模型上下文。

### 第 6 步：第三次 LLM 调用——Query Writer

真实模型输出的假设：`device_orders.product_l1` 已是权威一级分类，无需多余 join；H1 为 202601–202606；只统计 confirmed；单位 CNY。

生成 SQL：

```sql
SELECT
  product_l1,
  SUM(order_amount) AS device_order_amount,
  SUM(profit_amount) AS device_profit_amount
FROM device_orders
WHERE org_code = 'ORG_1001'
  AND year_month BETWEEN 202601 AND 202606
  AND status = 'confirmed'
GROUP BY product_l1
```

它没有把 `product_master` 连进来，因为基础事实表已含 `product_l1`。这既减少复杂度，也避免不必要 join。

### 第 7 步：验证，不直接执行

验证器依次检查：

1. sqlglot 能否按 DuckDB dialect 解析。
2. 是否为单个只读 `SELECT`，禁止 insert/update/delete/create/drop/alter。
3. 表是否真实存在。
4. 表是否在已选择上下文内。
5. 列是否真实存在。
6. 是否包含显式 `org_code=ORG_1001`。
7. 是否包含 `status=confirmed`。
8. 是否包含 202601、202606 和 `year_month`。
9. DuckDB `EXPLAIN` 是否通过。

主 SQL 第一次就全部通过，所以没有浪费额外修复调用。

### 第 8 步：执行与结果验证

DuckDB 执行后得到：

| product_l1 | device_order_amount | device_profit_amount |
|---|---:|---:|
| Compute | 7500 | 1560 |
| IoT | 3400 | 650 |
| Network | 3800 | 730 |

结果按业务键排序后与 [`golden CSV`](../demos/common/expected/org1001_h1_by_product.csv) 完全一致。原始模型 SQL 没有 `ORDER BY`，第一次 verifier 错把行顺序差异当成业务错误；修正为集合语义比较后重新完整调用模型，结果仍通过。这个问题记录在失败报告中。

---

## 五、如何证明自动纠错真的可工作

如果主模型恰好一次生成正确 SQL，纠错分支不会运行。为了可验证，实验独立注入：

```sql
FROM device_order_fact
```

这个表不存在。验证器返回：

```text
unknown tables: ['device_order_fact']
tables outside selected context: ['device_order_fact']
unknown columns: [order_amount, org_code, product_l1,
                  profit_amount, status, year_month]
```

### 第 4 次 LLM：Researcher

输入包括坏 SQL、精确 validation errors、table index、已取 schema 和 domain knowledge。真实输出：

```json
{
  "replacement_table": "device_orders",
  "evidence": "certified=true, deprecated=false，且包含全部所需字段"
}
```

### 第 5 次 LLM：Fixer

Fixer 将 `device_order_fact` 替换为 `device_orders`，同时保留组织、月份、confirmed 过滤与分组。修复 SQL再次通过所有验证。

完整轨迹在 [`06_controlled_correction_trace.json`](../demos/route3/linkedin_text2sql/results/agent/06_controlled_correction_trace.json)。

---

## 六、LLM 到底调用了几次，记录了什么

最终：

```json
{
  "configured": true,
  "model": "glm-5.2",
  "calls": 5,
  "successful_calls": 5,
  "fallback_calls": 0,
  "api_key_logged": false
}
```

五次分别是 `02_table_ranker`、`03_column_ranker`、`05_query_writer`、`08_controlled_researcher`、`09_controlled_query_fixer`。

每次的 system prompt、输入 JSON、模型原始响应、解析后结果和 token usage 在 [`llm_calls/`](../demos/route3/linkedin_text2sql/results/agent/llm_calls)。文件只记录模型名，不记录 key 或 base URL。

---

## 七、LinkedIn 公开的效果数字应该怎样理解

论文报告的生产评估包括：table recall 78%、column recall 56%、LLM judge 4 分以上 48%、SQL compile 96%、table/column identifier valid 99%、平均 4.6 次 LLM calls、专家评审 correct/close 53%、helpful 77%，主要错误中 filter 问题 24%、join 错误 4%，超过 300 weekly users。

工程文章还指出：只给 schema 的消融结果显著差；加入 reranker、说明和示例查询改善表召回；独立 app 集成到日常数据平台后采用率提升 5–10 倍；“Fix with AI”占 80% sessions。[工程文章](https://www.linkedin.com/blog/engineering/ai/practical-text-to-sql-for-data-analytics)

这些数字最值得借鉴的不是某个绝对准确率，而是：

- 企业 Text-to-SQL 的主要难点是选择权威上下文与过滤口径，不只是 SQL grammar。
- 只看 compile rate 会高估质量；必须单独衡量 table、column、join、filter、aggregation。
- 一个问题可能有多个正确 SQL，golden set 也必须演化。
- 用户界面让人看见候选表、认证、解释和 validation checks，会影响实际采用。

---

## 八、对现有“无业务行数据”资产的直接对应

你拥有 BI SQL、BI 中间模型、物理 schema/表头和备注，但没有业务行数据。LinkedIn 路线说明这些资产仍足够先做大量工作：

| 现有资产 | 可构造的知识 |
|---|---|
| 物理表/字段/备注 | table/column nodes、描述索引、类型、约束 |
| BI SQL | example query、表/字段使用、join、filter、aggregation、别名 |
| BI 中间组件 | dashboard/chart/data model nodes 与 lineage |
| 中文注释 | jargon/term/domain-knowledge 候选，但要保留来源和置信度 |
| 日志中的用户/组织 | 使用矩阵、产品域/团队个性化候选，需隐私治理 |
| 无行数据 | 仍可做静态解析、候选召回、identifier 验证、dialect parse；不能验证数值真值和数据分布 |

因此，第一阶段不是手工建设一个无穷大 ontology，而是自动产生“可追溯候选”：表/字段事实、SQL 结构事实、口径候选、同义词候选、使用与血缘关系；再让有限的人力集中审定高价值指标和冲突。

## 最终证据

- [`07_final_response.json`](../demos/route3/linkedin_text2sql/results/agent/07_final_response.json)：问题、SQL、三行答案、LLM 统计。
- [`verification.json`](../demos/route3/linkedin_text2sql/results/verification.json)：11 项检查全部通过。
- [`72b clean-run log`](../runs/20260804-clean-verification/steps/72b-linkedin-agent-real-llm/stdout.txt)：洁净复跑的原始输出。
- 公开依据：[论文](https://arxiv.org/abs/2507.14372)、[LinkedIn 工程文章](https://www.linkedin.com/blog/engineering/ai/practical-text-to-sql-for-data-analytics)。

