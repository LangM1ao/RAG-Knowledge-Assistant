# 系统架构与文件上传流程

## 运行架构

```text
浏览器 :8501
  -> Streamlit frontend 容器
  -> API_BASE_URL=http://backend:8000
  -> FastAPI backend 容器 :8000
     -> SQLite：文档 metadata 与问答历史
     -> ChromaDB：chunk 文本、metadata、embedding 与向量检索
     -> BM25：从 ChromaDB 恢复 chunk，构建轻量内存稀疏索引
     -> OpenAI API：embedding、答案生成与答案依据校验
```

Docker Compose 使用 `rag-knowledge-assistant-data` 命名卷挂载到后端的 `/app/data`。容器删除或重启不会自动删除该卷；只有显式执行 `docker compose down -v` 才会删除数据卷。

## 上传一个文件后发生什么

1. 用户在 Streamlit 选择 TXT/PDF，前端以 multipart 请求调用 `POST /documents/upload`。
2. FastAPI 校验扩展名并生成 `document_id`，把原文件保存到 `data/uploads`。
3. `document_parser.py` 提取文本；PDF 使用 pypdf，TXT 读取文本内容。
4. `chunker.py` 按默认 500 字符、50 字符 overlap 切分，尽量在句子边界停止。
5. 每个 chunk 调用 embedding 模型得到向量。
6. `vector_store.py` 把向量、chunk 文本、`document_id` 和 `source_file` 写入 ChromaDB。
7. SQLite 更新文档状态为 `indexed`，记录 chunk_count；前端刷新文档列表。
8. 用户选择 Vector、BM25 或 Hybrid。Vector 使用 query embedding；BM25 使用 token 统计；Hybrid 用 RRF 融合两路排名。
9. 统一 Retriever 返回相同 chunk 结构，符合规则的 chunk 组成 context。
10. LLM 根据 context 生成答案；检索无结果直接拒答。
11. 默认调用 `verify_answer(question, context, generated_answer)`，使用同一份 context 检查答案事实。纯固定拒答跳过校验。
12. PASS 返回原答案与 sources；FAIL 返回安全拒答；校验故障返回服务不可用提示。只把最终返回的答案与来源写入 SQLite。

## Hybrid Retrieval

```text
Document Upload
   ├─ Parse
   ├─ Chunk
   ├─ Embedding → ChromaDB
   └─ Chunk Text + Metadata → ChromaDB（BM25 的唯一恢复来源）

User Query
   ├─ Vector Retrieval ─┐
   └─ BM25 Retrieval ───┤
                        ↓
                    RRF Fusion
                        ↓
                  Final Top-K Context
                        ↓
                    LLM Draft Answer
                        ↓
                  Answer Verification
                   ├─ PASS → Answer + Sources
                   ├─ FAIL → Refusal
                   └─ ERROR → Service unavailable
```

BM25 每次查询读取当前 Chroma collection，并在内存重建索引。知识库变化后无需维护第二份持久化索引，因此上传、删除、单文档 rebuild、rebuild-all 和容器重启都不会造成两套 chunk 数据不一致。代价是查询前有 O(N) 的建索引开销，只适合当前小规模项目。

## 本地与 Docker 的区别

- 本地：`ApiClient()` 默认访问 `http://127.0.0.1:8000`。
- Docker：Compose 注入 `API_BASE_URL=http://backend:8000`，`backend` 是 Docker 内部 DNS 服务名。
- 宿主机仍通过 `http://127.0.0.1:8501` 打开前端，通过 `http://127.0.0.1:8000/docs` 打开 Swagger。


答案校验开关、结构化输出和异常处理详见 [answer_verification.md](answer_verification.md)。阈值仍仅过滤向量分支，新增校验不改变 BM25 / RRF 的规则。


## 2026-10-22 检索质量链路

Query -> NFKC/casefold -> scoped explicit aliases -> Vector/BM25 -> deduplicated RRF -> Top-K -> bounded same-document/section neighbors -> bounded context -> partial evidence answer -> same-context verification -> actual citations -> history。

Ingestion -> real pages -> structure chunks/offset -> identity-aware embedding (source unchanged) -> journaled staged index switch -> SQLite update。Startup recovers interrupted switches; one API worker, not distributed atomicity。
