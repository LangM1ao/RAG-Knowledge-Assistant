# 最终认证与权限架构

Authentication 回答“你是谁”：密码通过Argon2id验证，后端签发短期JWT。每次检查签名、HS256白名单、exp、issuer、audience，再读取SQLite会话和账号状态，不相信客户端角色。

Authorization 回答“你能做什么”：RBAC使用admin/user分配管理能力，Document Ownership记录上传者，private/shared控制普通用户读取范围。共享不授予修改权。

Retrieval Access Control 落实到检索前：SQLite生成authorized_ids，selected_ids必须全部合法；最终交集传入Chroma where与BM25 collection.get(where)。BM25仅在授权语料上计算词频/IDF。RRF融合两条已过滤分支，别名和相邻Chunk继承同一范围，不重写原算法。

None是可信内部调用的未指定范围；API始终传明确列表；空列表直接返回空。无归属的孤立向量不会被API授权。所有文档入口，包括aliases和rebuild-all，都有后端检查。

受保护同步路由拿ACCESS_LOCK后重新查用户和会话，退出、禁用、重置、降权、共享更新使用同一锁，排队请求不能沿用旧身份。仅支持单进程单worker。索引切换保留原INDEX_LOCK/journal；回滚排除owner_id和visibility，不恢复旧权限。

Streamlit只在自己的Session State存Token，每次刷新调用/auth/me，401清空全部状态。退出先后端撤销，再清除身份、答案和控件。授权集合变化清除旧答案；没有共享Token缓存。

历史保存user_id和当次可能使用的文档范围，只允许本人且仍全部可访问时读取。无法证明生成范围的旧记录保留但隐藏。这可能保守隐藏未实际引用撤权文档的记录。

上传在接收正文前鉴权，累计限制实际字节（含流式请求），文件上限20MiB，整个multipart请求21MiB。文件落盘使用UUID与扩展名，错误不回传解析异常正文。开发端口localhost；公网HTTPS/连接超时由部署层补充。

迁移先备份，再事务加列；首位管理员命令分配历史归属。保留Chroma document_id与已有向量，不重新Embedding。回滚需要停止服务并恢复同一备份时点的代码和完整数据。
