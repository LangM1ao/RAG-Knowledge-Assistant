from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.api import chat
from app.main import app
from app.schemas.chat import ChatQueryRequest
from app.services import rag_pipeline


def test_chat_query_request_keeps_old_payload_compatible():
    request = ChatQueryRequest(question="What is RAG?", top_k=3)

    assert request.similarity_threshold is None
    assert request.document_ids is None
    assert request.source_files is None


def test_chat_query_request_accepts_filters_and_validates_bounds():
    request = ChatQueryRequest(
        question="policy",
        top_k=5,
        similarity_threshold=0.35,
        document_ids=["doc-1"],
        source_files=["policy.txt"],
    )

    assert request.source_files == ["policy.txt"]
    with pytest.raises(ValidationError):
        ChatQueryRequest(question="bad", top_k=0)
    with pytest.raises(ValidationError):
        ChatQueryRequest(question="bad", similarity_threshold=-0.1)


def test_chat_route_forwards_retrieval_controls(monkeypatch):
    captured = {}

    def fake_answer_question(**kwargs):
        captured.update(kwargs)
        return {"answer": "ok", "sources": []}

    monkeypatch.setattr(chat, "answer_question", fake_answer_question)
    monkeypatch.setattr(chat, "create_chat_record", lambda **kwargs: None)

    response = TestClient(app).post(
        "/chat/query",
        json={
            "question": "policy",
            "top_k": 5,
            "similarity_threshold": 0.35,
            "document_ids": ["doc-1"],
            "source_files": ["policy.txt"],
        },
    )

    assert response.status_code == 200
    assert captured == {
        "question": "policy",
        "top_k": 5,
        "similarity_threshold": 0.35,
        "document_ids": ["doc-1"],
        "source_files": ["policy.txt"],
    }


def test_threshold_empty_result_refuses_without_calling_llm(monkeypatch):
    class FakeStore:
        def query(self, **kwargs):
            assert kwargs["similarity_threshold"] == 0.2
            return []

    monkeypatch.setattr(rag_pipeline, "VectorStore", FakeStore)
    monkeypatch.setattr(
        rag_pipeline,
        "generate_answer",
        lambda messages: pytest.fail("LLM should not be called"),
    )

    result = rag_pipeline.answer_question(
        "unknown",
        similarity_threshold=0.2,
        source_files=["policy.txt"],
    )

    assert result["sources"] == []
    assert "没有找到相关依据" in result["answer"]
