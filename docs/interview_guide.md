# 面试讲解与常见追问

## 一句话介绍

这是一个可容器化运行的企业知识库 RAG 系统，覆盖文档入库、向量检索、引用、拒答、历史记录、固定评估集和可复现交付。

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

