# 企业 BI 语义知识挖掘研究包

本目录记录截至 2026-08-03 的本地盘点、公开方案研究、实验和建议架构。

如果你希望先理解“元数据平台怎样采集、MCP / SDK 实际返回什么”，请直接从 `08_route2_asset_ingestion_mcp_sdk_lab.md` 开始；它包含本机运行的 DataHub 连接器、MCP 与 SDK 原始结果，并明确区分实测、源码核验和官方文档。

1. `00_project_charter.md`：经历史讨论重新校准的目标与边界。
2. `01_local_baseline.md`：当前原型、真实样例和风险基线。
3. `02_landscape.md`：公开研究、标准与开源方案的系统性梳理。
4. `03_capability_matrix.md`：能力矩阵、复用决策与平台定位。
5. `04_target_architecture.md`：建议的知识模型、流水线和 Agent 消费架构。
6. `05_roadmap_and_evaluation.md`：分阶段路线图与评估体系。
7. `06_experiment_results.md`：SQLGlot、Claim 消歧、WrenAI 与 Apache Ossie 实验记录。
8. `sources.md`：主要一手资料索引。
9. `07_human_readable_build_and_use.md`：面向人的完整构建与使用说明，是推荐阅读入口。
10. `08_route2_asset_ingestion_mcp_sdk_lab.md`：路线 2 的逐层拆解和本机可复现实验，是当前推荐阅读入口。

早期实验代码位于 `experiments/`，输出位于 `outputs/research_*`；本次路线 2 实验统一位于 `lab/`，不会影响原 `data-ex` 工程。
