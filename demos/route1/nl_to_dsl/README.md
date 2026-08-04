# 路线一缺失环节：真实 LLM 从自然语言生成查询 DSL

这个实验专门补足原路线一 Demo 没有覆盖的前半段：

```text
人的问题
→ 读取受控语义上下文
→ 真实 LLM 判断是否可执行
→ Cube Query / Wren query_cube 参数
→ 确定性校验
→ 语义引擎编译并执行
→ 与 golden result 对账
```

## 诚实边界

- 这是仓库内实现的、完全可检查的外部 Agent 编排，不是 Cube Cloud 或 Wren Cloud 的私有 Prompt 复刻。
- Cube 上下文来自本机真实 `/meta`；Wren 上下文来自真实编译产物 `target/mdl.json` 和 `knowledge/rules`。
- 当前两个模型都很小，因此在设备业务域硬过滤后使用完整上下文，没有伪装成大规模 Top-K 检索。
- 每次 LLM 调用保存完整 system/user messages、原始响应、解析结果、token usage 和确定性校验；不保存 API key 或 base URL。
- 没有确定性 fallback。LLM 判断错误会让实验失败，而不是用预写答案覆盖。
- 排序不属于业务语义判断：LLM 可以省略 `order`，执行验证会按业务键确定性排序后对账。
- `dimensions` 只能包含用户明确要求的分组字段，组织和时间过滤字段不能因为出现在 filters 中就重复进入分组。

## 五个问题

| Case | 检查目的 | 期望 |
|---|---|---|
| `01_exact` | 标准业务表达 | 生成可执行 DSL |
| `02_synonyms` | “产品大类”“设备订货额”等同义词 | 生成与标准问题等价的 DSL |
| `03_ambiguous_amount` | 只说“金额” | 追问订货金额还是利润金额 |
| `04_missing_org` | 缺少必填组织 | 追问组织编码 |
| `05_out_of_domain` | 把“销售金额”带入设备模型 | 明确不支持，不偷换成订货金额 |

## 运行

先确保公共数据、Wren MDL 和 Cube Meta 已构建。真实 LLM 配置从相邻 `data-ex/.env` 读取：

```bash
runtime/.venv-tools/bin/python demos/route1/nl_to_dsl/run_experiment.py
```

执行已通过校验的查询时启动 Cube：

```bash
cd demos/route1/cube
docker compose up -d
cd ../../..
runtime/.venv-tools/bin/python demos/route1/nl_to_dsl/execute_generated.py
cd demos/route1/cube
docker compose down -v --remove-orphans
```

主要产物：

- `results/calls/`：每个框架、每个问题的完整 LLM 输入与输出。
- `results/generated/`：只有 `ready` 问题才会产生的查询 DSL。
- `results/llm_summary.json`：十次真实调用的状态判断和校验汇总。
- `results/execution/`：Cube/Wren 的编译 SQL、真实数据和 golden 对账。
- `results/execution_summary.json`：所有可执行查询的最终汇总。
- `results/verification.json`：两轮失败、最终 10/10、4/4 执行和秘密字段标志的离线总校验。

不重新调用 LLM，只核对已经保留的证据：

```bash
runtime/.venv-tools/bin/python demos/route1/nl_to_dsl/verify_results.py
```
