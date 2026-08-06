# DbCC 机制级复现

论文：*Database Context Compression for Text-to-SQL on Real-World Large Databases*。

## 本目录做了两件不同的事

1. `src/run_official_preprocessors.py` 直接调用作者仓库中的 `RawStrategy`、
   `FactorizationStrategy` 和 `InheritanceStrategy`，验证公开代码实际输出什么。
2. `src/run_demo.py` 用约 300 行可读代码重现论文四个核心算子，并额外验证压缩后的表结构能否展开回原始结构。

这两个结果必须分开看。官方仓库是作者实现，但没有打包一键复刻论文所有表格所需的完整数据；
本目录的机制复现覆盖四个算子，但用的是可公开的小型合成企业 schema，不代表论文 benchmark 成绩。

## 输入

- `data/database.json`：8 张企业风格的分区订单、退款、客户和字典表。
- `data/external_knowledge.json`：指标公式、状态码、地域定义和无关知识。
- `data/question.json`：本次需要净收入、区域和退款排除规则的问题。

## 运行

```bash
python3 src/run_demo.py
./fetch_official_source.sh
python3 src/run_official_preprocessors.py
python3 ../../verify_all.py
```

官方源码固定在 `source.lock.json` 记录的提交。`official-source/` 仅作为本机依赖，不进入当前仓库。

## 重点输出

- `outputs/01_raw_context.txt`
- `outputs/02_factorized_context.txt`
- `outputs/03_template_context.txt`
- `outputs/04_semantic_context.txt`
- `outputs/05_purified_evidence.json`
- `outputs/reproduction_summary.json`
- `outputs/official_*_context.txt`
- `outputs/official_preprocessor_summary.json`
