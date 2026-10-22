# 检索质量升级诊断（2026-10-22，实施前）

## 范围与证据
实际工程为 E:/RAG项目/rag-knowledge-assistant-bm25，起点 HEAD 296a25f，分支 codex/retrieval-quality-upgrade。已有答案校验修改未提交；已备份完整源码、差异、Git 历史和停机复制的 Docker 数据到 backups/retrieval_upgrade_20261022/。原 75 项自动化测试通过（1 条依赖弃用警告）。Docker backend/frontend 均健康。当前真正上传简历在 Docker named volume，本地 data/uploads 为空，不能误测本地空库。

## 实际架构和调用流程
Streamlit -> POST /chat/query -> answer_question -> Retriever.query -> VectorStore.query / BM25Retriever.query -> reciprocal_rank_fusion -> top_k -> build_context -> generate_answer -> verify_answer -> SQLite chat_history。上传 parse_document -> rebuild_document_by_id -> chunk_text -> add_chunks -> SQLite documents。

## 已确认
1. BM25 tokenize 已支持英文标识符和中文双字片段；没有明确中英实体别名。分词不等于姓名翻译。
2. Chroma 实际 collection 为 knowledge_base_cosine，metadata hnsw:space=cosine。distance > threshold 被过滤，方向正确。vector_score 实为距离，名称含混；RRF 正确使用排名，候选数与最终 top_k 已区分，保留其设计。
3. chunk_size / overlap 按 Python 字符计算，不是 token。旧 split_into_sentences 去掉段间空白后直接拼接，所有 start/end 为 0；遇到长句先输出长句再输出此前积累的短句，可能改变顺序。overlap 加新句还可能超过 size。
4. PDF 解析丢弃页码；Chunk 无 chunk_index/section_title，不能可靠查邻块。
5. 重建先删除旧向量再请求 Embedding；API 失败时旧索引已丢。chunk 参数在重建中未从 config 传入。
6. prompt 的“依据不足只回复固定拒答”可能抑制部分回答；当前来源把全部候选作为来源，纯拒答也可能附来源；需要明确只返回实际引用。
7. 默认普通日志包含完整用户问题，前端 Week11 检索控制仍带开发阶段名，调试字段缺少逐层数量。
8. 正在运行的简历 ID 42c4c214-7899-4aff-9ed1-919af11c7609，共 19 块。真实解析文本未匹配 Final Average 或 75/100，Chroma 同样未匹配。不能把用户提供的成绩写入知识库或问答代码。

## 用户亲测与待核实
用户报告“王皓楠”问学校失败、“Haonan Wang”成功；联合询问学校/成绩出现整题拒答。以上是用户观察，具体落在哪一层需保存真实升级前后查询。尚不能断言 Embedding 不支持中文，不能声称成绩被 Chunk 截断。PDF 复杂版面/扫描内容是否无法提取仍需结合原件目视检查。

## 设计与实施顺序
保留 FastAPI/Chroma/SQLite/Streamlit，使用独立查询标准化与 SQLite 文档级显式别名，不引入框架或付费服务。保留中文双字 BM25，统一 Unicode 标准化；别名匹配后范围取交集并限制扩展，姓名只写用户授权的配置。结构/段落优先、硬长度上限、真实字符偏移和页码；邻块仅同文档同章节、限数量和总字符预算。重建先准备/验证新索引，保留旧快照并在异常时恢复，保留原文件。保留距离字段兼容别名，增加 vector_distance/vector_similarity 和可关闭诊断。部分事实有依据则回答该部分，缺失事实明确说明，现有验证器继续审查真实断言与引用。

## 受影响文件
app/services/{chunker,document_parser,document_service,vector_store,retriever,bm25_retriever,rag_pipeline,answer_verifier}.py；新增 query_normalizer.py/entity_aliases.py；app/api/{chat,documents}.py；app/schemas/chat.py；app/core/config.py；frontend/{api_client,streamlit_app}.py；测试、README、.env.example、Compose、教学/实验/面试记录。

## 验收原则
真实运行与 Mock 测试分开，旧 Week11 CSV 只作历史，不伪造同口径改善百分比。真实简历均分缺失应部分回答或拒答；另用明确标注的合成文档测试有成绩/跨块/不同人物隔离。所有运行问题记录现象、原因、改动、回归证据；私人数据快照与真实答案不提交 Git。


## 后续验证更正（2026-10-22）

本文件上方为实施前事实快照。其中“未匹配Final Average或75/100”仅是当时精确词串检索结果，不能推出没有任何成绩。最终逐段核对发现原文真实字段为Overall GPA: 75 / 100（含空格）；新学校教育块已包含该原文。最终回答允许引用该GPA，但不无条件把它改称最终毕业均分。

第一次结构分块后发生召回回归：学校块约0.713，去姓名查询约0.655，均未过0.6。明确实体身份作为Embedding上下文后约0.403，保持阈值和原文不变；完整最终修复/验证见本轮复盘。
