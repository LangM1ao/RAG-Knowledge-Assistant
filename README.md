# Production-aware Enterprise RAG Knowledge Base Assistant

面向企业知识库的多用户 RAG 智能问答系统。在原有中英文检索、结构化分块、BM25、Hybrid/RRF、答案依据校验和引用能力上，增加账号认证、文档所有权和后端检索权限隔离。

**RAG FINAL COMPLETED**：本地与Docker各176项测试通过，真实模型验收22/22通过。最终范围与历史数据限制见[交付验收记录](docs/FINAL_DELIVERY.md)。本阶段收尾，不继续扩展RAG功能。

## 功能与技术栈

- TXT/PDF 上传、结构优先字符分块、页码/offset、原文件保留、安全重建和回滚。
- OpenAI Embedding、Chroma cosine、中文双字/英文标识符 BM25、Hybrid/RRF。
- 查询规范化、显式实体别名、同文档同叶结构有界邻块；不硬编码姓名或问题答案。
- 无依据拒答、实际引用定位、LLM 二次答案依据校验；诊断默认关闭。
- FastAPI、Streamlit、SQLite、ChromaDB、OpenAI SDK、PyJWT、argon2-cffi、pytest、Docker Compose。
- Argon2id 密码哈希、HS256 JWT、SQLite 会话撤销、登录失败限速、Admin/User。
- Private/Shared 文档权限；Vector/BM25 同一授权集合；按用户隔离历史记录。

本机验收 Python 3.12，Docker 使用 Python 3.11。结果、失败修复与限制见 [最终报告](docs/RAG_FINAL_UPGRADE_REPORT.md) 和 [安全测试报告](docs/final_security_test_report.md)。历史评估指标不代表本次权限升级的性能。

## 架构与流程

    用户 → Streamlit → FastAPI → JWT签名/过期 + SQLite会话/账号状态
         → SQLite文档权限 ∩ 用户选择范围
         → Chroma where / 授权语料 BM25 → 原Hybrid/RRF
         → 授权邻块与有界上下文 → LLM → 答案依据与引用校验
         → 当前用户的答案、引用与历史

上传时后端取认证用户 ID 写入 owner_id，默认 private，忽略前端伪造的 owner_id。检索时先查 SQLite，主动选择的 document_id 必须全部可访问，再将最终集合同时传给 Vector、BM25、别名和邻块扩展。空授权集合直接拒答，不访问 Embedding/LLM，不退回全库。无归属的孤立 Chroma 片段不会进入授权集合。

账号登录证明“你是谁”；文档权限决定“你能看什么”。仅隐藏按钮或让 LLM 自觉拒答，无法防止直接调用 API 或另一条检索分支泄露。

## 角色与权限

| 操作 | Admin | User |
| --- | --- | --- |
| 上传文档 | 可以 | 可以，归属自己 |
| 读取/检索自己的文档 | 可以 | 可以 |
| 读取/检索其他人的私人文档 | 可以 | 不可以 |
| 读取/检索共享文档 | 可以 | 可以 |
| 删除、重建、修改别名 | 所有文档 | 仅自己的文档 |
| 设置 private/shared | 可以 | 不可以 |
| 创建、禁用、调整角色、重置密码 | 可以 | 不可以 |

最后一个有效管理员不能禁用或降权。密码重置、账号状态/角色变更撤销旧会话。退出撤销当前会话；JWT 过期也会拒绝。受保护操作在锁内重新查询会话，防止排队期间撤权仍使用旧身份。

共享撤回后，相关历史不再展示；按当次可能使用的文档范围保守隐藏，可能隐藏没有实际引用该文档的回答。升级前缺少上下文范围的旧历史保留 SQLite，但不通过新界面公开。

## 本地运行与管理员初始化

1. 建立虚拟环境，安装 requirements.txt。
2. 从 .env.example 复制 .env，设置 OPENAI_API_KEY。生成独立随机 JWT_SECRET_KEY：至少32随机字节的 URL-safe 编码，例如 Python secrets.token_urlsafe(48) 的输出；不要提交真实值。
3. 首次执行初始化命令，在终端输入至少12字符密码。仅数据库没有账号时允许初始化；启动不覆盖管理员。
4. 分别启动 API 和前端。

    python -m venv .venv
    # Windows: .venv\Scripts\activate
    # Linux/macOS: source .venv/bin/activate
    pip install -r requirements.txt
    python -m app.bootstrap_admin --username admin
    uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
    # 另一个终端
    streamlit run frontend/streamlit_app.py --server.address=127.0.0.1

打开 http://127.0.0.1:8501。管理员展开“用户管理”创建普通用户。没有公开注册或固定默认密码。初始化支持 --password-file；文件必须在受保护且 Git 忽略的目录，不能放进镜像。

## Docker

    docker compose up -d --build --wait
    docker compose exec backend python -m app.bootstrap_admin --username admin
    docker compose ps
    docker compose restart
    docker compose up -d --wait

- 常规 Compose 使用 rag-knowledge-assistant-data 命名卷，SQLite/Chroma/原文件在 /app/data。重建不删除卷；不要执行 down -v。
- portable 使用 ./data 绑定目录：docker compose -f docker-compose.portable.yml up -d --build --wait。它与命名卷不是同一套数据库，不要混用。
- 两服务只绑定主机 127.0.0.1，后端单 worker。公网需配置 HTTPS、可信代理与连接限流/超时；当前锁不能用于多 worker 或多副本。
- 文件最大20 MiB；含 multipart 开销的请求最大21 MiB，流式实际字节也计数，未认证上传在读取正文前拒绝。

## 配置

| 配置 | 含义 |
| --- | --- |
| OPENAI_API_KEY | Embedding/LLM 凭据，只放本机 .env |
| JWT_SECRET_KEY | 随机签名密钥，无可用默认值 |
| JWT_ALGORITHM | 仅 HS256 |
| ACCESS_TOKEN_EXPIRE_MINUTES | 默认60，允许1–1440 |
| METADATA_DB_PATH / CHROMA_DB_DIR / UPLOAD_DIR | 数据位置 |
| EMBEDDING_MODEL / LLM_MODEL | 沿用模型，不无故改变 Embedding |
| CHUNK_SIZE / CHUNK_OVERLAP | 原分块参数 |
| VECTOR_CANDIDATE_K / BM25_CANDIDATE_K / RRF_K | 原候选数与融合参数 |
| ANSWER_VERIFICATION_ENABLED | 默认 true |
| RETRIEVAL_DEBUG_ENABLED | 默认 false，还需请求 debug=true |
| CONTEXT_MAX_CHARS / CONTEXT_MAX_CHUNKS | 上下文预算 |

similarity_threshold 保留历史名字，实际是最大 cosine distance，越小越相似。二次模型校验降低幻觉风险，不保证答案绝对正确。

## 数据库与迁移

- users：唯一id/username、password_hash、role、is_active、created_at、updated_at。
- auth_sessions：随机jti、user_id、expires_at、revoked，不保存完整JWT。
- login_attempts：哈希化用户名/IP bucket、失败次数、15分钟窗口；用户名5次/IP30次失败限速。
- documents：保留原document_id，新增owner_id、visibility，默认private。
- chat_history：新增user_id、document_ids_json记录可能使用的上下文范围。
- entity_aliases：沿用原SQLite别名，不重建Chroma Metadata。

事务内幂等加列；首位管理员初始化接管无owner历史文档并设private。不删除文档、不换ID、不重新Embedding。升级前备份SQLite、Chroma、上传文件；回滚时先停止服务，恢复同一时间点完整数据与代码，不覆盖运行中的数据库。

## API

除 /health、/auth/login 与 API 文档外，业务接口要求 Authorization: Bearer TOKEN。认证失败401，管理员操作权限不足403；不可访问与不存在的文档统一404；非法主动检索范围403。

| 方法与路径 | 功能 |
| --- | --- |
| POST /auth/login | 用户名密码登录 |
| GET /auth/me、POST /auth/logout | 当前用户、撤销会话 |
| GET/POST /admin/users | 列出/创建账号 |
| PATCH /admin/users/{id} | 状态与角色 |
| POST /admin/users/{id}/reset-password | 重置并撤销旧会话 |
| POST /documents/upload、GET /documents/list | 上传、授权列表 |
| GET/DELETE /documents/{id} | 详情、删除 |
| POST /documents/{id}/rebuild | 所有者或管理员重建 |
| POST /documents/rebuild-all | 仅管理员，会调用Embedding |
| GET/PUT/DELETE /documents/{id}/aliases | 读取、所有者或管理员修改 |
| PATCH /documents/{id}/visibility | 管理员共享设置 |
| POST /chat/query、GET /chat/history | 授权问答、本人且仍有权限的历史 |

在 /docs 查看字段，Authorize 填令牌。Token 不放URL、日志或共享缓存。用户名大小写敏感。

## 测试与演示

    python -m pytest -q
    python -m pytest tests/test_final_auth.py tests/test_final_permissions.py tests/test_final_retrieval.py tests/test_final_integration.py tests/test_final_frontend.py -q

tests/conftest.py 强制临时SQLite/Chroma和假API key。保留原测试；API单元测试显式注入身份，安全测试实际登录并调用后端。真实临时Chroma用确定性向量与Mock LLM验证候选/引用隔离。

演示：管理员创建Alice/Bob → 各自上传私文档 → Bob三模式查询Alice测试事实无泄露 → 管理员shared → Bob可问答不可删/重建 → 撤共享历史隐藏 → 重启检查账号文档权限。

真实外部API合成验收脚本 evals/run_final_security_smoke.py 仅接受专用 rag-final-acceptance 容器，不对业务容器运行。原检索评估 evals/run_general_retrieval.py 继续使用隔离库；--with-answers产生模型费用，不以缓存延迟冒充性能提升。

## 已知限制

- 单机SQLite、单worker；权限锁覆盖长问答，其他操作可能等待，不宣称高并发。
- 模型拒答和校验可能误判；BM25跨语言词法召回有限，未加翻译/reranker/新框架。
- 不支持OCR；原文件已缺失的旧本地副本无法重建，但已有向量保留。
- 已展示/复制的内容不能被之后撤权收回；后续请求会重新鉴权。
- 部署管理员须保护.env、数据库、备份和密码文件的OS访问权限。应用管理员拥有全库读取权。
- 后续按需求补HTTPS、审计日志、并发架构；本次不做多租户、多部门、Redis、PostgreSQL或Agent。

## 项目资料

- [最终报告](docs/RAG_FINAL_UPGRADE_REPORT.md) · [安全报告](docs/final_security_test_report.md)
- [权限架构](docs/final_auth_architecture.md) · [学习与面试总结](docs/RAG_FINAL_LEARNING_SUMMARY.md)
- [原通用检索记录](docs/general_retrieval_upgrade_20261022.md) · [原答案校验](docs/answer_verification.md) · [历史变更](docs/change_history.md)

密码实现参考 [argon2-cffi 官方文档](https://argon2-cffi.readthedocs.io/en/stable/api.html)。
