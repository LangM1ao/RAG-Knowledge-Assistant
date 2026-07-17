# Week12 最终验收记录

验收日期：2026-07-17

## 自动化测试

- 环境变量新增测试：2 passed。
- 原项目回归测试：32 passed，2 warnings。
- warning 为 Starlette/httpx 弃用提示与受限账户 pytest cache 写入提示，不影响测试结论。

## Docker 实测

- Docker Desktop：4.82.0。
- Docker Engine：29.6.1，linux/amd64。
- Docker Compose：v5.3.0。
- backend 镜像：273MB。
- frontend 镜像：273MB。
- backend：healthy，`GET /health` 返回 `status=ok`。
- frontend：healthy，`GET /_stcore/health` 返回 200 / ok。
- 前端容器访问 `http://backend:8000/health` 成功。
- 后端重启前后命名卷名称、挂载点和创建时间完全一致。
- 浏览器实际渲染成功，页面显示“后端连接正常”。

原始日志位于工作区 `docker-validation/docker-validation.log`；项目截图为 `docs/screenshots/week12-docker-home.png`。

## 尚未宣称完成

- 尚未创建远程 GitHub 仓库或推送代码。
- 尚未部署到公网云平台。
- 未实现认证、多租户、异步队列、正式 BM25/hybrid/rerank。

