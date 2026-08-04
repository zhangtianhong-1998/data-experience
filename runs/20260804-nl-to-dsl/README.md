# 自然语言 → Cube/Wren DSL 真实 LLM 实验记录

本次运行补足路线一原来缺少的自然语言规划环节。共进行了三轮、30 次真实 LLM 调用，没有使用预写结果 fallback。

## 步骤和结果

| Step | 发生了什么 | 结果 |
|---|---|---|
| `00-cube-clean` | 清理 Cube 容器与本 Demo 卷 | 成功 |
| `01-cube-start` | 从空容器状态启动 Cube | 成功 |
| `02-cube-refresh-meta` | 读取新增 description/ai_context 后的真实 `/meta` 并复查查询 | `match=true` |
| `03-wren-validate` | 用相对 executable 启动 Wren | 失败：日志器切换 cwd 后路径失效 |
| `03b-wren-validate-retry` | 改用经过解析的绝对路径 | 成功，1 model |
| `04-wren-build` | 重建 `target/mdl.json` | 成功 |
| `05-real-llm-planning` | 第一轮 10 次真实调用 | 9/10；Cube 没有识别“金额”歧义 |
| `06-cube-refresh-ambiguity-context` | 将歧义规则加入 Measure `meta.ai_context`，重新读取 `/meta` | Cube 查询仍 `match=true` |
| `07-real-llm-planning-after-context-fix` | 第二轮 10 次真实调用 | 歧义修复；8/10，暴露排序误判和过滤维度混入分组 |
| `08-final-real-llm-planning` | 修正规划规则和验证边界后第三轮 10 次真实调用 | 10/10，0 fallback |
| `09-execute-generated-queries` | 执行标准/同义词产生的 Cube/Wren DSL | 4/4 与 golden result 一致 |
| `10-cube-stop` | 停止并移除 Cube 容器与卷 | 成功 |
| `11-verify-retained-evidence` | 离线核对两轮失败、最终调用、秘密字段标志和执行结果 | 全部检查通过 |

## 为什么保留两轮失败？

第一轮证明 `meta.ai_context` 不是装饰文字：缺少“裸词金额必须追问”时，Cube Agent 真的会擅自选择指标；补充并重新读取 Meta 后才修复。

第二轮区分了两类错误：省略排序不改变聚合语义，是验证器过严；把过滤字段放进分组会改变粒度，是真错误。最终规则只修复真正的规划边界，没有把预写 DSL 注入模型回答。

## 证据位置

- 第一轮完整调用：`demos/route1/nl_to_dsl/results/attempts/01_before_cube_ambiguity_context/`
- 第二轮完整调用：`demos/route1/nl_to_dsl/results/attempts/02_after_cube_context_before_planner_rule/`
- 最终 10 次调用：`demos/route1/nl_to_dsl/results/calls/`
- 最终生成 DSL：`demos/route1/nl_to_dsl/results/generated/`
- 引擎编译与数据：`demos/route1/nl_to_dsl/results/execution/`
- 最终判断汇总：`demos/route1/nl_to_dsl/results/llm_summary.json`
- 最终执行汇总：`demos/route1/nl_to_dsl/results/execution_summary.json`

每个运行 Step 都保留 `request.json`、`stdout.txt`、`stderr.txt` 和 `result.json`。`.env` 只在运行时读取；记录中没有 API key 或 base URL。
