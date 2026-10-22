# 检索质量升级：零基础学习与面试复盘

本轮实际工程是 E:/RAG项目/rag-knowledge-assistant-bm25。原架构继续使用 FastAPI、SQLite、Chroma、BM25、RRF、Streamlit。完整最终实现和每行中文导读见 [代码全文与逐行说明](retrieval_upgrade_code_walkthrough.md)，不要只背概念。

## Part 1：从真实问题理解排查

你上传英文简历后，英文姓名能问出学校，中文姓名不能；一起问学校和均分时还会整题拒答。相同事实没有变，变化的是查询名称、召回片段和生成规则。

应逐层问：原文有吗？解析有吗？存入哪块？召回了吗？阈值留下了吗？最终 context 包含吗？模型回答与引用正确吗？本次确认 BM25 原本已有中文双字切分，Chroma 使用 cosine distance，RRF 使用排名，这些设计没有错误，保留。

重要更正：原文实际是 Overall GPA: 75 / 100。最初只搜索 Final Average 和无空格的75/100，遗漏了字段。不能把“搜索没命中”说成“原文没有成绩”。原文没有明确 Final Average 标签，因此回答保留 GPA 原标签，不自行断言它一定是最终毕业均分。

## Part 2：Chunk 是什么

一份文档往往比模型能高效处理的上下文长。Chunk 就是从原文取出的小片段。例如学校、学位和成绩属于同一教育章节，能放进500字符就保留在一起，不应因为其中有空行就拆开。

旧 chunk_text 按标点切句后直接拼接，段落空白会消失；遇长句还可能先输出长句、后输出此前短句，offset一律0。新 chunk_text 在原文上计算章节区间和边界，优先章节、段落/行/列表，再句子，最后字符硬切。每块严格不超过 chunk_size；需要硬切长内容时保留 overlap，完整结构边界处不机械复制。

500/50 的单位是 Python 字符，不是 token。500控制每块最多多长，50让被迫切断的长段在下一块重复末尾一小段。重叠有助连续理解，也会增加存储与费用，不能越大越好。

parse_document_pages 返回 DocumentPage；PDF页号来自 enumerate(reader.pages, start=1)，TXT页号为None。chunk_document 保存 chunk_index、section_title、真实字符位置和页码；Chroma页范围以JSON字符串保存，绝不编造页码。通用全大写标题只是启发式，复杂扫描/表格版面仍需更强解析，本轮没有实现OCR。

## Part 3：中英文检索与实体

Embedding把文字表示成数字向量，擅长语义相近表达；BM25根据词项、词频、逆文档频率和长度排序，擅长错误码、配置名。中文分词使中文词项可匹配，但不能凭空知道“中文姓名”和“英文姓名”是同一个人。

normalize_query 用NFKC统一全半角，casefold统一大小写，规范弯引号与空白，保留 API_TIMEOUT_MS 等专业标识。entity_aliases 把用户明确登记的标准名称与别名放在同一个SQLite的文档级表里。不拼音猜人，不在通用检索函数中写具体姓名。

Retriever先按用户document_ids/source_files过滤可见别名，再识别别名、用标准实体名称替换，并把检索限制到该文档。同名同时命中多份文档时保守拒绝，要求缩小范围；本轮没有完整的实体消歧或权限系统。

本次还遇到一个新问题：结构切分后“姓名块”和“学校块”分开了。仅查名字容易命中个人信息。试验中学校块distance约0.713，去名字仍约0.655，都未过0.6。最终prepare_chunks给Embedding输入加已登记Entity前缀，学校块distance约0.403，保持阈值不变。注意：这只是检索身份上下文；documents里仍保存原文，GPA来自原文，不来自别名。修改标准实体名后要重建索引。

## Part 4：混合检索和分数

Vector与BM25先各召回候选，Hybrid默认各至少8个，再按RRF排序，最终Top-K默认3。候选数量决定搜索范围，Top-K决定最终给模型多少主要证据，它们不是一回事。

RRF公式是 1/(k+rank)，本项目k默认60。同一块在两路都靠前会获得两份排名贡献。不能把cosine distance和BM25原始分数直接相加，它们量纲不同。本轮去重键为(document_id, chunk_id)，一条检索分支内重复项也不能重复投票，同分按稳定标识排序。

Chroma的cosine distance越小越接近。旧similarity_threshold其实是“最大允许距离”，保留兼容名称，distance大于阈值才过滤。vector_distance是距离；vector_similarity=1-distance是余弦相似度，可能为负数，均不等于相关性百分比。vector_score是兼容旧接口的距离别名。

阈值只作用于Vector分支。BM25或RRF得分不能和距离阈值比较。不要为了让演示成功而普遍放宽阈值；本次保持0.6，用真实候选证据判断问题。

## Part 5：命中文档为何仍可能答不全

命中某份PDF只说明它的一块相关，其他事实可能在别的块。expand_context只对明确多事实问题检查邻块；要求同document_id、同非空section_title、同source_file、chunk_index相差1，并去重和限额。普通单点问题保持原Top-K，旧块没有可靠序号/章节时不猜邻块。

最后_bounded_context按整块限制：默认最多6块、总共6000字符，连来源头和身份映射都计入。邻块保留原ID和出处，不跨文档拼接，不能把另一个人的成绩拿来补当前人的答案。

## Part 6：部分回答、拒答与引用

如果有学校依据、没有最终均分标签，合理答案是回答学校，并指出资料仅提供Overall GPA或缺少明确最终均分，不应整题拒答。完全无依据时拒答，实际断言仍要经过同一context的verify_answer。

校验器PASS表示实际作出的事实有支持；明确说明缺失并不等于FAIL。FAIL会替换答案并清空来源；超时/结构错误返回服务不可用，不能把技术故障说成没有资料。

生成模型需在事实后写[n]。sources只取实际引用的块；编号越界拒绝；完全拒答清空来源。若模型没有写引用，返回citation_status=missing、sources=[]，绝不伪造引用。模型语义校验仍可能误判，不能声称消灭幻觉。

## Part 7：完整调用链与如何操作

上传：POST /documents/upload -> parse_document -> rebuild_document_by_id -> parse_document_pages -> chunk_document -> VectorStore.prepare_chunks -> 全部Embedding成功 -> 新块入库/核对 -> 删除旧ID -> SQLite更新 -> journal committed。

问答：Streamlit -> POST /chat/query -> answer_question -> Retriever.query -> normalize_query/resolve_aliases -> VectorStore.query + BM25Retriever.query -> reciprocal_rank_fusion -> Top-K -> expand_context -> _bounded_context/build_context -> generate_answer -> verify_answer -> sources -> SQLite history。

重建之前备份原文件、原document记录、完整原向量（含Embedding），写入data/index_backups。失败时原索引继续可查或用原Embedding回滚。启动recover_pending_rebuilds处理switching日志；恢复失败阻止启动。INDEX_LOCK保护本进程读写，建议单API worker。SQLite与Chroma不是跨库原子事务，也不保证任意外部读进程看不到切换窗口。

在前端文档列表展开别名，保存标准实体名与别名，再点重建文档即可。调试默认关闭；需要受信任开发环境服务端RETRIEVAL_DEBUG_ENABLED=true且请求debug=true才能返回完整诊断。折叠面板不等于权限系统，普通日志不写完整查询、文档或Prompt。

## Part 8：面试能怎么讲

1. 为什么优化Chunk？原切分丢掉结构、可能改变顺序；我保留章节和真实偏移，同时硬限制长度，用测试保证不丢内容。
2. 为什么中文分词还不够？分词解决字面词项，解决不了跨语言实体对应。我用用户明确登记的文档级别名，范围过滤始终生效。
3. 结构切分为什么曾让效果下降？姓名和事实分离后，检索只命中姓名。我对照阈值前候选，试过去姓名但未通过；最后加入显式身份Embedding上下文，并重建验证。
4. 为什么RRF不混原始分数？距离和BM25分数量纲不同，使用排名贡献更容易解释；它仍可能强化两路共同偏差，不能保证优于每一种单路。
5. 如何防编造？只用实际context生成，支持部分回答；同context二次校验和真实编号引用，纯拒答不附来源。
6. 如何证明改好？用相同26题/3demo/参数做前后对比，另保存真实中英姓名及联合问题。来源级Hit未提高也如实报告，不能用它冒充事实完整率。
7. 遇到哪些真实整合问题？SQLite tuple/Row不一致曾漏过mock测试，容器API验收发现后补真实连接回归；拒答判定器错误地排除了PASS状态的忠实缺失说明，保留原回答后修正评估口径。
8. 如何保护旧数据？先备份、先准备新Embedding、再验证切换、异常用旧Embedding回滚；明说不是分布式事务。

30秒表述：我从自己测试时的中英文姓名不一致和联合问题整题拒答出发，按解析、分块、召回、阈值、上下文、生成逐层排查，增加明确别名与实体上下文、结构分块和可回滚重建，再用回归和真实API验证。效果与限制都能指回原始记录。
