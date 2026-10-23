from app.services.auth_service import locked_access
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, APIRouter, File, HTTPException, UploadFile

from app.core.config import UPLOAD_DIR
from app.core.logging_config import get_logger
from app.db.document_repository import (
    create_document,
    get_document as get_document_by_id,
    list_document_records,
)
from app.schemas.document import DocumentInfo, DocumentUploadResponse
from app.schemas.entity_alias import DocumentAliasesRequest
from app.services import entity_aliases
from app.services.document_parser import parse_document
from app.services.document_service import (
    delete_document_by_id,
    rebuild_document_by_id,
)


from app.services.auth_service import current_user, admin_user, ACCESS_LOCK
from app.services.permissions import require_document, accessible_documents
from app.db.document_repository import update_document
from pydantic import BaseModel
from typing import Literal

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(current_user)])
logger = get_logger(__name__)


@router.post("/upload", response_model=DocumentUploadResponse)
@locked_access
def upload_document(file: UploadFile = File(...), user=Depends(current_user)):
    document_id = str(uuid4())
    filename = (file.filename or "uploaded_file").replace("\\", "/").rsplit("/", 1)[-1]
    if not filename or len(filename) > 200 or any(ord(c) < 32 for c in filename):
        raise HTTPException(400, "Invalid filename.")
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
    saved_path = UPLOAD_DIR / f"{document_id}{suffix}"

    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds 20 MiB limit.")

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
        message = "Document parsing failed."
        error_message = "Document parsing failed."

        # 记录解析失败，并显示具体报错位置
        logger.warning(
            "Document parse failed: document_id=%s error=%s",
            document_id,
            type(exc).__name__,
        )

    document_info = {
        "document_id": document_id,
        "owner_id": user["id"],
        "visibility": "private",
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
            message = "Indexing failed; the document was retained for retry."

    return DocumentUploadResponse(
        document_id=document_id,
        filename=filename,
        status=status,
        message=message,
    )


@router.get("/list")
@locked_access
def list_documents(user=Depends(current_user)):
    return {
        "documents": [{k:v for k,v in d.items() if k not in {"file_path", "error_message"}} for d in accessible_documents(user)]
    }


@router.post("/rebuild-all")
@locked_access
def rebuild_all_documents_api(user=Depends(admin_user)):
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
@locked_access
def get_document(document_id: str, user=Depends(current_user)):
    document = require_document(user, document_id)

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
@locked_access
def delete_document_api(document_id: str, user=Depends(current_user)):
    require_document(user, document_id, modify=True)
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
            detail="Document operation failed.",
        )

    logger.info(
        "Document deleted successfully: document_id=%s",
        document_id,
    )

    return {k:v for k,v in result.items() if k != "backup_path"}


@router.post("/{document_id}/rebuild")
@locked_access
def rebuild_document_api(document_id: str, user=Depends(current_user)):
    require_document(user, document_id, modify=True)
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
            detail="Document operation failed.",
        )

    logger.info(
        "Document rebuilt successfully: document_id=%s",
        document_id,
    )

    return {k:v for k,v in result.items() if k != "backup_path"}


@router.get("/{document_id}/aliases")
@locked_access
def get_aliases(document_id: str, user=Depends(current_user)):
    require_document(user, document_id)
    if get_document_by_id(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return entity_aliases.get_document_aliases(document_id)


@router.put("/{document_id}/aliases")
@locked_access
def set_aliases(document_id: str, request: DocumentAliasesRequest, user=Depends(current_user)):
    require_document(user, document_id, modify=True)
    if get_document_by_id(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    try:
        return entity_aliases.set_document_aliases(document_id, request.entity_name, request.aliases)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.delete("/{document_id}/aliases")
@locked_access
def remove_aliases(document_id: str, user=Depends(current_user)):
    require_document(user, document_id, modify=True)
    if get_document_by_id(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    entity_aliases.delete_document_aliases(document_id)
    return {"success": True}


class VisibilityUpdate(BaseModel):
    visibility: Literal['private','shared']

@router.patch('/{document_id}/visibility')
@locked_access
def set_visibility(document_id: str, request: VisibilityUpdate, user=Depends(admin_user)):
    with ACCESS_LOCK:
        require_document(user, document_id, modify=True)
        update_document(document_id, {'visibility': request.visibility})
    return {'document_id': document_id, 'visibility': request.visibility}
