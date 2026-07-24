# 面试讲解与常见追问

## 一句话介绍

这是一个可容器化运行的企业知识库 RAG 系统，覆盖文档入库、Vector/BM25/Hybrid 检索、RRF 融合、引用、拒答、历史记录、固定评估集和可复现交付。

## 常见追问

### 为什么同时使用 SQLite 和 ChromaDB？

SQLite 保存结构化业务状态，例如文档状态和问答历史；ChromaDB 保存 embedding 和 chunk metadata，负责相似度检索。两者职责不同。

### Dockerfile 与 Docker Compose 分别做什么？

Dockerfile 定义单个镜像如何构建；Compose 定义后端、前端如何一起启动、连接、做健康检查和挂载数据卷。

### 为什么前端在容器里不能访问 127.0.0.1:8000？

容器内的 127.0.0.1 只指向前端容器自己。Compose 网络中应使用服务名 `backend:8000`，因此项目通过 `API_BASE_URL` 切换地址。

### 如何减少幻觉？

使用 similarity threshold、固定 top-k、来源引用和无依据拒答；Week11 用 20 题固定集分别观察 hit rate、answer accuracy 和 refusal accuracy。它不能彻底消除幻觉。

### 当前还缺什么生产能力？

认证授权、多租户、异步任务、复杂 PDF 解析、监控告警、更多人工标注评估和 CI/CD。面试时应把这些说成边界和下一步，而不是已完成能力。

### 为什么已有向量检索还需要 BM25？

向量检索擅长语义改写，但错误码、配置名和政策编号依赖精确词项。BM25 用 TF、IDF 和长度归一化补足这类查询，两者互补。

### BM25 与 contains 有什么区别？

contains 只判断子串是否存在；BM25 还考虑词在当前 Chunk 的频率、在整个语料中的稀有程度，以及 Chunk 长度，并对高词频做饱和处理。

### 为什么两路原始分数不能相加？

当前 Vector 返回 cosine distance，通常越小越近；BM25 score 越大越相关，量纲和方向都不同。项目使用只依赖排名的 RRF，避免强行校准原始分数。

### RRF 如何计算和去重？

每条分支第 `rank` 名贡献 `1 / (RRF_K + rank)`。同一 chunk_id 在两路出现时只保留一份 Chunk，累加两路贡献，再按总分排序。

### 上传、删除和 rebuild 后 BM25 怎样同步？

ChromaDB 保存 Chunk 文本和 metadata，是 Vector 与 BM25 的共同真相源。BM25 查询时读取当前 collection 并重建内存索引；删除旧向量后 BM25 就看不到旧 Chunk，rebuild 写入新 Chunk 后下一次查询自动读取新数据。

### Hybrid 一定更好吗？

不一定。它通常更稳定，但候选更多会增加延迟，分词不佳也可能引入噪声。必须按 semantic、exact_keyword、entity、mixed 和 unanswerable 分类评估，不能只挑成功案例。

### 为什么不用 Elasticsearch？

当前是小规模教学项目，目标是可运行、可解释和索引一致。引入独立集群会增加部署与运维复杂度。百万文档规模下应考虑 Elasticsearch/OpenSearch、增量索引、分片和异步更新。

### Hybrid 与 Reranker 有什么区别？

Hybrid 是多路召回与融合，解决“候选从哪里来”；Reranker 在候选之后用更强模型重排，解决“候选之间如何精排”。本项目没有实现 Cross-Encoder Reranker。

### Threshold 在 Hybrid 中如何处理？

Similarity Threshold 只过滤 Vector 候选；BM25 按排名返回；RRF 只融合通过各自规则的候选，不复用 cosine threshold。

### 为什么不能只看最终回答？

LLM 可能凭语言能力猜对答案，掩盖错误检索。Retriever 必须单独评估 Hit Rate@K、Recall@K、MRR、拒答与延迟，才能知道知识依据是否真的被召回。

