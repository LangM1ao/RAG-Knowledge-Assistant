from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import UPLOAD_DIR
from app.core.logging_config import get_logger
from app.db.document_repository import (
    create_document,
    get_document as get_document_by_id,
    list_document_records,
)
from app.schemas.document import DocumentInfo, DocumentUploadResponse
from app.services.document_parser import parse_document
from app.services.document_service import (
    delete_document_by_id,
    rebuild_document_by_id,
)


router = APIRouter(prefix="/documents", tags=["documents"])
logger = get_logger(__name__)


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    document_id = str(uuid4())
    filename = file.filename or "uploaded_file"
    suffix = Path(filename).suffix.lower()

    # 记录开始上传
    logger.info(
        "Uploading document: filename=%s document_id=%s",
        filename,
        document_id,
    )

    if suffix not in [".txt", ".pdf"]:
        logger.warning(
            "Unsupported file type: filename=%s suffix=%s",
            filename,
            suffix,
        )

        raise HTTPException(
            status_code=400,
            detail="Only txt and pdf files are supported.",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = UPLOAD_DIR / f"{document_id}_{filename}"

    content = await file.read()

    if not content:
        logger.warning(
            "Uploaded file is empty: filename=%s document_id=%s",
            filename,
            document_id,
        )

        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty.",
        )

    saved_path.write_bytes(content)

    try:
        text = parse_document(saved_path)

        if not text:
            raise ValueError("Parsed text is empty.")

        status = "parsed"
        message = "Document uploaded and parsed successfully."
        error_message = None

        # 记录解析成功
        logger.info(
            "Document parsed successfully: document_id=%s",
            document_id,
        )

    except Exception as exc:
        status = "failed"
        message = str(exc)
        error_message = str(exc)

        # 记录解析失败，并显示具体报错位置
        logger.exception(
            "Document parse failed: document_id=%s error=%s",
            document_id,
            exc,
        )

    document_info = {
        "document_id": document_id,
        "filename": filename,
        "file_path": str(saved_path),
        "file_type": suffix.replace(".", ""),
        "upload_time": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "chunk_count": 0,
        "vector_status": "not_indexed",
        "error_message": error_message,
    }

    create_document(document_info)

    logger.info(
        "Document metadata saved: document_id=%s status=%s",
        document_id,
        status,
    )

    if status == "parsed":
        index_result = rebuild_document_by_id(document_id)
        if index_result["success"]:
            status = "indexed"
            message = "Document uploaded, parsed, and indexed successfully."
        else:
            status = "failed"
            message = index_result["message"]

    return DocumentUploadResponse(
        document_id=document_id,
        filename=filename,
        status=status,
        message=message,
    )


@router.get("/list")
def list_documents():
    return {
        "documents": list_document_records()
    }


@router.post("/rebuild-all")
def rebuild_all_documents_api():
    documents = list_document_records()
    results = []

    logger.info(
        "Rebuilding all documents: document_count=%s",
        len(documents),
    )

    for document in documents:
        result = rebuild_document_by_id(document["document_id"])

        results.append({
            "document_id": document["document_id"],
            "result": result,
        })

    logger.info(
        "Finished rebuilding all documents: document_count=%s",
        len(documents),
    )

    return {"results": results}


@router.get("/{document_id}", response_model=DocumentInfo)
def get_document(document_id: str):
    document = get_document_by_id(document_id)

    if document is None:
        logger.warning(
            "Document not found: document_id=%s",
            document_id,
        )

        raise HTTPException(
            status_code=404,
            detail="Document not found.",
        )

    return document


@router.delete("/{document_id}")
def delete_document_api(document_id: str):
    logger.info(
        "Deleting document: document_id=%s",
        document_id,
    )

    result = delete_document_by_id(document_id)

    if not result["success"]:
        logger.warning(
            "Document deletion failed: document_id=%s message=%s",
            document_id,
            result["message"],
        )

        raise HTTPException(
            status_code=404,
            detail=result["message"],
        )

    logger.info(
        "Document deleted successfully: document_id=%s",
        document_id,
    )

    return result


@router.post("/{document_id}/rebuild")
def rebuild_document_api(document_id: str):
    logger.info(
        "Rebuilding document: document_id=%s",
        document_id,
    )

    result = rebuild_document_by_id(document_id)

    if not result["success"]:
        logger.warning(
            "Document rebuild failed: document_id=%s message=%s",
            document_id,
            result["message"],
        )

        raise HTTPException(
            status_code=400,
            detail=result["message"],
        )

    logger.info(
        "Document rebuilt successfully: document_id=%s",
        document_id,
    )

    return result
