# CSR-RAG 精读：三路召回到底各自在找什么

> 论文：*CSR-RAG: An Efficient Retrieval System for Text-to-SQL on the Enterprise Scale*，arXiv:2601.06564v1，2026-01-10。

## 先说结论

CSR-RAG 不是 SQL 生成器，也不是把知识图谱直接塞进 LLM。

它是 SQL 生成前面的“候选表和字段选择器”：

```text
用户问题
  ├─ Contextual RAG：找历史上相似的问题曾使用哪些表
  └─ Structural RAG：从 schema 图中找语义相似的字段属于哪些表
                    ↓ 合并候选表
       Relational RAG：在候选表中找字段和可用 Join
                    ↓
       交给下游 LLM 的少量 table.column + join
```

它把检索拆成三路，是因为“历史问题像不像”“字段语义像不像”“表之间能不能连”是三种不同判断，不能只靠一个向量相似度同时做好。

---

## 一、它想解决的真实问题

Spider 等传统数据集通常直接告诉模型相关 schema。企业环境不会这样：

- 可能有几百或几千张表；
- 一个问题可能需要七张以上的表；
- 一张表可能有上百字段；
- 外键很多，Join 路径复杂；
- 直接把全库 schema 放进 LLM 又贵又容易干扰。

所以 SQL Writer 之前必须先回答：

> 这一次究竟应该把哪些表、字段和 Join 交给模型？

CSR-RAG 的输出就是这份候选清单。

论文用匿名企业数据库说明规模差异，但没有公开该企业数据集，因此外部人员不能复算其原始结果。

---

## 二、先认识所有变量

| 符号 | 人话 |
|---|---|
| `q` | 当前自然语言问题 |
| `Q` | 历史问题全集 |
| `D` | 数据库 schema |
| `T` | 所有表集合 |
| `F` | 所有字段集合 |
| `S_i` | 第 i 条历史 SQL 使用的相关表集合 |
| `C_i=(q_i,S_i)` | 一条历史检索记录：问题 + 当时用过的表 |
| `φ(q)` | 给问题补充 schema 描述后的文本表示 |
| `Sim` | 两段文本的相似度，论文实验认为 cosine 足够 |
| `k` | Contextual RAG 取多少条历史问题 |
| `G=(V,E)` | Structural RAG 的普通图 |
| `V=T∪F` | 图节点由表和字段组成 |
| `l` | Structural RAG 取多少个字段-表 triplet |
| `H=(V,E)` | Relational RAG 使用的超图 |
| `h` | Relational RAG 最后取多少个语义实体或字段对 |
| `⊗` | 将表与字段组合成一个可打分对象，不是乘法 |
| `Υ(v,e)` | 某个表-字段组合对当前问题的相关度 |

三个最需要记住的参数：

```text
k：继承多少条历史问题的表
l：从 schema 图取多少个字段 triplet
h：最终保留多少个 table.column
```

它们越大，通常 Recall 越高、Precision 越低。

---

## 三、Contextual RAG：借鉴“以前有人问过什么”

### 输入是什么

历史系统已经积累：

```text
历史问题：monthly gross and net sales by geographic region
历史 SQL 使用表：fact_orders、fact_returns、dim_region
```

它们被保存为 chunk：

```text
C_i = (q_i, S_i)
```

这不是文档切片，而是“问题和相关表”的一条监督记录。

### `φ(q)` 是什么

论文写：

```text
φ(q) = q + desc(S,D)
```

意思是：不要只 embedding 一句孤立的问题，还可以把相关表名、字段名和描述拼进去，让历史记录带有数据库语境。

本机实现中的历史向量文本是：

```text
question: monthly gross and net sales by geographic region
known relevant schema:
  fact_orders: one row per customer order; columns: ...
  fact_returns: one row per returned order; columns: ...
  dim_region: sales geography dictionary; columns: ...
```

需要注意，论文没有完全讲清当前未知问题如何获得 `S` 再做 `φ(q)`。本机实现只给历史 chunk 加已知 schema 描述，当前问题保持原文，避免先假设正确答案。

### 召回公式怎么读

论文写：

```text
R(q') = 取和 q' 最相似的 k 个 C_i
```

取到历史问题后，把这些历史记录使用的表做并集。

例如本机问题：

> For July show net revenue by sales region excluding refunds

最相似历史问题为：

```json
{
  "history_id": "h1",
  "score": 0.542304,
  "tables": ["fact_orders", "fact_returns", "dim_region"]
}
```

这一路直接得到三张正确表。

### 它的优点

- 复用真实 SQL 经验；
- 对企业内部说法、缩写和固定分析习惯很有效；
- 不需要重新学习复杂业务规则。

### 它的风险

- 新问题没有相似历史时会失效；
- 错误历史 SQL 会把错误表带回来；
- 一个历史问题的表很多时，会扩大噪声；
- schema 改版后，旧记录可能过期。

因此历史问题必须带版本、成功状态和认证信息，不能把所有查询日志同等对待。

---

## 四、Structural RAG：直接从 schema 图找字段

### 图是怎样构建的

论文不用 LLM 抽取图关系，而是根据数据库 schema 确定性构建：

```text
节点：表、字段
边：字段 --column_of--> 表
```

例如：

```text
refund_amount --column_of--> fact_returns
region_name   --column_of--> dim_region
```

每个 triplet 还可以带字段和表的描述。

本机索引文本：

```text
field refund_amount is a column of table fact_returns;
table purpose: one row per returned order;
field meaning: currency amount refunded
```

### 公式怎么读

论文写：

```text
γ(q,G,l) → top-l {(field, table)}
```

人话：

> 把问题与所有“字段属于表”的 triplet 比相似度，返回前 l 个。

本机同一问题召回前几项：

```text
fact_returns.refund_amount     0.378697
dim_region.region_name         0.318842
fact_orders.gross_amount       0.299121
dim_region.country_code        0.297826
dim_region.region_id           0.269945
fact_orders.discount_amount    0.264048
```

它确实找到大部分目标字段，但也找到了：

```text
marketing_campaign.budget_amount
dim_product.unit_cost
```

原因并不神秘：`revenue、amount` 与预算和成本在 embedding 空间中也很接近。

### 为什么还需要 Contextual RAG

Structural RAG 只知道字段文字像不像问题，不知道企业过去真正如何回答类似问题。

Contextual RAG 可以用历史使用事实补充它；Structural RAG 则能在没有相似历史问题时提供新对象。两者并行后做并集，是为了先保 Recall。

---

## 五、为什么普通图之后又要超图

这是论文里最容易让人困惑的一段。

### 普通图适合表示“字段属于表”

```text
fact_orders -- region_id
dim_region  -- region_id
```

### 超图适合表示“一列可能连接多张表”

普通边通常连接两个节点。超边可以同时连接多个节点。

以 `order_id` 为例：

```text
超边 order_id
  ├─ fact_orders
  ├─ fact_returns
  ├─ fact_shipments
  └─ fact_payments
```

这更接近企业数据库中“一种业务键贯穿多张表”的情况。

论文把：

- 表当作超图节点；
- 列当作超边；
- 多表共享或关联的列连接这些表。

这里的知识图谱不是为 LLM 提供百科事实，而是为了限制和排序可用 Join。

---

## 六、Relational RAG：在候选范围内找列和 Join

前两路的表先合并：

```text
候选表 = Contextual 表 ∪ Structural 表
```

然后 Relational RAG 只在这些表里工作。

论文写：

```text
β(q,H) → top-h {(table ⊗ column)}
```

这里 `⊗` 不要理解成数学乘法。它只表示把：

```text
表名 + 表描述 + 字段名 + 字段描述
```

组合成一个可计算相似度的对象。

### Algorithm 1 每行在干什么

论文伪代码可以翻译为：

1. 遍历候选表节点和字段超边；
2. 检查某个候选是否拥有任务需要的 metadata；
3. 使用某个 operator 把表、字段和问题组合起来；
4. 根据配置权重算分；
5. 没有有效权重或 metadata 就给 0 分；
6. 所有候选降序排序；
7. 取前 h 个。

### 论文没有公开的关键细节

它没有告诉我们：

- `operator` 的确切字符串或函数是什么；
- 哪些 metadata 被视为必须；
- 每个 metric 的权重是多少；
- 外键和同名列如何共同计分；
- 超图候选如何去重。

所以没有官方源码就不可能逐数字完全复现。

本机实现明确采用：

```text
operator = table purpose + column name + column description
score = cosine(question, operator)
```

然后在候选表两端都存在时，把真实外键列补入输出。

这是一种合理且可读的实例化，不是作者未公开实现的还原。

---

## 七、用一个问题看完整链路

问题：

> For July show net revenue by sales region excluding refunds

### 第一步：Contextual RAG

```text
命中历史 h1
表：fact_orders、fact_returns、dim_region
```

### 第二步：Structural RAG

返回 10 个字段 triplet，涉及：

```text
fact_orders
fact_returns
dim_region
dim_product             ← 噪声
marketing_campaign      ← 噪声
```

### 第三步：合并候选表

```json
[
  "dim_product",
  "dim_region",
  "fact_orders",
  "fact_returns",
  "marketing_campaign"
]
```

### 第四步：Relational RAG 排字段

前几项：

```text
fact_returns.refund_amount
dim_region.region_name
dim_region.region_id
fact_orders.gross_amount
fact_orders.status_code
fact_orders.region_id
```

### 第五步：补 Join

正确 Join：

```text
fact_orders.region_id = dim_region.region_id
fact_returns.order_id = fact_orders.order_id
```

因为 `dim_product` 被误召回，系统还补了一条不需要的 Join：

```text
fact_orders.product_id = dim_product.product_id
```

### 最终结果

```text
表 Precision = 3/5 = 60%
表 Recall = 3/3 = 100%
字段 Precision = 43.75%
字段 Recall = 87.5%
```

缺失的 gold 字段是 `fact_orders.order_date`。问题中“July”表达了时间，但 `order_date` 的语义得分没有进入前 12。这正好说明：保持表 Recall 并不等于字段完整，也不等于最终 SQL 一定正确。

---

## 八、k、l、h 为什么要反复调

本机神经 embedding 参数扫描：

| k/l/h | 表 Precision | 表 Recall | 字段 Precision | 字段 Recall |
|---|---:|---:|---:|---:|
| 1/6/8 | 100% | 100% | 63.33% | 85.57% |
| 1/10/12 | 77.5% | 100% | 47.61% | 96.88% |
| 2/10/12 | 58.75% | 100% | 42.33% | 96.88% |
| 2/18/18 | 37.80% | 100% | 28.07% | 96.88% |

这张表非常直观：

- 多取历史问题、多取 triplet、多取字段，Recall 容易保住；
- 但候选越来越脏，Precision 明显下降；
- 从 1/10/12 再继续扩大，字段 Recall 已不再提高，却持续引入噪声。

论文图 6-10 表达的也是这个调参关系。

不能把本机的 1/6/8 当作通用最优值。数据集只有四个问题，而且历史问题设计得较清楚。生产系统必须用真实评测集按业务域调参。

---

## 九、本机复现是怎样实现的

工作区：[workspace/csr_rag](../workspace/csr_rag/README.md)。

### 输入

```text
12 张表
52 个字段
11 条外键
8 个历史问题↔相关表记录
4 个测试问题及 gold 表/字段
```

### Embedding

论文只写 BERT-like encoder，没有公开 checkpoint。本机使用：

```text
sentence-transformers/all-MiniLM-L6-v2
```

也运行了 TF-IDF 作为不下载模型时的降级基线。

### 实际结果

| 后端 | 表 Precision | 表 Recall | 字段 Precision | 字段 Recall | 中位检索耗时 |
|---|---:|---:|---:|---:|---:|
| TF-IDF | 52.5% | 91.67% | 38.17% | 80.36% | 约 0.5 ms |
| MiniLM | 77.5% | 100% | 47.61% | 96.88% | 约 36 ms |

MiniLM 对 `sales region/geographic region`、`refund/returned` 等语义变体明显更好，但仍会把 `amount` 相关的预算和成本字段召回。

### 为什么不能和论文 30 ms 直接比较

论文使用 Intel Xeon Gold 5317、匿名企业数据和自己的索引实现。本机是 Apple Silicon、小数据和 Python/SentenceTransformer。

两个数字接近只是巧合。可以证明“检索链能够低延迟运行”，不能证明本机复刻了论文性能。

---

## 十、论文的 40% Precision、80% Recall 应该怎样理解

论文声称最高 Precision 超过 40%、Recall 超过 80%。

这不是 SQL 执行准确率，而是检索相关表/字段的准确程度。

企业大 schema 下 40% Precision 看起来不高，但如果：

```text
原来 3000 个字段
召回后只剩 20 个，其中 8 个真正相关
```

Precision 40% 已经大幅缩小 LLM 输入范围。前提是 Recall 足够高，不要漏掉 SQL 必需对象。

论文没有公开匿名企业数据、gold 生成过程和源码，外部读者无法确认每个实验点的统计细节。这是主要证据限制。

---

## 十一、它的知识图谱究竟怎么使用

现在可以直接回答你之前的疑问。

图谱没有整体进入 Prompt。它被使用在两个位置：

### 位置一：Structural RAG 的检索索引

```text
问题 → embedding → 从 (字段, 属于, 表) triplet 中取 top-l
```

图在这里帮助从字段回到表。

### 位置二：Relational RAG 的候选和 Join 约束

```text
候选表 → 超图 → 排 table.column → 返回有效 Join 列
```

最后传给 SQL Writer 的不是全图，而是：

```json
{
  "tables": ["fact_orders", "fact_returns", "dim_region"],
  "columns": ["fact_orders.region_id", "dim_region.region_name"],
  "joins": ["fact_orders.region_id = dim_region.region_id"]
}
```

所以 CSR-RAG 中图谱的角色是检索后端和关系过滤器，不是 Prompt 里的长篇知识文本。

---

## 十二、它适合怎样接到你的 Data Agent

结合你的资产，可以这样替换论文输入：

### Contextual RAG 的历史记录

来自：

- 看板标题；
- 用户中文注释；
- 历史 SQL；
- SQL 涉及的表和字段；
- 查询是否成功、是否被复用。

形成：

```text
“新客支付转化率按渠道”
↔ fact_order、dim_channel、对应字段和过滤
```

### Structural RAG 的图

来自：

- 物理 schema；
- BI 中间模型；
- SQL AST；
- 表字段描述；
- 表、字段、指标和维度绑定。

图不应只有 `field --column_of--> table`，还应增加：

```text
metric --computed_from--> column
term --binds_to--> metric/column
dashboard --uses--> query
query --joins--> table
column --joins_to--> column
```

### Relational RAG 的超图和约束

来自：

- 声明主外键；
- 历史 SQL 高频 Join；
- BI 模型关系；
- Join 认证状态、次数和时间版本。

不要只用同名列推断 Join。同名的 `id` 在企业数据库里非常危险。

### 给 Agent 的最终上下文

Context Builder 应返回：

```text
候选语义对象
候选物理表字段
认证 Join 路径
相似历史 SQL
必须使用的过滤规则
每条证据的来源和置信度
```

然后 SQL Writer 或语义 DSL Writer 再生成查询。

---

## 十三、我对 CSR-RAG 的评价

### 值得保留的设计

1. 将相似问题、schema 语义和 Join 关系拆成三路；
2. 前两路可以并行；
3. 先保 Recall，再在关系阶段收缩；
4. 图关系留在检索服务中，不需要塞满 Prompt；
5. 检索层可以独立评测，不必每次都跑昂贵 SQL LLM。

### 不够清楚的地方

1. 当前问题的 `φ(q)` 如何获得 schema 描述写得含糊；
2. Relational RAG 的 operator、metadata、weights 没有公开；
3. 超图与真实外键、同名列、复合键的关系讲得不够细；
4. 匿名企业数据不公开；
5. 没有官方源码；
6. 论文只验证检索，没有给出完整 SQL 端到端执行准确率。

### 最终一句话

CSR-RAG 最值得学的不是某个复杂图算法，而是：

> 先用历史经验和 schema 语义各自找候选，再用数据库关系检查这些候选能不能形成合理的表、字段和 Join，最后只把这个局部结果交给 SQL Agent。
