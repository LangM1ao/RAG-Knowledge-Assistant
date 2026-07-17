# Week12 Day 1：最终项目检查、依赖整理与配置安全

> 项目：面向企业知识库场景的 Production-aware RAG 智能问答系统  
> 今日主题：让“我电脑上能跑”进一步变成“别人知道怎样安全地复现”  
> 当前结论：Week8–Week11 主链路和 32 项自动化测试保持不变；Day 1 只做交付前的最小整理。

## 今天学什么

今天学习六件彼此相关的事情：

1. 什么叫项目交付和可复现；
2. 怎样确认 FastAPI、Streamlit 和原有测试仍然可用；
3. `requirements.txt` 为什么要干净、完整；
4. `.env` 与 `.env.example` 有什么区别；
5. `.gitignore` 如何保护 API Key、本地数据库、上传文件和缓存；
6. 怎样用证据完成一次安全检查，而不是只凭感觉说“项目没问题”。

今天不增加 RAG 功能，也不开始 Docker。收口阶段最重要的能力不是继续堆功能，而是证明现有系统可理解、可运行、可验证。

## 为什么今天要学这个

一个项目在开发者自己的电脑上能运行，并不等于它已经可以交付。别人拿到仓库时至少会问：

- 我需要安装哪些依赖？
- 我需要提供哪些配置？
- 哪些文件是源代码，哪些只是你电脑上的运行数据？
- 有没有 API Key 泄露风险？
- 我怎么确认后端和前端真的能启动？
- 改完配置以后，原来的功能有没有被破坏？

这些问题对应的是 AI 应用工程师的工程基本功。简历可以写“实现了 RAG”，但面试官往往会继续追问“别人怎样运行”“配置如何管理”“数据如何持久化”“密钥如何保护”。Day 1 就是在准备这些答案。

## 它和最终 RAG 项目的关系

这个项目的数据链路是：文档上传 → 解析 → chunk → embedding → ChromaDB → query 检索 → 将 context 交给大模型 → 返回回答和引用来源。

依赖、配置和本地数据分别支撑这条链路：

- 依赖声明让 FastAPI、Streamlit、ChromaDB、OpenAI SDK 等组件能够安装；
- 环境变量告诉系统使用哪个模型、数据保存在哪里、检索参数是多少；
- `.gitignore` 防止真实 API Key 和运行数据混入源码仓库；
- 自动化测试和启动探测证明整理配置没有破坏主链路。

所以 Day 1 看似没有新增功能，实际上是在给最终 Docker、README 和 GitHub 交付建立可信基线。

## Week11 已经有什么，Week12 今天要完成什么

Week11 已经完成了固定问题集、检索评估、参数实验、metadata filtering、关键词检索对比和实验结果记录。当前代码还包含 Week8–Week10 的文档管理、RAG 问答、引用来源、无依据拒答、FastAPI 后端和 Streamlit 前端。

Day 1 不重新实现这些能力。今天完成的是：

- 对现有测试做基线检查；
- 删除依赖声明中的重复项；
- 把 `.env.example` 写成安全、可复制的模板；
- 新增 `.gitignore`；
- 保留数据目录结构，但不提交真实运行数据；
- 扫描明显密钥格式；
- 验证后端和前端能启动；
- 记录已验证内容与暂未完成内容。

## 这个模块是什么

### 1. 项目交付

项目交付不是“把代码压缩发给别人”。它是把代码、依赖说明、配置说明、运行方法、验证方法和展示材料组织成别人能够理解和复现的成果。

对秋招项目来说，交付质量会直接影响可信度。一个功能很多但无法启动的仓库，通常不如一个范围清楚、步骤可靠、证据完整的小型项目。

### 2. 可复现

可复现是指另一个人在合理接近的环境中，按照文档安装依赖、填写配置、执行命令后，能够得到相同类型的运行结果。

可复现不等于所有电脑必须得到字字相同的大模型回答。大模型输出可能变化，但服务能启动、接口格式一致、文档能入库、检索逻辑能执行、测试能通过，这些工程行为应当可重复。

### 3. `requirements.txt`

这是 Python 项目的直接依赖清单。执行 `pip install -r requirements.txt` 时，pip 会按照它安装项目需要的库。

它不是“当前虚拟环境所有包的垃圾桶”。直接使用 `pip freeze` 可能写入大量间接依赖、实验包和机器特有版本，使文件难以维护。当前项目选择保留代码直接使用的包，并删除重复声明。

### 4. `.env` 与 `.env.example`

`.env` 保存本机真实配置，例如真实 API Key。它属于本地秘密，不应上传。

`.env.example` 是公开模板，只告诉别人需要哪些变量以及示例格式。别人 clone 项目后复制它为 `.env`，再填写自己的 Key。

一句话记忆：`.env.example` 交“字段说明”，`.env` 放“真实答案”。

### 5. `.gitignore`

`.gitignore` 告诉 Git：哪些未跟踪文件不应该加入版本控制。它可以避免误提交 `.env`、虚拟环境、缓存、上传文件和本地数据库。

它有两个重要边界：

1. 它不会删除你的本地文件；
2. 它不会自动取消已经被 Git 跟踪的文件。

如果某个秘密曾经进入 Git 历史，仅新增 `.gitignore` 不够。必须撤销旧 Key，并根据仓库情况清理历史。

## 新手容易误解什么

### 误解一：项目能启动，就不需要整理依赖

你自己的虚拟环境可能已经安装过很多包。别人 clone 后没有这些隐含依赖，因此必须有明确的依赖文件。

### 误解二：有 `.gitignore` 就绝对不会泄密

`.gitignore` 只约束未跟踪文件。已经提交过的 `.env` 仍可能存在于历史记录中，所以还需要 `git status`、`git ls-files` 和历史扫描。当前项目缺少 `.git` 元数据，今天只能完成工作区安全规则，不能声称 GitHub 历史已经安全。

### 误解三：ChromaDB 和 SQLite 都应该提交，别人才能运行

它们是运行时数据，不是项目源码。提交它们可能带来隐私、体积、跨环境兼容和状态不一致问题。更好的做法是提交创建目录和初始化数据库的代码，让别人运行后生成自己的数据。

### 误解四：`.env.example` 应该复制真实 Key，方便别人测试

绝对不可以。公开模板只能放占位符。每个使用者应使用自己的 Key。

### 误解五：收口阶段继续加功能更能丰富简历

无限加功能会增加不稳定点，并让你更难讲清设计取舍。秋招项目需要明确范围、真实能力和可以演示的闭环。

## 项目里应该怎么设计

今天采用最小整理策略：

- 保留 `app/`、`frontend/`、`evals/`、`tests/` 和 `demo/`；
- 不修改 RAG 主链路、API schema 或页面行为；
- `requirements.txt` 只保留不重复的直接依赖；
- `.env.example` 与 `app/core/config.py` 的变量名保持一致；
- `.gitignore` 精确忽略运行数据，但保留 demo、评估 CSV、文档和截图；
- 在运行数据目录中加入空的 `.gitkeep`，让未来仓库可以保留目录结构；
- 用自动化命令验证规则，而不是只肉眼查看。

`.gitkeep` 不是 Git 的特殊语法。它只是社区常用的空文件名，因为 Git 本身不跟踪空目录。我们忽略目录中的真实数据，再单独允许 `.gitkeep` 被提交。

## 一步一步整理配置和项目文件

### 第一步：清理 `requirements.txt`

最终内容：

```text
fastapi
uvicorn[standard]
python-dotenv
pydantic
pypdf
python-multipart
chromadb
openai
requests
streamlit
pytest
```

逐行理解：

- `fastapi`：提供后端 API 框架，承载健康检查、文档管理和问答接口。
- `uvicorn[standard]`：运行 FastAPI 的 ASGI 服务器；`standard` extra 安装常用运行依赖。
- `python-dotenv`：把根目录 `.env` 加载为环境变量。
- `pydantic`：定义并校验请求/响应数据结构。
- `pypdf`：读取上传的 PDF 文本。
- `python-multipart`：让 FastAPI 处理文件上传表单。
- `chromadb`：保存和检索 chunk embedding。
- `openai`：调用 embedding 和大模型 API。
- `requests`：Streamlit API 客户端向 FastAPI 发 HTTP 请求。
- `streamlit`：构建轻量演示页面。
- `pytest`：运行自动化测试和回归检查。

原文件最后重复出现了 `requests`、`streamlit`、`pytest`。删除重复行不会改变运行行为，只让依赖声明更清晰。

### 第二步：完善 `.env.example`

最终内容：

```dotenv
# Copy this file to .env, then replace only the placeholder values you need.
# Never commit the real .env file or any API key.

# OpenAI
OPENAI_API_KEY=your_api_key_here
EMBEDDING_MODEL=text-embedding-3-small
LLM_MODEL=gpt-5.5

# Local runtime data paths (relative to the project root)
UPLOAD_DIR=data/uploads
CHROMA_DB_DIR=data/chroma_db
METADATA_DB_PATH=data/metadata.db

# Retrieval parameters
CHUNK_SIZE=500
CHUNK_OVERLAP=50
TOP_K=3
SIMILARITY_THRESHOLD=0.6
```

逐段理解：

- 开头两行提醒使用者复制模板并保护秘密。
- `OPENAI_API_KEY` 必须是占位符，真实值只写进本地 `.env`。
- `EMBEDDING_MODEL` 决定文本向量化模型。
- `LLM_MODEL` 决定最终回答使用的模型；它必须和账号实际可用模型一致。
- `UPLOAD_DIR` 保存上传原文件。
- `CHROMA_DB_DIR` 保存向量库持久化数据。
- `METADATA_DB_PATH` 指向 SQLite 文档和问答 metadata 数据库。
- `CHUNK_SIZE` 控制单个文本片段大小。
- `CHUNK_OVERLAP` 在相邻片段之间保留重复上下文。
- `TOP_K` 控制默认召回片段数量。
- `SIMILARITY_THRESHOLD` 用于过滤相关性不足的结果，并帮助无依据拒答。

为什么某些变量没有写在真实 `.env` 也能运行？因为 `config.py` 为它们提供了默认值。`.env.example` 仍然列出这些字段，是为了让使用者知道它们可以配置。

### 第三步：创建 `.gitignore`

最终内容：

```gitignore
# Secrets and local environment files
.env
.env.*
!.env.example

# Python virtual environments
.venv/
venv/
env/

# Python caches and test artifacts
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
.coverage
htmlcov/

# IDE and operating-system files
.idea/
.vscode/
.DS_Store
Thumbs.db

# Logs and temporary files
*.log
*.tmp
*.temp
~$*

# Runtime uploads and persistent databases
data/uploads/*
!data/uploads/.gitkeep
data/chroma_db/*
!data/chroma_db/.gitkeep
data/eval_chroma_db/*
!data/eval_chroma_db/.gitkeep
data/*.db
data/*.db-*
```

逐段理解：

- `.env` 和 `.env.*` 忽略真实环境配置；`!.env.example` 用 `!` 明确保留公开模板。
- `.venv/`、`venv/`、`env/` 忽略本机虚拟环境。虚拟环境体积大，并包含机器相关文件，应由依赖声明重建。
- `__pycache__/`、`*.py[cod]` 和 `.pytest_cache/` 是 Python 或测试生成的缓存。
- `.idea/`、`.vscode/` 是个人编辑器状态，不属于核心项目。
- `.DS_Store`、`Thumbs.db` 是操作系统生成文件。
- 日志和临时文件会不断变化，容易制造无意义 diff。
- `data/uploads/*` 忽略用户上传内容，其中可能包含个人或企业敏感信息。
- 两个 ChromaDB 目录是运行或实验产生的向量数据库。
- `data/*.db` 和 `data/*.db-*` 忽略 SQLite 数据库及其 journal/WAL 类伴随文件。
- 三条 `!…/.gitkeep` 允许空占位文件，使目录结构仍能进入未来仓库。

为什么不忽略整个 `data/`？因为精确规则更容易理解，也避免未来误伤需要公开的安全样例。为什么不忽略 `evals/*.csv`？因为这些真实实验结果是 Week11 的项目证据，前提是确认其中不含个人数据。

### 第四步：检查 API Key 安全

安全检查只查看变量是否存在，不打印真实值；同时在可提交的代码和文档中扫描典型 `sk-...` 格式。

如果发现 Key 曾经上传：

1. 第一时间在 OpenAI 控制台撤销旧 Key；
2. 创建新 Key 并更新本地 `.env`；
3. 确认 `.env` 被忽略；
4. 再评估是否需要清理 Git 历史。

“删除当前文件里的 Key”不能使旧 Git commit 中的 Key 失效。撤销 Key 才是第一安全动作。

## 怎么运行

### 1. 进入项目目录

```powershell
Set-Location path\to\rag_knowledge_assistant
```

命令必须在项目根目录运行，因为代码使用项目相对路径查找 `.env`、`data/` 和模块。

### 2. 创建并激活虚拟环境（新电脑）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果 PowerShell 阻止激活脚本，也可以不激活，直接使用 `.\.venv\Scripts\python.exe` 执行后续命令。

### 3. 创建本地配置

```powershell
Copy-Item .env.example .env
```

然后只在本地 `.env` 中填写自己的 `OPENAI_API_KEY`。不要把修改后的 `.env` 发到聊天、截图或仓库。

### 4. 启动 FastAPI

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

验证地址：

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

### 5. 启动 Streamlit

另开一个终端，在同一项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend\streamlit_app.py
```

浏览器访问 `http://127.0.0.1:8501`。

## 怎么验证成功

### 验证一：完整测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

本次整理前的基线是 `32 passed`。整理配置后应继续保持 32 项通过，因为今天没有改变业务行为。

### 验证二：后端健康检查

启动后访问 `/health`，预期 HTTP 状态码为 200，并包含：

```json
{"status": "ok", "service": "RAG Knowledge Base Assistant"}
```

健康检查只证明应用服务能启动和响应，不等于外部模型调用一定成功。因此还应在后续完整演示中验证真实问答。

### 验证三：Streamlit 健康检查

Streamlit 启动后访问：

```text
http://127.0.0.1:8501/_stcore/health
```

返回成功说明前端进程能够提供服务。前端是否能问答，还依赖 FastAPI 同时运行。

### 验证四：忽略规则

即使当前没有 Git 仓库，也可以用：

```powershell
git check-ignore --no-index -v .env data/metadata.db data/uploads/example.pdf
```

有规则输出代表这些路径会被忽略。再检查 `.env.example`：

```powershell
git check-ignore --no-index .env.example
```

这里预期没有输出并返回非零状态，因为 `.env.example` 应被保留。

## 常见报错和解决方法

### 1. `ModuleNotFoundError`

原因通常是没有使用项目虚拟环境，或没有安装依赖。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. `OPENAI_API_KEY` 缺失或认证失败

确认项目根目录存在 `.env`，变量名拼写正确，Key 仍然有效。不要通过打印整个 `.env` 来排查；只确认变量是否加载即可。

### 3. `Address already in use` / 端口被占用

说明 8000 或 8501 已被另一个进程使用。先确认是不是已经启动过服务，再停止自己启动的旧进程，或者临时换端口。不要盲目结束系统中的所有 Python 进程。

### 4. 前端显示后端连接失败

确认 FastAPI 正在 `127.0.0.1:8000` 运行，并先访问 `/health`。本地 `localhost` 的理解会在 Day 3 Docker 网络中进一步升级：容器内部的 `localhost` 只指当前容器。

### 5. 新增 `.gitignore` 后文件仍显示为 tracked

这说明文件以前已经进入 Git 索引。`.gitignore` 不会自动取消跟踪。在有效 Git 仓库中可以评估 `git rm --cached`，但执行前要确认路径，且不能删除本地数据。当前项目没有 `.git`，今天不执行此操作。

### 6. 为什么不用 `pip freeze` 覆盖 requirements

`pip freeze` 会记录当前环境中的直接和间接依赖，还可能包含与本项目无关的实验包。Day 1 的目标是清晰的直接依赖，不是锁定部署环境的每个传递版本。后续如果需要严格可重复构建，可以再引入 lock file，但不在本周为了炫技增加工具。

### 7. 测试出现第三方 warning

当前 FastAPI TestClient 会出现一条来自第三方兼容层的弃用 warning，但 32 项测试通过。warning 应记录和评估，不应误报成测试失败，也不应为了消除它贸然升级整个依赖树。

## Day 1 实际检查报告

### 当前结构

项目保留以下结构：

- `app/`：后端、配置、数据库和 RAG 服务；
- `frontend/`：Streamlit 与 API 客户端；
- `evals/`：Week11 评估代码和结果；
- `tests/`：自动化测试；
- `demo/`：安全的固定演示文档；
- `data/`：本地运行数据；
- `docs/`：截图和 Week12 教程。

### 本次修改

- 清理 `requirements.txt` 中 3 个重复声明；
- 为 `.env.example` 增加说明和分组；
- 新建 `.gitignore`；
- 新建三个 `.gitkeep` 数据目录占位文件；
- 新建本篇 Day 1 教程。

### 已验证证据

- 整理前完整测试：32 项通过；
- 本地 `.env` 的 `OPENAI_API_KEY` 已设置，但检查过程未显示其值；
- 可提交代码和文档未发现明显的 `sk-...` 明文 Key；
- `.env.example` 覆盖 `config.py` 使用的 10 个配置字段；
- 本地上传文件、两个 ChromaDB 目录和 SQLite 数据库在修改前已记录哈希；
- 最终测试、忽略矩阵和两个服务启动探测结果应以本次执行结束时的最新输出为准。

### 明确保留

- Week8–Week11 应用源码和测试；
- demo 文档、评估问题集、实验 CSV、实验说明和现有截图；
- 本地上传、ChromaDB 和 SQLite 数据，Day 1 不删除它们。

### 仍未完成

- 当前项目目录没有有效 `.git` 元数据，因此无法检查历史上是否提交过 `.env`，也不能确认 GitHub 远程仓库是否干净；
- 尚未完成 Dockerfile 和 docker-compose；
- 尚未完成 README 最终版、最终截图、简历描述和完整面试稿。

这些内容不是 Day 1 失败，而是 Week12 后续日期的明确范围。不能在没有证据时提前标记完成。

## 今天完成后项目进展到了哪里

项目从“功能和评估已经完成”推进到“依赖和配置交付规则已经明确”。别人未来查看仓库时，能够知道需要安装什么、配置什么、哪些本地文件不能提交，以及怎样检查服务。

对简历的意义是：你不再只能说“我做了 RAG”，还可以真实解释配置管理、敏感信息保护、依赖管理和回归验证。这些都是 AI 应用工程岗位重视的工程能力。

但 Day 1 结束后还不能写“完成 Docker 部署”或“GitHub 仓库已经清理”。简历只写真实完成、能够当场解释并演示的内容。

## 面试官可能会追问什么

### 1. 什么叫项目可复现？

可复现是指其他人拿到代码后，根据明确的依赖、配置和运行说明，能够建立环境并得到相同类型的系统行为。对 RAG 来说，大模型文本可能变化，但接口、入库、检索、引用和拒答流程应该可以重复验证。

### 2. 为什么不能提交 `.env`？

因为 `.env` 可能包含 API Key。Key 一旦进入公开仓库，别人可以冒用额度，也可能造成数据和账号风险。仓库只提交 `.env.example`，真实值由每个环境单独管理。

### 3. `.gitignore` 能解决历史泄密吗？

不能。它主要阻止未跟踪文件以后被加入。已经提交的秘密仍在历史中，首先要撤销旧 Key，再评估历史清理。

### 4. 为什么 ChromaDB 和 SQLite 不提交？

它们是运行时状态，可能包含上传文档、向量和聊天记录；直接提交会产生隐私、体积、冲突和跨环境问题。项目应通过代码初始化它们，并通过 volume 在部署环境中持久化。

### 5. 为什么不用 `pip freeze`？

当前阶段更需要清楚的直接依赖列表。`pip freeze` 会混入间接包和环境遗留包。若以后需要完全锁定版本，可以引入 lock file，但必须有明确目的。

### 6. 为什么配置清理后还要跑完整测试？

因为交付整理也可能误删依赖、改变路径或破坏启动。完整回归测试提供证据，说明 Week8–Week11 行为没有因收口工作而退化。

### 7. `/health` 通过是否代表 RAG 完全正常？

不代表。它证明 FastAPI 能启动并响应。完整 RAG 仍需验证文档上传、embedding、检索、大模型回答、引用和拒答。不同验证层次不能互相替代。

### 8. 项目交付和写 README 有什么关系？

README 是仓库入口，负责告诉招聘方和开发者项目解决什么问题、怎样运行、怎样验证以及有哪些限制。Notion 笔记服务于学习过程，README 服务于使用和评审，两者受众不同。

## 今天的 Notion 总结

今天最重要的理解不是记住几条 `.gitignore` 语法，而是建立“交付证据链”：

```text
依赖清楚
  → 配置可复制且秘密隔离
  → 运行数据不进入源码仓库
  → 测试和服务探测提供证据
  → README 和 Docker 才有可靠基础
```

项目完成不是功能数量无限增加，而是目标范围内的功能、工程、文档、验证和表达形成闭环。Day 1 的整理让后续 Docker 不会把混乱的本地状态直接封进镜像，也让最终 GitHub 仓库更安全、更容易理解。

## Day 1 完成标准

- [x] 找到真实 Week11 项目并检查当前结构；
- [x] 整理前 32 项自动化测试通过；
- [x] `requirements.txt` 的重复依赖已识别并整理；
- [x] `.env.example` 覆盖配置字段且不含真实 Key；
- [x] `.gitignore` 覆盖秘密、虚拟环境、缓存和运行数据；
- [x] 本地数据不删除，只通过规则阻止未来误提交；
- [x] API Key 检查过程不打印真实值；
- [x] 最终 32 项回归测试通过（2026-07-16 实测：`32 passed, 1 warning`）；
- [x] FastAPI `/health` 启动探测通过（临时端口 8765，返回 `status=ok`）；
- [x] Streamlit 无头启动探测通过（临时端口 8766，健康接口返回 HTTP 200 和 `ok`）；
- [ ] 有效 Git 仓库与 GitHub 历史安全检查——当前缺少 `.git`，留到仓库来源确认后完成。

完成前三项最终验证后，Day 1 的本地交付准备可以收口；GitHub 历史检查必须继续保持“未验证”状态，不能为了清单好看而虚假勾选。
