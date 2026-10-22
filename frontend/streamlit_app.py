import time

import streamlit as st

from frontend.api_client import ApiClient, ApiClientError


st.set_page_config(
    page_title="企业知识库 RAG 智能问答系统",
    page_icon="📚",
    layout="wide",
)

client = ApiClient()

st.title("企业知识库 RAG 智能问答系统")
st.caption("基于 FastAPI、ChromaDB、SQLite 与 Streamlit 的轻量级 RAG 产品演示")

st.subheader("后端连接状态")
health = client.check_health()
if health.connected:
    st.success(f"{health.message}｜服务：{health.service}")
else:
    st.error(health.message)

st.divider()
st.subheader("文档上传")
uploaded_file = st.file_uploader(
    "选择知识库文档",
    type=["txt", "pdf"],
    help="支持 TXT 和 PDF。上传后由 FastAPI 完成解析、切分、向量化和入库。",
)

if st.button("上传并入库", type="primary", disabled=uploaded_file is None):
    try:
        with st.spinner("正在上传、解析并写入向量库……"):
            result = client.upload_document(
                filename=uploaded_file.name,
                content=uploaded_file.getvalue(),
                content_type=uploaded_file.type or "application/octet-stream",
            )
        st.success(
            f"上传完成｜document_id：{result['document_id']}｜状态：{result['status']}"
        )
    except ApiClientError as exc:
        st.error(str(exc))

st.divider()
st.subheader("文档列表")
st.caption("修改实体标准名称后请重建文档，更新各片段的检索身份提示。")

if st.button("刷新文档列表"):
    st.rerun()

try:
    documents = client.list_documents()
except ApiClientError as exc:
    documents = []
    st.error(str(exc))

if not documents:
    st.info("知识库中还没有可展示的文档。")
else:
    for document in documents:
        document_id = document["document_id"]
        with st.container(border=True):
            st.markdown(f"**{document['filename']}**")
            st.write(
                {
                    "document_id": document_id,
                    "upload_time": document.get("upload_time"),
                    "status": document.get("status"),
                    "chunk_count": document.get("chunk_count"),
                    "vector_status": document.get("vector_status"),
                }
            )
            rebuild_column, delete_column = st.columns(2)
            with rebuild_column:
                if st.button("重建文档", key=f"rebuild-{document_id}"):
                    try:
                        result = client.rebuild_document(document_id)
                        st.success(
                            f"重建完成｜chunk_count：{result.get('chunk_count', 0)}"
                        )
                        st.rerun()
                    except ApiClientError as exc:
                        st.error(str(exc))
            with delete_column:
                if st.button("删除文档", key=f"delete-{document_id}"):
                    try:
                        client.delete_document(document_id)
                        st.success("文档已删除。")
                        st.rerun()
                    except ApiClientError as exc:
                        st.error(str(exc))

            with st.expander("文档别名设置"):
                st.caption("将中文名、英文名或简称对应到本文档的实体；别名只用于身份对应，不证明成绩等事实。")
                alias_state_key = f"aliases-{document_id}"
                if st.button("加载别名配置", key=f"load-aliases-{document_id}"):
                    try:
                        st.session_state[alias_state_key] = client.get_document_aliases(document_id)
                        st.session_state[f"entity-name-{document_id}"] = st.session_state[alias_state_key].get("entity_name") or ""
                        st.session_state[f"alias-values-{document_id}"] = "\n".join(st.session_state[alias_state_key].get("aliases") or [])
                    except ApiClientError as exc:
                        st.error(str(exc))
                if alias_state_key in st.session_state:
                    entity_name = st.text_input("实体名称", key=f"entity-name-{document_id}")
                    alias_text = st.text_area("别名（每行一个）", key=f"alias-values-{document_id}")
                    if st.button("保存别名", key=f"save-aliases-{document_id}"):
                        try:
                            st.session_state[alias_state_key] = client.update_document_aliases(
                                document_id, entity_name.strip(),
                                [line.strip() for line in alias_text.splitlines() if line.strip()],
                            )
                            st.success("别名配置已保存。")
                        except ApiClientError as exc:
                            st.error(str(exc))

st.divider()
st.subheader("RAG 问答")
question = st.text_area(
    "请输入问题",
    placeholder="例如：这份知识库说明了哪些退款规则？",
)
show_chunks = st.toggle("显示检索片段", value=True)

document_options = {
    f"{document.get('filename', 'unknown')}｜{document.get('document_id', '')}": document.get("document_id")
    for document in documents
    if document.get("document_id")
}
with st.expander("检索设置（高级）"):
    retrieval_mode_label = st.radio(
        "检索模式", options=["Vector", "BM25", "Hybrid"], horizontal=True,
        help="Vector 适合语义改写，BM25 适合精确名称和配置名，Hybrid 融合两路排名。",
    )
    retrieval_mode = retrieval_mode_label.casefold()
    top_k = st.slider("Top-K 检索数量", min_value=1, max_value=10, value=3)
    selected_document_labels = st.multiselect(
        "限定文档范围",
        options=list(document_options),
        help="不选择时默认检索整个知识库。",
    )
    use_threshold = st.toggle("启用相似度阈值", value=False)
    similarity_threshold = st.number_input(
        "Cosine distance 最大值",
        min_value=0.0,
        max_value=2.0,
        value=0.60,
        step=0.05,
        disabled=not use_threshold,
        help="当前使用 cosine distance，数值越小通常越相似。",
    )
    request_debug = st.toggle(
        "请求检索诊断", value=False,
        help="包含检索问题和原文，仅供排查；必须同时由服务端开启。折叠面板本身不限制数据访问。",
    )

selected_document_ids = [
    document_options[label] for label in selected_document_labels
]

if st.button("提交问题", type="primary"):
    if not question.strip():
        st.warning("问题不能为空，请先输入问题。")
    else:
        started_at = time.perf_counter()
        try:
            with st.spinner("正在检索知识库并生成回答……"):
                debug_options = {"debug": True} if request_debug else {}
                result = client.query(
                    question.strip(),
                    top_k=top_k,
                    retrieval_mode=retrieval_mode,
                    similarity_threshold=(similarity_threshold if use_threshold else None),
                    document_ids=(selected_document_ids or None),
                    **debug_options,
                )
            result["elapsed_seconds"] = time.perf_counter() - started_at
            st.session_state["last_answer"] = result
        except ApiClientError as exc:
            st.error(str(exc))

result = st.session_state.get("last_answer")
if result:
    st.markdown("### 回答")
    st.write(result.get("answer", ""))
    st.caption(f"检索模式：{result.get('retrieval_mode', retrieval_mode)}")
    st.caption(f"响应时间：{result.get('elapsed_seconds', 0):.2f} 秒")

    verification_status = (result.get("verification") or {}).get("status")
    verification_labels = {
        "PASS": "通过",
        "FAIL": "未通过，已拒答",
        "ERROR": "校验服务暂时不可用",
        "SKIPPED": "模型已拒答，跳过校验",
        "DISABLED": "已关闭",
    }
    if verification_status in verification_labels:
        st.caption(f"答案依据校验：{verification_labels[verification_status]}")

    sources = result.get("sources") or []
    st.markdown("### 引用来源")
    if not sources:
        if verification_status == "ERROR":
            st.warning("校验服务暂时不可用，未展示未经校验的答案。")
        elif result.get("citation_status") == "missing":
            st.info("本次回答未提供可定位引用，未将检索结果自动列为来源。")
        else:
            st.warning("知识库中未找到可靠依据。")
    else:
        for index, source in enumerate(sources, start=1):
            citation_index = source.get("citation_index", index)
            distance = source.get("distance")
            distance_text = f"{distance:.4f}" if isinstance(distance, (int, float)) else "未知"
            with st.expander(
                f"引用 [{citation_index}]｜{source.get('source_file', 'unknown')}"
            ):
                st.caption(f"片段：{source.get('chunk_id', 'unknown')}")
                if isinstance(distance, (int, float)):
                    st.caption(f"向量距离：{distance_text}（越小越相似）")
                if show_chunks:
                    st.write(source.get("chunk_preview") or "没有可显示的片段预览。")

    if result.get("debug_enabled"):
        with st.expander("检索诊断", expanded=False):
            st.caption("vector_score 是兼容旧接口的向量距离字段，数值越小越相似；BM25 和 RRF 分数越大排名越靠前。")
            st.json(result.get("retrieval_trace") or {})
            st.json(result.get("retrieval_debug") or [])
    elif request_debug:
        st.caption("本次未返回检索诊断；服务端需开启诊断权限。")

st.divider()
st.subheader("问答历史")
try:
    history = client.get_chat_history(limit=10)
except ApiClientError as exc:
    history = []
    st.error(str(exc))

if not history:
    st.info("还没有问答历史。成功提交问题后，记录会保存在 SQLite。")
else:
    for record in history:
        with st.expander(
            f"{record.get('created_at', '')}｜{record.get('question', '')}"
        ):
            st.markdown("**回答**")
            st.write(record.get("answer", ""))
            st.caption(f"引用数量：{len(record.get('sources') or [])}")
