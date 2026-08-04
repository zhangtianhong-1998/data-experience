# 知识图谱不是一段 Prompt：2026 Data Agent 上下文工程调研

> 调研与核验日期：2026-08-04。重点使用 2026 年企业公开资料和论文；LinkedIn 2024/2025 的资料只作为路线三的原始依据。产品文档、技术文章、论文和会议分享的证据强度不同，文中分别标明，不把未公开实现猜成事实。

## 先用三分钟读懂结论

你的直觉是对的：LinkedIn 说自己构建了知识图谱，但论文没有把“某个问题到底怎样在图上走、最后哪一段图进入模型”讲透。

把公开资料、本机复现结果和 2026 年的新工作合在一起，答案是：

1. **知识图谱可以改善 Data Agent，但通常不应该把整张图转成三元组后塞进 Prompt。** 图最有价值的地方，是在模型调用前找到候选对象、补全一两跳关系、执行权限和废弃过滤；真正进入模型的，应该是十几条短小、带类型、能绑定到表或字段的“证据卡片”。
2. **图、向量检索和语义层不是三选一。** 向量检索负责找到“可能相关”的种子；图负责回答“它连接什么、依赖什么、能否一起使用”；指标语义层负责确定性地把已确认的指标、维度和关系编译成 SQL；LLM 负责消歧、规划和解释。
3. **多处召回不是重复劳动。** 表召回、字段召回、示例召回、业务规则召回和出错后的补充召回，面对的对象和错误风险都不相同。一次“大而全”的召回既浪费 token，也会把不该出现的规则和表带进后续步骤。
4. **2026 年的方向是上下文整理和压缩，而不是一味增加上下文。** 阿里 EntSQL 的实验中，给完整企业长文时最好执行准确率为 15.9%，给精炼证据时为 21.4%；DbCC 将最大的数据库上下文从 260 万 token 压到 3.47 万，同时提升 schema linking 和最终执行准确率。这说明“知识很多”不等于“模型能用好”。
5. **你没有业务行数据，并不妨碍先做高价值知识工程。** BI SQL、看板中间模型、物理 schema、中文注释和查询日志，足以抽取表/字段使用、join、指标表达、过滤口径、粒度、血缘、别名、同义词和权威度。缺少行数据主要影响枚举值匹配、数据分布判断和结果真值验证，不会让整个方向失效。

一句话概括最合理的运行形态：

```text
问题
  → 向量/关键词找到种子对象
  → 知识图谱扩展一两跳关系
  → 权限、废弃、置信度和时效规则过滤
  → 重排并压缩成证据卡片
  → LLM 解析意图或生成计划
  → 语义引擎/SQL Agent 执行
  → 校验失败时定向补取知识
```

---

## 一、先分清“上下文”到底是什么

很多分享把所有东西都叫上下文，读起来就会觉得混乱。对 Data Agent 而言，至少有五种不同的上下文：

| 上下文 | 例子 | 怎样进入模型 | 是否应长期保留 |
|---|---|---|---|
| 静态指令 | 只读 SQL、目标方言、输出 JSON 格式 | system/developer prompt | 可以，但应短小稳定 |
| 本次检索证据 | 指标定义、候选表、字段、join 路径、业务规则 | 检索后拼成当前调用的输入 | 只保留本问题相关部分 |
| 工具返回 | `get_schema`、`search_metric`、`EXPLAIN`、查询结果 | tool/MCP call 的 output 回到模型 | 由本轮任务需要决定 |
| 会话与记忆 | 用户纠正“活跃用户要排除测试账号” | conversation state 或记忆检索 | 要区分个人、团队、全局范围 |
| 模型外控制状态 | ACL、废弃表过滤、SQL 白名单、指标编译图 | 由程序或语义引擎直接消费 | 不应只靠 Prompt 约束 |

这里最容易犯的错误，是把“存在知识库里”误认为“已经进入模型”，或者把“通过 MCP 可查询”误认为“模型每次都看到了”。实际情况是：只有被检索、被工具返回、并被放进当前请求的那部分内容，才是本次推理的上下文。

### MCP 和 SDK 在这里是什么角色

MCP 不是知识库，也不是知识图谱；它是让模型调用外部能力的一种通道。以 OpenAI Responses API 的官方流程为例：

1. API 先产生 `mcp_list_tools`，把可用工具的名称、说明和参数结构告诉模型。
2. 模型决定调用哪个工具，产生 `mcp_call.arguments`。
3. MCP server 返回 `mcp_call.output`。
4. **这个 output 才会进入模型上下文，供后续回答使用。**

因此，你可以用 MCP 暴露以下工具：

```text
resolve_business_term(question)
search_semantic_objects(query, object_types, top_k)
expand_graph(seed_ids, edge_types, max_hops)
get_metric_definition(metric_id)
get_join_paths(dataset_ids)
validate_sql(sql)
```

但工具不应该返回整张图。一个合理的返回大致是：

```json
{
  "seed": "metric:device_order_amount",
  "facts": [
    {
      "type": "metric_definition",
      "expression": "SUM(device_orders.order_amount)",
      "required_filters": ["device_orders.status = 'confirmed'"],
      "source": "bi_sql:dashboard_817",
      "confidence": 0.96
    }
  ],
  "join_paths": [],
  "warnings": ["deprecated_device_orders 已废弃"]
}
```

OpenAI 官方文档还提供 `allowed_tools` 限制本次可见工具，避免把几十个工具定义全放进上下文；`file_search` 则负责对文件知识库做语义加关键词检索，并可限制 `max_num_results`、按 metadata 过滤。它们解决的是“如何接入和取回”，不是“企业语义知识怎样建模”。

依据：[OpenAI MCP 与 Connectors 文档](https://developers.openai.com/api/docs/guides/tools-connectors-mcp)、[OpenAI File Search 文档](https://developers.openai.com/api/docs/guides/tools-file-search)。

---

## 二、LinkedIn 路线三的知识图谱到底怎样被使用

### 2.1 它不是一张图直接交给一个模型

LinkedIn 的图包含用户、表簇、表和字段节点；节点属性来自 DataHub、查询日志、用户贡献的业务知识、wiki/notebook 示例等。公开文章还明确了以下规模变化：

```text
数百万张表
  → 根据热度、组织和用户访问习惯缩到几千张
  → embedding retrieval 取前 20 张
  → LLM reranker 选前 7 张
  → 才读取完整 schema 并做字段筛选
```

所以，“图的使用”至少拆成了六种动作：

| 阶段 | 查询什么 | 返回什么 | 谁使用 | 是否原样进入 LLM |
|---|---|---|---|---|
| 1. 个性化候选 | `user → table_cluster → table`、组织/产品域、表热度 | 几千张当前用户更可能使用的表 ID | 检索系统 | 否，只用于缩小搜索空间 |
| 2. 表语义召回 | 问题对表描述索引做 embedding search | Top 20 表及相似度 | 表重排器 | 表的短描述和治理属性进入 |
| 3. 附着证据召回 | `example → table`、`knowledge → table/column`、jargon 索引 | 示例 SQL、业务规则、黑话解释 | 表重排器 | 只进入与候选表有关的少量证据 |
| 4. 字段扩展 | `table → field`，再读取 DataHub 属性 | Top 7 表的完整 schema、字段说明、top-K 值、类型与热度 | 字段重排器 | 是，但只对已选表展开 |
| 5. 写 SQL | 已选表字段 + 示例 + 规则 + 前序计划状态 | 一个小型任务上下文 | Query Writer | 是 |
| 6. 纠错补取 | 坏 SQL、校验错误，再查表/字段工具 | 缺失或正确的表字段 | Researcher/Fixer | 错误和补充证据进入修复调用 |

这也解释了你看到的“多处进行不同方式的内容召回”：

- 第一次要解决“几百万张表里可能是哪几张”，追求高召回。
- 第二次要解决“这些候选表中哪张权威”，需要认证、废弃、说明和业务黑话。
- 第三次要解决“选中的表里哪些列能实现问题”，需要完整 schema 和字段属性。
- 示例 SQL 解决的是“公司过去通常怎样写这个模式”，不是替代表检索。
- 业务规则解决的是“过滤、时间、统计口径怎样落到 SQL”，不是替代字段检索。
- 出错后召回使用精确错误作为新查询，比第一次盲目扩大上下文更有效。

因此，多索引不是把同一份内容存五次，而是为不同对象建立不同的检索入口。

依据：[LinkedIn 工程文章](https://www.linkedin.com/blog/engineering/ai/practical-text-to-sql-for-data-analytics)、[LinkedIn 论文](https://arxiv.org/abs/2507.14372)。

### 2.2 用本机复现的问题把整条链走一遍

本机问题是：

> 请统计 ORG_1001 在 2026 年上半年按产品一级分类的设备订货金额和设备利润，只统计已确认订单。

图中并不存在一段已经写好的完整答案，而是存在一些互相连接的对象：

```text
analyst_a
  → device_business 表簇
    → device_orders
      → year_month / org_code / product_l1 / order_amount / profit_amount / status

“设备订货金额”
  → SUM(device_orders.order_amount)
  → 必须使用 status='confirmed'

批准示例 SQL
  → 使用 device_orders
  → 包含 org_code、year_month、status 和 product_l1
```

#### 第一次：图和索引只负责找候选

用户/产品域关系先将候选限制为 4 张表。随后表索引、示例索引、domain knowledge 和 jargon 索引分别召回：

- `device_orders`、`product_master`、`sales_orders`、`deprecated_device_orders`；
- 两条 approved SQL；
- 两条统计口径；
- 四个问题中出现的企业术语解释。

完整可见结果在 [`01_retrieval_trace.json`](../demos/route3/linkedin_text2sql/results/agent/01_retrieval_trace.json)。

#### 第二次：表重排模型看到的内容

表重排模型没有看到全部字段，只看到这种小对象：

```json
{
  "question": "请统计 ORG_1001 ... 设备订货金额和设备利润 ...",
  "tables_without_full_schema": [
    {
      "table": "device_orders",
      "description": "设备订货事实表。取消单不得计入订货指标。",
      "semantic_score": 0.095744,
      "popularity": 98,
      "certified": true,
      "deprecated": false,
      "example_descriptions": ["按产品一级分类统计指定组织...的已确认设备订货金额"]
    }
  ],
  "domain_knowledge": ["设备订货金额只统计 confirmed ..."],
  "jargon": {"设备订货": "不是 sales_orders 中的销售收入"}
}
```

模型返回表分数和解释；程序再确定性地给 certified 加分、给 deprecated 减 100。也就是说，**废弃规则不只是一句话让模型“自觉遵守”，程序本身也执行它。**

#### 第三次：只有选表后才取字段

选表后读取物理 schema，字段重排器返回：

```json
{
  "device_orders": {
    "relevant": [
      "org_code", "year_month", "status", "product_l1",
      "order_amount", "profit_amount"
    ],
    "potentially_relevant": [
      "order_date", "product_code", "country", "order_id"
    ]
  }
}
```

第二级字段保留了 join 和修复可能需要的列，避免一次过度剪枝导致关键列永远丢失。

#### 第四次：真正交给 SQL Writer 的上下文

真正的 Writer 输入在 [`04_query_writer_context.json`](../demos/route3/linkedin_text2sql/results/agent/04_query_writer_context.json)。它由以下内容组成：

```text
问题和 SQL 方言
+ 排序后的 3 张表及精选字段
+ 2 条已批准示例 SQL
+ 2 条业务口径
+ 4 个企业术语解释
+ 指标表达式、required_filters、单位和 owner
```

图的原始 37 个节点和 25 条边没有原样出现。图已经完成了定位、扩展和证据附着，Writer 看到的是压缩后的结果。

Writer 生成：

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

#### 第五次：校验失败才重新查图和 schema

本机实验又故意把表改成不存在的 `device_order_fact`。校验器先返回精确错误，Researcher 再根据错误搜索索引，找到 certified 且包含所需字段的 `device_orders`，Fixer 才修 SQL。轨迹在 [`06_controlled_correction_trace.json`](../demos/route3/linkedin_text2sql/results/agent/06_controlled_correction_trace.json)。

这就是 LinkedIn 所谓“知识图谱 + 多处召回”的可执行解释：**图负责在每个决策点提供不同的局部证据，而不是在开头一次性把所有知识交给模型。**

---

## 三、2026 年企业公开实践怎样搭建上下文

为了可比较，下面每家公司都回答四个问题：知识怎么建、运行时怎么取、什么真正进入模型、什么留在模型外。没有公开的部分会直接写“未公开”。

### 3.1 OpenAI：六层上下文，离线归一化，运行时只取相关部分

**资料级别：2026-01-29 官方工程文章，披露内部 Data Agent 的生产架构。**

OpenAI 内部平台覆盖 3,500 多名用户、70,000 个数据集和 600 PB 以上数据。它的六层上下文是：

1. schema、上下游血缘、历史查询模式和常见 join；
2. 专家维护的表/字段说明、含义与注意事项；
3. Codex 从生产代码推导的粒度、唯一键、刷新频率、范围、排除项和非 SQL 用法；
4. Slack、Google Docs、Notion 中的发布、事故、内部代号、指标定义和计算逻辑；
5. 从用户纠正中保存的个人或全局记忆，例如不明显的过滤条件；
6. 运行时向数据仓库、元数据服务、Airflow、Spark 查询得到的最新事实。

它怎样构建：每天离线把表使用情况、人工注释和代码增强结果合并为统一、归一化的表示，生成 embedding 并存储。组织文档也会被采集、嵌入，并保留 metadata 和权限。

它怎样使用：问题到来后，只通过 RAG 取相关的 enriched context，不扫描全部元数据和日志；如果信息缺失或过期，再实时调用数仓和数据平台工具。中间结果异常时，Agent 保留前序状态、调整查询并重试。

血缘本质上是一张关系图，但文章没有说“把完整血缘图塞进模型”。更合理的解读是：血缘用于解释表的来源、展开相关上下游，检索服务再返回当前问题需要的局部说明。这个解读是基于公开架构的推论，不是 OpenAI 对内部数据结构的命名。

对你的最大启示是：**生成表的代码比表名和 schema 更接近真实含义。** 你目前有 BI SQL 和 BI 中间组件，这些正好可以承担 OpenAI 所说的“代码级定义”角色。

依据：[OpenAI 内部数据智能体](https://openai.com/zh-Hans-CN/index/inside-our-in-house-data-agent/)。

### 3.2 阿里巴巴：历史 SQL 自动沉淀知识，用户也可以显式 `@` 上下文

**资料级别：2026 年阿里云产品文档 + 阿里/Qwen 团队 2026 年 EntSQL 论文。产品文档没有公开内部 Prompt 和排序算法。**

DMS/Meta Agent 公开了三类知识生产方式：

- 从历史 SQL 提取模板，转成自然语言问题，保存成“问题 ↔ 完整 SQL”记录；
- 从 SQL 执行历史和表结构生成片段知识；
- 用户手工录入、点赞或修改生成结果；新知识先进入 pending review，再由数据库开发者、表 owner 等验证。

Meta Agent 明确区分两种知识：

```text
SQL 记录：自然语言问题 ↔ 完整 SQL
片段知识：术语、字段含义、业务规则 ↔ 数据库对象
```

运行时，相似问题可以参考 SQL 记录，NL2SQL 生成时引用业务知识，并向用户显示使用了哪些知识。这与 LinkedIn 的“示例索引 + domain knowledge 索引”非常接近，只是产品形态不同。

DataWorks Code Assistant 还允许用户在对话里主动输入 `@`，选择：

- Table metadata；
- Node/Code file；
- Data Collection；
- Rules；
- Local file。

这是一种显式上下文控制：检索系统不确定时，用户可以直接告诉 Agent 本次该看哪张表、哪个代码节点、哪些规则。

阿里云 2026 年 AI-Native Database Service 文档则把向量、知识图谱和关系型架构统一为知识服务，并用 Agent Data Gateway 在数据库、表、列、行层面执行权限、安全规则、脱敏和审计。但公开文档只说明能力边界，没有公布“某问题在图上走几跳、最终 Prompt 长什么样”，因此不能把产品架构图当成已公开算法。

最重要的反面证据来自 EntSQL。1,066 个中英双语企业问题中，96% 需要 schema 以外的企业知识。实验结果：

| 输入 | 最好执行准确率 |
|---|---:|
| 问题 + schema | 6.8% |
| 问题 + schema + 完整长文档 | 15.9% |
| 问题 + schema + 专家精炼证据 | 21.4% |

在 212 个样本的专家实验中，专家使用精炼证据从 33.5% 提升到 84.0%；这说明证据本身很有用，但当前 Agent 把规则稳定翻译成复杂 SQL 的能力仍然有限。失败中 `WRONG_FILTER` 占 54.6%，`WRONG_SCOPE` 占 14.4%。

因此，阿里的最新证据不是“长上下文解决一切”，而是：**必须先把长企业知识定位成与本题有关的过滤、范围、指标和对象映射，再让 Agent 使用。**

依据：[DMS 知识库](https://www.alibabacloud.com/help/en/dms/knowledge-base-management)、[Meta Agent 知识管理](https://www.alibabacloud.com/help/zh/aidbs/latest/meta-agent-knowledge-management)、[DataWorks Code Assistant](https://www.alibabacloud.com/help/en/dataworks/user-guide/data-agent-coding-assistant)、[AI-Native Database Service](https://www.alibabacloud.com/help/en/aidbs/latest/what-is-ai-native-database-service)、[EntSQL](https://arxiv.org/abs/2606.03363)。

### 3.3 美团：图更多由语义引擎消费，而不是全交给 LLM

**资料级别：2026-03-20 美团技术团队文章。文章详细披露指标平台和查询编译，但没有公开自然语言助手的 Prompt。**

美团的做法能纠正一个常见误区：知识图谱不是只有“RAG 后放进 Prompt”这一种使用方式。

它先把业务语言定义的指标转成结构化逻辑表达，再利用主外键关系把数仓模型关联成星型、雪花和星座模型。复杂指标形成依赖树，系统预计算模型关联和指标扩展结果；查询时根据指标、维度、数据范围、引擎、分区、强制维度等规则做路由选表。

用户或上层 Agent 最终表达的是一个 DSL，其中包含：

- 查询人、业务线、场景和语言；
- 可用的公共/私有资产范围；
- 指标、维度、过滤、排序和截断；
- 同环比、占比、合计、TopN 等分析方法。

语义服务再把它变成指标/维度 AST 和执行拓扑，经过剪枝、分组和优化，生成物理 SQL。其三层结构是：

```text
数据源层：表、视图或复杂 SQL
  → 模型层：字段映射到原子指标和维度
    → 逻辑层：递归构建复合指标
```

对 Data Agent 而言，最可靠的集成方式不是让 LLM 自己重走这张复杂关系图，而是：

```text
LLM 识别“哪个指标、哪个维度、哪个时间范围”
  → 生成受约束 DSL
  → 美团式语义引擎确定性遍历指标和模型关系
  → 编译 SQL
```

这是根据美团已公开的语义平台和其自然语言助手结合方式作出的工程推论；美团没有公开助手内部的实际 Prompt。文章明确指出，相比传统 Text-to-SQL，指标平台可复用已沉淀的指标/维度业务与技术信息来减少二义性，并复用原有鉴权体系。

依据：[美团 BI 在指标平台和分析引擎上的探索和实践](https://tech.meituan.com/2026/03/20/Busniness-Intelligence-practice-in-meituan.html)。

### 3.4 蚂蚁：不是每个高准确率方案都需要企业知识图谱

**资料级别：2025 年底修订的 Agentar-Scale-SQL 论文和开源仓库；2026 年 FineStep 论文。**

Agentar-Scale-SQL 是一个很有价值的对照组：它没有建设你所说的指标、术语、口径企业图谱，而是把上下文拆成几种检索对象，然后用多候选生成、执行修复和选择提高准确率。

离线构建：

- schema 同时准备轻量 Markdown 和标准 DDL 两种表示；
- 文本型单元格值进入 `VD_cell` 向量库；
- 历史训练问题和 SQL 进入 `VD_example` 向量库。

运行时：

1. Task Understanding 从问题和 evidence 中抽取 `database_literals` 与 `question_skeleton`；
2. literals 检索真实单元格值，skeleton 检索相似 few-shot examples；
3. Reasoning Generator 收到 DDL、matched contents、问题和 evidence；
4. ICL Generator 收到轻量 schema、相似 examples、问题和 evidence；
5. 生成多个 SQL，执行并修复；
6. Selector 收到 schema、matched contents、evidence、问题、候选 SQL 及执行结果，选择最终答案。

论文附录公开的 Writer 输入骨架非常直白：

```text
Database Engine
Database Schema
Matched contents（值 + 来源表字段）
Evidence
Question
```

这个方案证明“多个专用索引 + 分阶段生成和验证”本身就能工作，但对你的场景有两点限制：

- 它高度依赖真实单元格值，而你当前没有业务行数据；
- 它没有解决企业内部指标定义、同义词冲突、口径版本和权限治理。

2026 年蚂蚁 FineStep 又把重点推进到“工具调用路径是否有效”：把 Text-to-SQL 看成连续决策与工具执行交织的过程，对每一步分配 reward，减少重复工具交互。它提醒我们，评估 Agent 不能只看最终 SQL，还要看为了得到它调用了多少次检索、schema、执行和修复工具。

依据：[Agentar-Scale-SQL 论文](https://arxiv.org/abs/2509.24403)、[官方仓库](https://github.com/antgroup/Agentar-Scale-SQL)、[FineStep](https://arxiv.org/abs/2605.04719)。

### 3.5 京东：先召回术语和历史案例，再根据初步判断召回关系知识

**资料级别：2026 年 KDD 论文。SHERLOCK 是电商风控 Agent，不是 Text-to-SQL；这里把它作为“异构企业知识怎样进入 Agent 上下文”的工业案例。**

SHERLOCK 从三类源构建知识：

- 120 万 token 的业务 SOP 和历史调查报告；
- 特征计算代码和风险策略，解析条件逻辑，并把 `ord_cnt_1w` 之类符号映射为自然语言；
- 专家会议纪要和评审备注，先过滤行政和无关对话。

LLM 先抽取候选，再由 15 名资深专家审定，形成四类 JSON 知识：

1. 企业术语；
2. 历史案例：案例描述、最终判断、专家理由；
3. 风险关联：多个风险因素怎样组合，既从文档抽，也从代码中的 AND 逻辑抽；
4. 业务先验：看似异常但实际合理的白名单解释。

运行时不是一次召回四类知识，而是两阶段：

```text
结构化 Markdown 案例
  → 自检歧义术语，召回术语定义
  → 向量召回相似历史案例
  → 生成初步风险因素
  → 用初步风险因素作为第二次检索词
  → 召回风险关联和业务先验
  → 核对事实、补漏、排除误报
```

论文还明确说，表格属性、图关系和非结构化文本最终被统一成结构化 Markdown。也就是说，图关系在这里以“与本案例有关的关系事实”进入上下文，不是把全量交易图展开给 LLM。

这是目前找到的最清楚的“为什么要在不同阶段召回不同知识”的企业例子：第一次模型还不知道具体风险因素，所以只能用原始案例召回术语和相似案例；有了初步因素后，第二次检索才能准确找到组合关系和反例。

它的消融也证明知识不是装饰：移除领域知识库后，推理信噪比从 4.34 降到 1.98，下降约 54%；完整系统在线专家接受率为 82%。这些数字只适用于京东风控任务，不能直接换算成 Text-to-SQL 提升，但证明了“分类型、分阶段的外部知识”可以显著改善专业 Agent。

京东 2026 年 Oxygen AIIC 还提供了另一条经验：面对数百万 ontology 条目，先用 semantic search 找少量候选概念，再让模型做 discrimination；ontology 保持在模型参数之外，可以持续演化。这个“先搜后判”很适合你的术语、同义词和指标对象解析。

依据：[SHERLOCK](https://arxiv.org/abs/2510.08948)、[JD Oxygen AI Item Center](https://arxiv.org/abs/2606.28070)。

### 3.6 喜马拉雅：关系召回只是多路召回中的一路

**资料级别：2025-01-08 DataFunSummit 整理的会议分享，分享嘉宾为喜马拉雅数据平台负责人；不是官方论文或开源代码，准确率口径也未公开。**

喜马拉雅披露的知识准备最接近你的资产：表和字段知识、SQL 方言、词汇、规则、业务知识、样例先加工治理；非结构化知识向量化，结构化知识关系化后存成图关系数据。

公开示例问题是：

> 本周小说频道的专辑 DAU 趋势如何？环比？

运行链路是：

1. 识别意图并改写问题；
2. 从知识库召回指标描述、时间规则、枚举值、企业术语和环比规则；
3. LLM 给出数据集候选，问题本身也检索数据集知识库；
4. 对两路候选排序选数据集；
5. 若是治理好的指标数据集，直接调用指标服务 API；
6. 若是表数据集，把改写问题和知识扩写为 Prompt，再做 NL2SQL；
7. 校验、纠错、查询并选择图表。

分享明确提到向量召回、关系化召回和大模型召回并用，再重排。因此关系图的作用是补充结构关系和规则关联，不是单独承担全部语义理解。

它还披露了一套值得借鉴的 trace：每阶段过滤/召回/重排、Prompt/SQL/模型结果、Agent 路由、API/SQL/权限、状态、用户反馈、延迟和 token 都要记录。这比只保存最终 SQL 更适合做知识工程迭代。

依据：[喜马拉雅基于大模型 ChatBI 实践探索](https://www.53ai.com/news/zhinenghuagaizao/2025010809175.html)。

### 3.7 字节/火山引擎：语义模型与企业知识分开配置，公开实现细节有限

**资料级别：2026 年火山引擎产品文档。它能证明产品接入方式，不能证明内部 Prompt 或排序算法。**

火山引擎 DataAgent 的公开文档把两类东西分开：

- 语义模型负责把技术数据集和字段重新命名、补充业务描述，帮助 Agent 选对数据集；
- 企业知识负责术语、模糊表达、文件知识和可授权检索范围。

私有化企业知识引擎支持在指定知识库或全部有权限的数据资产内问答，上传文件，并在多轮对话中改变检索范围；答案显示参考知识来源。Data Agent 产品还公开支持语义模型、企业知识引擎、自定义召回逻辑和 Prompt 干预。

公开资料没有说明一个分析问题实际调用几次召回、图关系是否被序列化、重排输入是什么。因此能可靠得出的结论只有：字节体系也把“受治理的数据语义”和“文档/企业知识检索”当作两条上下文通道，并在权限范围内组合；不能据此推断它采用了与 LinkedIn 相同的图结构。

依据：[火山引擎 DataAgent 智能问答](https://www.volcengine.com/docs/86760/2280244)、[DataAgent 产品页](https://www.volcengine.com/product/AnalyticsAgent)。

---

## 四、把这些路线放在一起看

| 公司/研究 | 离线知识怎么建 | 在线先召回什么 | 真正进入模型的内容 | 主要留在模型外的东西 |
|---|---|---|---|---|
| LinkedIn | DataHub、日志、wiki/code、用户知识、使用图 | 个性化表、示例、术语、规则 | 候选表卡、精选字段、示例、规则 | 用户图、全库图、ACL、validator |
| OpenAI | 每日归一化表使用、人工注释、代码增强并 embedding | 相关 enriched table context，必要时实时工具 | 相关片段、工具结果、记忆 | 全量日志/元数据、权限系统 |
| 阿里 | 历史 SQL→问答/SQL、片段、反馈、人工验证 | 相似 SQL、业务片段，或用户 `@` 指定 | SQL 示例、术语/规则、表或代码上下文 | 审核状态、权限、安全网关 |
| 美团 | 指标/维度定义、模型主外键、依赖拓扑预计算 | 已确认的指标、维度、路由条件 | 自然语言助手细节未公开；合理入口是受约束 DSL | 指标图遍历、选模、AST/执行计划、鉴权 |
| 蚂蚁 | DDL/轻 schema、单元格值索引、问题-SQL 示例索引 | literals 对值、skeleton 对示例 | schema、matched values、examples、evidence | 多候选执行、validator、selector 控制 |
| 京东 | 文档、代码、专家记录→四类审核知识 | 先术语/案例，后关系/业务先验 | 结构化 Markdown 和少量知识 JSON | 全量图/案例库、反馈与训练流水线 |
| 喜马拉雅 | 表字段、术语、规则、样例；向量化和关系化 | 指标规则 + 数据集，多路召回重排 | 扩写后的问题、表知识、规则 | 全量知识、关系图、权限与 trace |
| 字节/火山 | 语义模型 + 企业知识库 | 授权范围内的数据语义与知识 | 检索片段/引用，内部格式未公开 | 权限范围、全量知识、内部排序实现 |

共同点不是“都使用 Neo4j”或“都做 GraphRAG”，而是：

1. 离线把原始资产加工成可检索对象；
2. 在线先定位少量对象，再取详细信息；
3. 让不同知识服务于不同决策步骤；
4. 权限、废弃、SQL 安全和编译尽量确定性执行；
5. 用执行、校验、反馈和评测让知识持续更新。

---

## 五、知识图谱到底能不能提高效率和精度

### 5.1 可以，但“有图”本身不产生收益

图能带来四类实际收益：

#### 收益 A：候选路由

`用户 → 团队/业务域 → 常用数据集` 可以在 embedding 前先过滤几百万张表。LinkedIn 已经实际采用这种方式。

#### 收益 B：结构补全

问题直接命中 `device_orders` 后，图可以展开它的字段、上游来源、常用 join、所属指标和相关规则。它比继续做纯文本相似度更适合回答“与谁连接”。

2026 年 Nokia Bell Labs 的 CSR-RAG 给出了直接的 Text-to-SQL 证据：

- Contextual RAG 从相似历史问题取得相关表；
- Structural RAG 从 `field → table` 知识图谱召回 schema 元素；
- Relational RAG 再用 hypergraph 对 join 关系排序；
- 输出是相关 `table.column` 列表，交给下游 SQL 生成器，而不是整图；
- 企业测试达到 80% 以上 recall、约 30ms 平均检索延迟。

论文也指出，只有结构图而缺少语义上下文时 recall 会明显下降。也就是说，**图不能取代文本/向量检索，混合检索才是合理方案。**

依据：[CSR-RAG](https://arxiv.org/abs/2601.06564)。

#### 收益 C：确定性约束

权限、废弃、必填分区、指标 required filters、禁止多对多 join 等关系，可以在模型外过滤或验证。这样既减少 Prompt，也避免模型“知道规则但没遵守”。

#### 收益 D：证据溯源

每个候选口径连接到来源 SQL、看板、代码、owner、首次/最近出现时间和置信度。用户质疑答案时，Agent 可以说明“为什么采用这个口径”，人工也可以修正源头。

### 5.2 三种错误用法会让图降低准确率

1. **整图塞进 Prompt。** 大量无关边会增加 token 和注意力噪声。2026 年 DbCC 在大型数据库上把 260 万 token 压到 3.47 万，schema linking strict recall 从 0 提升到 56.5%，并在三个下游系统上使最终执行准确率绝对提升 1.8–1.9 个百分点。
2. **把自动抽取结果都当成真理。** 从一条个人 SQL 抽出的 join 或过滤，可能只是临时写法。它首先应该是 `observed_candidate`，不能直接升级为 `verified_canonical`。
3. **只按相似度取边。** 过时、低置信、无权限、跨业务域的关系即便文本很像也不应进入上下文。

DbCC 还发现压缩与准确率不是单调关系：压缩到约 3.47 万 token 时最好，继续压到 1 万以下又下降。正确目标不是“越短越好”，而是“最小但足以覆盖正确决策”。

依据：[Database Context Compression](https://arxiv.org/abs/2606.28601)。

### 5.3 图进入 Agent 的三种正确形式

#### 形式 1：实体卡片

```json
{
  "object": "metric:device_order_amount",
  "name": "设备订货金额",
  "definition": "已确认设备订货单的订货金额合计",
  "expression": "SUM(device_orders.order_amount)",
  "required_filters": ["status='confirmed'"],
  "grain": "order",
  "owner": "device_analytics"
}
```

#### 形式 2：短关系路径

```text
设备订货金额
  --defined_by--> device_orders.order_amount
  --requires_filter--> device_orders.status='confirmed'
  --groupable_by--> device_orders.product_l1
  --valid_for--> device_business
```

只提供一两跳、与本题相关的路径，并保留关系类型。不要给模型几百条匿名的 `<A, related_to, B>`。

#### 形式 3：模型外硬约束

```text
deprecated_device_orders：在候选生成前删除
用户无权访问的表：在检索前删除
required_filter：在生成后 AST 校验
指标依赖和 join：由语义引擎编译
```

这部分不需要消耗 LLM token，却往往比把规则写进 Prompt 更可靠。

---

## 六、针对你现有资产，应该抽什么图

不要一开始就尝试建设一张“包含全公司所有知识的终极本体”。更现实的是先建一张**可追溯的语义证据图**。

### 6.1 节点类型

```text
Term / Synonym
Metric / Measure / Dimension
Dataset / Column / BIModel / Dashboard / Chart
QueryPattern / SQL / FilterRule / JoinRule
CodeAsset / Pipeline
Team / User / Owner / PermissionScope
Evidence / Source
```

### 6.2 最先有价值的边

```text
Term --synonym_of--> Term
Term --refers_to--> Metric|Dimension|Dataset|Column
Metric --defined_by--> Measure|Expression
Metric --requires_filter--> FilterRule
Metric --has_grain--> Dimension
Metric --computed_from--> Dataset|Column
Dataset --has_column--> Column
Dataset --joins_to--> Dataset
Dataset --derived_from--> Dataset|SQL|BIModel
Dashboard --uses--> Metric|Dataset|Column
SQL --observes--> JoinRule|FilterRule|Aggregation
KnowledgeClaim --supported_by--> Evidence
Team|User --frequently_uses--> Dataset
PermissionScope --allows--> Dataset|Column
```

### 6.3 每条知识必须携带的治理属性

```json
{
  "source": "dashboard:817/sql:3",
  "extraction_method": "sql_ast",
  "confidence": 0.91,
  "status": "observed_candidate",
  "scope": "device_business",
  "first_seen": "2025-10-01",
  "last_seen": "2026-08-01",
  "support_count": 247,
  "contradiction_count": 3,
  "owner": null,
  "acl": ["team:device_analytics"]
}
```

最重要的是 `status`：

- `observed_candidate`：从 SQL/注释/日志自动观察到；
- `corroborated`：被多个独立资产支持；
- `verified`：owner 或领域专家确认；
- `deprecated`：已过期但为历史解释保留；
- `conflicted`：存在互相矛盾口径，不允许静默选择。

这样才能在海量自动抽取与有限人工之间取得平衡：机器负责发现和聚合，人只审核高频、高影响、冲突大的对象。

### 6.4 你的每种数据源能提供什么

| 现有数据源 | 可自动抽取 | 不应直接断言 |
|---|---|---|
| BI SQL | 表字段使用、join、filter、聚合、时间表达、别名、粒度候选 | 某次写法就是公司标准口径 |
| BI 中间组件 | 看板→数据集→字段关系、参数、计算字段、展示层同义词 | 展示名称一定是权威术语 |
| 物理表头和备注 | 类型、字段说明、可能的实体/维度、PK/FK | 无注释缩写字段的真实业务含义 |
| 中文注释 | 术语、同义词、口径和限制候选 | 注释一定准确或仍有效 |
| 查询日志 | 热度、共现、常用 join、用户/团队偏好、成功/失败模式 | 高频等于正确 |
| 无行数据 | 可以做以上静态知识、检索和 SQL identifier 校验 | 枚举值、数据分布、数值真值、真实结果质量 |

---

## 七、一次适合你项目的上下文拼装过程

仍以“设备订货金额和设备利润”为例。不要直接从图数据库导出一堆边，而是生成一个有预算的 `ContextPacket`。

### 步骤 1：解析查询并找种子

关键词/BM25/embedding 并行搜索 `Term`、`Metric`、`Dataset`、`ExampleQuery`，得到：

```json
{
  "term_seeds": ["设备订货", "设备利润", "上半年"],
  "metric_seeds": ["metric:device_order_amount", "metric:device_profit_amount"],
  "dataset_seeds": ["dataset:device_orders"]
}
```

### 步骤 2：图扩展，但只允许白名单关系和一两跳

```text
Metric → definition / required_filter / grain / source columns
Dataset → columns / certified / deprecated / common joins
Term → synonym / refers_to
Evidence → source / owner / recency
```

### 步骤 3：模型外过滤

- 根据用户 ACL 删除无权对象；
- 删除 deprecated 候选；
- 当前问题属于 `device_business`，降低其他域对象；
- 冲突口径不自动选，要求澄清或选择 verified 版本；
- 超过时效阈值的知识标记 warning。

### 步骤 4：重排和压缩

每种证据独立预算，例如：

```text
指标卡 ≤ 3
候选表 ≤ 7
每表字段 ≤ 20
join 路径 ≤ 3
业务规则 ≤ 8
示例 SQL ≤ 3
总输入 ≤ 12k tokens（应按模型和任务校准，不是固定标准）
```

### 步骤 5：形成 Writer 真正看到的包

```json
{
  "question": "请统计 ORG_1001 在 2026 年上半年...",
  "resolved_terms": [
    {"text": "上半年", "normalized": "202601..202606"}
  ],
  "metrics": [
    {
      "name": "设备订货金额",
      "expression": "SUM(device_orders.order_amount)",
      "required_filters": ["device_orders.status='confirmed'"]
    },
    {
      "name": "设备利润",
      "expression": "SUM(device_orders.profit_amount)",
      "same_population_as": "设备订货金额"
    }
  ],
  "datasets": [
    {
      "name": "device_orders",
      "certified": true,
      "grain": "one row per order",
      "columns": [
        "org_code", "year_month", "product_l1",
        "order_amount", "profit_amount", "status"
      ]
    }
  ],
  "join_paths": [],
  "approved_examples": ["一条最相近的已批准 SQL"],
  "hard_checks": [
    "org_code 必须显式出现",
    "status='confirmed' 必须出现",
    "只允许 SELECT"
  ],
  "provenance": [
    "metric 来源 dashboard:817 + 247 条历史 SQL",
    "口径状态 verified，owner=device_analytics"
  ]
}
```

### 步骤 6：不同 Agent 只拿自己需要的部分

| Agent | 应看到 | 不必看到 |
|---|---|---|
| Intent/Resolver | 术语、候选指标、歧义与范围 | 完整 schema、全部示例 SQL |
| Table Selector | 表卡、指标来源、治理属性、少量例子 | 每张表全部字段 |
| SQL Writer | 已选 schema、指标卡、join 路径、规则、例子 | 用户全局使用图、无关业务知识 |
| Validator | SQL AST、允许的表字段、hard checks | 长文档和术语解释 |
| Fixer | 坏 SQL、精确错误、缺失对象的补充证据 | 重新加载全部初始上下文 |

这样既能提高准确率，也能直接降低 token、检索延迟和重复工具调用。

---

## 八、怎样证明图真的改善了 Agent，而不是“看起来更先进”

必须做分层 A/B，而不是只比较最终回答的主观感觉。

### 8.1 四个逐步增加能力的实验组

```text
A：问题 + schema
B：A + 纯向量召回的文本/示例
C：B + 图扩展得到的指标、join、血缘和关系证据
D：C + 模型外权限/废弃/规则校验 + 定向纠错
```

### 8.2 分开测每一层

| 层 | 指标 |
|---|---|
| 术语解析 | entity/metric resolution accuracy、歧义识别率 |
| 检索 | seed recall@k、正确表/字段 recall、错误域污染率 |
| 图扩展 | 正确 join path recall、规则覆盖率、无关边比例 |
| 上下文 | token 数、证据利用率、冲突/过期知识进入率 |
| 生成 | table/column/join/filter/aggregation 准确率 |
| 执行 | parse/EXPLAIN 通过率、execution accuracy、结果等价率 |
| 安全 | ACL 违规数、敏感列泄漏数、只读违规数 |
| 效率 | 总延迟、LLM 调用数、工具调用数、修复轮数、成本 |

### 8.3 最应该单独观测的错误

最新企业基准已经说明，真正难点不是 SQL 能不能 parse：

- 选错统计范围；
- 漏掉 required filter；
- 选中相似但不权威的表；
- join 造成粒度膨胀；
- 使用了已过期口径；
- 自动抽取的低置信知识被当成标准；
- 有权限的替代表未被发现；
- 检索正确但 Writer 没有采用证据。

每个最终 SQL 都应保存一份可审计轨迹：问题、召回种子、图扩展路径、过滤原因、最终 ContextPacket、工具调用、SQL、validator 错误、修复内容、引用来源和用户反馈。

---

## 九、最后给你的直接判断

### 你的知识图谱值得做吗？

值得，但目标不应是“造出一张庞大的图，然后让 Agent 查询它”，而应是：

> 把海量 BI/SQL/元数据资产变成可追溯的候选语义对象和关系，并为 Agent 提供少量、准确、带约束和来源的上下文。

### 它应该怎样加入上下文？

不是整图加入，而是三步：

1. 图帮助检索器从种子对象扩展出正确邻域；
2. 上下文服务把邻域压成指标卡、表卡、规则卡、join 路径和证据来源；
3. 权限、废弃、指标编译和 SQL 校验尽量留在模型外确定性执行。

### 它能提高效率吗？

能。候选路由、图扩展和离线预计算减少全库扫描、Prompt token、无效 schema 探索和修复轮次。CSR-RAG 和 DbCC 提供了 2026 年的直接实验依据。

### 它能提高精度吗？

能，但前提是边有来源、置信度、时效、范围和状态，并采用混合检索与分阶段使用。京东 SHERLOCK、阿里 EntSQL、LinkedIn 和 OpenAI 的实践都表明，专业知识与局部证据有价值；同时也表明长文或结构图本身并不能保证模型正确应用规则。

### 你没有行数据会怎样？

第一阶段仍可建设高价值的“语义证据图”和 Agent 上下文服务；但要诚实标记暂时无法验证的部分：字段枚举和值映射、数据分布、基数、实时新鲜度、查询结果数值真值。未来如果允许受控运行查询，可以把这些能力作为 OpenAI 所说的“第六层运行时上下文”按需补入，而不必阻塞当前知识挖掘。

---

## 主要一手资料

### 企业公开资料

- [OpenAI：深入了解内部数据智能体，2026-01-29](https://openai.com/zh-Hans-CN/index/inside-our-in-house-data-agent/)
- [美团：BI 在指标平台和分析引擎上的探索和实践，2026-03-20](https://tech.meituan.com/2026/03/20/Busniness-Intelligence-practice-in-meituan.html)
- [阿里云 DMS 知识库，更新于 2026-06-21](https://www.alibabacloud.com/help/en/dms/knowledge-base-management)
- [阿里云 DataWorks Code Assistant，更新于 2026-07-10](https://www.alibabacloud.com/help/en/dataworks/user-guide/data-agent-coding-assistant)
- [阿里云 AI-Native Database Service，更新于 2026-07-13](https://www.alibabacloud.com/help/en/aidbs/latest/what-is-ai-native-database-service)
- [火山引擎 DataAgent 智能问答，更新于 2026-07-08](https://www.volcengine.com/docs/86760/2280244)
- [LinkedIn：Practical Text-to-SQL](https://www.linkedin.com/blog/engineering/ai/practical-text-to-sql-for-data-analytics)
- [喜马拉雅 ChatBI 分享，DataFunSummit 整理，2025-01-08](https://www.53ai.com/news/zhinenghuagaizao/2025010809175.html)

### 2026 论文

- [EntSQL: Grounding Text-to-SQL in Long-Context Enterprise Knowledge](https://arxiv.org/abs/2606.03363)
- [Database Context Compression for Text-to-SQL](https://arxiv.org/abs/2606.28601)
- [CSR-RAG: Enterprise-scale Text-to-SQL Retrieval](https://arxiv.org/abs/2601.06564)
- [SHERLOCK: Dynamic Knowledge Adaptation at JD.com](https://arxiv.org/abs/2510.08948)
- [JD Oxygen AI Item Center](https://arxiv.org/abs/2606.28070)
- [Every Step Counts: Tool-Integrated Text-to-SQL](https://arxiv.org/abs/2605.04719)

### 原路线与接口文档

- [LinkedIn: Text-to-SQL for Enterprise Data Analytics](https://arxiv.org/abs/2507.14372)
- [Ant Group: Agentar-Scale-SQL](https://arxiv.org/abs/2509.24403)
- [OpenAI MCP and Connectors](https://developers.openai.com/api/docs/guides/tools-connectors-mcp)
- [OpenAI File Search](https://developers.openai.com/api/docs/guides/tools-file-search)
