import json
import sqlite3
from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.db import database,chat_repository
from app.api import chat
from app.main import app
from app.services import rag_pipeline


def test_old_history_migrates_without_inventing_status(tmp_path,monkeypatch):
    path=tmp_path/'history.db'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE chat_history(id INTEGER PRIMARY KEY,question TEXT,answer TEXT,sources_json TEXT,created_at TEXT)')
        c.execute("INSERT INTO chat_history VALUES(1,'old','old answer','[]','2026-07-17')")
    monkeypatch.setattr(database,'METADATA_DB_PATH',path)
    rows=chat_repository.list_chat_records()
    assert rows[0]['metadata'] is None
    chat_repository.create_chat_record('new','answer',[],metadata={'verification':{'status':'PASS'},'settings':{'top_k':3}})
    rows=chat_repository.list_chat_records()
    assert rows[0]['metadata']['verification']['status']=='PASS'
    assert rows[1]['metadata'] is None


def test_history_trace_hidden_by_default_and_requires_server_flag(monkeypatch):
    record={'id':1,'question':'q','answer':'a','sources':[],'metadata':{'verification':{'status':'PASS'},'trace':{'retrieval_query':'PRIVATE_QUERY'}}}
    monkeypatch.setattr(chat,'list_chat_records',lambda limit:[record])
    client=TestClient(app)
    monkeypatch.setattr(chat.config,'RETRIEVAL_DEBUG_ENABLED',False)
    assert 'PRIVATE_QUERY' not in client.get('/chat/history?include_debug=true').text
    monkeypatch.setattr(chat.config,'RETRIEVAL_DEBUG_ENABLED',True)
    assert 'PRIVATE_QUERY' not in client.get('/chat/history').text
    assert 'PRIVATE_QUERY' in client.get('/chat/history?include_debug=true').text


def test_safe_run_metadata_records_stage_without_raw_context(monkeypatch):
    class Store:
        def query(self,**kwargs): return []
    monkeypatch.setattr(rag_pipeline,'VectorStore',Store)
    result=rag_pipeline.answer_question('private query',retrieval_mode='vector',top_k=2,similarity_threshold=0.6)
    meta=result['run_metadata']
    assert meta['settings']['top_k']==2
    assert meta['outcome']['stage']=='retrieval'
    assert meta['outcome']['final_refused'] is True
    assert meta['verification']['status']=='SKIPPED'
    assert 'private query' not in json.dumps(meta)
