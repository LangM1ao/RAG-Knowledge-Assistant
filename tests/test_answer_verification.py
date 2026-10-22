"""答案校验的行为测试：仅替换检索和外部 LLM 请求，不访问真实 API。"""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import chat
from app.main import app
from app.services import llm_client, rag_pipeline


@pytest.fixture
def scenario(monkeypatch):
    state = {
        "answer": "员工报销需要经过部门经理审批。[1]",
        "payload": {"verdict": "PASS", "reason": "审批人得到资料支持"},
        "chunks": [{
            "chunk_id": "chunk-1",
            "text": "员工报销需要经过部门经理审批。",
            "metadata": {"source_file": "policy.txt", "document_id": "doc-1"},
            "distance": 0.12,
        }],
        "generation_calls": [],
        "verification_calls": [],
        "client_options": [],
    }

    class FakeStore:
        def query(self, **kwargs):
            return state["chunks"]

    def generate(messages):
        state["generation_calls"].append(messages)
        return state["answer"]

    def parse(**kwargs):
        state["verification_calls"].append(kwargs)
        if "error" in state:
            raise state["error"]
        parsed = kwargs["response_format"].model_validate_json(
            json.dumps(state["payload"], ensure_ascii=False)
        )
        message = SimpleNamespace(parsed=parsed, refusal=None)
        if state.get("missing_parsed"):
            message.parsed = None
            message.refusal = "Cannot verify"
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    def client(**kwargs):
        state["client_options"].append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))

    monkeypatch.setattr(rag_pipeline, "VectorStore", FakeStore)
    monkeypatch.setattr(rag_pipeline, "generate_answer", generate)
    monkeypatch.setattr(rag_pipeline, "ANSWER_VERIFICATION_ENABLED", True, raising=False)
    monkeypatch.setattr(llm_client, "OPENAI_API_KEY", "mock-key")
    monkeypatch.setattr(llm_client, "OpenAI", client)
    return state


def test_supported_answer_passes_with_same_context_and_sources(scenario):
    result = rag_pipeline.answer_question("员工报销需要谁审批？")
    assert result["answer"] == "员工报销需要经过部门经理审批。[1]"
    assert result.get("verification", {}).get("status") == "PASS"
    assert result["sources"][0]["source_file"] == "policy.txt"
    assert result["sources"][0]["chunk_preview"] == "员工报销需要经过部门经理审批。"
    request = scenario["verification_calls"][0]
    data = json.loads(request["messages"][1]["content"])
    assert data["context"] == "[1] source=policy.txt, chunk_id=chunk-1\n员工报销需要经过部门经理审批。"
    assert data["context"] in scenario["generation_calls"][0][1]["content"]
    assert data["question"] == "员工报销需要谁审批？"
    assert data["generated_answer"] == result["answer"]
    assert request["model"] == llm_client.LLM_MODEL
    assert scenario["client_options"][0]["timeout"] == 30.0
    assert scenario["client_options"][0]["max_retries"] == 0


@pytest.mark.parametrize("answer, reason", [
    ("员工报销可以直接到账。", "资料只说明审批，没有到账规则"),
    ("员工报销上限为 5000 元。", "资料没有提供金额上限"),
])
def test_unsupported_answer_is_replaced_and_has_no_sources(scenario, answer, reason):
    scenario["answer"] = answer
    scenario["payload"] = {"verdict": "FAIL", "reason": reason}
    result = rag_pipeline.answer_question("员工报销的金额上限是多少？")
    assert result["answer"] == "根据当前知识库资料，无法确定该问题的答案。"
    assert result["sources"] == []
    assert result["verification"]["status"] == "FAIL"
    assert answer not in json.dumps(result, ensure_ascii=False)


def test_no_retrieval_skips_generation_and_verification(scenario):
    scenario["chunks"] = []
    result = rag_pipeline.answer_question("unknown", similarity_threshold=0.01)
    assert "没有找到相关依据" in result["answer"]
    assert result["sources"] == []
    assert scenario["generation_calls"] == []
    assert scenario["verification_calls"] == []


@pytest.mark.parametrize("answer", [
    "根据当前知识库资料，无法确定该问题的答案。",
    "知识库中没有足够依据。",
    "知识库中没有找到相关依据，因此我不能确定答案。",
])
def test_plain_generation_refusal_skips_verification(scenario, answer):
    scenario["answer"] = answer
    result = rag_pipeline.answer_question("金额上限？")
    assert result["answer"] == answer
    assert result["verification"]["status"] == "SKIPPED"
    assert scenario["verification_calls"] == []


def test_refusal_phrase_with_fabricated_fact_does_not_skip_verification(scenario):
    scenario["answer"] = "知识库中没有足够依据，但报销上限应该是 5000 元。"
    scenario["payload"] = {"verdict": "FAIL", "reason": "金额没有依据"}
    result = rag_pipeline.answer_question("金额上限？")
    assert "5000" not in result["answer"]
    assert result["verification"]["status"] == "FAIL"
    assert len(scenario["verification_calls"]) == 1


@pytest.mark.parametrize("error", [RuntimeError("SECRET_API_KEY"), TimeoutError("timeout")])
def test_verification_service_error_never_returns_draft(scenario, error, caplog):
    scenario["error"] = error
    result = rag_pipeline.answer_question("谁审批？")
    assert result["answer"] == "答案校验暂时不可用，请稍后重试。"
    assert result["sources"] == []
    assert result["verification"]["status"] == "ERROR"
    assert "SECRET_API_KEY" not in caplog.text
    assert scenario["answer"] not in json.dumps(result, ensure_ascii=False)


@pytest.mark.parametrize("payload", [
    {"verdict": "UNKNOWN", "reason": "unknown"},
    {"verdict": "PASS"},
    {"verdict": "PASS", "reason": ""},
    {"verdict": "PASS", "reason": "   "},
    {"verdict": "PASS", "reason": 123},
    {"verdict": "PASS", "reason": "ok", "extra": "unexpected"},
    "PASS", None,
])
def test_invalid_structured_result_is_not_treated_as_pass(scenario, payload):
    scenario["payload"] = payload
    result = rag_pipeline.answer_question("谁审批？")
    assert result["answer"] == "答案校验暂时不可用，请稍后重试。"
    assert result["sources"] == []
    assert result["verification"]["status"] == "ERROR"


def test_missing_parsed_result_is_not_treated_as_pass(scenario):
    scenario["missing_parsed"] = True
    result = rag_pipeline.answer_question("谁审批？")
    assert result["verification"]["status"] == "ERROR"
    assert result["answer"] != scenario["answer"]


@pytest.mark.parametrize("answer", ["", "  ", None])
def test_empty_generated_answer_is_not_returned_as_success(scenario, answer):
    scenario["answer"] = answer
    result = rag_pipeline.answer_question("谁审批？")
    assert result["verification"]["status"] == "ERROR"
    assert result["sources"] == []
    assert scenario["verification_calls"] == []


def test_disabled_verification_keeps_original_flow(scenario, monkeypatch):
    monkeypatch.setattr(rag_pipeline, "ANSWER_VERIFICATION_ENABLED", False)
    scenario["answer"] = "原有回答[1]"
    result = rag_pipeline.answer_question("谁审批？")
    assert result["answer"] == "原有回答[1]"
    assert result["sources"][0]["source_file"] == "policy.txt"
    assert scenario["verification_calls"] == []


def test_api_returns_only_verified_answer_and_saves_safe_history(scenario, monkeypatch):
    scenario["answer"] = "报销上限为 5000 元。"
    scenario["payload"] = {"verdict": "FAIL", "reason": "金额没有依据"}
    saved = []
    monkeypatch.setattr(chat, "create_chat_record", lambda **kwargs: saved.append(kwargs))
    response = TestClient(app).post("/chat/query", json={"question": "金额上限？"})
    assert response.status_code == 200
    body = response.json()
    assert body["verification"]["status"] == "FAIL"
    assert body["sources"] == []
    assert "5000" not in response.text
    assert "5000" not in saved[0]["answer"]


def test_verifier_rejects_empty_context_without_calling_api(scenario):
    import importlib
    assert importlib.util.find_spec("app.services.answer_verifier") is not None
    verifier = importlib.import_module("app.services.answer_verifier")
    with pytest.raises(verifier.AnswerVerificationError):
        verifier.verify_answer("谁审批？", " ", "经理审批。")
    assert scenario["verification_calls"] == []


def test_real_sdk_parses_strict_json_schema_with_mock_http(monkeypatch):
    import httpx
    from openai import OpenAI as RealOpenAI
    from app.services.answer_verifier import verify_answer

    def respond(request):
        body = json.loads(request.content)
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["strict"] is True
        return httpx.Response(200, json={
            "id": "chatcmpl-mock", "object": "chat.completion", "created": 1,
            "model": llm_client.LLM_MODEL,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": '{"verdict":"PASS","reason":"Supported"}',
                "refusal": None,
            }}],
        })

    client = RealOpenAI(
        api_key="mock-key", max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    monkeypatch.setattr(llm_client, "OPENAI_API_KEY", "mock-key")
    monkeypatch.setattr(llm_client, "OpenAI", lambda **kwargs: client)
    with client:
        result = verify_answer("Who approves?", "A manager approves.", "A manager approves.")
    assert result.verdict == "PASS"


@pytest.mark.parametrize("status, label", [
    ("PASS", "通过"),
    ("FAIL", "未通过，已拒答"),
    ("ERROR", "校验服务暂时不可用"),
])
def test_streamlit_displays_verification_and_service_error_correctly(monkeypatch, status, label):
    from streamlit.testing.v1 import AppTest
    from frontend import api_client

    class FakeClient:
        def check_health(self):
            return SimpleNamespace(connected=True, message="OK", service="test")

        def list_documents(self):
            return []

        def get_chat_history(self, limit):
            return []

    monkeypatch.setattr(api_client, "ApiClient", FakeClient)
    page = AppTest.from_file("frontend/streamlit_app.py")
    page.session_state["last_answer"] = {
        "answer": "已检查的回答" if status == "PASS" else "安全提示",
        "sources": [{"source_file": "policy.txt", "chunk_preview": "经理审批", "distance": .1}]
        if status == "PASS" else [],
        "verification": {"status": status},
    }
    page.run(timeout=10)
    assert not page.exception
    assert f"答案依据校验：{label}" in [item.value for item in page.caption]
    if status == "ERROR":
        assert "知识库中未找到可靠依据。" not in [item.value for item in page.warning]
    if status == "PASS":
        assert any("policy.txt" in item.label for item in page.expander)
