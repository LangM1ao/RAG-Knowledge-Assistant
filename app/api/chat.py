from app.services.auth_service import locked_access
from copy import deepcopy
from fastapi import APIRouter, HTTPException, Query, Depends
from app.services.auth_service import current_user, ACCESS_LOCK
from app.services.permissions import resolve_scope

from app.core import config
from app.core.logging_config import get_logger
from app.db.chat_repository import create_chat_record, list_chat_records
from app.schemas.chat import ChatQueryRequest
from app.services.rag_pipeline import answer_question

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/query")
@locked_access
def query_knowledge_base(request: ChatQueryRequest, user=Depends(current_user)):
    with ACCESS_LOCK:
        return _query_authorized(request, user)

def _query_authorized(request, user):
    scope = resolve_scope(user, request.document_ids, request.source_files)
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        result = answer_question(
            question=request.question,
            retrieval_mode=request.retrieval_mode,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
            document_ids=scope,
            source_files=request.source_files,
            debug=request.debug,
        )
    except Exception as exc:
        logger.warning("Chat request failed: type=%s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="问答服务暂时不可用，请稍后重试。") from None

    metadata = deepcopy(result.get("run_metadata"))
    if metadata and not (config.RETRIEVAL_DEBUG_ENABLED and request.debug and result.get("debug_enabled")):
        metadata.pop("trace", None)
    create_chat_record(
        question=request.question,
        answer=result["answer"],
        sources=result["sources"],
        metadata=metadata,
        user_id=user["id"],
        document_ids=scope,
    )

    response = {
        "question": request.question,
        "answer": result["answer"],
        "sources": result["sources"],
        "verification": result.get("verification"),
        "run_metadata": metadata,
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
@locked_access
def get_chat_history(limit: int = Query(default=10, ge=1, le=100), include_debug: bool = False, user=Depends(current_user)):
    rows = deepcopy(list_chat_records(limit=limit, user_id=user["id"], authorized_ids=resolve_scope(user)))
    if not (config.RETRIEVAL_DEBUG_ENABLED and include_debug):
        for row in rows:
            if row.get('metadata'):
                row['metadata'].pop('trace', None)
    return {'history': rows}
