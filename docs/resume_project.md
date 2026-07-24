# 简历项目表述

## 项目名称

企业知识库 RAG 智能问答系统

## 技术栈

Python、FastAPI、Streamlit、ChromaDB、SQLite、OpenAI API、Docker、Docker Compose、pytest

## 中文简历精简版

基于 FastAPI、Streamlit、ChromaDB 与 SQLite 构建企业知识库 RAG 系统；实现 Vector、BM25、Hybrid 三种检索模式，使用 RRF 完成多路召回融合，并支持文档过滤、来源引用、拒答、索引一致性、固定评估集与 Docker Compose 交付。

## 中文简历详细版

- 设计并实现 TXT/PDF 文档入库链路，完成解析、分块、Embedding、ChromaDB 向量存储、SQLite 元数据管理及来源引用问答。
- 构建 20 题固定评估集，隔离评估 chunk、top-k、cosine threshold 与 metadata filtering；在当前教学数据集上以实测结果选择 top_k=3、threshold=0.60，并明确数据规模边界。
- 使用双 Dockerfile 与 Docker Compose 容器化 FastAPI/Streamlit，配置服务健康检查、容器 DNS、环境变量与持久卷；完成宿主机 HTTP、容器间通信和重启持久性验收。
- 在 ChromaDB 向量检索基础上新增轻量 BM25 稀疏检索，保留错误码、配置名和中文双字 token；以 ChromaDB 为唯一 Chunk 真相源，保证上传、删除、rebuild 与容器重启后的索引一致。
- 设计统一 Retriever 支持 `vector`、`bm25`、`hybrid`，采用 RRF 按排名融合并以 chunk_id 去重，保留两路原始分数、排名、metadata 和引用来源。

## English Resume Version

Built a production-aware enterprise knowledge-base RAG assistant with FastAPI, Streamlit, ChromaDB, SQLite, and Docker Compose. Added Vector, BM25, and Hybrid retrieval modes, fused multi-channel candidates with Reciprocal Rank Fusion, preserved document filters and source metadata, and created a synthetic fixed evaluation suite for retrieval regression.

## 项目口述版本

这个项目覆盖文档上传、解析、切分、Embedding、ChromaDB、问答引用、SQLite 历史和 Docker 交付。升级后检索层不再只有向量检索：BM25 负责精确错误码和配置名，Vector 负责语义改写，Hybrid 用 RRF 融合两路排名。BM25 直接读取 ChromaDB 中持久化的 Chunk，因此没有第二套容易失同步的数据源。

## 使用原则

不要写 Elasticsearch、分布式索引、百万文档验证、Cross-Encoder Reranker、权限系统或云端部署。只有真实三模式评估成功后才能写具体提升百分比。

