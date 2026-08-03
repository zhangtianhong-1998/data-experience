任务：对下面一个报表及其全部组件进行局部语义发现。

处理顺序：

1. 先概括报表标题、业务目的、分析对象和明确的作用范围。
2. 逐组件检查数据集、SQL输出、字段注释、过滤和分组粒度。
3. 合并报表内部由多个组件共同支持的同一概念，但保留不同口径。
4. 输出概念、指标实现、局部关系和需要补充的信息。
5. 复制输入中的 `package_ref`、`report_ref` 和固定 `schema_version=report-extraction-v1`。

JSON Schema：

{{OUTPUT_SCHEMA}}

EvidencePackage：

{{PACKAGE_JSON}}

