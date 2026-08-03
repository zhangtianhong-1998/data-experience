# 公开方案与研究全景

## 1. 行业已经形成的共同认识

问题已经从“让 LLM 看 schema 写 SQL”转向“为 Agent 提供经过治理、可检索、可执行的业务上下文”。最贴近本项目的公开证据是 LinkedIn 的 [Text-to-SQL for Enterprise Data Analytics](https://arxiv.org/abs/2507.14372)：他们把表结构、文档、代码、历史查询、常用 join、组织术语与权限组织为知识图谱，并使用高召回检索、排序、写 SQL、验证与反馈链路。

该研究最重要的工程结论不是某个模型分数，而是：

- 示例查询、表/列属性和按团队/产品域形成的表簇，对语义正确性贡献最大。
- 只提供 schema 的企业效果很差；模型能力无法替代高质量知识。
- 不相关的领域知识和术语会污染上下文，因此需要检索与路由，而不是全量塞入 prompt。
- 编译成功不等于语义正确；错误过滤条件比错误 join 更常见。
- 多次生成或复杂 planner 未必提升质量，反而可能增加延迟和嵌套错误。

这与本项目的方向一致：知识构建和知识消费必须共同设计，并通过下游效用反向评价上游知识。

## 2. 元数据目录与治理平台

### DataHub

[DataHub](https://docs.datahub.com/) 提供资产发现、lineage、usage/query history、glossary、domain、data product、structured properties、logical models、proposal workflow 与权限。其 [MCP Server](https://docs.datahub.com/docs/features/feature-guides/mcp) 已能让 Agent 搜索资产、查询 lineage、获取真实历史 SQL、寻找 SQL context、草拟 SQL，并通过 proposal 而不是直接写入来治理 Agent 产生的元数据。

适合复用：元数据服务、检索、版本、权限、变更提案、Agent 工具面。

不解决：从海量 BI SQL 自动发现业务概念、确定统计口径、保守实体融合。

### OpenMetadata

[OpenMetadata](https://github.com/open-metadata/OpenMetadata) 具备 glossary、synonym、related term、层级、metric、lineage、policy、contract、data product 与版本历史。其 [AI SDK/MCP](https://docs.open-metadata.org/v1.12.x/api-reference/sdk/ai-sdk) 将描述、owner、lineage、glossary、tag 和质量结果作为 Agent 工具；[Metric](https://docs.open-metadata.org/v1.12.x/how-to-guides/data-governance/metrics) 可连接数据资产与其他指标；[Data Contract](https://docs.open-metadata.org/v1.12.x/api-reference/data-contracts) 可约束 schema、semantics、security、SLA 和 terms of use。

适合复用：治理实体、glossary/metric/contract、审批与 Agent context。

不解决：自动语义挖掘与无标注实体消歧。

### Apache Atlas

[Apache Atlas Glossary](https://atlas.apache.org/2.0.0/Glossary.html) 支持 glossary、term、category、层级与资产关联。它证明了 glossary/asset 关联的经典模型，但对本项目当前的 Agent、query history 和现代语义运行时需求不如前两者直接。

## 3. Lineage 与 provenance 标准

[OpenLineage](https://github.com/OpenLineage/OpenLineage/blob/main/spec/OpenLineage.md) 的核心是 Run Event、Job、Dataset、Run 和 Facet，且允许使用带不可变 schema URL 的 custom facet。它适合描述一次采集、解析、融合或发布活动如何使用输入并生成输出。

[W3C PROV-O](https://www.w3.org/TR/prov-o/) 提供 Entity、Activity、Agent 以及 wasDerivedFrom、used、wasGeneratedBy、wasAttributedTo 等通用 provenance 语义。

建议不是全盘 RDF 化，而是：内部事件和 claim 模型与 OpenLineage/PROV 的概念对齐，必要时提供映射或导出。

## 4. 语义层与指标执行

### Apache Ossie（原 OSI）

[Apache Ossie](https://ossie.apache.org/) 是 2026 年进入 Apache Incubator 的语义交换规范，原名 Open Semantic Interchange。当前仓库的 core spec 为 `0.2.0.dev0` draft，表达 dataset、field/dimension、relationship、metric、方言表达式与 AI context，并提供 dbt、Databricks、Snowflake、GoodData 等 converter。

定位：批准后的语义定义交换格式。

边界：仍处于快速演进；provenance、候选状态、冲突证据、否定知识与审批历史不是其核心模型。

### MetricFlow

[MetricFlow](https://github.com/dbt-labs/metricflow) 把指标定义编译成可复用 SQL，支持多跳 join、ratio/expression/cumulative metric 和不同时间粒度。0.209.0 以后采用 Apache 2.0，并参与 Ossie/OSI。

定位：已知且经过工程化定义的指标编译器。

边界：需要事先编写 semantic model，不负责从 BI 资产发现它们。

### Cube

[Cube](https://docs.cube.dev/reference/data-modeling/cube) 提供 measure、dimension、join、hierarchy、segment、pre-aggregation 和 [access policy](https://docs.cube.dev/docs/data-modeling/access-control/index)。

定位：可执行语义 API、缓存和访问控制。

边界：更像服务已确认定义的运行时，不是证据融合引擎。

### Malloy

[Malloy](https://github.com/malloydata/malloy) 将可复用 dimension、measure 和 join 与查询语言结合，适合作为语义建模语言参考。它同样假设模型由人或上游系统提供。

## 5. Agent-ready context 与 Data Agent

### WrenAI

[WrenAI](https://github.com/Canner/WrenAI) 当前定位为 Agent 的开放 context layer。MDL 描述模型、关系、计算与治理；Rust/DataFusion 引擎把语义 SQL 翻译到多种数据源；CLI、Python SDK、memory、cube 和 MCP 提供消费面。

本地实验验证了它适合作为早期 Agent 运行时，但不应成为内部 evidence/claim 真相模型。详见 `06_experiment_results.md`。

### DataHub / OpenMetadata MCP

二者都已把元数据图谱暴露为 Agent 工具。关键模式是：

- 先按用户身份和 domain/view 限制可见资产。
- 检索 metadata、usage、lineage、质量、历史 SQL 和组织知识。
- 修改元数据优先进入 proposal/approval，而不是 Agent 直接提交。
- 把治理、搜索和 SQL 草拟拆成多个工具。

### Vanna、DB-GPT、MindsDB

[Vanna](https://github.com/vanna-ai/vanna) 强调成功 NL-SQL 记忆、用户感知工具与权限，但仓库已于 2026-03-29 归档，不宜作为长期核心依赖。

[DB-GPT](https://github.com/eosphoros-ai/DB-GPT) 和 [MindsDB Engine](https://mindsdb.github.io/engine/) 提供更完整的 Agent/知识库/工作流能力，可作为交互编排参考；它们并不替代专门的语义挖掘和治理层。

## 6. 术语、同义与层级

[SKOS](https://www.w3.org/TR/skos-reference/) 非常适合约束概念层的关系语义：

- `prefLabel`、`altLabel`、`hiddenLabel`：首选名、同义/替代名、隐藏检索名。
- `broader` / `narrower`：直接层级。
- `related`：关联但非上下位。
- `exactMatch` / `closeMatch`：跨 scheme 映射强度。

这能防止把“近义、相关、上下级、同一个”都压成一个 `sameAs`。

[SHACL](https://www.w3.org/TR/shacl/) 可用于验证图形约束，例如：approved 指标必须有表达式、粒度、owner、证据；同一 concept scheme 的 prefLabel 唯一；exactMatch 不能与明确冲突边共存。即使内部不采用 RDF，也应实现等价的 shape validation。

## 7. 实体解析与弱监督

[Splink](https://moj-analytical-services.github.io/splink/topic_guides/blocking/blocking_rules.html) 展示了大规模实体解析的通用结构：blocking 控制候选对规模，概率模型进行 pair scoring，再进行 clustering。百万实体全比较约为 5000 亿对，因此候选生成必须是一等公民。

[Ditto](https://github.com/megagonlabs/ditto) 将 entity matching 转为预训练语言模型的序列对分类，但需要标注候选对，且公开依赖版本较旧，不适合作为第一阶段依赖。

[Panda](https://arxiv.org/abs/2106.10821) 和 [弱监督实体匹配的 ground-truth inference](https://arxiv.org/abs/2211.06975) 使用 labeling functions、label model 与传递性约束，说明可以把已有启发式、物理血缘、命名规范和历史行为组合成弱监督信号。但 labeling function 本身仍需要工程设计和小规模验证。

建议：借鉴 Splink/Panda 的流程，不直接把“概念消歧”简化为 embedding top-k 或一次 LLM 判断。

## 8. 评测基准

[Spider 2.0](https://spider2-sql.github.io/) 有 632 个企业级 workflow，数据库常超过 1000 列，且包含 68 个 DBT 仓库任务；它证明长上下文、多方言、多步工作流才是企业真实难度。

[BIRD-Interact](https://bird-interact.github.io/) 将 hierarchical knowledge base、文档、用户模拟器和可执行测试结合，并提供 conversational/agentic 两种模式；2026 年发布的 LiveSQLBench-Large 还加入 business-rule drift。

本项目不应直接用它们替代内部评测，但应借鉴：动态知识、交互澄清、执行测试、成本预算和持续更新。

## 9. 全景结论

公开生态可以提供 70% 的基础设施，但核心 30% 仍需自行构建：

```text
可复用：SQL AST、catalog、lineage 标准、术语关系、语义运行时、Agent 工具协议、ER 方法
必须自建：BI 资产适配、claim ledger、多证据融合、保守消歧、生命周期、内部评测与提升策略
```

