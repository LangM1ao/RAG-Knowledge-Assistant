# Week12 补充模块 Day 4：评估、Docker、README 与收口

## 今天完成了什么

扩展为 26 道合成问题，增加 exact_keyword、entity、semantic、mixed；新增三模式逐题与汇总评估脚本；更新 Docker、README、架构、简历和面试材料；完成安全审计准备。

## 评估设计

`evals/run_retrieval_comparison.py` 复用现有 `build_eval_store()`、固定问题集和独立 `data/eval_chroma_db`。对 Vector、BM25、Hybrid 记录 chunk_id、source、Hit、Reciprocal Rank、拒答、延迟和错误。

汇总按模式与问题类型计算：

- Hit Rate@K：正确来源是否进入 Top-K。
- Recall@K：当前每题只有一个 relevant source，因此数值等于 Hit Rate。
- MRR：正确来源首次出现位置的倒数。
- Refusal Accuracy：应拒答与实际空结果是否一致。
- Average Latency：只统计检索调用时间。

## 真实限制

本次环境禁止在未明确确认外部端点的情况下，把 demo Chunk 发送到 `.env` 配置的 Embedding API。因此未伪造 Vector/Hybrid 对比数字，也没有据此修改默认模式或写提升百分比。BM25、RRF、API 与 Docker 功能通过本地/容器测试验证；真实三模式 CSV 需得到端点数据发送许可后运行：

```powershell
python -m evals.run_retrieval_comparison
```

## Docker 修改与验证

Compose 新增检索配置，并允许覆盖 `BACKEND_PORT`、`FRONTEND_PORT`、`DATA_VOLUME_NAME`。端口只绑定 `127.0.0.1`，降低本机服务意外暴露风险。

实际使用隔离端口 18000/18501 和全新验证卷完成：

- 双镜像 build；
- backend/frontend healthy；
- HTTP health；
- 空 BM25 索引拒答；
- 写入合成 Chunk 后检索成功；
- backend 重启后 Chunk 仍可检索；
- 删除 Chunk 后 BM25 返回空。

第一次启动暴露了缺少 Key 时 OpenAI 客户端导入崩溃的问题，已改为懒初始化。

## README 与材料

README 增加 Why Hybrid、三模式、RRF、API、配置、索引生命周期、评估和限制。架构图明确两路召回。简历只写真实实现，不写 Elasticsearch、分布式索引、百万文档或 Reranker。

## 常见报错

- 8000/8501 被占用：覆盖 BACKEND_PORT/FRONTEND_PORT。
- 容器无 Key 启动失败：旧代码客户端初始化过早；当前版本已修复，只有真正调用 Embedding/LLM 时才要求 Key。
- Vector 评估连接失败：确认网络和端点授权，不要使用假结果代替。
- BM25 无结果：检查 Chroma 是否有 documents/metadatas，检查 token 和过滤条件。

## Debug 模板

```text
模式：
问题：
Query tokens：
Vector candidates/ranks：
BM25 candidates/ranks：
RRF scores：
Final Top-K：
Filters：
Threshold：
容器状态：
完整错误：
```

## 当前实现限制

轻量中文双字分词、查询时全量重建 BM25、同步上传和 Embedding、大文件可能阻塞、无认证与多租户、评估集规模小、尚无 Cross-Encoder Reranker。

## 面试重点

能解释为什么 Hybrid 不保证每题更好、为什么保持 Vector 默认、RRF_K 和 Candidate K 如何影响排名/延迟、为什么 Retriever 指标要与最终回答指标分开。

## 以后必须亲手重做

1. 给固定问题集补 ground truth。
2. 从逐题结果计算 MRR。
3. 运行三模式对比并分析失败案例。
4. 用隔离端口/卷做 Docker 验收。
5. 做一次 Git 上传前敏感信息扫描。
