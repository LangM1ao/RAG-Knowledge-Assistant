import json
from contextlib import closing
from datetime import datetime
from app.db import database


def create_chat_record(question: str,answer: str,sources: list[dict],metadata: dict | None=None) -> int:
    database.init_db()
    with closing(database.get_connection()) as connection,connection:
        cursor=connection.execute('''INSERT INTO chat_history
            (question,answer,sources_json,created_at,metadata_json) VALUES(?,?,?,?,?)''',
            (question,answer,json.dumps(sources,ensure_ascii=False),datetime.now().isoformat(timespec='seconds'),
             json.dumps(metadata,ensure_ascii=False) if metadata is not None else None))
        return int(cursor.lastrowid)


def list_chat_records(limit: int=10) -> list[dict]:
    database.init_db()
    with closing(database.get_connection()) as connection:
        rows=connection.execute('''SELECT id,question,answer,sources_json,created_at,metadata_json
            FROM chat_history ORDER BY id DESC LIMIT ?''',(max(1,min(limit,100)),)).fetchall()
    return [{'id':row['id'],'question':row['question'],'answer':row['answer'],
             'sources':json.loads(row['sources_json']),'created_at':row['created_at'],
             'metadata':json.loads(row['metadata_json']) if row['metadata_json'] else None} for row in rows]
