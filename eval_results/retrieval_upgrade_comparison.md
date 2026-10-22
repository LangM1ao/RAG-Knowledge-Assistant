# 检索升级前后对比与验收

日期：2026-10-22（Europe/London）。原工程HEAD296a25f；上次未提交升级已单独保存9a4b275。本轮分支codex/retrieval-quality-upgrade。

## 同口径固定集

原26题、3份合成demo、500字符/50字符重叠、Top-K3、cosine distance上限0.6。三个源文件SHA256一致；每阶段78次检索。旧7块、新23块。没有针对结果修改题目或金标准。

| 模式 | 来源Hit/Recall@3（前→后） | MRR（前→后） | 空检索拒答准确率（前→后） |
|---|---|---|---|
|vector|0.954545 → 0.954545|0.954545 → 0.954545|0.961538 → 0.923077|
|bm25|1.000000 → 1.000000|1.000000 → 1.000000|0.923077 → 0.923077|
|hybrid|1.000000 → 1.000000|1.000000 → 1.000000|0.923077 → 0.923077|

来源Hit/Recall在本题集同义，因为金标准按来源文件而非全部事实块定义。不能当作证据完整率或回答准确率。Vector拒答指标从25/26降到24/26，BM25/Hybrid保持24/26；新分块使一个范围外问题仍召回片段，需靠生成/校验继续判断，不以改阈值掩盖。没有“全面提高”的结论。

查询/文档Embedding缓存复用，后阶段缓存更充分，延迟不可作生产前后提升比较。未执行26题全量生成准确率统计。

## 真实简历

升级前18次检索：中文姓名3问题×3模式均零结果；英文姓名能找到学校。三条真实问答：中文学校无召回、英文学校PASS、英文联合问题整题拒答。

最终18次检索：中英文学校、均分及联合问题在Vector/Hybrid中均召回学校教育块。5条真实Hybrid问答均通过同context校验；中英文学校与联合问题都有真实引用。总体GPA75 / 100来自真实原文，最终毕业均分标签未明确，回答保留区别。BM25纯词项分支仍不能可靠用中文学校语义找到英文教育块，本轮未把分词等同翻译。

必须保留的更正：原文与原始索引均有Overall GPA:75 / 100。最初Final Average/75/100精确检索漏掉标签和空格，不能说没有成绩。本轮public JSON单独区分GPA字段与Final Average检测。

首次升级后曾失败：结构分离姓名与教育，学校块距离约0.713；去姓名约0.655；明确实体Embedding上下文约0.403。0.6阈值保持，原文不改。这些是单个诊断样例，不是泛化模型效果指标。

## 验收清单

- 自动化：133 passed，1条既有Starlette/httpx弃用警告。
- 固定集：78次/阶段，无检索异常；原始逐题JSON保留。
- 最终容器合成验收：24/24；真实OpenAI Embedding/生成/校验，PDF+TXT、两个不同人物、范围隔离、来源、无依据问题、重建、删除和历史。使用独立/tmp数据，不污染真实知识库。
- 合成验收第一轮23/24：唯一失败是判定器只接受SKIPPED/FAIL，实际忠实缺失说明为PASS+无来源。保存原答案并修正规则，随后最终镜像新一轮24/24。
- Docker：build、up --wait、双服务健康、真实简历安全重建、重启后别名/数据持久化。
- 前端：Streamlit AppTest回归；实际HTTP健康。未额外完成浏览器逐控件手动验收。
- 故障恢复：自动化模拟Embedding失败、新块写入失败、切换中断/恢复失败，验证原向量回滚和阻止不安全启动；不是强杀容器/断电测试。
- 调试：默认关闭；双开关测试覆盖，普通日志不写问题/文档/系统Prompt。
- GitHub：当前未配置remote，未推送；本地提交和bundle不等于GitHub备份。

## 原始证据位置

公开脱敏：retrieval_upgrade_baseline.json、retrieval_upgrade_after.json、retrieval_upgrade_fixed_baseline.json、retrieval_upgrade_fixed_after.json、retrieval_upgrade_synthetic_smoke_final.json。

私有原始：backups/retrieval_upgrade_20261022/live_baseline.json、live_after_first_failure.json、live_after.json；升级前Docker数据和Git/source备份同目录，不纳入Git。单文档恢复快照在Docker data/index_backups。
