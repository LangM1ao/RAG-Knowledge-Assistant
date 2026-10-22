# 2026-10-22 检索质量升级：挑战、修复与验收

## 范围
正式运行工程 E:/RAG项目/rag-knowledge-assistant-bm25，起点296a25f，升级分支codex/retrieval-quality-upgrade。本次不扩展Agent、登录/RBAC、异步队列或V1.5的其他功能。Notion里已有V1.5历史笔记，本轮只追加当前工程实测，不能把两套评测数字混用。

## 用户亲测与实际排查
- 用户亲测：中文姓名找不到英文简历学校，英文姓名成功；联合询问学校和最终均分时整题拒答。
- 本轮升级前复现：6问×3模式18次；中文姓名3问均零召回。3条真实问答中中文学校停在检索层；英文学校PASS；联合问题生成阶段直接拒答。
- 已确认原BM25支持中文双字，cosine阈值方向和基于排名的RRF正确。vector_score命名易误解，保留兼容并新增明确字段。
- 旧分块存在顺序、字符offset、硬长度和章节元数据问题；旧重建先删后Embedding，失败会丢可用索引。

## 实施中真实挑战和取舍
1. **运行库与本地库不同**：本地data/uploads为空，真实简历位于Docker named volume。先核对运行服务，再停止后端复制数据快照，避免对空库得出错误结论。
2. **已存在未提交升级**：答案校验文件已保存但未进入Git。先备份差异与源码，后以独立提交9a4b275保存，之后才提交本次改动。
3. **SQLite类型不一致**：mock连接设了Row，真实仓储返回tuple；容器读取别名失败。用真实连接补失败测试，别名模块显式设置Row并关闭连接，原用例通过。
4. **结构切分引入召回退化**：首次新索引学校问题仅命中个人信息，学校块distance约0.713，被0.6阈值过滤。去姓名内容查询约0.655，仍失败；用已登记实体前缀丰富Embedding输入后约0.403。保持阈值和原文不变，重建后中英文学校与联合问题均恢复。
5. **字段诊断覆盖不足**：最初查Final Average/无空格75/100，没有匹配。最终实际原文是Overall GPA: 75 / 100，不能声称原文没有成绩。保留此更正；不能把GPA标签无条件改称最终毕业均分。
6. **拒答评估口径过窄**：合成测试最初23/24，唯一失败回答为“当前资料没有提供密码，无法确定”，sources为空，校验为PASS。评估器错误地只接受SKIPPED/FAIL。保留真实回答、人工核对并修正规则为24/24；没有改答案来凑通过。

## 实际完成
结构/页码/真实offset；明确文档别名；Unicode标准化；实体Embedding上下文；稳定去重RRF；受限同章节邻块；上下文预算；部分回答与引用；默认关闭的服务端+请求双调试开关；可恢复重建；前端“检索设置（高级）”。

## 证据和限制
完整测试、真实结果和旧固定题对比见eval_results/及本轮comparison报告。真实简历回答原文和失败尝试只存backups，不进入Git。公开报告不含简历原文、问题姓名或UUID。

固定26题使用来源级Hit/Recall/MRR，本轮未提高：Vector21/22、BM25/Hybrid22/22；Vector空检索拒答准确率25/26降至24/26，BM25/Hybrid24/26不变。没有据此宣称所有指标改善。未做所有26题生成准确率评估；带缓存延迟不当作生产性能比较。

BM25单独面对“英文简历+中文学校语义”仍可能只命中姓名词项，不能把别名等同于翻译。本轮真实学校依据在Vector/Hybrid稳定召回；这是推荐Hybrid的具体边界，而非承诺BM25全场景解决。

原文出现GPA75/100并不是把用户提供的预期写入代码：值来自PDF教育片段，引用指向该真实chunk。合成数据使用76/88两个不同人物，独立/tmp数据库验证，未污染私人知识库。

## 保存与复盘入口
- docs/retrieval_upgrade_diagnosis.md：实施前诊断及后续更正。
- docs/retrieval_upgrade_tutorial.md：八部分教学与面试问答。
- docs/retrieval_upgrade_code_walkthrough.md：最终完整源码与逐行导读。
- docs/change_history.md：历次记录保存审计。
- eval_results/retrieval_upgrade_comparison.md：前后对比、运行证据与未执行项。
- backups/retrieval_upgrade_20261022/：升级前源码zip、Git bundle、diff、原Docker数据、真实简历原始回答、首次失败结果。
- Docker data/index_backups/：每次单文档重建的原文件、元数据、向量及journal。

## 启动与旧文档
在工程目录运行 docker compose up -d --build --wait，前端http://127.0.0.1:8501，后端http://127.0.0.1:8000/docs。停止用docker compose down，不加-v。

本地两窗口分别运行 .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 和 .venv\Scripts\python.exe -m streamlit run frontend/streamlit_app.py。当前知识库在Docker卷，本地启动不会自动看到同一数据。

本轮真实简历已安全重建，其余旧文档需要重新索引才能获得章节/页号/实体上下文。先设置别名，再点“重建文档”或POST /documents/{document_id}/rebuild；不会要求重新上传或清空库。API说明备份路径，失败保留旧索引。单API worker是本轮恢复锁的适用范围。
