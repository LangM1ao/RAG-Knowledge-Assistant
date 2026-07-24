# Week12 补充模块 Day 2：正式 BM25 Retriever

## 今天完成了什么

新增 `app/services/bm25_retriever.py`，实现正式 BM25 稀疏检索。它支持中文、英文、错误码、配置名、Top-K、document_id/source_file 过滤、metadata 保留、空索引和异常日志。

## 为什么这样设计

项目原来只有 ChromaDB 保存完整 Chunk 文本、chunk_id 和 metadata；SQLite 只保存文档级信息。为了避免维护第二套会失同步的 Chunk 文件，BM25 直接调用 Chroma collection 的 `get()`，以 ChromaDB 为唯一真相源。

当前知识库规模很小，因此每次 BM25 查询重新读取 Chunk 并构建内存索引。优点是上传、删除、rebuild 和重启后天然一致；缺点是 O(N) 重建开销，不适合百万文档。

## 修改前后调用链

```text
修改前：Question → VectorStore.query → Chroma cosine
修改后：Question → BM25Retriever.query → Chroma.get → tokenize → BM25 → Top-K
```

## 真实文件

- `app/services/bm25_retriever.py`：tokenize、过滤、加载 Chunk、BM25 计分。
- `app/core/config.py`：增加候选数和 RRF 配置。
- `tests/test_bm25_retriever.py`：覆盖精确错误码、中文、英文、过滤、空索引和同步。

## Tokenize

英文使用大小写归一化并完整保留 `_ . : -`，因此 `ERR_CONNECTION_104`、`API_TIMEOUT_MS` 不会被拆碎。连续中文使用双字 token，避免只按空格分词。它是轻量方案，不等同于专业中文分词。

## 关键公式

```text
score += IDF(term) × TF × (k1 + 1)
         / [TF + k1 × (1 - b + b × length / average_length)]
```

输入是 Query token 和一个 Chunk 的 token 统计；输出是该 Chunk 的 BM25 分数。分数越大通常越相关。

## 统一输出字段

`query()` 返回 `chunk_id`、`text`、`metadata`、`score`、`rank`、`retrieval_source`、`bm25_score`、`bm25_rank`，并为 Vector/RRF 字段填入 `None`。

## 生命周期

- 启动：不预建第二份索引。
- 查询：从持久化 ChromaDB 读取当前 Chunk，构建内存索引。
- 上传/rebuild：现有流程写入新 Chroma Chunk，下一次查询自动看见。
- 删除：现有流程删除 Chroma Chunk，下一次查询不再看见。
- 容器重启：命名卷恢复 ChromaDB，BM25 再从中建立索引。
- 失败：记录日志并安全返回空列表。

## 实际遇到的问题

隔离 worktree 没有 `.env`，新版 OpenAI SDK 在模块导入时因缺少 Key 直接失败。解决办法是把 `OpenAI()` 客户端改为调用时懒初始化，使 health check、BM25 和离线测试不依赖真实 Key。

## 放弃的方案

- `rank-bm25`：当前功能用标准库足够，避免旧依赖兼容风险。
- SQLite 新建 Chunk 表：会形成第二套 Chunk 真相源。
- Elasticsearch/OpenSearch：超出当前规模与教学目标。
- 复杂增量索引：当前规模下全量内存重建更可靠。

## 测试与 Debug

```powershell
python -m pytest tests/test_bm25_retriever.py -q -p no:cacheprovider
```

排查顺序：打印 Query tokens；检查 `collection.get()` 的 ids/documents/metadatas 长度；检查 document_id/source_file；检查 0 分是否源于 token 不一致。

## 当前限制与面试追问

中文双字 token 不能理解专业词边界；每次查询重建索引有延迟。面试需要能解释：BM25 为什么不需要 Embedding、为什么 ChromaDB 是共同真相源、为什么当前不用 Elasticsearch。

## 以后必须亲手重做

1. 独立实现 `tokenize()`。
2. 手写 IDF 和 BM25 公式。
3. 用 FakeCollection 验证过滤。
4. 模拟集合内容变化，验证删除/rebuild 同步。
