from pathlib import Path

from app.db.document_repository import delete_document, get_document, update_document
from app.services.chunker import chunk_text
from app.services.document_parser import parse_document
from app.services.vector_store import VectorStore


def delete_document_by_id(document_id: str) -> dict:
    document = get_document(document_id)

    if document is None:
        return {"success": False, "message": "Document not found."}

    store = VectorStore()
    store.delete_by_document_id(document_id)

    delete_document(document_id)

    file_path = Path(document["file_path"])
    if file_path.exists():
        file_path.unlink()

    return {"success": True, "message": "Document deleted successfully."}


def rebuild_document_by_id(document_id: str) -> dict:
    document = get_document(document_id)

    if document is None:
        return {"success": False, "message": "Document not found."}

    file_path = Path(document["file_path"])
    if not file_path.exists():
        update_document(document_id, {"status": "failed", "error_message": "Original file not found."})
        return {"success": False, "message": "Original file not found."}

    try:
        update_document(document_id, {"status": "rebuilding", "vector_status": "rebuilding", "error_message": None})

        text = parse_document(file_path)
        chunks = chunk_text(text, source_file=document["filename"])

        store = VectorStore()
        store.delete_by_document_id(document_id)
        chunk_count = store.add_chunks(chunks, document_id=document_id)

        update_document(
            document_id,
            {
                "status": "indexed",
                "chunk_count": chunk_count,
                "vector_status": "indexed",
                "error_message": None,
            },
        )

        return {"success": True, "message": "Document rebuilt successfully.", "chunk_count": chunk_count}

    except Exception as exc:
        update_document(document_id, {"status": "failed", "vector_status": "failed", "error_message": str(exc)})
        return {"success": False, "message": str(exc)}