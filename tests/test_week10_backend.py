from fastapi.testclient import TestClient

from app.main import app
from app.services import rag_pipeline


def test_upload_indexes_document_before_returning(monkeypatch, tmp_path):
    from app.api import documents

    captured = {}

    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(documents, "parse_document", lambda path: "hello world")
    monkeypatch.setattr(documents, "create_document", lambda info: captured.update(info))
    monkeypatch.setattr(
        documents,
        "rebuild_document_by_id",
        lambda document_id: {"success": True, "chunk_count": 2},
    )

    response = TestClient(app).post(
        "/documents/upload",
        files={"file": ("guide.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "indexed"
    assert "indexed" in response.json()["message"].lower()
    assert captured["status"] == "parsed"


def test_answer_question_sources_include_chunk_preview(monkeypatch):
    class FakeStore:
        def query(self, question: str, top_k: int):
            return [
                {
                    "chunk_id": "chunk-1",
                    "text": "A useful passage about the company policy.",
                    "metadata": {"source_file": "policy.txt"},
                    "distance": 0.12,
                }
            ]

    monkeypatch.setattr(rag_pipeline, "VectorStore", FakeStore)
    monkeypatch.setattr(rag_pipeline, "generate_answer", lambda messages: "Answer")

    result = rag_pipeline.answer_question("What is the policy?", top_k=1)

    assert result["sources"][0]["chunk_preview"] == "A useful passage about the company policy."
