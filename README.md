# data-experience：企业语义层三条路线的真实运行实验

这不是“产品功能摘抄”，而是一套已经在本机跑过、能逐层查看输入和输出的实验。工作区与相邻的 `data-ex` 完全隔离；原工程没有被改动。

## 先看什么

如果只想先弄明白结论，按这个顺序阅读：

1. [`reports/00_先读这份_从问题到答案.md`](reports/00_先读这份_从问题到答案.md)：用同一个业务问题讲清三条路线分别解决什么。
2. [`reports/01_路线1_指标语义层如何构建和调用.md`](reports/01_路线1_指标语义层如何构建和调用.md)：MetricFlow、Cube、WrenAI 的真实定义、编译 SQL、API/MCP 返回。
3. [`reports/02_路线2_资产如何采集以及MCP返回什么.md`](reports/02_路线2_资产如何采集以及MCP返回什么.md)：DataHub、OpenMetadata 的连接器、SDK、查询日志、血缘与 MCP 实际返回。
4. [`reports/03_路线3_LinkedIn_Text_to_SQL逐步复现.md`](reports/03_路线3_LinkedIn_Text_to_SQL逐步复现.md)：知识图谱、检索、重排、SQL 生成、校验和纠错的完整链路。
5. [`reports/05_复现手册.md`](reports/05_复现手册.md)：早期三条路线的环境要求与逐套复跑命令。
6. [`解答/02_真实LLM如何从语义上下文生成DSL.md`](解答/02_真实LLM如何从语义上下文生成DSL.md)：逐条展示真实 LLM 输入、DSL、失败修复、SQL 和结果。
7. [`reports/07_2026_Data_Agent上下文工程与知识图谱使用.md`](reports/07_2026_Data_Agent上下文工程与知识图谱使用.md)：解释 LinkedIn 的图怎样在多次召回中使用，并给出知识图谱进入 Agent 上下文的具体方式。
8. [`reports/08_主流厂商如何构建知识体系并接入Data_Agent.md`](reports/08_主流厂商如何构建知识体系并接入Data_Agent.md)：逐家拆解主流厂商怎样生产、治理和召回知识。
9. [`reports/09_DbCC论文人类精读与公式拆解.md`](reports/09_DbCC论文人类精读与公式拆解.md)：把 DbCC 的全部变量、公式和四个算子翻译成人话，并逐项映射官方代码和本机结果。
10. [`reports/10_CSR_RAG人类精读与代码梳理.md`](reports/10_CSR_RAG人类精读与代码梳理.md)：用一个问题讲清 Contextual、Structural、Relational 三段召回和知识图谱的实际使用位置。
11. [`reports/11_两篇论文复现过程与结果评价.md`](reports/11_两篇论文复现过程与结果评价.md)：记录输入、中间产物、命令、指标、失败边界以及两篇方法如何组合。

两篇论文及可执行代码分别位于 [`paper/`](paper/README.md) 和 [`workspace/`](workspace/README.md)。旧的失败日志、项目完成性审计和机器证据索引已从阅读主线移到 [`archive/legacy_reports/`](archive/legacy_reports/README.md)，内容没有删除。

## 本机最终结果

| 路线 | 系统 | 实际执行内容 | 终态 |
|---|---|---|---|
| 1 | MetricFlow | dbt 构建、语义校验、dataflow/SQL 编译、DuckDB 查询 | 通过 |
| 1 | Cube | 官方 Docker、REST `/sql`、REST `/load`、真实 DuckDB 查询 | 通过 |
| 1 | WrenAI | MDL 校验/编译、cube 查询、dry-plan、官方 MCP 调用 | 通过 |
| 1 | 自然语言规划补充实验 | 30 次真实 LLM 调用；最终 10/10 判断正确，4/4 DSL 执行结果正确 | 通过 |
| 2 | DataHub | 全新 quickstart、schema/view/lineage/query-log 采集、SDK 丰富、官方 MCP | 通过 |
| 2 | OpenMetadata | 全新 1.13.0、MySQL 连接器、Python SDK、内置 `/mcp` | 通过 |
| 3 | LinkedIn Text-to-SQL | 按论文公开架构重建；FastICA、多个索引、5 次真实 LLM 调用、纠错 | 通过 |

统一问题是：

> 请统计 ORG_1001 在 2026 年上半年按产品一级分类的设备订货金额和设备利润，只统计已确认订单。

六套主体实验和路线一补充实验最终都围绕同一口径得到：

| 产品一级分类 | 设备订货金额 | 设备利润 |
|---|---:|---:|
| Compute | 7,500 | 1,560 |
| IoT | 3,400 | 650 |
| Network | 3,800 | 730 |

## 证据在哪里

- `demos/common/`：统一合成数据、物理元数据、词汇表和 golden result。
- `demos/route1/`：三种可执行语义层项目及最终结果。
- `demos/route1/nl_to_dsl/`：Cube/Wren 的完整 LLM messages、原始响应、两轮失败、最终 DSL 和引擎执行。
- `demos/route2/`：两种元数据平台的采集 recipe、SDK/MCP 客户端与原始返回。
- `demos/route3/`：LinkedIn 路线的输入、知识图谱索引、每次 LLM 调用和纠错轨迹。
- `runs/20260804-route-demo/`：首次探索运行，保留所有失败和调整。
- `runs/20260804-clean-verification/`：从清空状态复跑的每步请求、标准输出、错误输出、退出码和产物哈希。
- `runs/20260804-nl-to-dsl/`：自然语言规划三轮实验、30 次真实调用、最终执行和清理记录。
- [`archive/legacy_reports/evidence_manifest.json`](archive/legacy_reports/evidence_manifest.json)：早期洁净复跑的机器可读索引；7 套终态检查全部通过。
- [`workspace/run_logs/run_manifest.json`](workspace/run_logs/run_manifest.json)：两篇论文本轮复现的 7 步命令、耗时、退出码和日志索引。
- [`workspace/verification.json`](workspace/verification.json)：本轮两项复现的跨实验最终验证。

## 版本快照

- MetricFlow `0.211.0`，dbt-metricflow `0.13.0`，dbt-core `1.11.12`，dbt-duckdb `1.10.1`
- Cube `cubejs/cube:latest`，本次镜像摘要 `sha256:4d479d545003...`
- WrenAI `0.13.2`，wren-core-py `0.7.3`，MCP `1.29.0`
- DataHub CLI `1.6.0`，GMS `v1.5.0.6`，官方 MCP server `0.6.0`
- OpenMetadata server `1.13.0`，openmetadata-ingestion `1.13.0.0`
- LinkedIn 路线：论文公开架构重建，不冒充其未公开的生产代码

## 密钥与本地状态

实验只在 LinkedIn 重建路线和路线一自然语言规划补充实验的运行时读取相邻 `data-ex/.env` 中的大模型配置。`.env`、JWT、数据库持久卷、虚拟环境、vendor 源码和本地数据库均被忽略，不进入 Git。日志记录模型名、调用次数、完整 messages 和是否 fallback，但不记录 API key 或 base URL。
