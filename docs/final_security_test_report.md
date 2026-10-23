# RAG FINAL 安全与回归验收

最终收尾复验：本地176项、Docker176项通过，真实模型22/22；新增原文件路径不可访问检查。详见[最终交付验收](FINAL_DELIVERY.md)。以下保留前次升级记录。

日期：2026-10-23。结果来源为本次实际执行，不沿用历史通过记录。

## 结果

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 升级前原有基线 | 151 passed | backups/final_baseline_tests.log |
| Windows完整测试 | 175 passed，1条既有Starlette/httpx弃用警告 | backups/final_local_verified.log |
| Linux Docker完整测试 | 175 passed | backups/final_container_verified.log |
| 真实OpenAI、HTTP、临时容器演示 | 22/22 | final_live_smoke.json |
| 首轮真实模型演示 | 20/22，已保留失败记录 | final_live_smoke_initial.json |
| Docker build/up | 两服务healthy | backups/final_docker_build_latest.log、final_docker_up.log |
| 真实数据迁移 | 本地3份、Docker1份ID保留 | backups/final_migration_check.json |
| Docker重启持久化 | 登录、文档、owner、private正常 | backups/final_persistence_check.json |
| 向量保留 | Docker24个Embedding ID与二进制索引哈希未变 | 同上 |

## 实际覆盖

- 正确/错误/不存在账号、重复用户名、Argon2id哈希、无效/过期/伪造JWT、无Token、注销后重放。
- 普通用户不能管理用户；管理员禁用、重置密码使旧会话失效；最后有效管理员不能被禁用。
- 登录失败SQLite限速；排队请求在退出后重新鉴权，不能使用陈旧身份。
- 上传自动绑定身份，伪造owner被忽略；路径规范化、大小/类型限制；未认证上传不消费请求体，流式请求超限413。
- 私人文档列表/详情/删除/重建/别名隔离；rebuild-all仅管理员；共享可读不可改；普通用户不能设置共享。
- Vector/BM25/Hybrid：显式空授权不查询存储；真实临时Chroma隔离私人内容、文件名、孤立片段、引用和发送给LLM的上下文。
- 授权交集、非法document_id拒绝、共享前后切换、按用户历史、撤共享后历史隐藏。
- 原Chunk、查询规范化、中英文实体别名、Hybrid/RRF、相邻结构、答案依据校验、引用/拒答、安全重建测试全部保留。
- Streamlit登录页无私人控制项，Token附带Authorization，401清理回调；原已登录页面功能回归保留。
- 真实外部服务22项含上传入库、三个模式私人不泄露/共享回答引用、中文问英文文档、拒答、重建、删除、退出和容器重启。

## 发现与修复

1. 初始新增权限测试10项全部失败：没有所有权检查、空列表会放宽范围、BM25全库读取。接入统一授权和预过滤后通过。
2. 旧回归测试未提供身份、新字段或where参数；保留原行为断言，显式补登录夹具和元数据，没有删除失败用例。安全测试使用真实JWT，不使用这些单元测试身份替身。
3. 新旧Streamlit AppTest相对路径解析不同，改绝对路径；模拟文档补owner，使按钮在正确身份下可编辑。
4. 重建回滚恢复旧visibility：新增测试复现失败，排除权限字段后通过。
5. 独立审查发现排队身份过期：新增测试复现，锁内重新查询会话修复；所有受保护路由与撤权同锁。
6. 独立审查发现ApiClient丢弃显式空列表：改is not None，避免客户端自行扩大范围。
7. 独立审查实测multipart默认接收22,020,096字节后才检查大小。增加ASGI字节限制和正文前鉴权，新增测试通过。
8. 首轮合成资料称内容为禁止分享的机密授权码，模型在Vector/BM25已正确检索后拒绝披露，故20/22。保留原报告，改为无凭据含义的虚构项目代号，重跑同22项为22/22；未修改检索/生成算法迎合材料。

## 范围与限制

本次真实演示使用合成数据调用OpenAI；自动化隔离测试不使用真实业务资料。未对真实私人文档批量重新Embedding。当前真实Docker库1份原文正常、24块完整。本地旧库3份文档原文件在升级前已缺失，在项目备份中也未找到同名文件，因此不能宣称这3份原文件的重建/上传回归已经完成；保留其元数据与既有向量。

模型回答具有随机性，测试通过不是永不泄漏/永不幻觉的数学证明。单worker锁限制并发；公网HTTPS、反向代理连接超时、多租户、完整审计平台不在范围。诊断须服务端和请求双开启；已显示或复制的内容不能事后收回。

备份、原始测试日志、初始化密码都在Git忽略目录；公开报告不包含真实密码、JWT、私人文件正文或API Key。

最终敏感信息检查：159个候选文件，无实际API Key/JWT Secret/管理员密码匹配；没有业务SQLite/Chroma/上传或备份文件待提交。git diff --check通过。
