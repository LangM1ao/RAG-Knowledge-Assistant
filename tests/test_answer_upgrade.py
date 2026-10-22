"""Behavioral checks for partial answers, actual citations, and opt-in diagnostics."""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import chat
from app.main import app
from app.services import answer_verifier, rag_pipeline
from app.services.answer_verifier import VerificationResult, VERIFICATION_REFUSAL
from frontend.api_client import ApiClient


def chunk(chunk_id, text, document_id="doc-a", **kwargs):
    return {"chunk_id": chunk_id, "text": text,
            "metadata": {"document_id": document_id, "source_file": "transcript.txt", "section": "Results"},
            "distance": 0.14, **kwargs}


@pytest.fixture
def flow(monkeypatch):
    state = {
        "chunks": [chunk("real-10", "Alice Example\nSensors | mark 76"),
                   chunk("real-11", "Other notes without credit information")],
        "answer": "Sensors 成绩为 76。[1] 学分：当前资料没有提供，无法确定。",
        "verdict": "PASS", "generation": [], "verification": [],
        "trace": {"normalized_query": "PRIVATE_QUERY", "vector_candidate_count": 4,
                  "bm25_candidate_count": 3, "fused_count": 5, "threshold_filtered_count": 1,
                  "context_expansion": {"added": ["real-11"]}},
    }

    class FakeRetriever:
        def __init__(self, **kwargs):
            self.last_debug = state["trace"]

        def query(self, **kwargs):
            return state["chunks"][:1]

        def expand_context(self, question, chunks, **kwargs):
            state["expansion_filters"] = kwargs
            return state["chunks"]

    def generate(messages):
        state["generation"].append(messages)
        return state["answer"]

    def verify(question, context, answer):
        state["verification"].append((question, context, answer))
        return VerificationResult(verdict=state["verdict"], reason="mock verdict")

    monkeypatch.setattr(rag_pipeline, "Retriever", FakeRetriever)
    monkeypatch.setattr(rag_pipeline, "VectorStore", lambda: object())
    monkeypatch.setattr(rag_pipeline, "generate_answer", generate)
    monkeypatch.setattr(rag_pipeline, "verify_answer", verify)
    monkeypatch.setattr(rag_pipeline, "ANSWER_VERIFICATION_ENABLED", True)
    monkeypatch.setattr(rag_pipeline, "RETRIEVAL_DEBUG_ENABLED", False)
    return state


def test_partial_answer_keeps_supported_facts_and_missing_credit(flow):
    result = rag_pipeline.answer_question("Sensors 的成绩和学分分别是多少？", document_ids=["doc-a"])
    assert result["answer"] == flow["answer"]
    assert result["verification"]["status"] == "PASS"
    assert [source["chunk_id"] for source in result["sources"]] == ["real-10"]
    assert flow["verification"][0][1] in flow["generation"][0][1]["content"]
    assert "部分信息缺失不应导致整题拒答" in flow["generation"][0][0]["content"]
    assert "不应仅因未答全而 FAIL" in answer_verifier.VERIFICATION_SYSTEM_PROMPT
    assert flow["expansion_filters"]["document_ids"] == ["doc-a"]


@pytest.mark.parametrize("draft", [
    "Alice Example 的 Sensors 成绩为 97。[1]",
    "另一位同学的 Sensors 成绩为 76。[1]",
    "Sensors 成绩为 76，学分为 20。[1]",
])
def test_unsupported_number_person_or_credit_fail_closed(flow, draft):
    flow["answer"] = draft
    flow["verdict"] = "FAIL"
    result = rag_pipeline.answer_question("成绩和学分？")
    assert result["answer"] == VERIFICATION_REFUSAL
    assert result["sources"] == []
    assert result["verification"]["status"] == "FAIL"
    assert draft not in json.dumps(result, ensure_ascii=False)


def test_citations_preserve_real_neighbor_id_and_original_number(flow):
    flow["answer"] = "补充信息来自第二个片段。[2] 再次引用同一片段。[2]"
    result = rag_pipeline.answer_question("课程和其他信息？")
    assert [source["chunk_id"] for source in result["sources"]] == ["real-11"]
    assert result["sources"][0]["citation_index"] == 2
    assert result["sources"][0]["document_id"] == "doc-a"


@pytest.mark.parametrize("citation", ["[0]", "[3]", "[1][99]"])
def test_invalid_citations_cannot_become_trusted_sources(flow, citation):
    flow["answer"] = f"成绩为 76。{citation}"
    result = rag_pipeline.answer_question("成绩？")
    assert result["sources"] == []
    assert result["answer"] == VERIFICATION_REFUSAL
    assert result["citation_status"] == "invalid"


@pytest.mark.parametrize("enabled", [False, True])
def test_missing_citations_do_not_attach_all_retrieved_sources(flow, monkeypatch, enabled):
    monkeypatch.setattr(rag_pipeline, "ANSWER_VERIFICATION_ENABLED", enabled)
    flow["answer"] = "Sensors 成绩为 76。"
    result = rag_pipeline.answer_question("成绩？")
    assert result["answer"] == flow["answer"]
    assert result["sources"] == []
    assert result["citation_status"] == "missing"


@pytest.mark.parametrize("enabled", [False, True])
def test_pure_refusal_always_clears_sources(flow, monkeypatch, enabled):
    monkeypatch.setattr(rag_pipeline, "ANSWER_VERIFICATION_ENABLED", enabled)
    flow["answer"] = VERIFICATION_REFUSAL + "[1]"
    result = rag_pipeline.answer_question("其他问题？")
    assert result["sources"] == []
    assert not flow["verification"]
    assert "[1]" not in result["answer"]


@pytest.mark.parametrize("server, debug_requested", [(False, False), (False, True), (True, False), (True, True)])
def test_diagnostics_require_both_switches(flow, monkeypatch, server, debug_requested):
    monkeypatch.setattr(rag_pipeline, "RETRIEVAL_DEBUG_ENABLED", server)
    result = rag_pipeline.answer_question("question", debug=debug_requested)
    assert result["debug_enabled"] is (server and debug_requested)
    if server and debug_requested:
        trace = result["retrieval_trace"]
        assert trace["vector_candidate_count"] == 4
        assert [entry["chunk_id"] for entry in trace["generation_context_chunks"]] == ["real-10", "real-11"]
        assert trace["generation_context_chunks"][1]["text"] == flow["chunks"][1]["text"]
        assert len(result["retrieval_debug"]) == 2
        assert len(result["sources"]) == 1
    else:
        assert "retrieval_debug" not in result
        assert "retrieval_trace" not in result
        assert "PRIVATE_QUERY" not in json.dumps(result)
        assert flow["chunks"][1]["text"] not in json.dumps(result)


def test_context_budget_counts_headers_and_never_exposes_omitted_sources(flow, monkeypatch):
    monkeypatch.setattr(rag_pipeline, "RETRIEVAL_DEBUG_ENABLED", True)
    first = rag_pipeline.build_context(flow["chunks"][:1])
    monkeypatch.setattr(rag_pipeline, "CONTEXT_MAX_CHARS", len(first))
    result = rag_pipeline.answer_question("question", debug=True)
    assert flow["verification"][0][1] == first
    assert result["retrieval_trace"]["generation_context_chars"] == len(first)
    assert result["retrieval_trace"]["context_filtering"] == [{"chunk_id": "real-11", "reason": "context_character_limit"}]
    assert len(result["retrieval_debug"]) == 1
    assert result["sources"][0]["chunk_id"] == "real-10"


def test_alias_mapping_scoped_to_documents_and_same_verifier_context(flow):
    flow["trace"]["alias_matches"] = [
        {"document_id": "doc-a", "entity_name": "Alice Example", "matched_alias": "爱丽丝"},
        {"document_id": "doc-b", "entity_name": "Unrelated Identity", "matched_alias": "其他人"},
    ]
    rag_pipeline.answer_question("爱丽丝的成绩和学分？")
    context = flow["verification"][0][1]
    assert "爱丽丝" in context and "Alice Example" in context
    assert "不证明成绩" in context
    assert "Unrelated Identity" not in context
    assert context in flow["generation"][0][1]["content"]


def test_ordinary_logs_exclude_question_context_answer_and_verifier_reason(flow, monkeypatch, caplog):
    monkeypatch.setattr(rag_pipeline, "verify_answer", answer_verifier.verify_answer)
    monkeypatch.setattr(answer_verifier, "generate_structured_answer", lambda *args: {
        "verdict": "PASS", "reason": "SECRET_REASON_WITH_SOURCE_TEXT",
    })
    with caplog.at_level("INFO"):
        rag_pipeline.answer_question("SECRET_ORIGINAL_QUESTION")
    for sensitive in ["SECRET_ORIGINAL_QUESTION", "SECRET_REASON_WITH_SOURCE_TEXT", flow["chunks"][0]["text"], flow["answer"]]:
        assert sensitive not in caplog.text
    assert "verdict=PASS" in caplog.text


@pytest.mark.parametrize("server, debug_requested", [(False, True), (True, False)])
def test_api_does_not_leak_debug_even_if_service_returns_it(monkeypatch, server, debug_requested):
    monkeypatch.setattr(chat.config, "RETRIEVAL_DEBUG_ENABLED", server, raising=False)
    monkeypatch.setattr(chat, "answer_question", lambda **kwargs: {
        "answer": "safe", "sources": [], "debug_enabled": True,
        "retrieval_debug": [{"text": "RAW_CONTEXT"}], "retrieval_trace": {"normalized_query": "RAW_QUERY"},
    })
    monkeypatch.setattr(chat, "create_chat_record", lambda **kwargs: None)
    result = TestClient(app).post("/chat/query", json={"question": "test", "debug": debug_requested})
    assert result.status_code == 200
    assert result.json()["debug_enabled"] is False
    assert "RAW_CONTEXT" not in result.text and "RAW_QUERY" not in result.text


def test_api_exception_does_not_echo_sensitive_provider_message(monkeypatch, caplog):
    def fail(**kwargs):
        raise RuntimeError("SECRET_PROMPT_OR_KEY")
    monkeypatch.setattr(chat, "answer_question", fail)
    result = TestClient(app).post("/chat/query", json={"question": "test"})
    assert result.status_code == 500
    assert "SECRET_PROMPT_OR_KEY" not in result.text + caplog.text


def test_api_client_alias_methods_and_explicit_debug_payload():
    calls = []
    def record(method):
        def request(url, **kwargs):
            calls.append((method, url, kwargs))
            return SimpleNamespace(status_code=200, json=lambda: {"document_id": "doc-a", "aliases": ["Alias"]})
        return request
    client = ApiClient(get=record("get"), put=record("put"), post=record("post"))
    client.get_document_aliases("doc-a")
    client.update_document_aliases("doc-a", "Example", ["Alias"])
    client.query("question", debug=True)
    assert calls[0][1].endswith("/documents/doc-a/aliases")
    assert calls[1][2]["json"] == {"entity_name": "Example", "aliases": ["Alias"]}
    assert calls[2][2]["json"]["debug"] is True


def test_ui_diagnostics_default_off_and_aliases_load_only_when_requested(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from frontend import api_client
    calls = []
    class FakeClient:
        def check_health(self):
            return SimpleNamespace(connected=True, message="OK", service="test")
        def list_documents(self):
            return [{"document_id": "doc-a", "filename": "transcript.txt"}]
        def get_chat_history(self, limit):
            return []
        def get_document_aliases(self, document_id):
            calls.append(("get_aliases", document_id))
            return {"entity_name": "Example", "aliases": ["Alias"]}
        def update_document_aliases(self, document_id, entity_name, aliases):
            calls.append(("put_aliases", document_id, entity_name, aliases))
            return {"entity_name": entity_name, "aliases": aliases}
        def query(self, question, **kwargs):
            calls.append(("query", kwargs))
            return {"answer": "76 [2]", "sources": [{"citation_index": 2, "source_file": "transcript.txt", "chunk_id": "real-11", "vector_rank": 2}], "debug_enabled": False}
    monkeypatch.setattr(api_client, "ApiClient", FakeClient)
    page = AppTest.from_file("frontend/streamlit_app.py").run(timeout=10)
    assert not page.exception and not calls
    assert "检索设置（高级）" in [entry.label for entry in page.expander]
    assert not next(entry for entry in page.toggle if entry.label == "请求检索诊断").value
    next(entry for entry in page.text_area if entry.label == "请输入问题").set_value("成绩？")
    next(entry for entry in page.button if entry.label == "提交问题").click().run()
    assert not page.exception
    assert "debug" not in calls[0][1]
    assert any("引用 [2]" in entry.label for entry in page.expander)
    assert all("vector_rank" not in str(entry.value) for entry in page.json)
    next(entry for entry in page.button if entry.label == "加载别名配置").click().run()
    assert not page.exception
    assert calls[-1] == ("get_aliases", "doc-a")
    next(entry for entry in page.text_input if entry.label == "实体名称").set_value("New Example")
    next(entry for entry in page.button if entry.label == "保存别名").click().run()
    assert not page.exception
    assert calls[-1] == ("put_aliases", "doc-a", "New Example", ["Alias"])
