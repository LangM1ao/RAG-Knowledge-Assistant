# 通用检索真实对照（2026-10-22）

基线1d39989；after文件在本轮未提交工作树上执行，code_commit字段是当时HEAD父版本，不是声称after运行了旧代码。源码升级前zip/Git bundle保留。题目与语料固定，SHA256在JSON中；最终源码版本由本轮提交和manifest追溯。

8份非私人合成文档，24题，其中22可答、2不可答；每轮Vector/BM25/Hybrid各24次检索。参数TopK3、最大距离0.60、分块500/50。

## 全量检索：before_v1 → after_v2

| 模式 | 来源Hit/旧Recall@3 | 来源MRR | 证据Recall@3 | 上下文证据Recall | 空检索拒答准确率 |
| --- | --- | --- | --- | --- | --- |
| vector | 0.9545 → 1.0000 | 0.9318 → 0.9545 | 0.9545 → 1.0000 | 0.9545 → 1.0000 | 0.9583 → 1.0000 |
| bm25 | 0.7727 → 0.6364 | 0.7500 → 0.6364 | 0.5909 → 0.6364 | 0.5909 → 0.6364 | 0.7917 → 0.7083 |
| hybrid | 0.9545 → 1.0000 | 0.9242 → 0.9697 | 0.9091 → 1.0000 | 0.9091 → 1.0000 | 0.8750 → 0.9583 |

旧Week11 Recall@K是单个expected_source是否出现，因此与来源Hit相同；它不能证明正确事实召回。新证据指标要求expected_evidence文字在真实来源块内，不会把模型记忆当RAG成功。多事实按证据组平均召回；不是所有生产文档的通用金标。

BM25来源Hit和MRR确实下降：g06/g07/g08/g24之前命中同文件错误章节，证据为0；修复后无共同内容词项就返回空。g16多实体证据0→1。证据召回总体提升，不隐藏负数，不要求BM25翻译。

## 真实答案抽样：边界必须分清

| 模式 | before_v1答案/拒答准确率 | after_v1答案/拒答准确率 | before→after_v1引用精确率 |
| --- | --- | --- | --- |
| vector | 1.0000/1.0000 | 1.0000/1.0000 | 1.0000 → 1.0000 |
| bm25 | 0.5000/0.5000 | 0.5000/0.5000 | 1.0000 → 1.0000 |
| hybrid | 1.0000/1.0000 | 0.8333/0.8333 | 1.0000 → 0.8333 |

上述两轮均抽g01/g03/g04/g06/g09/g11共6题×3模式=18份输出，有些为空检索直接拒答，没有发生生成API请求。引用精确率仅对有引用输出计算；证据片段支持来源，不能取代逐断言人工核对。答案rubric检查预设关键词组、全部context证据、实际证据来源、禁词及原校验PASS；它不是独立语义金标。保存了原始答案以便复核。

after_v1 Hybrid g11失败：问题问未知密码，答案额外引用真实但无关的access背景，校验PASS不等于回答相关。补通用编号匹配门槛及生成相关性规则后，after_v2仅针对g11三模式生成最终输出，3/3正确拒答、无引用（全部空候选直接拒答）。这不是最终18份全量QA重跑。额外after_no_evidence_probe针对无技术编号g22三模式也3/3正确拒答；Hybrid仍召回背景，依靠正确生成拒答，不把空检索指标当最终答案指标。没有把重用旧输出拼成一轮全新100% QA。

## 已运行验证

- 基线133项；最终151项自动化通过，1条既有Starlette/httpx弃用警告。
- 最终Docker镜像build/up --wait及双健康通过；API/前端HTTP200。
- 隔离PDF/TXT真实API冒烟27/27：上传、真实页号、别名后重建、76/88事实隔离、拒答、删除、重建不重复、新历史参数/校验。
- 初次25/26失败原报告保留。新标准实体名保存后未重建导致旧向量缺身份；按照已有流程重建后在同0.60阈值召回并回答88/100。测试修正了准备步骤，没有降低断言。
- 私人生产文档只重建已明确授权的一份，24块，原始文件不改，9条旧历史metadata仍未知。中文截图项目问题已真实召回并回答PASS。

缓存Embedding改善成本但不能用于宣称生产速度提升。8份24题小语料不能证明企业级规模或所有多语言问题完全解决；语义噪声、标题启发式、OCR/复杂表格仍有限制。

## 复现命令

在项目目录（会有真实API费用；run-id换成新值，禁止覆盖旧隔离库）：

```powershell
.venv\Scripts\python.exe -m evals.run_general_retrieval --stage after --with-answers --run-id my_run
docker compose cp evals/run_container_general_smoke.py backend:/tmp/general_smoke.py
docker compose exec -T backend python /tmp/general_smoke.py
```

原始JSON：general_retrieval_before_v1.json、general_retrieval_after_v1.json、general_retrieval_after_v2.json、general_retrieval_after_no_evidence_probe.json、general_retrieval_container_smoke_before_alias_rebuild.json、general_retrieval_container_smoke.json及general_retrieval_runtime_health.json。
