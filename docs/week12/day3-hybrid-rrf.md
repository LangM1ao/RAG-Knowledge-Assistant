# Week12 补充模块 Day 3：Hybrid Retrieval 与 RRF

## 今天完成了什么

新增统一 `Retriever`，支持 `vector`、`bm25`、`hybrid`；实现 RRF 去重融合；扩展 FastAPI 请求、响应和 Streamlit 模式选择与调试区。

## 修改前后调用链

```text
修改前：
chat API → rag_pipeline → VectorStore → Context → LLM

修改后：
chat API(retrieval_mode) → rag_pipeline → Retriever
  ├─ VectorStore
  ├─ BM25Retriever
  └─ reciprocal_rank_fusion
→ 统一 Chunk → Context → LLM → Sources/Debug
```

## 真实文件

- `app/services/retriever.py`：模式路由、Vector 标准化、RRF。
- `app/services/rag_pipeline.py`：改为调用统一 Retriever。
- `app/schemas/chat.py`：`Literal["vector","bm25","hybrid"]` 校验。
- `app/api/chat.py`：传递模式并返回 debug。
- `frontend/api_client.py`：发送 retrieval_mode。
- `frontend/streamlit_app.py`：模式按钮和可展开分数。
- `tests/test_retriever.py`、`tests/test_week11_chat_filters.py`：融合和兼容测试。

## Vector 与 BM25 如何统一

Vector 原始结果有 `distance`；BM25 有 `bm25_score`。适配层统一补充 `rank`、`retrieval_source`、`vector_score/vector_rank`、`bm25_score/bm25_rank`、`rrf_score`。不存在的字段为 `None`，RAG 不需要维护三套逻辑。

## RRF 逐步计算

```text
RRF contribution = 1 / (RRF_K + rank)
```

例如 `RRF_K=60`：

- Chunk A：Vector 第 1，贡献 `1/61`；BM25 第 2，贡献 `1/62`。
- Chunk B：只在 Vector 第 2，贡献 `1/62`。
- A 的两路贡献相加，因此通常排在 B 前面。

`chunk_id` 是字典 key，同一个 Chunk 只保留一份，metadata 和文本不丢失。项目禁止直接把 cosine distance 和 BM25 score 相加。

## Threshold

`similarity_threshold` 只进入 VectorStore。BM25 只按分数和排名取候选；RRF 只看名次。某一路为空时使用另一条；两路都空时沿用原有拒答。

## API 与 Streamlit

旧请求不传 `retrieval_mode` 时仍默认 `vector`。非法值由 Pydantic 返回 422。Streamlit 显示当前模式；普通回答仍只显示 answer/sources，展开 Chunk 时才显示内部排名和分数。

## 实际遇到的问题

旧测试通过 monkeypatch 替换 `VectorStore`，FakeStore 没有 BM25 collection。解决办法是让 BM25Retriever 延迟创建：只有 bm25/hybrid 模式才读取 `vector_store.collection`，保证旧 Vector 调用兼容。

## 放弃的方案

- 在 answer service 里写三段 if/else：会让回答层理解检索细节。
- 原始分数加权：量纲和方向不同，需要额外校准。
- 默认立即切换 Hybrid：真实三模式评估尚受外部 Embedding 授权阻塞，因此保持 Vector 默认最诚实。

## 测试

```powershell
python -m pytest tests/test_retriever.py tests/test_week11_chat_filters.py tests/test_frontend_api_client.py -q -p no:cacheprovider
```

覆盖三模式、重复去重、两路为空、单路为空、RRF 公式、Top-K、metadata、过滤、非法模式和旧请求兼容。

## 以后必须亲手重做

1. 用两个手写排名列表计算 RRF。
2. 实现 chunk_id 去重。
3. 给旧 API 增加可选 Literal 参数。
4. 在 Streamlit 展示 debug，但不污染回答正文。
