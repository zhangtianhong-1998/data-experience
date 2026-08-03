# 本地项目基线

## 1. 当前原型已经具备的价值

现有 `bi_semantic_pipeline.py` 不是生产系统，但已经确立了几个正确方向：

- 保留报表、组件、数据集、SQL、物理表的嵌套结构，而不是先压平成一张表。
- 生成 evidence 与 evidence package，并要求 LLM 输出引用证据 ID。
- LLM 只产生 annotation、relation 和 unresolved，不允许无证据扩写事实。
- 记录输入哈希、模型、prompt、schema 和运行清单，具备可复现意识。
- 对默认组件名、缺失物理表、重复 SQL、多查询组件等异常显式建模。

这些能力适合继续作为“证据流水线”的原型，而不应直接扩成一个把所有结果写入知识图谱的单体程序。

## 2. 当前主要技术缺口

| 位置 | 当前方式 | 主要风险 | 建议 |
|---|---|---|---|
| SQL 解析 | FROM/JOIN 正则与轻量表达式处理 | 丢失 schema、CTE、嵌套查询、字段依赖、方言语义 | AST 解析为主，正则仅降级 |
| 证据模型 | evidence 文本片段 | 缺少 claim 状态、有效期、推导活动和否定知识 | 增加 claim ledger 与 provenance |
| 实体融合 | 尚未形成独立层 | 同名误合并、链式传递污染 | blocking → pair scoring → constrained clustering |
| 语义生命周期 | annotation 结果 | proposed 与 certified 混在同一输出层 | 状态机与审批/自动提升策略 |
| Agent 消费 | evidence package 直接进 LLM | 上下文过宽、权限和可信度边界弱 | 多索引检索、rerank、策略过滤、可执行语义层 |
| 评估 | 结构校验为主 | 不知道知识是否真正改善 Agent | 构建质量与 Agent 效用双层评估 |

## 3. 真实样例观察

对 `示例表.xlsx` 的无 LLM 基线运行得到：

- 15 条源记录、2 个报表、9 个组件、4 个数据集路径、10 条去重 SQL。
- 5 个重复 SQL 组，1 个组件存在两个查询变体。
- 组件名均为“图表N”一类系统名，不能当作业务语义。
- 真实业务信息主要藏在输出别名、聚合表达式、过滤字段和数据集路径中。
- 临时物理表字段是 `c2`、`c7`、`c27` 等技术名，且当前物理元数据无法匹配。
- 反复出现的候选包括“年月”“产品LV1”“内部分类”“设备订货”“设备利润”，但它们仍只是局部 claim。

因此，当前资产最有价值的不是一段完整的自然语言描述，而是大量可组合的弱证据：

```text
SQL AST 结构 + 中文输出别名 + 数据集/报表路径 + 重复使用行为
+ 物理字段元数据 + 血缘 + 历史查询 + 权限上下文
```

## 4. 本地验证状态

- bundled Python 下单元测试：3/3 通过。
- pipeline self-test：通过。
- 真实样例基线输出：`outputs/local_example_baseline/`。
- SQLGlot、Claim 消歧、WrenAI/Ossie 实验详见 `06_experiment_results.md`。

## 5. 基线结论

下一阶段优先级应是：

1. 把 SQL 中确定可解析的结构升级为一等事实。
2. 在 canonical concept 之前引入 claim ledger。
3. 用小型标注评估集测量 false merge，而不是先扩大 LLM 生成量。
4. 将“挖掘内核”与“目录/图存储”“可执行语义层”“Agent”解耦。

