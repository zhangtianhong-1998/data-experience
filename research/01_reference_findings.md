# 外部工程实践筛选结论

更新时间：2026-08-03

本文件不做产品选型，而是回答：现有工程实践中，哪些结构可以进入本项目，
哪些前提不适用于“从已有 BI 资产中发现语义”的场景。

## 1. 可借鉴部分

| 参考实践 | 可借鉴结构 | 本项目中的位置 | 不直接照搬的原因 |
|---|---|---|---|
| Apache Ossie | dataset、field、metric、relationship、SQL dialect expression | 经过审核的部门/集团语义导出格式 | Ossie 描述的是已经定义好的语义模型，不负责保存模型从哪些报表证据中发现，也不负责未决 claim |
| dbt Semantic Layer / MetricFlow | entity、dimension、metric type、aggregation、filter、time grain | 指标实现结构和 Agent 消费模型 | 它假设语义模型已由工程人员维护；本项目面对的是未整理、可能冲突的历史资产 |
| DataHub | entity、aspect、URN、ownership、dashboard/chart/dataset 关系 | 资产层、部门归属、可独立更新的元数据切面 | 不需要把整个 DataHub 引入原型；借鉴“稳定资产身份 + 独立 aspect”即可 |
| OpenMetadata | dashboard/table/column lineage、owner、domain、quality status | 资产映射、血缘、质量问题、影响分析 | 它适合数据目录，但不能替代本项目的语义 claim、证据等级和保守对齐 |
| OpenLineage | Job 与 Run 分离、静态元数据与运行实例分离、facet 扩展 | 抽取运行、源快照、LLM 调用及结果版本 | BI 查询不是完整 ETL 作业；只借鉴运行与设计事实分离 |
| SQLGlot | 多方言 AST、projection、filter、join、column lineage | L0/L1 确定性 SQL 事实 | AST 角色不是业务含义；聚合列只能叫 measure candidate，不能自动叫集团指标 |
| Splink blocking | 多个严格 blocking rule、候选数分析、倾斜块识别 | 部门内跨报表候选生成 | Splink 面向记录链接；本项目只借鉴“先 blocking 后判断”，不使用其概率作为语义置信度 |
| JSON Schema / Pydantic | 结构化输出契约、严格解析、错误分类 | LLM 输出解析、版本化和程序校验 | 结构合法不代表语义正确，仍必须校验证据引用和业务约束 |
| Spider 2.0 / BIRD | 执行正确率、真实企业元数据检索难度 | Data Agent 对照评测 | 公共榜单不能替代企业内部指标、别名、口径和权限知识的验证 |

## 2. 参考资料

- Apache Ossie：https://ossie.apache.org/
- dbt Semantic models：https://docs.getdbt.com/docs/build/semantic-models
- dbt Metrics：https://docs.getdbt.com/docs/build/metrics-overview
- DataHub metadata model：https://docs.datahub.com/docs/metadata-modeling/metadata-model
- DataHub lineage：https://docs.datahub.com/docs/features/feature-guides/lineage
- OpenMetadata lineage：https://docs.open-metadata.org/v1.12.x/how-to-guides/data-lineage/explore
- OpenLineage object model：https://openlineage.io/docs/spec/object-model
- OpenLineage facets：https://openlineage.io/docs/spec/facets/
- SQLGlot lineage：https://sqlglot.com/sqlglot/lineage.html
- Splink blocking：https://moj-analytical-services.github.io/splink/topic_guides/blocking/blocking_rules.html
- JSON Schema 2020-12：https://json-schema.org/draft/2020-12
- Pydantic JSON validation：https://pydantic.dev/docs/validation/latest/concepts/json/
- Spider 2.0：https://spider2-sql.github.io/
- BIRD：https://bird-bench.github.io/

## 3. 对当前工程的直接决策

1. 不把 Ossie、dbt 或 Wren 的“已发布语义模型”直接作为 LLM 首轮输出。
2. 首轮输出必须是有证据、有限作用域、可撤销的 claim。
3. 物理表继续使用完整限定表名作为唯一键；物理字段使用“表名 + 字段名”，
   不额外暴露一批随机 ID。
4. Report、Component、Dataset 在源平台没有稳定 ID 时使用可读 ref 和
   `identity_status=provisional`，以后拿到平台 ID 再映射，不偷偷假装已经稳定。
5. SQL AST、字段血缘、缺失值和源映射由程序生成；LLM 不重复解析这些确定性事实。
6. 报表级一次抽取覆盖全部组件；额外校验和对齐调用由异常或候选触发。
7. 部门是第一轮 blocking 边界；集团语义只接收已经在部门实验中被验证的结果。

