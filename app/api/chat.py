from fastapi import APIRouter, HTTPException, Query

from app.core import config
from app.core.logging_config import get_logger
from app.db.chat_repository import create_chat_record, list_chat_records
from app.schemas.chat import ChatQueryRequest
from app.services.rag_pipeline import answer_question

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/query")
def query_knowledge_base(request: ChatQueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        result = answer_question(
            question=request.question,
            retrieval_mode=request.retrieval_mode,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
            document_ids=request.document_ids,
            source_files=request.source_files,
            debug=request.debug,
        )
    except Exception as exc:
        logger.warning("Chat request failed: type=%s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="问答服务暂时不可用，请稍后重试。") from None

    create_chat_record(
        question=request.question,
        answer=result["answer"],
        sources=result["sources"],
    )

    response = {
        "question": request.question,
        "answer": result["answer"],
        "sources": result["sources"],
        "verification": result.get("verification"),
        "retrieval_mode": result.get(
            "retrieval_mode",
            request.retrieval_mode,
        ),
        "citation_status": result.get("citation_status"),
        "debug_enabled": bool(config.RETRIEVAL_DEBUG_ENABLED and request.debug and result.get("debug_enabled")),
    }

    if response["debug_enabled"]:
        response["retrieval_debug"] = result.get("retrieval_debug", [])
        response["retrieval_trace"] = result.get("retrieval_trace", {})
    return response


@router.get("/history")
def get_chat_history(limit: int = Query(default=10, ge=1, le=100)):
    return {"history": list_chat_records(limit=limit)}
