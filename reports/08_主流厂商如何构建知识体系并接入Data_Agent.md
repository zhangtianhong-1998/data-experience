# 主流厂商如何构建知识体系，并把它接入 Data Agent

> 调研日期：2026-08-04。本文优先使用企业官方工程文章、产品文档和公开演讲。论文只用来补充公开实践未披露的实验结论。

## 先回答你的质疑

上一份报告确实仍然有一个问题：虽然列出了企业案例，但“论文味”太重。你真正想知道的是两件具体的事：

1. 企业每天到底怎样把数据库、BI、SQL、文档和人的经验加工成知识；
2. 用户提问时，这些知识究竟通过什么接口、以什么形态进入 Data Agent。

本轮进一步查证后的直接答案是：

> 主流厂商很少建设一张图，然后把整张图交给大模型。它们建设的是一个由语义对象、关系、示例、规则、文档和反馈共同组成的“上下文供应系统”。知识图谱只是其中负责关系定位的一层。

生产系统通常有三个平面：

| 平面 | 存什么 | 谁使用 |
|---|---|---|
| 语义登记平面 | 指标、维度、术语、表达式、逻辑模型、版本、Owner | 人、检索器、语义引擎 |
| 检索平面 | 向量索引、关键词索引、图邻接、历史问题/SQL 索引 | Context Builder |
| 执行与治理平面 | SQL/DSL 编译器、元数据 API、权限、校验、审计 | Agent 的工具，而非 Prompt |

因此，“把知识附加到 Agent”也不是一种动作，而是五种动作：

1. 少量稳定规则放入 Agent Instructions；
2. 与本题相关的知识被召回后放入 Prompt；
3. Prompt 只放一个语义模型 ID，由服务端读取完整模型；
4. 图谱、元数据和文档通过工具按需查询；
5. 指标关系、Join、权限等留在模型外，由确定性引擎执行。

一句话概括：**知识图谱不是上下文本身，而是上下文的定位器、约束器和工具后端。**

---

## 一、怎样判断下面哪些是“真实企业实践”

公开资料的详细程度差异很大。本文使用三个证据等级，避免把产品宣传当成已经公开的算法。

| 等级 | 含义 | 本文案例 |
|---|---|---|
| A | 企业公开了内部流程、对象或实际调用链 | 京东运力小智、蚂蚁 DeepInsight、OpenAI 内部 Data Agent、美团指标平台 |
| B | 官方产品文档公开了配置对象、API 输入或返回 | 阿里 DMS、火山 DataAgent、Databricks Genie、Snowflake Cortex Analyst、Microsoft Fabric |
| C | 会议整理或只公开产品能力，没有代码和内部 Prompt | 喜马拉雅、部分字节内部效果描述 |

本文不会声称厂商公开了它没有公开的 Prompt。能看到接口时展示真实接口；只能看到架构时，会把“公开事实”和“工程推断”分开写。

---

## 二、先看一张厂商全景表

| 厂商/产品 | 知识从哪里来 | 建成什么 | 运行时怎样进入 Agent |
|---|---|---|---|
| 京东运力小智 | 逻辑模型元数据、业务方言、同义词、血缘、SOP | 70 万余实体语义图谱、逻辑模型、文档知识库 | RAG + 血缘推理先定位指标/维度/模型；准确元素进入 Prompt，模型生成 SQL/OLAP |
| 蚂蚁 DeepInsight | 元数据、指标、文档、人工澄清、相似查询、对话 | Vector Store、Meta Store、个人/公共知识、Memory | Context Constructor 合并 Prompt、记忆、召回知识和元数据；工具循环搜索、校验、修正 |
| 阿里 DMS/Meta Agent | 历史 SQL、问答点赞/修改、人工录入、CSV、资产盘点 | 问题↔SQL 记录、术语/规则↔对象片段知识 | 相似 SQL 作为示例，片段知识作为业务约束；用户还可显式 `@` 表、代码和规则 |
| 火山 DataAgent | 数据集、字段、文档、业务名词、同义词、字段值、用户反馈 | 语义模型、企业知识、规则化知识条目、Prompt 配置 | 相似度/默认/关键词三种召回；限制数量；系统展示最终送给模型的知识文本 |
| 美团指标平台 | 指标定义、数仓模型、PK/FK、维度、查询规则 | 指标依赖、模型关系、逻辑表达、DSL/AST | LLM 只选择指标/维度并产出 DSL；语义引擎在模型外遍历关系并编译 SQL |
| OpenAI 内部 Data Agent | schema、血缘、历史 SQL、注释、生产代码、Slack/Docs/Notion、纠正 | 每日归一化表知识、embedding、权限文档索引、个人/全局记忆 | RAG 只取相关记录；缺失时实时调用数仓、元数据、Airflow、Spark 工具 |
| Google Knowledge Catalog/Looker | 多平台 catalog、LookML、使用日志、数据画像、文档 | 统一 Knowledge Catalog、业务语义、关系和混合搜索索引 | 语义+关键词+重排并做 ACL 过滤；专业 Agent 或 MCP 只取得授权的局部上下文 |
| Databricks Genie | Unity Catalog、PK/FK、说明、样例值、作者配置、验证 SQL | Agent 级 Knowledge Store、SQL expressions、trusted assets | 服务端智能过滤 metadata、示例 SQL 和会话；API 请求只需 `space_id + question` |
| Snowflake Cortex Analyst | 物理表、查询历史、人工确认、样例值 | Semantic View、metrics/dimensions/relationships、VQR | API 传 `semantic_view` 名称；服务端读取模型、选 verified query，返回 SQL 和置信信息 |
| Microsoft Fabric Data Agent | 授权 schema、instructions、示例 SQL、Power BI 语义模型、图/本体 | 每个数据源的描述、规则、few-shot、Verified Answers | 官方明确披露 Prompt = 问题 + 授权 schema + 示例/规则，再路由到 SQL/DAX/KQL/GQL 工具 |

可以看出，没有一家成熟系统只维护一种“知识库”。它们至少同时维护结构化语义、可检索示例和运行时工具。

---

## 三、京东：目前最接近你设想的“从元数据抽图，再供 Data Agent 使用”

### 3.1 公开了什么

京东云开发者社区 2024 年的《基于大模型搭建运力业务的“小红书”》是这次调研中最直接的企业案例。虽然文章日期不是最新，但它公开的工程细节比很多 2026 产品文章更具体。

京东运力团队不是先让 LLM 猜表，而是已经有一层逻辑模型。一个模型对象里包含：

- 指标及其字段、类型、格式；
- 维度及中文名称、物理字段、说明；
- 时间字段和“日、日期、天”等别名；
- 操作人、更新时间；
- 模型对应的视图和物理表。

公开示例的一部分可以概括为：

```json
{
  "dimensions": [
    {
      "names": ["区域"],
      "field": "transport_org_name",
      "type": "str",
      "description": "区域"
    }
  ],
  "timeSeries": [
    {
      "names": ["日", "日期", "天"],
      "field": "dt",
      "type": "yyyy-mm-dd"
    }
  ],
  "updatedAt": 1714112126
}
```

### 3.2 知识图谱怎样构建

它的构建链条是：

```text
逻辑模型元数据
  + 语义词典定时构建任务
  + 业务人员添加的方言和同义词
  + 模型、视图、物理表之间的血缘
  → 运力业务域语义知识图谱
```

文章披露当时已积累 70 万余实体。图中的主要对象不是百科实体，而是：

- 指标；
- 维度和标签；
- 维度值；
- 逻辑模型；
- 视图；
- 物理表。

这说明你的图谱节点不应只有 `table` 和 `column`。业务问题首先碰到的是指标、维度、时间和业务词，然后才沿关系走到表。

### 3.3 图谱怎样被使用

公开文章给出的运行逻辑可以翻译成下面这条链：

```text
问题：“12 月西南每个车队的装载率，折线图”
  ↓ 切词/语素识别
时间 = 12 月
汇总维度 = 西南、车队
指标 = 装载率
分析方法 = 趋势/折线
  ↓ 语义词典把业务语言变成技术对象
  ↓ RAG 找候选对象
  ↓ 沿血缘关系推理
装载率 → 逻辑模型 → 视图 → 物理表
车队 → 维度字段
12 月 → 时间字段和范围
  ↓
把已经定位准确的元素交给 Prompt
  ↓
生成 SQL/OLAP，执行并解读
```

所以，京东的图谱不是被序列化成几万条三元组。它承担的是“坐标系统”：判断每个语素在知识体系中的位置，并把问题匹配到一个可执行的逻辑模型。

### 3.4 哪些东西没有进入 LLM

- 70 万实体不会全部进入 Prompt；
- 血缘遍历由检索/推理模块完成；
- 权限和物理执行在数据能力层完成；
- 文档知识问答与数据分析是两个接口。文章披露其先调用数据分析接口；未命中数据意图时再调用知识问答接口并返回知识卡片。

这是一种非常重要的产品边界：**SOP 文档问答和指标查询共用入口，但不强行共用一套检索和生成路径。**

依据：[京东运力小智实践](https://developer.jdcloud.com/article/4044)、[京东零售数据资产能力升级](https://developer.jdcloud.com/article/3663)。

---

## 四、蚂蚁 DeepInsight：把知识、记忆、元数据和工具组装成 Context

### 4.1 资料不是论文

这一部分来自蚂蚁高级技术专家余志鹏在 QCon 的公开演讲《蚂蚁 DeepInsight 智能分析 Agent 在业务场景的落地实践》。演讲稿共 45 页，公开了产品流程和上下文构造图。

### 4.2 知识体系怎样构建

演讲把知识源分成元数据、文本/文档和指标。文档被切块，知识和问题分别向量化，进入 Vector Store；数据元数据保存在 Meta Store；相似历史查询也形成可召回示例。

它特别处理了一类普通 RAG 很难得到的知识：**用户澄清后的业务习惯。**

流程是：

```text
用户提出模糊问题
  ↓
识别语义歧义、细化需求、泛化需求、指代问题
  ↓
用 schema 匹配、术语歧义和上下文缺失计算歧义分数
  ↓
只追问最少、最关键的问题
  ↓
把用户回答转成结构化知识
  ↓
写入个人知识库或公共知识库
```

公开的应用类型包括：

- 领域口径定义；
- 时间范围定义；
- 指标路径澄清；
- 业务习惯定义。

这不是简单保存整段聊天。系统把“这次用户为什么选择 A 而不是 B”抽成下次可检索的结构化知识。

### 4.3 运行时怎样附加

蚂蚁公开图中的 `context constructor` 同时读取：

```text
System Prompt：预置模板和任务边界
Memory：本轮多轮对话记忆
Vector Store：RAG 召回的相似查询和领域知识
Meta Store：实时查询的数据集与字段元数据
```

然后模型可以自主调用：

- 维值精确搜索；
- 字段模糊搜索；
- 语法校验器；
- 语义校验器；
- DAX、DAL、SQL 执行沙箱。

因此它不是“检索一次 → 写 SQL”。它是：

```text
构造初始 Context
  → 模型发现字段/值不确定
  → 调用搜索工具
  → 把工具返回追加到当前上下文
  → 生成代码
  → 执行和校验
  → 反馈反思修正
```

### 4.4 Validator 看到什么

演讲还披露了另一套校验 Prompt 的组成：

```text
用户输入的诉求
+ 数据集信息
+ 领域知识
+ 取数 SQL
+ 关系代数/执行计划
```

它不是让生成 SQL 的同一个模型仅仅“再看一眼自己的答案”，而是引入能力更强的校验模型，并用 SQL 与关系代数两条异构路径交叉检查。这说明知识附加不只发生在 Writer 前，也发生在 Validator 前；不同 Agent 应得到不同 Context。

演讲公布的内部评测校验准确率为 91.7%，线上真实评测为 88%。这些数字是“校验任务”的指标，不等于端到端 Text-to-SQL 准确率。

依据：[蚂蚁 DeepInsight 公开演讲稿](https://www.wesee.club/usr/uploads/2025/11/2676871471.pdf)。

---

## 五、阿里 DMS/Meta Agent：把历史 SQL 和用户反馈变成可审核知识

### 5.1 它没有强迫用户先建完整图谱

阿里 2026 年 Meta Agent 文档把知识简化为两类：

```text
SQL 记录：自然语言问题 ↔ 已验证 SQL
片段知识：术语/业务规则 ↔ 表、字段或过滤条件
```

例如：

```text
“VIP 客户”指 customer 表中 level = 3 或 4 的记录
```

这条知识同时连接了术语、表、字段和值条件，已经是一条小型关系知识；不一定需要先放进通用图数据库。

### 5.2 知识怎样产生

公开的生产入口包括：

1. 分析数据库历史 SQL，发现高频模式并生成候选知识；
2. 用户对正确答案点赞，问答自动沉淀为 SQL 记录；
3. 用户修改 SQL，保留纠正后的查询经验；
4. 专家手工录入术语、字段含义和规则；
5. CSV 批量迁移已有词表和 SQL 对；
6. SQL 自动解析关联的表和字段；
7. 使用标签按交易、用户、商品等领域分类。

关键不是“自动生成”四个字，而是知识有来源、类型、标签和维护入口。业务变化后可以编辑或删除，而不是把错误的 LLM 推断永久写入图谱。

### 5.3 运行时怎样使用

```text
用户问题
  ↓
按问题相似度找 SQL 记录
按术语/对象找片段知识
  ↓
将少量 SQL 示例和业务约束交给 NL2SQL
  ↓
生成、执行、展示 SQL
  ↓
点赞/修改再次进入知识候选
```

DataWorks 还允许用户通过 `@Table`、`@Node/Code`、`@Data Collection`、`@Rules` 或本地文件显式指定上下文。自动召回不确定时，人可以直接缩小范围。

OneMeta、资产盘点和 Agent Data Gateway 则留在 Prompt 外，分别提供资产语义和库/表/列/行权限、脱敏、SQL 风险控制与审计。

依据：[Meta Agent 知识管理](https://www.alibabacloud.com/help/zh/aidbs/latest/meta-agent-knowledge-management)、[DMS Data Copilot](https://www.alibabacloud.com/help/dms/dms-data-copilot-intelligent-assistant)、[AI 原生数据库服务](https://www.alibabacloud.com/help/zh/aidbs/latest/what-is-ai-native-database-service)。

---

## 六、字节/火山 DataAgent：公开到“这一条知识怎样被放进模型”

### 6.1 知识构建不只上传文档

火山引擎公开了两类不同的知识准备：

**文档知识：**

- PDF/Word/PPT/HTML 解析；
- OCR、版面分析、表格和图片提取；
- 按阅读顺序转成带逻辑结构的 Markdown；
- 自动或自定义切片后进入企业知识引擎。

**数据集业务知识：**

- 业务名词；
- 名词说明；
- 同义词；
- 与字段名的关联；
- 与字段值的关联；
- 召回规则。

比如：

```text
业务名词：抖西
说明：抖音、西瓜、今日头条
参与字段值召回：是
```

该知识不仅帮助理解“抖西”，还帮助系统反向召回包含这些值的“产品名”字段。

### 6.2 单条知识有三种进入模型的方式

火山文档公开了三种召回规则：

| 规则 | 何时进入 Context | 适合什么 |
|---|---|---|
| 跟随知识库配置 | 名词或同义词与问题相似时 | 普通术语、近义词 |
| 默认召回 | 每个问题都传给模型 | 极少量全局强规则 |
| 自定义规则 | 问题包含/不包含指定关键词时 | 精确场景规则、冲突口径 |

它还提供“知识召回上限”，明确说明是为了防止召回过多知识干扰模型；配置页的“预览”展示业务名词、连接词和说明串联后的文本，并明确称这是“最终给到模型的知识”。

这回答了一个非常具体的问题：图或结构化知识经过召回后，最终往往仍然会被序列化成一小段可读文本，而不是保持图数据库内部格式进入 Transformer。

### 6.3 Prompt 和语义知识不是一个对象

火山把 Prompt 单独管理，可按通用、网页生成、多表关联等场景配置“提示”或“要求”。官方示例强调规则要写成精确触发条件，而不是一大段含混说明。

因此它的线上上下文大致是：

```text
系统内置 Prompt
+ 命中的自定义 Prompt
+ 召回的业务知识
+ 相关语义模型/字段
+ 当前问题与对话
```

公开文档没有披露内部重排模型和完整最终 Prompt，所以只能确认配置和传递机制，不能声称知道其私有算法。

依据：[数据集知识库配置](https://www.volcengine.com/docs/86760/1874927?lang=zh)、[Prompt 配置](https://www.volcengine.com/docs/86760/1874853?lang=zh)、[文档处理算子](https://www.volcengine.com/docs/86760/2280961?lang=zh)、[DataAgent 新版概述](https://www.volcengine.com/docs/86760/2552692?lang=zh)。

---

## 七、美团：最重要的知识不一定进入 Prompt，而是进入语义编译器

美团的公开实践说明，指标知识真正稳定的使用方式是“编译”，而不只是“提示”。

### 7.1 怎样构建

```text
业务语言指标定义
  → 解析成结构化逻辑表达
数仓模型 + 主外键
  → 星型/雪花/星座关系
原子指标 + 维度
  → 衍生和复合指标依赖
查询历史和性能规则
  → 指标高亮、路由选表、预计算
```

### 7.2 怎样接到 Data Agent

上层自然语言助手只需要解决：

- 用户说的是哪个指标；
- 按什么维度；
- 什么时间和过滤条件；
- 需要同比、环比、TopN 还是归因。

然后生成受约束 DSL。指标依赖、模型关系、选表和权限由语义引擎生成 AST、执行拓扑和物理 SQL。

```text
自然语言 → 指标/维度 DSL → 语义 AST → 模型路由 → SQL
```

这对你的知识图谱有直接影响：`metric → field → model → table` 这类确定性关系，不必全部转成自然语言放进 Prompt。Agent 可以只提交 `metric_id`，让语义服务在外部完成图遍历。

依据：[美团 BI 在指标平台和分析引擎上的探索和实践](https://tech.meituan.com/2026/03/20/Busniness-Intelligence-practice-in-meituan.html)。

---

## 八、OpenAI：代码、组织知识和记忆是三条不同的生产线

### 8.1 每日离线知识生产

OpenAI 内部 Data Agent 每天把以下信息归一化：

- 表使用情况；
- schema 和血缘；
- 历史查询与常见 Join；
- 专家注释；
- Codex 从生产代码提取的粒度、唯一键、刷新频率、范围和排除项。

归一化记录被转换为 embedding，供数万张表的在线检索。

组织文档走另一条管道：Slack、Google Docs、Notion 被采集、嵌入，并保留 metadata 和权限。个人/全局 Memory 又是第三种存储，用于保存纠正、特殊过滤条件和非显然约束。

### 8.2 运行时怎样附加

```text
问题
  ↓ RAG
只取相关的表级归一化记录
  ↓ 必要时
检索带权限的组织文档
  ↓ 必要时
读取个人/全局 Memory
  ↓ 信息不足或过期
实时调用数仓、元数据、Airflow、Spark
```

血缘是关系图，但官方文章没有说整图进入 Prompt。关系用于帮助检索和解释局部上下游；检索服务最终给 Agent 的是相关表知识。

### 8.3 MCP 在这里不是知识库

OpenAI 的官方 MCP 文档展示的过程是：

1. Responses API 导入 MCP 工具定义，产生 `mcp_list_tools`；
2. 模型决定调用工具，输出 `mcp_call.arguments`；
3. MCP 服务返回 `mcp_call.output`；
4. output 进入当前会话，供模型继续推理。

`allowed_tools` 用于减少无关工具定义带来的 token、成本和延迟。因此 MCP 是“Agent 获取知识和执行能力的通道”，并不负责自动把企业知识建好。

依据：[OpenAI 内部 Data Agent](https://openai.com/index/inside-our-in-house-data-agent/)、[MCP 与 Connectors](https://developers.openai.com/api/docs/guides/tools-connectors-mcp)、[File Search](https://developers.openai.com/api/docs/guides/tools-file-search)。

---

## 九、Google：把 catalog 升级成持续富化、权限感知的上下文引擎

Google 2026 年公开的 Knowledge Catalog 是一个很典型的“企业上下文供应系统”。

### 9.1 知识怎样构建

它公开了三个阶段：

1. **Aggregation**：聚合 Google Cloud、第三方 catalog、应用、操作系统和 AI 平台的上下文；LookML Agent 与 BigQuery measures 将业务逻辑写回平台。
2. **Continuous enrichment**：分析组织使用日志、数据画像和非结构化文件；生成缺失 schema，推断关系。
3. **Search and retrieval**：语义检索、词法检索和机器学习重排结合，并在检索阶段执行权限过滤。

BigQuery Data Insights 还公开了关系来源：

- schema 中声明的 PK/FK；
- 查询日志中出现的 Join；
- Gemini 根据表名、字段名和说明推断的候选关系。

注意第三类只能是候选，应经过验证后再进入可信关系层。

### 9.2 怎样进入 Agent

Knowledge Catalog 先找出授权且相关的资产，再把局部上下文提供给专业 Agent。对外也可以通过 BigQuery、Looker 等 MCP 工具查询。

Looker Conversational Analytics 则让开发者为 Agent 选择 Explore，并配置：关键字段、排除字段、过滤/分组字段、同义词和自定义计算。运行时回答主要基于 LookML schema 和这些 Agent Instructions。

Google 没有公开内部最终 Prompt，但公开了“聚合—富化—权限检索—Agent/MCP 消费”的整条数据供应链。

依据：[Google Knowledge Catalog](https://cloud.google.com/blog/products/data-analytics/whats-new-in-the-agentic-data-cloud)、[BigQuery Data Insights](https://docs.cloud.google.com/bigquery/docs/data-insights)、[Looker Data Agents](https://cloud.google.com/looker/docs/studio/conversational-data-agents-looker)。

---

## 十、Databricks Genie：知识保存在 Agent Space，提问 API 不传完整 Prompt

### 10.1 Knowledge Store 里真正存什么

Databricks 2026 文档列出的对象非常具体：

- Agent 级表/字段说明；
- synonyms；
- Join relationships；
- SQL expressions：指标、过滤和维度表达式；
- prompt matching 设置；
- example question/SQL；
- verified parameterized queries 和 SQL functions，即 trusted assets；
- benchmark 问题。

Benchmark 只用于评测，不进入运行时上下文。这是很多自建项目容易混淆的一点：测试集不能偷渡成 few-shot。

管理对象的结构近似：

```json
{
  "instructions": [
    "last month 指上一自然月；金额保留两位小数"
  ],
  "example_question_sqls": [
    {
      "question": ["Show top 10 customers by revenue"],
      "sql": ["SELECT ..."]
    }
  ],
  "join_specs": [
    {
      "left": {"identifier": "sales.orders"},
      "right": {"identifier": "sales.customers"},
      "sql": ["orders.customer_id = customers.customer_id"]
    }
  ],
  "sql_snippets": {
    "measures": [
      {
        "display_name": "total revenue",
        "synonyms": ["revenue", "total sales"],
        "sql": ["SUM(orders.order_amount)"]
      }
    ]
  }
}
```

### 10.2 运行时如何选择上下文

官方明确说明 Genie 会智能过滤：

- Unity Catalog 中的相关表和字段 metadata；
- PK/FK；
- 相关 sample values；
- Knowledge Store context；
- 相关 example SQL；
- SQL functions；
- 当前对话历史。

旧对话在超过 token 限制时会从最早部分开始丢弃。因此“保存在 Space”不等于“每次全部送进模型”。

### 10.3 API 输入和返回

客户端发出的请求很小：

```http
POST /api/2.0/genie/spaces/{space_id}/start-conversation

{
  "content": "Give me top sales for last month"
}
```

`space_id` 就是知识体系句柄。上下文组装在 Genie 服务端完成。

轮询消息后，`attachments` 会逐步返回：

- 生成的 SQL；
- SQL 说明；
- 文本回答；
- follow-up questions；
- query result ID；
- reasoning trace；
- trusted asset 使用时的参数。

也就是说，自建上层 Agent 不需要再次把 Genie 的语义知识复制进自己的 Prompt；它把 Genie 当成一个受治理的数据工具即可。

依据：[Genie Agent Concepts](https://docs.databricks.com/aws/en/genie-agents/concepts)、[Genie Conversation API](https://docs.databricks.com/aws/en/genie/conversation-api)、[Genie Best Practices](https://docs.databricks.com/aws/en/genie/best-practices)。

---

## 十一、Snowflake：语义模型作为数据库对象，通过名称附加

### 11.1 怎样构建 Semantic View

Snowflake 把语义定义做成数据库 schema 级对象，包含：

- logical tables 与物理表/SQL 的映射；
- primary key、unique keys；
- relationships 和 Join key；
- dimensions、facts、metrics；
- SQL expression；
- synonyms、description、sample values；
- enum 标记；
- custom instructions；
- Verified Query Repository（问题↔确认 SQL）。

创建向导可以根据列名和样例值生成初始说明和同义词，但官方警告自动同义词可能降低质量，仍需人审核。

### 11.2 反馈飞轮怎样工作

Snowflake 从查询历史和 Cortex Analyst 使用数据中发现：

- 高频且有意义的新问题；
- 模型缺少的 filter；
- 模型缺少的 metric；
- 值得加入 VQR 的 SQL。

这些只进入 Suggestions 队列，人需要 Accept、Edit 或 Dismiss。已验证 SQL 又可以反推出更一般的 filter、metric、description、synonym 和 custom instruction。

这是一条很成熟的知识飞轮：

```text
真实问题/SQL
  → 候选知识
  → 人工确认
  → Verified Query
  → 提炼通用指标/过滤/同义词
  → 扩大未见问题覆盖率
```

### 11.3 怎样附加到 Agent

REST 请求无需内联全部 YAML，可以只传语义视图名字：

```json
{
  "messages": [
    {
      "role": "user",
      "content": [{"type": "text", "text": "上月各区域净收入"}]
    }
  ],
  "semantic_models": [
    {"semantic_view": "analytics.semantic.sales"}
  ]
}
```

Cortex Analyst 服务读取 Semantic View，选择适合的对象或 verified query，生成物理 SQL。响应可返回：

- SQL；
- 文本解释或建议问题；
- warning；
- 使用了哪条 verified query；
- verified_by 和 verified_at；
- 使用的模型名称。

关系图在这里主要由语义编译器消费；LLM 通过语义视图对象获得它需要的业务含义，而不必接收整张关系图。

依据：[Semantic View Overview](https://docs.snowflake.com/en/user-guide/views-semantic/overview)、[YAML Specification](https://docs.snowflake.com/en/user-guide/views-semantic/semantic-view-yaml-spec)、[Cortex Analyst REST API](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/rest-api)、[Suggestions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/verified-query-suggestions)。

---

## 十二、Microsoft Fabric：官方直接写明 Prompt 拼装内容

Microsoft 是少数明确描述 Prompt 组成的厂商。Fabric Data Agent 在用户身份下读取授权 schema，然后组合：

```text
User Query
+ Schema Information
+ Examples
+ Instructions
```

再交给底层 Agent 选择 NL2SQL、NL2DAX、NL2KQL 或 NL2GQL 工具。

### 12.1 知识配置对象

每个数据源可以分别配置：

- Schema Selection：允许使用的表、视图、函数；
- Data Source Description：该源回答什么主题；
- Data Source Instructions：Join、关键字段和业务术语；
- Example Queries：自然语言↔SQL/KQL；
- Agent Instructions：跨数据源路由和全局规则。

Example Queries 会通过向量相似度只取 Top examples，不是把全部示例放进 Prompt。对于 Power BI Semantic Model，知识保存在 Prep for AI 的 AI Data Schema、AI Instructions 和 Verified Answers 中。

### 12.2 图谱可以怎样使用

Fabric 将 Graph 和 Ontology 当作正式数据源：

- Graph Data Agent 可生成 GQL 并在图上执行；
- 图数据源可以配置描述、instructions 和 GQL examples；
- Ontology 用于数据源路由和业务对象表达；
- 图执行结果再供上层 Agent 总结。

这是一种不同于 GraphRAG 的方式：图不被压成 Prompt 文本，而是被当作可查询数据库。模型先生成 GQL，执行器返回本题需要的子图事实。

依据：[Create a Fabric Data Agent](https://learn.microsoft.com/en-us/fabric/data-science/how-to-create-data-agent)、[Add Data Sources](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-add-datasources?tabs=gql)、[Improve Routing](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-routing)。

---

## 十三、腾讯、百度和喜马拉雅补充了什么

### 腾讯 TCDataAgent

腾讯官方文档公开了两条通道：用户选择授权库表，Agent 自动执行 NL2SQL；同时将 PDF、Office、表格、COS 或网页解析成知识库。API 可传 `KnowledgeBaseIds`，因此上层系统可以明确指定本次允许检索的知识库。

这能证明“结构化数据源”和“文档知识库”可以同时挂在一个 Data Agent 上，但公开文档没有说明两者在最终 Prompt 中如何排序，也没有公开数据语义图谱。

依据：[配置知识库](https://cloud.tencent.com/document/product/1800/122737)、[对话问答](https://cloud.tencent.com/document/product/1800/122735)、[DataAgent API](https://cloud.tencent.com/document/product/1800/125015)。

### 百度千帆知识库

百度公开支持从文档切片中抽取三元组，并在检索时返回图谱信息，用于跨文件总结和多实体关系问题。官方同时提示：图谱检索会增加延迟，而且问答模型上下文不得小于 32K。

这证明“图关系可以被检索后放入上下文”，但它是通用文档问答证据，不能直接证明 Text-to-SQL 会因此更准。对你的数据 Agent，图谱还必须绑定表、字段、指标和规则才能产生 SQL 价值。

依据：[百度千帆知识库](https://cloud.baidu.com/doc/qianfan/s/Imh4stpo0)。

### 喜马拉雅

公开会议整理显示其将非结构化知识向量化、结构化知识关系化；运行时同时进行向量、关系和大模型召回，再重排，之后分别走指标 API 或 NL2SQL 路径。因为不是官方代码或产品文档，只能把它视为实践分享，不能据此复原私有 Prompt。

依据：[喜马拉雅 ChatBI 分享整理](https://www.53ai.com/news/zhinenghuagaizao/2025010809175.html)。

---

## 十四、同一个问题，知识究竟怎样一步步进入 Agent

下面不用抽象术语，直接使用一个接近你资产的问题：

> 统计 2026 年 7 月各渠道的新客支付转化率，只看正式订单。

假设企业数据库字段仍是英文且无中文注释，但 BI SQL 和看板标题中出现过“新客支付转化率”。

### 第一步：离线从现有资产生产候选知识

SQL 解析器从大量 BI SQL 中统计到：

```sql
COUNT(DISTINCT CASE WHEN is_new_buyer = 1 AND pay_status = 'PAID'
                    THEN user_id END)
/
COUNT(DISTINCT CASE WHEN is_new_buyer = 1
                    THEN user_id END)
```

它还发现：

- 该表达式经常被别名 `new_buyer_pay_rate`；
- 看板标题称它为“新客支付转化率”；
- `channel_id` 经常 Join `dim_channel.id`；
- 大多数已认证查询都带 `order_type = 'NORMAL'`；
- 这些查询主要使用 `fact_order_daily`。

系统先生成候选，而不是直接发布：

```json
{
  "candidate_type": "metric",
  "name": "新客支付转化率",
  "expression": "...",
  "grain": ["dt", "channel_id"],
  "default_filter": "order_type = 'NORMAL'",
  "evidence": [
    "dashboard:经营日报/新客转化",
    "query_cluster:q_4821",
    "sql_occurrences:186"
  ],
  "status": "candidate"
}
```

LLM 可以帮助起名和解释，但表达式、Join 和出现次数来自 SQL AST 与日志。Owner 审核冲突口径后才发布。

### 第二步：发布到不同存储，而不是只存一张图

```text
语义注册表
  metric:new_buyer_pay_rate
  expression、grain、version、owner、valid_time

知识图谱
  新客支付转化率 --BINDS_TO--> metric:new_buyer_pay_rate
  metric --COMPUTED_FROM--> fact_order_daily.user_id/pay_status/is_new_buyer
  metric --REQUIRES_FILTER--> order_type=NORMAL
  fact_order_daily.channel_id --JOINS_TO--> dim_channel.id

向量/关键词索引
  “新客支付转化率”“首购用户转化”“拉新支付率”

示例库
  已认证问题 ↔ SQL/DSL
```

图保存关系，向量索引解决自然语言入口，注册表保存权威定义，示例库保存真实查询模式。四者不能互相完全替代。

### 第三步：在线解析问题

```json
{
  "time": {"from": "2026-07-01", "to": "2026-08-01"},
  "metric_mentions": ["新客支付转化率"],
  "dimension_mentions": ["渠道"],
  "constraints": ["正式订单"]
}
```

### 第四步：多路召回

```text
词法召回：精确命中“新客支付转化率”
向量召回：命中 metric:new_buyer_pay_rate
图扩展 1 跳：字段绑定、默认过滤、渠道 Join
示例召回：找到 2 条相似已认证查询
```

此时图返回的不是 70 万实体，而是 6 到 15 个局部事实。

### 第五步：模型外治理

在拼 Prompt 前先做：

- 删除用户无权访问的表和字段；
- 只保留当前有效版本；
- 优先 Owner 认证知识；
- 对冲突口径触发澄清，不让 LLM 自选；
- 限制每种证据的数量和 token。

### 第六步：形成 ContextPacket

```json
{
  "question": "统计 2026 年 7 月各渠道的新客支付转化率，只看正式订单",
  "semantic_objects": [
    {
      "id": "metric:new_buyer_pay_rate",
      "name": "新客支付转化率",
      "formula": "paid_new_buyers / all_new_buyers",
      "grain": ["day", "channel"],
      "owner": "growth_analytics",
      "status": "certified"
    }
  ],
  "bindings": [
    "paid_new_buyers := COUNT(DISTINCT user_id) WHERE is_new_buyer=1 AND pay_status='PAID'",
    "all_new_buyers := COUNT(DISTINCT user_id) WHERE is_new_buyer=1"
  ],
  "required_filters": ["fact_order_daily.order_type = 'NORMAL'"],
  "join_paths": [
    "fact_order_daily.channel_id = dim_channel.id"
  ],
  "relevant_schema": [
    "fact_order_daily(dt,user_id,is_new_buyer,pay_status,order_type,channel_id)",
    "dim_channel(id,channel_name)"
  ],
  "examples": ["<一条最相似且已认证的 SQL>"],
  "provenance": ["dashboard:经营日报", "query_cluster:q_4821"]
}
```

这就是“图谱加入上下文”的实际形态：图谱提供了 `bindings`、`required_filters` 和 `join_paths`，但 Writer 不需要知道它们原来存在哪种数据库里。

### 第七步：Writer 真正看到什么

```text
你必须只使用给定的 certified semantic objects 和 schema。
如果所需信息冲突或缺失，返回 clarification，不要猜测。

Question:
统计 2026 年 7 月各渠道的新客支付转化率，只看正式订单。

Metric:
- 新客支付转化率 = paid_new_buyers / all_new_buyers
- paid_new_buyers: is_new_buyer=1 and pay_status='PAID' 的去重 user_id
- all_new_buyers: is_new_buyer=1 的去重 user_id

Required filter:
- fact_order_daily.order_type = 'NORMAL'

Join:
- fact_order_daily.channel_id = dim_channel.id

Relevant schema:
- fact_order_daily(...)
- dim_channel(id, channel_name)

Return JSON DSL only.
```

### 第八步：LLM 输出 DSL，而不是自由 SQL

```json
{
  "metrics": ["new_buyer_pay_rate"],
  "dimensions": ["channel_name"],
  "time_range": ["2026-07-01", "2026-08-01"],
  "filters": ["order_type = NORMAL"]
}
```

随后由美团、Snowflake、Cube 一类语义引擎确定性编译 SQL。若没有语义引擎，Writer 可以直接写 SQL，但 Validator 仍应读取相同口径、schema、SQL 和执行计划进行复核。

---

## 十五、你的知识图谱到底应该放在哪里

### 应放在 Prompt 外、作为服务保留的内容

- 全量节点和边；
- 全量血缘；
- 全量历史查询；
- 权限和敏感字段策略；
- 指标依赖计算；
- 版本冲突和可信度排序；
- 图搜索、路径查找和候选过滤。

### 可以检索后放进 Prompt 的内容

- 1 到 3 个指标定义；
- 当前问题涉及的术语解释；
- 1 到 2 条 Join 路径；
- 必须使用或禁止使用的过滤规则；
- 相关表字段的精简 schema；
- 1 到 3 条认证示例；
- 来源、Owner、版本和置信度。

### 更适合做工具调用的内容

```text
search_semantic_objects(query, user, domain)
get_metric_definition(metric_id, as_of)
expand_relationships(seed_ids, edge_types, max_hops=2)
get_join_path(left, right)
get_relevant_examples(question, top_k=3)
compile_semantic_query(dsl)
validate_sql(sql, semantic_constraints)
```

MCP 可以把这些工具暴露给 Agent。SDK 可以供固定工作流直接调用。两者返回的应该是局部、结构化、带 provenance 的结果，而不是一份无边界的“企业知识全文”。

---

## 十六、结合你的资产，主流实践给出的现实建设顺序

你没有行数据，因此暂时不能像 Databricks、Snowflake 那样充分利用 sample values，也不能像蚂蚁的维值搜索一样验证真实枚举。但你拥有非常有价值的替代信号：BI SQL、BI 中间组件、物理 schema、看板名称和中文注释。

### 第一阶段：自动构建可审计的候选知识

从 SQL AST 和 BI 模型稳定提取：

- 表/字段使用频率；
- Join 边和方向；
- 聚合表达式；
- Group By 维度；
- 高频过滤条件；
- 别名和中文标题；
- 看板→查询→表→字段血缘；
- 同一表达式的不同叫法；
- 同一叫法对应多个表达式的冲突。

LLM 只负责候选命名、摘要、术语聚类和冲突解释，不负责凭空确认口径。

### 第二阶段：形成最小可用知识对象

优先建设：

1. `AssetCard`：表/字段的用途、粒度、Owner、来源；
2. `MetricCard`：名称、公式、过滤、粒度、维度、版本；
3. `TermCard`：术语、同义词、歧义和绑定对象；
4. `JoinEdge`：两端字段、来源 SQL 数、认证状态；
5. `QueryExample`：问题、SQL、涉及对象、是否认证；
6. `RuleCard`：强制过滤、时间范围、排除规则。

### 第三阶段：同时发布三个索引

- 关键词/向量索引用于找种子；
- 知识图谱用于一两跳关系扩展；
- 结构化注册表用于返回权威定义和版本。

### 第四阶段：先让图服务一个可测决策

不要以“图里有多少节点”为成功标准。第一个目标可以是：

> 给定问题，在 Top-5 中召回正确指标；在 Top-10 中召回正确表；返回唯一可执行 Join 路径。

只有这三项明显优于“schema + 向量搜索”基线，图谱才证明了价值。

### 第五阶段：建立厂商都在做的反馈飞轮

```text
用户问题
  → 召回证据和生成结果
  → 用户接受/修改/追问/澄清
  → 生成候选知识
  → 规则校验 + Owner 审核
  → 发布新版本
  → 固定评测集回归
```

点赞不能直接把错误 SQL 升级成全局规则；自动推断关系不能直接变成 certified edge。阿里和 Snowflake 的公开实践都保留人工确认环节，蚂蚁则区分个人知识与公共知识。

---

## 十七、最终判断

### 只有论文吗？

不是。现在已有相当具体的厂商实践：

- 京东公开了 70 万实体语义图谱怎样从模型元数据和方言构建、怎样定位逻辑模型；
- 蚂蚁公开了 Context Constructor、知识沉淀和搜索/校验工具；
- 火山公开了知识条目如何选择性传给模型；
- Microsoft 公开了 Prompt 由什么组成；
- Databricks 和 Snowflake 公开了服务端知识对象、API 请求和返回；
- OpenAI、Google 公开了大规模上下文的离线富化与权限检索管道。

### 企业是在构建一张大知识图谱吗？

通常不是。更准确的说法是构建“企业上下文层”：图谱保存关系，语义层保存确定性定义，向量库解决自然语言召回，示例库保存真实查询模式，工具层负责实时数据与执行。

### 图谱能不能附加到 Data Agent？

能，主要有三种成熟方式：

1. 图检索后，把少量关系事实压成证据文本或 JSON；
2. 把图查询做成工具，Agent 按需获取子图；
3. 把图放进语义引擎，Agent 只生成指标/维度 DSL，由引擎遍历图并编译 SQL。

第三种对指标和 Join 最可靠，第一种最容易起步，第二种适合复杂探索。一个成熟系统往往同时使用三种。

### 对你的项目最重要的改变是什么？

不要把目标写成“从海量资产自动生成完整企业知识图谱”。更可执行的目标是：

> 从 BI SQL、BI 模型和 schema 自动生成可追溯的候选语义对象与关系；通过检索、图扩展和治理形成小型 ContextPacket；让 Agent 或语义引擎只消费与当前问题有关、可绑定、可验证的知识。

这与当前主流企业实践是一致的，也允许你在没有行数据、没有完整中文注释的情况下先开始，并通过真实问题逐步长出知识体系。

---

## 主要非论文资料

### 国内企业工程与产品

- [京东：基于大模型搭建运力业务的“小红书”](https://developer.jdcloud.com/article/4044)
- [京东：零售数据资产能力升级与实践](https://developer.jdcloud.com/article/3663)
- [蚂蚁 DeepInsight 智能分析 Agent 在业务场景的落地实践](https://www.wesee.club/usr/uploads/2025/11/2676871471.pdf)
- [阿里云：Meta Agent 知识管理](https://www.alibabacloud.com/help/zh/aidbs/latest/meta-agent-knowledge-management)
- [阿里云：AI 原生数据库服务](https://www.alibabacloud.com/help/zh/aidbs/latest/what-is-ai-native-database-service)
- [美团：BI 在指标平台和分析引擎上的探索和实践](https://tech.meituan.com/2026/03/20/Busniness-Intelligence-practice-in-meituan.html)
- [火山引擎：数据集知识库配置](https://www.volcengine.com/docs/86760/1874927?lang=zh)
- [火山引擎：Prompt 配置](https://www.volcengine.com/docs/86760/1874853?lang=zh)
- [腾讯云：TCDataAgent 配置知识库](https://cloud.tencent.com/document/product/1800/122737)
- [百度千帆：知识库与图谱检索增强](https://cloud.baidu.com/doc/qianfan/s/Imh4stpo0)

### 国际厂商工程与产品

- [OpenAI：Inside our in-house data agent](https://openai.com/index/inside-our-in-house-data-agent/)
- [Google：Knowledge Catalog and Agentic Data Cloud](https://cloud.google.com/blog/products/data-analytics/whats-new-in-the-agentic-data-cloud)
- [Databricks：Genie Agent Concepts](https://docs.databricks.com/aws/en/genie-agents/concepts)
- [Databricks：Genie Conversation API](https://docs.databricks.com/aws/en/genie/conversation-api)
- [Snowflake：Semantic Views](https://docs.snowflake.com/en/user-guide/views-semantic/overview)
- [Snowflake：Cortex Analyst REST API](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/rest-api)
- [Microsoft：Create a Fabric Data Agent](https://learn.microsoft.com/en-us/fabric/data-science/how-to-create-data-agent)
- [Microsoft：Configure Data Sources, Graph and Ontology](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-add-datasources?tabs=gql)
