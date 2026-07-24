from fastapi import APIRouter, HTTPException, Query

from app.db.chat_repository import create_chat_record, list_chat_records
from app.schemas.chat import ChatQueryRequest
from app.services.rag_pipeline import answer_question

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
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    create_chat_record(
        question=request.question,
        answer=result["answer"],
        sources=result["sources"],
    )

    return {
        "question": request.question,
        "answer": result["answer"],
        "sources": result["sources"],
        "retrieval_mode": result.get(
            "retrieval_mode",
            request.retrieval_mode,
        ),
        "retrieval_debug": result.get(
            "retrieval_debug",
            result["sources"],
        ),
    }


@router.get("/history")
def get_chat_history(limit: int = Query(default=10, ge=1, le=100)):
    return {"history": list_chat_records(limit=limit)}
