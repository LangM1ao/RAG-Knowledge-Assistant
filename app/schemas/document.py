from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    message: str


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
    file_path: str
    file_type: str
    upload_time: str
    status: str
    chunk_count: int
    vector_status: str
    error_message: str | None = None