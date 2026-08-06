# CSR-RAG 论文算法复现

论文没有提供公开源码或公开企业数据集。本目录按照论文中可见的公式、图 2 和 Algorithm 1，
实现一个可审计的小规模版本。

## 三段检索分别做什么

1. Contextual RAG：用问题找历史相似问题，继承历史 SQL 使用过的表。
2. Structural RAG：把每个 `字段属于某张表` 表示成 triplet，直接用问题召回相关 triplet。
3. Relational RAG：在前两路得到的候选表里，对 `table.column` 排序，并补上有效外键两端的 Join 列。

前两段并行缩小表空间，第三段只在缩小后的范围里找字段和 Join。CSR-RAG 本身不生成 SQL。

## 安装与运行

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r ../requirements.txt
HF_HOME="$PWD/model-cache" .venv/bin/python src/run_demo.py --backend sentence-transformer
.venv/bin/python -m unittest discover -s tests -v
```

默认模型为 `sentence-transformers/all-MiniLM-L6-v2`，revision 固定在 `model.lock.json`。
论文只写了 BERT-like encoder，没有公开具体 checkpoint，因此这里选择公开、轻量、适合语义检索的
MiniLM，并在输出中记录模型名和 revision。

无网络降级运行：

```bash
.venv/bin/python src/run_demo.py --backend tfidf
```

## 输出

- `outputs/schema_triplets.json`：Structural RAG 的完整图索引。
- `outputs/hypergraph.json`：列作为超边、表作为节点的关系表示。
- `outputs/cases.json`：每个问题三段召回的完整中间结果。
- `outputs/parameter_sweep.json`：不同 `k/l/h` 取值的 Precision/Recall 取舍。
- `outputs/summary.json`：最终配置、准确率和本机延迟。

## 不能声称什么

- 不能声称复现了论文匿名企业数据集的 40% Precision、80% Recall。
- 不能声称我们的 Relational 打分就是作者私有实现；论文没有公开 operator、metadata 和权重细节。
- 可以声称三段数据流、候选集合并、超图字段排序和参数取舍已经被独立实现并实际运行。
