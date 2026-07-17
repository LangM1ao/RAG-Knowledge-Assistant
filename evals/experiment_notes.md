# Week11 检索优化与效果评估实验报告

## 1. 实验目的

Week10 证明系统可以上传文档、完成 RAG 问答并展示引用。Week11 进一步回答：正确来源有没有进入 top-k、文档外问题是否拒答、不同 chunk/top_k/threshold 是否改变结果。

所有实验只使用 `data/eval_chroma_db/`，没有重建或覆盖 `data/chroma_db/`。

## 2. 固定条件

- 文档：三份 `demo/*.txt`
- 问题：`evals/test_questions.json`，共 20 题
- Embedding：当前 `.env` 配置的 OpenAI embedding 模型
- Chroma metric：cosine distance，越小越相似
- 人工金标准：expected_answer、expected_source、should_refuse

## 3. 指标

- hit rate：有 expected_source 的 16 道题中，正确来源进入 retrieved sources 的比例。
- answer accuracy：baseline 的 20 个答案逐题对照 expected_answer 人工标记。
- refusal accuracy：系统是否在 should_refuse=true 时拒答，并在 should_refuse=false 时不误拒答。
- average result count：threshold 后平均保留多少 chunk，用于观察上下文规模和噪声。

## 4. Baseline

参数：chunk_size=500、overlap=50、top_k=3、未使用 threshold。

结果：

- retrieval hit rate：1.00
- 人工 answer accuracy：1.00（20/20）
- 基于真实答案措辞的 refusal accuracy：1.00（20/20）
- 平均返回 chunk：3.00

解释：固定题集中所有有来源问题都命中了正确文档。四个文档外问题虽然仍检索到弱相关 chunk，但 LLM 根据 prompt 明确拒答。这个结果不能证明检索器已经能主动识别文档外问题，因此还需要 threshold 实验。

## 5. chunk_size / overlap

| chunk_size | overlap | hit rate | 平均返回数 |
|---:|---:|---:|---:|
| 300 | 50 | 1.00 | 3.00 |
| 500 | 50 | 1.00 | 3.00 |
| 800 | 100 | 1.00 | 3.00 |

三组在当前 20 题上没有 hit rate 差异。正确结论不是“参数无影响”，而是当前 demo 文档较短、问题与来源边界明确，这套题集不足以区分三组 chunk 策略。后续若加入长文档、表格、章节引用和更复杂跨段问题，差异可能扩大。

当前继续保留 500/50，因为它位于三组中间，兼顾上下文完整性与片段粒度，但这不是统计意义上的最优证明。

## 6. top_k

| top_k | hit rate | 平均返回数 |
|---:|---:|---:|
| 3 | 1.00 | 3.00 |
| 5 | 1.00 | 5.00 |
| 8 | 1.00 | 6.00（collection 只有 6 个 chunk） |

top_k 从 3 增加到 8 没有提升 hit rate，却扩大了 context。当前推荐 top_k=3，因为正确来源已经命中，继续增加只会引入更多弱相关片段和 token 成本。

## 7. distance probe 与 threshold

probe 结果：

- 有正确来源问题的正确来源 distance：约 0.256–0.549
- 文档外问题的最小 distance：约 0.761–0.954

因此测试 0.45、0.60、0.80：

| threshold | hit rate | refusal accuracy | 平均保留 chunk |
|---:|---:|---:|---:|
| 0.45 | 0.50 | 0.60 | 0.45 |
| 0.60 | 1.00 | 1.00 | 1.90 |
| 0.80 | 1.00 | 0.95 | 4.75 |

0.45 过严，丢失一半正确来源；0.80 过宽，让至少一个文档外问题保留弱相关 chunk；0.60 在当前固定集上实现 hit/refusal 平衡。

推荐值 0.60 只适用于当前 embedding 模型、cosine collection、三份 demo 和问题集。更换模型、metric 或文档后必须重新 probe。

## 8. metadata filtering

对 q001（报销）和 q005（P0）分别限定报销文档、运维文档：

- 报销 filter 下，返回来源全部是 `company_reimbursement_policy.txt`。
- 运维 filter 下，返回来源全部是 `product_ops_manual.txt`。
- 错误范围会排除正确来源，因此 filter 是检索范围约束，不是自动提高正确率的魔法。
- 不传 filter 时仍保持全库检索。

metadata filtering 适合用户明确选择知识库、部门或文档范围；它不是权限系统，权限校验仍需在更外层完成。

## 9. keyword 与 vector 对比

透明 keyword baseline 的代表结果保存在 `keyword_comparison.csv`：

- `P0 的目标响应时间` 等精确术语题得到较强字面信号。
- `严重故障多久要有人确认` 等语义改写仍可能命中，但 keyword score 明显降低。
- 向量检索更适合语义相近但词面不同的问题。

当前 keyword retriever 只是教学基线，不是 BM25。成熟 BM25 会考虑词频、逆文档频率和文档长度。hybrid search 可以合并 BM25 与 vector 候选；rerank 位于初召回之后，对候选重新排序。本项目本周只说明设计，没有接外部 reranker。

## 10. Debug Log

### refusal evaluator 漏识别真实措辞

- 现象：baseline 模型明确回答“没有文档依据，无法回答”，但首次 refusal accuracy 是 0.80。
- 根因：拒答短语表没有覆盖这类真实表达。
- 修复：先添加失败测试，再加入“没有文档依据”的识别，并重新人工复核 baseline。
- 结果：baseline refusal accuracy 为 1.00。

### sandbox 阻止创建 eval Chroma

- 现象：首次运行报 `PermissionError: data/eval_chroma_db`。
- 原因：当前工具对项目外写入有限制。
- 处理：只为已批准的实验命令申请权限；路径安全函数仍拒绝 production Chroma。

### 跨进程 embedding 缓存不共享

- 现象：多条独立 CLI 命令会重复生成 question embeddings。
- 影响：增加实验时间与少量 API 成本，但不改变结果。
- 后续：可把完整矩阵放进同一 Python 进程共享缓存；本周不为性能优化重构实验含义。

## 11. 局限

- 只有 20 题和短 demo 文档，不能代表生产数据分布。
- answer accuracy 是单人逐题复核，不是多人一致性标注。
- baseline 只运行一次，没有置信区间。
- 没有实现正式 BM25、hybrid fusion 或 reranker。
- threshold 对 embedding 模型和 distance metric 敏感。

## 12. 当前推荐配置

- chunk_size=500
- chunk_overlap=50
- top_k=3
- similarity_threshold=0.60（仅当前评估集）

推荐依据是当前实验的稳定性、较小 context 和拒答平衡，而不是声称全局最优。
