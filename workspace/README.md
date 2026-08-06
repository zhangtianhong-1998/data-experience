# 两篇论文的可运行复现工作区

这里不是“放一些示意代码”的目录，而是本轮精读对应的可重复实验工作区。

## 包含什么

- `dbcc/`：DbCC 的公式级复现，以及官方 `SchemaCompression` 源码的离线预处理实跑。
- `csr_rag/`：根据论文公开算法重新实现的 Contextual、Structural、Relational 三段检索。
- `requirements.txt`：CSR-RAG 使用的本地 embedding 运行依赖。
- `run_all.sh`：从输入开始重跑两个实验。
- `verify_all.py`：核对输出是否齐全、关键不变量是否成立。

## 一键运行

```bash
cd workspace
./run_all.sh
python3 verify_all.py
```

第一次运行 CSR-RAG 时会下载 `sentence-transformers/all-MiniLM-L6-v2`。模型缓存保存在
`workspace/csr_rag/model-cache/`，不会提交到 GitHub。

如果无法访问 Hugging Face，程序会明确报错；可以使用：

```bash
./run_all.sh --tfidf
```

TF-IDF 是无网络降级方案，不是论文中 BERT-like embedding 的等价实现，因此结果会单独标记。

## 结果边界

这里完成的是“小规模、机制级复现”：证明论文的输入、每个中间对象、排序与压缩输出可以跑通，
并测量本机上的 token 估算、Precision、Recall 和延迟。它不是 Spider 2.0-Snow 或企业私有数据集的
完整论文数字复刻。详细原因见 `reports/11_两篇论文复现过程与结果评价.md`。
