import requests

from frontend.api_client import ApiClient, ApiClientError


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


def test_check_health_returns_connected_result():
    def fake_get(url: str, timeout: float):
        assert url == "http://127.0.0.1:8000/health"
        assert timeout == 3.0
        return FakeResponse(200, {"status": "ok", "service": "RAG Knowledge Base Assistant"})

    result = ApiClient(get=fake_get).check_health()

    assert result.connected is True
    assert result.status == "ok"
    assert result.service == "RAG Knowledge Base Assistant"
    assert result.message == "后端连接正常"


def test_check_health_handles_timeout():
    def fake_get(url: str, timeout: float):
        raise requests.Timeout("request timed out")

    result = ApiClient(get=fake_get).check_health()

    assert result.connected is False
    assert result.status == "timeout"
    assert "超时" in result.message


def test_check_health_handles_connection_failure():
    def fake_get(url: str, timeout: float):
        raise requests.ConnectionError("connection refused")

    result = ApiClient(get=fake_get).check_health()

    assert result.connected is False
    assert result.status == "connection_error"
    assert "无法连接" in result.message


def test_check_health_handles_abnormal_response():
    def fake_get(url: str, timeout: float):
        return FakeResponse(503, {"detail": "Service unavailable"})

    result = ApiClient(get=fake_get).check_health()

    assert result.connected is False
    assert result.status == "http_error"
    assert "503" in result.message


def test_upload_document_sends_multipart_file():
    def fake_post(url: str, files: dict, timeout: float):
        assert url == "http://127.0.0.1:8000/documents/upload"
        assert files["file"] == ("guide.txt", b"hello", "text/plain")
        assert timeout == 30.0
        return FakeResponse(200, {"document_id": "doc-1", "status": "indexed"})

    result = ApiClient(post=fake_post).upload_document(
        filename="guide.txt",
        content=b"hello",
        content_type="text/plain",
    )

    assert result["document_id"] == "doc-1"


def test_list_documents_returns_document_rows():
    def fake_get(url: str, timeout: float):
        assert url.endswith("/documents/list")
        return FakeResponse(200, {"documents": [{"document_id": "doc-1"}]})

    assert ApiClient(get=fake_get).list_documents() == [{"document_id": "doc-1"}]


def test_delete_and_rebuild_document_use_existing_endpoints():
    calls = []

    def fake_delete(url: str, timeout: float):
        calls.append(("delete", url))
        return FakeResponse(200, {"success": True})

    def fake_post(url: str, timeout: float):
        calls.append(("post", url))
        return FakeResponse(200, {"success": True, "chunk_count": 2})

    client = ApiClient(post=fake_post, delete=fake_delete)
    client.delete_document("doc-1")
    client.rebuild_document("doc-1")

    assert calls == [
        ("delete", "http://127.0.0.1:8000/documents/doc-1"),
        ("post", "http://127.0.0.1:8000/documents/doc-1/rebuild"),
    ]


def test_query_and_history_use_chat_endpoints():
    def fake_post(url: str, json: dict, timeout: float):
        assert url.endswith("/chat/query")
        assert json == {"question": "What is RAG?", "top_k": 3}
        return FakeResponse(200, {"answer": "Answer", "sources": []})

    def fake_get(url: str, params: dict, timeout: float):
        assert url.endswith("/chat/history")
        assert params == {"limit": 5}
        return FakeResponse(200, {"history": [{"question": "What is RAG?"}]})

    client = ApiClient(get=fake_get, post=fake_post)

    assert client.query("What is RAG?", top_k=3)["answer"] == "Answer"
    assert client.get_chat_history(limit=5)[0]["question"] == "What is RAG?"


def test_query_adds_only_selected_week11_controls():
    captured = {}

    def fake_post(url: str, json: dict, timeout: float):
        captured.update(json)
        return FakeResponse(200, {"answer": "Answer", "sources": []})

    ApiClient(post=fake_post).query(
        "policy",
        top_k=5,
        similarity_threshold=0.35,
        document_ids=["doc-1"],
        source_files=None,
    )

    assert captured == {
        "question": "policy",
        "top_k": 5,
        "similarity_threshold": 0.35,
        "document_ids": ["doc-1"],
    }


def test_api_error_uses_backend_detail():
    def fake_get(url: str, timeout: float):
        return FakeResponse(400, {"detail": "Bad request"})

    try:
        ApiClient(get=fake_get).list_documents()
    except ApiClientError as exc:
        assert str(exc) == "Bad request"
    else:
        raise AssertionError("ApiClientError was not raised")
