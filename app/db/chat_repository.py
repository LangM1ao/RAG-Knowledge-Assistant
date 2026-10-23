import json
from contextlib import closing
from datetime import datetime
from app.db import database


def create_chat_record(question: str, answer: str, sources: list[dict], metadata: dict | None=None,
                       user_id: int | None=None, document_ids: list[str] | None=None) -> int:
    database.init_db()
    with closing(database.get_connection()) as connection, connection:
        cursor=connection.execute('''INSERT INTO chat_history
            (question,answer,sources_json,created_at,metadata_json,user_id,document_ids_json) VALUES(?,?,?,?,?,?,?)''',
            (question,answer,json.dumps(sources,ensure_ascii=False),datetime.now().isoformat(timespec='seconds'),
             json.dumps(metadata,ensure_ascii=False) if metadata is not None else None,user_id,
             json.dumps(document_ids) if document_ids is not None else None))
        return int(cursor.lastrowid)


def list_chat_records(limit: int=10, user_id: int | None=None, authorized_ids: list[str] | None=None) -> list[dict]:
    database.init_db()
    with closing(database.get_connection()) as connection:
        query='SELECT * FROM chat_history'
        args=[]
        if user_id is not None:
            query+=' WHERE user_id=?'; args.append(user_id)
        rows=connection.execute(query+' ORDER BY id DESC',args).fetchall()
    result=[]
    for row in rows:
        sources=json.loads(row['sources_json'])
        scope=json.loads(row['document_ids_json']) if row['document_ids_json'] is not None else None
        if authorized_ids is not None:
            # Old history has unknown generation context: do not expose it via the API.
            if scope is None or not set(scope)<=set(authorized_ids):
                continue
            if any(s.get('document_id') not in authorized_ids for s in sources):
                continue
        result.append({'id':row['id'],'question':row['question'],'answer':row['answer'],'sources':sources,
                       'created_at':row['created_at'],'metadata':json.loads(row['metadata_json']) if row['metadata_json'] else None})
        if len(result)>=max(1,min(limit,100)):
            break
    return result
