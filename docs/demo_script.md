# 两分钟演示脚本

1. 执行 `docker compose up -d --build`，展示两个服务都是 healthy。
2. 打开 `http://127.0.0.1:8501`，指出 Streamlit 只负责交互，业务逻辑在 FastAPI。
3. 上传 demo TXT，说明保存、解析、chunk、embedding、ChromaDB、SQLite 的完整链路。
4. 提问文档内问题，展示 answer、source_file 和检索片段。
5. 提问文档外问题，展示相似度阈值和拒答边界。
6. 刷新页面，展示 SQLite 中仍保留问答历史。
7. 结束时展示 `evals/experiment_summary.csv`：解释 Week11 固定评估集和参数选择证据。

演示前检查：

```powershell
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
```

