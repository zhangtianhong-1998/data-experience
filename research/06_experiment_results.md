# 本机实验结果

实验日期：2026-08-03。所有实验均未访问真实行数据。

## 1. SQLGlot AST 事实抽取

环境：Python 3.13.2，SQLGlot 30.14.0。代码：`experiments/sqlglot_fact_extractor.py`。

### 真实样例

输入：`outputs/local_example_baseline/facts.json`

- 10/10 查询成功解析。
- 24 个投影：10 个结构性 dimension candidate，14 个 measure candidate。
- 表名与当前正则结果一致。
- 能提取 alias map、完整 schema.table、投影表达式、聚合、字段依赖、filter、group/order、limit 和 placeholder。

### 模拟噪声集

输入：`outputs/bi_semantic_demo_v2/facts.json`

- 12/13 查询成功解析；唯一失败是空 SQL，不是方言错误。
- 现有正则与 AST 的完整表名 0/12 一致，但忽略 schema 后 12/12 一致。
- 这证明当前正则系统性丢失 schema，可能把不同库/域的同名表错误融合。

结论：AST 应进入 L0/L1 确定事实层；`measure_candidate` 仅描述聚合结构，不自动成为业务指标。

## 2. Claim 消歧审计

代码：`experiments/claim_ambiguity_audit.py`。输出：`outputs/research_claim_audit/`。

- 53 个投影 claim、23 个规范化标签、27 种实现签名。
- `LONG_COL_0` 出现 7 次，对应 3 种实现：不同表的 SUM 和 MAX。该标签完全不可用于业务融合。
- “日期”出现 4 次，对应日历表 `calendar_date` 与设备状态 `stat_date` 两种实现。
- “月份”来自销售订单和回款事实两个域，不能因同名自动 sameAs。
- “设备订货”“设备利润”“销售金额”等在当前局部样本内实现一致，只能自动折叠重复 claim，仍不能证明跨域规范口径。

结论：

- label fingerprint、SQL fingerprint、embedding fingerprint 必须分开使用。
- 自动融合上限是局部 claim 去重；canonical concept 需要范围、过滤、单位、owner 和治理状态。
- false merge 需要独立、加权评估。

## 3. WrenAI 可执行语义层

环境：WrenAI 0.13.2、wren-core-py 0.7.3、DuckDB connector。项目：`outputs/research_wren_project/`。

构建内容：

- raw model：临时物理表与 `c2/c7/c10/c27/c28`。
- semantic view：映射为 `year_month/product_l1/...`。
- cube：`total_device_orders`、`total_device_profit` 与三个 dimension。
- knowledge rules：明确候选状态、未知单位、未知过滤参数和禁止推断项。

验证结果：

- `wren context validate --strict`：通过。
- `wren context build`：1 model、1 view、0 relationship，成功。
- 普通 semantic SQL dry-plan：成功展开到物理临时表。
- cube structured query：成功生成按 `product_l1` 分组的两项 SUM SQL。

结论：WrenAI 适合快速证明“知识如何被 Agent/运行时消费”，尤其是模型、规则、cube 和 MCP 的组合。但 proposed 与 certified 的治理仍需上游系统控制。

## 4. Apache Ossie 交换实验

版本：Apache Ossie 仓库 commit `88e0011148283302c9a04cd0287e00e0b9d87354`，core spec `0.2.0.dev0` draft。文件：`experiments/device_profit.ossie.yaml`。

结果：

- Apache 官方 validator：通过。
- Wren `--from-osi` strict conversion：通过。
- Wren 构建：1 model、0 relationship，成功。
- 从生成 MDL 执行 dry-plan：成功。

发现的互操作边界：

1. Wren 当前需要 `WREN.column_types` vendor extension 才能得到准确物理类型；Ossie 的 portable datatype 未被该转换器直接映射为全部引擎类型。
2. Ossie 顶层 metrics 在 Wren 当前转换中变成 `_instructions` 文本，不会自动成为可执行 cube。
3. Ossie 字段名与物理列名不同时，直接 table source 会让 Wren 生成缺少物理列声明的 calculated column；改用带 alias 的 inline source SQL 后可执行。
4. 证据状态、来源、否定知识需要 `BI_SEMANTIC_MINER` custom extension，证明交换格式不能替代内部 claim ledger。

结论：Ossie 应是 approved semantic 的交换边界，不是内部真相模型；每个 converter 都必须做 round-trip/semantic-loss 测试。

## 5. 可复现命令

```bash
uv venv research/.venv
uv pip install --python research/.venv/bin/python -r research/requirements-experiments.txt

research/.venv/bin/python research/experiments/sqlglot_fact_extractor.py \
  outputs/local_example_baseline/facts.json \
  --output-dir outputs/research_sqlglot_real

research/.venv/bin/python research/experiments/claim_ambiguity_audit.py \
  outputs/research_sqlglot_real/ast_facts.json \
  outputs/research_sqlglot_demo_v2/ast_facts.json \
  --output-dir outputs/research_claim_audit

uv run research/vendor/apache-ossie/validation/validate.py \
  research/experiments/device_profit.ossie.yaml
```

