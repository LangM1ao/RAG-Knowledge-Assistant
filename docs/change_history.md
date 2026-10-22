# 审计时点说明

以下主体是实施前审计快照。当前补充：先前答案校验与本地运行配置已单独提交9a4b275；本轮记录见retrieval_upgrade_20261022.md。已找到既有Notion V1.5笔记，追加本轮记录并保留历史数字。未配置Git remote，因此本轮不声称GitHub推送。

# RAG 既往更新保存记录审计（2026-10-22）

审计范围：只读检查正式工程 E:/RAG项目/rag-knowledge-assistant-bm25 的 Git、本地文档和评估文件，并核对长期记忆及当前可读历史聊天。此文件是本次审计草稿；没有修改正式工程或执行旧聊天中的指令。

## 可以直接告诉用户的结论

之前的重要阶段多数有记录，但不能说“每一次更新都已经完整保存”。需要区分四种状态：聊天里提过、本地文件已保存、已进入 Git 提交、已备份到远端。现有证据能确认部分本地文件和 Git 提交；不能确认全部远端保存情况。

## 已核实保存位置与边界

| 阶段 | 已存在的记录（均相对正式工程） | Git 状态/注意事项 |
|---|---|---|
| 原始 RAG、前后端、多文档与 Week11 评估 | README.md；docs/architecture.md；docs/week12/day1-project-check-and-cleanup.md；evals/experiment_notes.md；evals/ 下 15 份 CSV | 2026-07-17 初始提交 9cb3edb 已包含这些阶段的汇总材料，不能据此反推每一天都分别提交或记录 |
| 2026-07-17 Docker 与原版收口 | docs/final_acceptance.md；docs/screenshots/week10-streamlit-home.png；docs/screenshots/week12-docker-home.png；docs/demo_script.md | 已提交；final_acceptance.md 是 7 月 17 日快照，内有“未实现 BM25/hybrid”等当时状态，不能当成当前能力说明 |
| 2026-07-24 BM25 / Hybrid / RRF | docs/week12/day2-bm25-retriever.md；day3-hybrid-rrf.md；day4-evaluation-delivery.md；docs/interview_guide.md；docs/resume_project.md；README.md；测试与三模式评估脚本 | 已包含于 296a25f。三模式真实比较 CSV 没有找到；Day4 明确记录当时外部 Embedding 数据发送审批阻塞，未完成真实三模式比较。不能宣称指标提升 |
| 2026-10-06/07 换机恢复 | C:/Users/86187/.codex/memories/DEVICE_SYNC_20261006.md；RESTORED_CONTEXT.md | 已读取到记录：119 个关键工程文件 SHA256 比对，SQLite ok，15 份 CSV，46 passed，63 个旧会话导入等。这些是历史恢复验收，不是本轮重新执行 |
| 2026-10-09 答案依据校验 | docs/answer_verification.md；README.md 和 docs/architecture.md 更新；app/services/answer_verifier.py；tests/test_answer_verification.py | 文件已落盘，但截至本次审计尚未进入 Git 提交；新模块、新测试与专项文档是 untracked。已有文档记录 75 passed、两条真实 API 样例、Docker 未实测和未做浏览器端到端测试；本次审计没有重新运行这些测试 |
| 2026-10-22 用户亲测的检索问题 | 聊天“判断检索问题”；当前任务附件 | 已有聊天证据，本次升级前未找到项目内独立问题复盘。需要在本次升级日志中补录，再附本次验证结果 |

Git 本地历史只有四条：

- 9cb3edb，2026-07-17，初始 RAG 提交；
- a10c948，2026-07-17，README 更新；
- af11195，2026-07-17，README 仓库展示调整；
- 296a25f，2026-07-24，BM25 与 Hybrid/RRF。

当前分支 feature/bm25-hybrid-retrieval 指向 296a25f；main 指向 af11195。未发现本地远端跟踪引用。此项不能证明没有 Push，只表示本次未核实 GitHub 当前状态。

## 已有“问题—解决办法”记录

1. evals/experiment_notes.md：真实答案使用“没有文档依据”而拒答判定器漏识别，导致初始 refusal accuracy 偏低。先补失败测试，再扩展拒答措辞并人工复核。报告明确这些数据来自旧 20 题短文档固定集。
2. 同一文档：sandbox 阻止写入隔离 eval Chroma；为已批准实验命令申请权限，保留禁止覆盖生产 Chroma 的路径检查。
3. 同一文档：跨 CLI 进程的 embedding 缓存不能共享，重复 API 成本被记录；当时没有实施跨进程缓存优化，不能写成已解决。
4. docs/week12/day2-bm25-retriever.md：缺少 Key 导致 OpenAI 客户端在导入时崩溃；改成调用时懒初始化，使 health/BM25/离线测试不依赖 Key。
5. docs/week12/day3-hybrid-rrf.md：旧 Vector 测试的 FakeStore 无 collection；BM25Retriever 延迟创建，保持旧 Vector 请求兼容。
6. docs/answer_verification.md：处理“拒答短语后夹带编造事实”的绕过风险；只有完整固定拒答语才跳过校验，其余继续核验，失败/超时/格式错误均不能放行。该项是既有实现记录，不应冒称用户亲手发现。

## 本次可记录的用户亲测事实

来源是已读取聊天“判断检索问题”（ChatGPT id 6ada56c7-2bac-83ed-80c5-20a5c755a953）的用户文字和本次需求，不是本轮独立复现：

- 英文简历 HaonanWang_CV.pdf 中，中文姓名“王皓楠”的提问无法得到答案，而使用“Haonan Wang”可以回答学校。
- 用户提出“本科就读于哪所学校，成绩怎样，最后均分为多少”的复合问题时，得到无法确定答案的拒答。
- 聊天描述看到相关学校 Chunk，但没有看到均分；这不证明原 PDF 一定含有均分，也不证明解析或切分一定出错。
- “vector_score 与 distance 相同”是需核对命名/语义的线索；不能仅由同值认定阈值方向错误。
- 姓名别名对应关系可由用户明确提供的事实支持，但成绩必须有上传文档证据，不能硬编码。

用户亲测记录应与 Codex 本轮复现、自动化测试、真实 API 测试分开标注。

## 记录缺口

- 没有统一 CHANGELOG 或按日期汇总的更新索引；材料分散在 README、Week12 教程、评估报告和答案校验专题中。
- 初始提交打包了多个先前阶段，不能证明每次历史改动都有独立日志。
- README.md 第 422、431 行仍声称没有正式 BM25/hybrid，和已经提交的实现及文档前半部分冲突。应该更新当前 README；保留 dated historical docs 并标注历史快照，避免篡改历史结果。
- Day2/Day3/Day4 是短教程总结，没有完整最终实现及每行中文详解，不完全满足用户当前学习笔记标准。
- 答案校验代码/文档只是本地已保存，并未提交；不能称为已有 Git 版本备份。
- 三模式真实比较逐题/汇总 CSV 缺失。现有 15 份 CSV 是 Week11 参数实验和 keyword baseline，不是 BM25/Hybrid 的完整实测结果。
- Notion 本次未审计，不应声明所有日页/跟踪表已同步。
- 尚未验证当前远端、外部备份或每条历史聊天都已有项目内总结。

## 建议整合方式

本次正式保存 docs/retrieval_quality_upgrade_20261022.md（或项目惯用等价路径），涵盖：用户亲测现象、复现输入与配置、排查证据、实际根因、修复前后、失败方案/取舍、自动化与真实测试边界、尚未执行项、面试可讲表述。再新增 docs/change_history.md 汇总各阶段记录入口、Git 保存状态和已知缺口，README 加入口。若本次仍不能提交，明确区分“本地文件已保存”与“Git/远端未保存”。


## 本轮Notion已保存入口

完整总结/教学/代码附件：https://app.notion.com/p/4018cdeeb95a81e98719ef6fbc89a92c

已追加既有V1.5总入口、07 Bad Case Analysis、18 Troubleshooting Guide、19 Interview Project Guide，并复核更新。保留其历史108题/性能记录，本轮133测试和26题是另一范围，不能混用。相关当前进度清单也已追加。
