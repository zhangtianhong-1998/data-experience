# 部门级 BI 语义发现实验架构

更新时间：2026-08-03

## 1. 第一轮实验边界

第一轮只选择一个部门及其一小组报表。部门归属来自实验配置或已有组织映射，
不能仅凭路径片段自动确认为事实。路径中的组织名称只能生成候选。

```text
四类源文件
  → 源快照与质量检查
  → 数据资产映射
  → SQL AST 与字段实现事实
  → 报表级证据包
  → 报表局部语义 claim
  → 部门内候选发现
  → 保守对齐/冲突保留
  → Data Agent 四组对照评测
```

## 2. 六层数据职责

### L0 源快照

保存文件指纹、行号、原始值和加载状态。原始值不被覆盖。路径规范化、去重和
缺失检查是派生结果。

### L1 数据资产与实现事实

保存 Report → Component → Dataset → Query → Table/Field 的映射、字段血缘和
SQL AST 事实。这里的事实必须由规则或解析器复算。

### L2 证据与报表局部声明

LLM 生成 `ConceptMention` 和 `SemanticClaim`，每条声明包含报表作用域、
组件/查询/字段引用、证据引用、缺失信息和抽取运行。此层不产生集团真值。

### L3 部门语义

在同一部门内生成候选对，关系可以是 `equivalent`、`variant`、`broader`、
`narrower`、`related`、`conflict` 或 `insufficient`。默认保留原局部 claim；
只有明确策略允许时才生成部门概念簇。

### L4 集团标准语义

多个部门验证后才能进入。第一轮仅保留接口和作用域字段，不自动构建。

### L5 Agent 运行与反馈

记录问题、可见上下文、召回候选、生成 SQL、执行结果、正确资产、错误类型和
人工结论。反馈不能直接修改语义，只能生成新的修订任务。

## 3. 身份与引用策略

用户可见输出优先使用可读引用，不用无意义的随机 ID：

```text
report://<规范化报表路径>
component://<report-ref>/<报表内组件号>
dataset://<规范化数据集路径>
query://<component-ref>/<SQL序号>
table://<catalog.schema.table>
field://<catalog.schema.table>/<column>
evidence://<证据包>/<局部序号>
mention://<report-ref>/<局部序号>
claim://<report-ref>/<局部序号>
```

- 有 BI 平台原生 ID 时，`source_id` 才是稳定主身份。
- 暂时没有平台 ID 时，ref 标记为 `provisional`；路径变更可通过映射表迁移。
- 表名和字段名本身唯一时不额外创建用户可见 ID。
- 哈希只保存到 `fingerprint` 字段，用于变更检测、缓存和审计，不替代语义。

## 4. 各阶段最小输出

### Stage A：`source_snapshot.json`

```json
{
  "run_ref": "ingest://2026-08-03T...",
  "sources": [{"path": "...", "sha256": "...", "row_count": 16}],
  "issues": [{"source_ref": "...#row=8", "code": "missing_sql", "message": "..."}]
}
```

### Stage B：`asset_graph.json`

以报表为根保存组件、一个组件使用的数据集、SQL 列表、物理表、字段血缘、
映射状态和部门归属。物理元数据保留源 JSON 结构，只在每张表最后追加文字
`status`，符合此前已经确认的约束。

### Stage C：`sql_facts.jsonl`

每条 SQL 保存：

- 原文、清洗文本、解析状态和方言；
- 表、字段、投影表达式、聚合、Join、Filter、Group By、Order By；
- 精确 fingerprint；
- 参数化结构 signature（仅供缓存/候选检索，不能证明语义相同）；
- 解析错误和正则降级结果。

### Stage D：`report_evidence_packages.jsonl`

每个报表一个包，包含全部组件及相关 SQL 事实、物理字段注释、字段血缘和映射。
包内每个可引用事实有可读 `evidence_ref`。超出上下文预算时按组件簇拆包，并在
报表汇总步骤合并 claim，不按单组件反复调用模型。

### Stage E：`report_extractions.jsonl`

LLM 一次返回四类内容：

1. 报表目的和分析对象；
2. 概念提及：实体、事件、指标、度量、维度、属性、术语、枚举、规则；
3. 指标实现：表达式、聚合、过滤、粒度、维度、单位、时间语义；
4. 概念关系、疑似同义、口径变体、冲突和未决信息。

每项必须引用输入资产和 evidence；不输出模型自评分。程序依据证据种类计算
`evidence_grade`，模型只描述依据和不确定点。

### Stage F：`department_alignment_candidates.jsonl`

候选召回使用多个 blocking 信号：规范标签、概念类型、共同字段实现、共同业务表、
共同数据集、字符/语义相似度。公共表和高频通用标签降权。候选分数只表示检索排序，
不表示概念相同概率。

### Stage G：`department_alignment_decisions.jsonl`

LLM 只判断 Top-K 候选，并必须比较名称、定义、表达式、聚合、过滤、粒度、单位、
时间范围和组织作用域。`insufficient` 是正常结果，不要求强制二选一。

### Stage H：`agent_evaluation.json`

固定问题、固定模型参数、固定输出 schema，分别运行四种上下文：

```text
A 物理元数据
B 物理元数据 + 资产/SQL事实
C B + 报表局部语义
D C + 部门语义
```

## 5. 提示词协议

提示词不写死在一个四千行程序中，拆成版本化文件：

- `prompts/report_system.md`
- `prompts/report_extraction.md`
- `prompts/department_alignment.md`
- `prompts/agent_answer.md`
- `schemas/report_extraction.schema.json`
- `schemas/department_alignment.schema.json`
- `schemas/agent_answer.schema.json`

调用时记录 prompt 文件 hash、schema hash、模型、温度、输入 hash、响应原文、
解析结果、程序校验结果和 token/耗时。默认不做第二轮；JSON 语法错误可选一次纯语法
修复，证据越界或业务约束失败直接进入失败队列，不能让模型偷偷改写事实。

## 6. 自动合并边界

第一轮原型不把大模型的 `equivalent` 直接变成全局合并。自动动作仅允许：

- 同一报表内完全相同的 observation 去重；
- 同一部门、同类型、非通用标签、相同实现与相同限定条件的局部重复折叠；
- 其他情况只写关系，不删除原始 mention/claim。

