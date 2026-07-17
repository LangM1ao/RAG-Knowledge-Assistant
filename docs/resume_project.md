# 简历项目表述

## 项目名称

企业知识库 RAG 智能问答系统

## 技术栈

Python、FastAPI、Streamlit、ChromaDB、SQLite、OpenAI API、Docker、Docker Compose、pytest

## 三条项目经历

- 设计并实现 TXT/PDF 文档入库链路，完成解析、分块、Embedding、ChromaDB 向量存储、SQLite 元数据管理及来源引用问答。
- 构建 20 题固定评估集，隔离评估 chunk、top-k、cosine threshold 与 metadata filtering；在当前教学数据集上以实测结果选择 top_k=3、threshold=0.60，并明确数据规模边界。
- 使用双 Dockerfile 与 Docker Compose 容器化 FastAPI/Streamlit，配置服务健康检查、容器 DNS、环境变量与持久卷；完成宿主机 HTTP、容器间通信和重启持久性验收。

## 使用原则

简历可以写“完成并验证 Docker 容器化”，但不要写 Kubernetes、正式 BM25、rerank、权限系统或云端部署，因为这些尚未实现。

