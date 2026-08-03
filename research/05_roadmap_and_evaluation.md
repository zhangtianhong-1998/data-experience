# 分阶段路线图与评估体系

## Phase 0：语料与评测基座

目标：先让“好坏”可测。

- 固化 source namespace、snapshot、occurrence 和 run manifest。
- 选 2–3 个业务域，抽取 200–500 个代表性组件，而不是随机全量。
- 建立最小人工 gold：表/字段 lineage、候选指标、同名不同义、同义不同名、过滤/粒度冲突。
- 错误 taxonomy：parse、wrong table、wrong column、wrong join、wrong filter、wrong grain、wrong metric、permission、stale definition。

退出条件：任何新算法都能在固定数据上报告 precision/recall、false merge 与运行成本。

## Phase 1：确定性 Fact Plane

目标：把现有正则升级为可扩展 SQL 事实层。

- 集成 SQLGlot，按来源系统路由方言。
- 输出 AST facts、alias map、column dependencies、filter/grain/join facts 和多种 fingerprint。
- 解析失败、缺 schema、ambiguous column 作为显式状态。
- 将 QueryOccurrence 与去重 QueryDefinition 分开。

核心指标：

- parse coverage（按 BI 引擎/方言/复杂度分层）。
- table/column lineage precision、recall。
- schema 保留率、unresolved reference 率。
- 每万 SQL 的 CPU、内存和延迟。

退出条件：代表语料 parse coverage ≥95%，高频方言表级 lineage precision ≥99%，字段级 gold 达到可接受基线。

## Phase 2：Claim Ledger 与局部语义

目标：不做全局知识图谱，先形成可追溯的局部 claim。

- 为 alias、description、path term、formula、relation、policy 建统一 claim schema。
- 引入 negative knowledge 和冲突检测。
- 构建 domain-local lexical/implementation indexes。
- 确定性重复 claim 自动折叠，但保留 occurrence 和来源频次。

核心指标：provenance completeness、claim 冲突发现率、重复压缩率、更新幂等性。

退出条件：任意候选语义能回溯到原始单元格/SQL 片段/元数据字段与处理版本。

## Phase 3：保守实体解析

目标：证明可以在有限人工下扩大，但不引入大规模误合并。

- 为 term、field、dataset、metric 分别设计 blocking 和 feature。
- 用 labeling functions 组合强规则、弱规则和否定规则。
- 对高价值 block 使用 LLM rerank，不做全量 pair 调用。
- 使用 cannot-link 的约束聚类；建立 review queue 和 active sampling。

核心指标：

- blocking pair reduction 与 candidate recall。
- pair precision/recall、PR-AUC。
- cluster B-cubed precision/recall、variation of information。
- weighted false merge rate：指标/权限/财务口径权重最高。
- 每个人工审核小时确认的高价值实体数。

退出条件：高风险类型的自动 merge precision 达到业务可接受阈值；达不到时保持 proposed，不以覆盖率换精度。

## Phase 4：可执行语义与 Catalog 发布

目标：让 approved 知识变成可验证能力。

- 将批准的局部域导出到 WrenAI；并与 Cube/MetricFlow 至少比较一个。
- 输出 Apache Ossie 作为交换格式，但保留内部 claim/evidence 扩展。
- 对 DataHub/OpenMetadata 做同场景 bake-off，不先做全量重平台化。
- 实现 shape validation、版本、owner、policy、deprecation 和 rollback。

核心指标：导出无损率、SQL compile 成功率、定义冲突率、回滚耗时、权限策略一致性。

退出条件：至少一个业务域可从 source evidence 重建到 approved metric，并在运行时生成确定 SQL。

## Phase 5：Data Agent 闭环

目标：以真实任务证明知识资产有用。

- 构建四类索引：asset/schema、query example、term/rule、usage/join。
- permission-aware 高召回检索 + table rerank + column expansion。
- writer 优先使用 approved semantic API；验证器检查 schema、policy、filter、grain 和 dialect。
- UI 显示假设、来源、状态、参考查询和未满足信息。
- 将用户改 SQL、采纳、拒绝、澄清与 review 结果写回反馈层。

### Agent 指标

- table recall@K、column recall@K、metric selection accuracy。
- join/filter/grain correctness。
- compilation rate、schema hallucination rate。
- policy violation rate（目标必须为 0）。
- provenance/citation coverage 与正确 abstention 率。
- 端到端语义评分、用户修改距离、采纳率、重复使用率。
- p50/p90 latency、LLM/embedding/DB 调用数和单任务成本。

### 必做消融

- schema only。
- + 别名/备注。
- + 历史 query examples。
- + usage/table clusters。
- + glossary/domain knowledge。
- + approved metrics。
- + feedback memory。

若某类知识加入后降低质量，就应改进检索或降低权重，而不是继续扩大上下文。

## 无行数据条件下能验证什么

可以验证：

- SQL parse、表列 lineage、表达式、filter、grain、join、dialect compile。
- 语义定义一致性、证据完备性、冲突、权限和版本。
- table/column/metric retrieval、query plan 与人工语义评审。

不能充分验证：

- 数值正确性、分布、枚举值含义、真实基数与数据质量。
- 参数过滤的实际业务取值和单位。

因此生产上线前仍需只读 EXPLAIN/VALIDATE、受控采样或由数据平台返回的统计元数据；没有这些时 Agent 必须能 abstain。

## 最近四个实施增量

1. 将本实验 AST extractor 合入 pipeline 的新 fact builder，旧正则保留为 fallback。
2. 设计 `claim.schema.json` 与 20–30 条 shape rules，迁移现有 evidence。
3. 从真实样例扩到一个业务域，建立 100 对 match/non-match gold 与 30 个 Agent 问题。
4. 对 WrenAI + DataHub/OpenMetadata 选出的一个 catalog 做端到端小域发布和消融测试。

