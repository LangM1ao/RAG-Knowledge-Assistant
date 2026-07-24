from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import DEFAULT_RETRIEVAL_MODE


class ChatQueryRequest(BaseModel):
    question: str
    retrieval_mode: Literal["vector", "bm25", "hybrid"] = DEFAULT_RETRIEVAL_MODE
    top_k: int = Field(default=3, ge=1, le=20)
    similarity_threshold: float | None = Field(default=None, ge=0, le=2)
    document_ids: list[str] | None = None
    source_files: list[str] | None = None
