# 能力矩阵与复用决策

评级：强 / 中 / 弱 / 无。评级针对本项目需求，不代表项目总体质量。

| 方案 | 自动发现 | Provenance/lineage | 概念/指标表达 | 治理/权限 | Agent 消费 | 本项目定位 |
|---|---|---|---|---|---|---|
| SQLGlot | 强：AST 事实 | 弱 | 中：表达式结构 | 无 | 间接 | 立即采用为 SQL 事实抽取内核 |
| OpenLineage | 无 | 强 | 弱 | 中 | 间接 | 采集/处理事件与 facet 对齐标准 |
| DataHub | 弱 | 强 | 中 | 强 | 强：MCP、query context | 候选 metadata serving/control plane，不做挖掘内核 |
| OpenMetadata | 弱 | 强 | 强：metric/glossary/contract | 强 | 强：AI SDK/MCP | 候选治理后端，与 DataHub 做场景 bake-off |
| Apache Ossie | 无 | 弱 | 强：可移植 dataset/field/metric | 弱 | 中 | 仅发布 approved semantics；不做内部 claim store |
| MetricFlow | 无 | 中 | 强：指标编译 | 中 | 中 | 成熟指标域的执行候选 |
| Cube | 无 | 中 | 强 | 强：行/列访问策略 | 强：API | 需要缓存、API 和严格访问控制时的执行候选 |
| WrenAI | 弱 | 中 | 强：MDL/cube/context | 中 | 强：CLI/SDK/MCP | 最适合当前快速验证 Agent 消费链路 |
| Malloy | 无 | 弱 | 强 | 弱 | 中 | 建模语言参考，不列为首个运行时 |
| SKOS | 无 | 无 | 强：术语/层级/映射 | 弱 | 间接 | 采用语义子集约束概念关系 |
| PROV-O | 无 | 强 | 弱 | 弱 | 间接 | 采用轻量 profile 描述 claim 推导 |
| SHACL | 无 | 中 | 中 | 中 | 间接 | 为 approved concept/metric 建 shape validation |
| Splink | 中：候选/匹配 | 弱 | 无 | 无 | 无 | 借鉴 blocking、概率匹配和规模分析；需自定义特征 |
| Ditto | 中 | 弱 | 无 | 无 | 无 | 有标签数据后再评估；当前依赖与成本不优先 |
| Panda/弱监督 EM | 中 | 中 | 无 | 无 | 无 | 用 labeling functions 组合弱证据的方法参考 |
| LinkedIn 企业方案 | 强：参考架构 | 强 | 中 | 强 | 强 | Agent 检索、索引、排序、验证和消融评测的主要蓝本 |

## 推荐组合

### 现在就采用

- SQLGlot AST + 原始 SQL 保留 + 方言路由 + 失败降级。
- claim-first 内部模型，provenance 与 OpenLineage/PROV 概念对齐。
- SKOS 风格关系词表，严格区分 exact、close、related、broader/narrower。
- 自建 blocking 与 pair feature 管线；先规则/统计，后模型。
- WrenAI 作为轻量消费试验场，验证知识能否变成确定 SQL。

### 经过 bake-off 后选择

- DataHub 与 OpenMetadata 二选一或分工：重点测试 query history、logical model、metric/glossary、proposal、权限和 MCP 的 OSS/商业边界。
- WrenAI、Cube、MetricFlow：按现有技术栈、权限模型、缓存需求和指标复杂度选择运行时，不强求全局唯一。

### 暂不作为核心依赖

- 图数据库：先证明图查询是瓶颈，再选 Neo4j/RDF store；早期可用关系库 + 对象存储 + 搜索索引。
- Ditto/大模型匹配器：没有高质量候选对与评测集时，复杂模型只会隐藏 false merge。
- Vanna：概念可借鉴，但已归档。

## 平台选择的验收问题

对 DataHub/OpenMetadata 不能只做 feature checklist，应使用同一批真实资产回答：

1. 能否保留来源级、字段级、query occurrence 级 provenance？
2. proposed 与 approved 语义能否隔离检索和执行？
3. Agent 是否继承用户权限，搜索结果是否在召回前就被过滤？
4. 历史 SQL、常用 join、usage、glossary、metric 是否能被同一查询面检索？
5. 是否支持 proposal/approval、版本、回滚和变更影响分析？
6. 百万组件规模下的写入、更新、索引和多跳查询成本如何？
7. 核心能力在 OSS 还是商业版本，升级路径和数据可迁移性如何？

