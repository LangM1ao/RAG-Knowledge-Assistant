> 本文为上次答案校验的历史验收快照；本轮已支持部分回答、实际引用及隐私诊断。当前行为与最新测试见retrieval_upgrade_20261022.md，历史75 passed不代表当前测试总数。

# 答案依据校验：使用与验收

本次在现有工程 `E:/RAG项目/rag-knowledge-assistant-bm25` 原地增加答案校验。原分支 `feature/bm25-hybrid-retrieval`，实现前最近提交 `296a25f`。没有新建项目、重置工作区、修改真实 `.env` 或推送 GitHub；原有未跟踪文件保持原样。

## 流程

升级前：用户问题 → 原有检索与过滤 → LLM 生成 → 返回答案与来源。

升级后：用户问题 → 原有检索与过滤 → LLM 生成 → 二次 LLM 校验 → PASS 返回原答案与来源 / FAIL 拒答 / 服务异常提示稍后重试。

原有 threshold 只过滤向量分支，BM25 和 RRF 没有新增阈值。检索无片段直接拒答，不调用生成或校验模型。开启校验时，生成 Prompt 要求依据不足只输出固定拒答语；只对完整固定拒答语跳过校验，其他措辞保守地继续校验。

## verify_answer() 做什么

输入是原始问题、生成时实际使用的完整 context、生成答案。把这三项作为 JSON 数据发给同一个配置的模型，独立 system prompt 要求逐项核对事实，禁止执行检索资料、问题、候选答案里的指令。

SDK 使用 `chat.completions.parse` 和 Pydantic 定义的严格结构；`verdict` 只能是 PASS 或 FAIL，`reason` 必须是非空字符串，额外字段被拒绝。模型说 PASS 才放行；不是查找文本中是否含有 PASS。

FAIL 的原答案不会出现在接口响应或问答历史中。返回“根据当前知识库资料，无法确定该问题的答案。”，sources 为空。PASS 保留原 sources；来源仍代表提供给生成模型的检索片段，不是逐句自动验证的点击式原文定位。

API 失败、30 秒超时、模型拒绝校验、格式错误均返回“答案校验暂时不可用，请稍后重试。”，不放行原答案。异常日志只记录异常类型；正常校验日志记录结果、简短原因和耗时。没有新增数据库或框架。

## 配置与启动

不需要修改已有 `.env`，代码默认开启。需要关闭时在 `.env` 添加 `ANSWER_VERIFICATION_ENABLED=false` 并重启后端，重新开启则设为 true。没有修改真实密钥。

打开两个 PowerShell 终端，分别运行：

```powershell
# 切换到已有工程目录。
Set-Location 'E:\RAG项目\rag-knowledge-assistant-bm25'
# 使用现有虚拟环境启动后端；修改代码会自动重载。
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
# 第二个终端也切换到工程目录。
Set-Location 'E:\RAG项目\rag-knowledge-assistant-bm25'
# 启动前端，浏览器打开 http://127.0.0.1:8501。
.\.venv\Scripts\python.exe -m streamlit run frontend/streamlit_app.py
```

标准 Docker Compose 显式传递新开关；portable Compose 原本使用 `env_file: .env`，可以直接传递，未改动这个用户已有的未跟踪文件。容器重建命令为 `docker compose up --build -d`。本机未发现 Docker 命令，因此没有实际构建或运行容器。

## 自动化与真实 API 验收

自动化测试只替换外部 API 或检索依赖；保留真实 pipeline、接口、结构验证和页面逻辑。覆盖：

- 有依据答案 PASS，原答案与来源保留，校验 context 与生成 context 相同。
- 资料相关但结论无依据，以及编造 5000 元的答案 FAIL，替换答案并清空来源。
- 检索无结果不调用生成和校验；固定拒答不重复校验。
- 拒答短语后夹带编造事实仍然必须校验。
- 调用失败、超时、无解析结果、未知 verdict、缺字段、额外字段、空原因、错误字段类型均不能通过。
- 空生成结果不展示为成功；关闭开关恢复原流程。
- FastAPI 只返回并保存最终安全答案；Streamlit 显示 PASS / FAIL / ERROR，并区别服务故障和资料不足。
- 真实 OpenAI SDK 在 Mock HTTP 下发送严格 JSON Schema 并解析结果。

2026-10-09 最终自动化结果：全量 **75 passed**，其中新增校验相关测试 **29 passed**；修改前原有测试为 46 passed。语法编译检查及 Git 空白差异检查通过。保留原有 1 条 FastAPI/Starlette 的 httpx 弃用警告。两份 Compose YAML 均成功解析，默认校验开关确认为 true。

另用真实 API 单独调用 verify_answer 两次，context 均为“员工报销需要经过部门经理审批。”：

| 问题与待校验答案 | 实际结果 |
|---|---|
| 谁审批？ / 员工报销需要经过部门经理审批。 | PASS |
| 金额上限？ / 员工报销上限为 5000 元。 | FAIL |

这两次真实 API 验证了校验模块，不等于全量知识库准确率或真实前后端端到端测试。自动化验收命令：`.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`。没有重新运行需要大量真实 API 的旧评估矩阵，旧 CSV 保持原样。

## 手动验证

建立一个 TXT，只写“员工报销需要经过部门经理审批。”，上传并限定检索这个文档。

1. 问“员工报销需要谁审批？”：应正常回答经理审批，并显示校验通过和来源。
2. 问“员工报销的金额上限是多少？”：应拒答。若生成阶段已经拒答，显示跳过校验，这也是正确行为。不能为了看到 FAIL 要求生成模型必须编造。想确定性验证 FAIL，运行新增测试中的编造数字用例；真实 API 中直接校验“5000 元”的结果已为 FAIL。

## 局限与面试表述

正常事实回答多一次 LLM 请求，增加 Token 和延迟。生成与校验复用同一模型，可能有相同盲点，也可能误拒答；Prompt 对资料中的恶意指令仅有缓解作用，不能保证抵御所有提示注入。两条真实样例不能证明总体幻觉率下降幅度。

可以在面试中说：“我在原有 RAG 中保留检索无结果拒答和 System Prompt 约束，又在生成后增加基于同一份检索资料的二次 LLM 校验。通过严格结构解析处理 PASS/FAIL，对无依据答案拒答，对超时和格式错误安全返回服务提示，不放行未经校验的答案。功能支持关闭，并通过自动化回归测试及两个真实 API 样例验证，但不能保证完全消除幻觉。”
