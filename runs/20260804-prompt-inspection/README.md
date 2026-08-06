# Cube / WrenAI 提示词与 Meta 补充验证

本次补充运行用于回答两个问题：

1. Wren 0.13.2 的 `guided` 和 `direct` 模式实际打印什么提示词？
2. Cube Core 实际通过 `/meta` 暴露什么语义对象，保存 Meta 后是否仍能生成正确 SQL 和查询结果？

## 运行步骤

| Step | 输入 | 结果 |
|---|---|---|
| `00-wren-guided` | 同一中文业务问题，`wren ask --guided` | 成功；完整原文保存在 `stdout.txt` |
| `01-wren-direct` | 同一中文业务问题，`wren ask --direct` | 成功；完整原文保存在 `stdout.txt` |
| `10-cube-clean` | `docker compose down -v --remove-orphans` | 成功；清除本 Demo 的容器和卷状态 |
| `11-cube-start` | `docker compose up -d` | 成功；重新创建 Cube 容器 |
| `12-cube-query-and-meta` | 等待 `/meta` ready，调用 `/sql` 与 `/load` | 成功；Meta、SQL、Load 三份响应均保存并记录哈希，业务结果 `match=true` |
| `13-cube-stop` | `docker compose down -v --remove-orphans` | 成功；Cube 容器和本次卷已移除 |

每个 Step 目录均包含：

```text
request.json
stdout.txt
stderr.txt
result.json
```

`request.json` 记录工作目录和命令，但不保存秘密值；`result.json` 记录退出码、运行时长、标准输出/错误哈希及声明产物哈希。

## 结论

- Wren 两种 `ask` Prompt 已从本机安装的 0.13.2 包直接执行验证，不是根据文档重写。
- Cube `/meta` 返回 1 个 Cube、3 个 Measures、6 个 Dimensions；原始响应保存在 `demos/route1/cube/results/meta_response.json`。
- 保存 Meta 后，Cube 仍把相同查询编译为带 `confirmed` 口径和参数绑定的 SQL，查询结果与 golden result 完全一致。
- Cube Core 流程中仍没有 LLM 调用；本运行不能被表述成抓取到了 Cube Cloud 的内部提示词。
