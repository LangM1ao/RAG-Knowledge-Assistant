import sqlite3
from typing import Any

from app.core.config import METADATA_DB_PATH


def get_connection():
    METADATA_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(METADATA_DB_PATH)


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_type TEXT NOT NULL,
                upload_time TEXT NOT NULL,
                status TEXT NOT NULL,
                chunk_count INTEGER NOT NULL,
                vector_status TEXT NOT NULL,
                error_message TEXT
            )
            """
        )
        conn.commit()


def create_document(document_info: dict[str, Any]) -> None:
    init_db()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO documents (
                document_id,
                filename,
                file_path,
                file_type,
                upload_time,
                status,
                chunk_count,
                vector_status,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_info["document_id"],
                document_info["filename"],
                document_info["file_path"],
                document_info["file_type"],
                document_info["upload_time"],
                document_info["status"],
                document_info["chunk_count"],
                document_info["vector_status"],
                document_info["error_message"],
            ),
        )
        conn.commit()


def get_document(document_id: str) -> dict | None:
    init_db()

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT *
            FROM documents
            WHERE document_id = ?
            """,
            (document_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)


def list_document_records() -> list[dict]:
    init_db()

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT *
            FROM documents
            ORDER BY upload_time DESC
            """
        )
        rows = cursor.fetchall()

    return [dict(row) for row in rows]

def update_document(document_id: str, updates: dict) -> None:
    if not updates:
        return

    fields = ", ".join([f"{key} = ?" for key in updates.keys()])
    values = list(updates.values())
    values.append(document_id)

    with get_connection() as connection:
        connection.execute(
            f"UPDATE documents SET {fields} WHERE document_id = ?",
            values,
        )
        connection.commit()


def delete_document(document_id: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM documents WHERE document_id = ?",
            (document_id,),
        )
        connection.commit()