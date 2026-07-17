# 系统架构与文件上传流程

## 运行架构

```text
浏览器 :8501
  -> Streamlit frontend 容器
  -> API_BASE_URL=http://backend:8000
  -> FastAPI backend 容器 :8000
     -> SQLite：文档 metadata 与问答历史
     -> ChromaDB：chunk embedding 与相似度检索
     -> OpenAI API：embedding 与答案生成
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
8. 用户提问时，问题先 embedding，再在 ChromaDB 做 top-k cosine 检索；符合阈值的 chunk 组成 context。
9. LLM 只能基于 context 生成答案；响应返回 answer 与 sources，并把问答历史写入 SQLite。

## 本地与 Docker 的区别

- 本地：`ApiClient()` 默认访问 `http://127.0.0.1:8000`。
- Docker：Compose 注入 `API_BASE_URL=http://backend:8000`，`backend` 是 Docker 内部 DNS 服务名。
- 宿主机仍通过 `http://127.0.0.1:8501` 打开前端，通过 `http://127.0.0.1:8000/docs` 打开 Swagger。

