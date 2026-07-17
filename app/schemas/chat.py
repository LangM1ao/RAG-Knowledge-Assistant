from pydantic import BaseModel, Field


class ChatQueryRequest(BaseModel):
    question: str
    top_k: int = Field(default=3, ge=1, le=20)
    similarity_threshold: float | None = Field(default=None, ge=0, le=2)
    document_ids: list[str] | None = None
    source_files: list[str] | None = None
