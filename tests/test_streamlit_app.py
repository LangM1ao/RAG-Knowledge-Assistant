from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_streamlit_page_contains_week10_product_sections(monkeypatch):
    from frontend.api_client import ApiClient, HealthCheckResult
    monkeypatch.setattr(ApiClient, 'me', lambda self: {'id':1,'username':'fixture','role':'user'})
    monkeypatch.setattr(ApiClient, 'check_health', lambda self: HealthCheckResult(True,'ok','OK','test'))
    monkeypatch.setattr(ApiClient, 'list_documents', lambda self: [])
    monkeypatch.setattr(ApiClient, 'get_chat_history', lambda self, limit: [])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "frontend/streamlit_app.py"))
    app.session_state["access_token"] = "test-token"
    app.run(timeout=10)

    assert app.title[0].value == "企业知识库 RAG 智能问答系统"
    assert "文档上传" in [item.value for item in app.subheader]
    assert "文档列表" in [item.value for item in app.subheader]
    assert "RAG 问答" in [item.value for item in app.subheader]
    assert "问答历史" in [item.value for item in app.subheader]
    assert "请输入问题" in [item.label for item in app.text_area]
    assert "Top-K 检索数量" in [item.label for item in app.slider]
    assert "显示检索片段" in [item.label for item in app.toggle]
    assert "启用相似度阈值" in [item.label for item in app.toggle]
    assert "限定文档范围" in [item.label for item in app.multiselect]
    assert "提交问题" in [item.label for item in app.button]
