import json
from datetime import datetime

from app.db import database


def create_chat_record(
    question: str,
    answer: str,
    sources: list[dict],
) -> int:
    database.init_db()
    created_at = datetime.now().isoformat(timespec="seconds")

    with database.get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO chat_history (
                question,
                answer,
                sources_json,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                question,
                answer,
                json.dumps(sources, ensure_ascii=False),
                created_at,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def list_chat_records(limit: int = 10) -> list[dict]:
    database.init_db()
    safe_limit = max(1, min(limit, 100))

    with database.get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, question, answer, sources_json, created_at
            FROM chat_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "question": row["question"],
            "answer": row["answer"],
            "sources": json.loads(row["sources_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]
