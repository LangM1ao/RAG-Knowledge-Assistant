import json
import pytest
import chromadb
from test_final_auth import secured, headers
from test_final_permissions import seed
from app.services import rag_pipeline, vector_store
from app.services.vector_store import VectorStore
from app.services.answer_verifier import VerificationResult

@pytest.mark.parametrize('mode',['vector','bm25','hybrid'])
def test_real_chroma_private_shared_and_citations(secured,monkeypatch,tmp_path,mode):
    c,u=secured; seed(u['alice']['id'],'a'); seed(u['bob']['id'],'b')
    client=chromadb.PersistentClient(path=str(tmp_path/'chroma'))
    collection=client.get_or_create_collection('security_test',metadata={'hnsw:space':'cosine'})
    collection.add(ids=['a1','b1','orphan'],documents=['private_key ZEBRA_5839 confidential policy','robot manual start motor','private_key ORPHAN_SECRET'],
        embeddings=[[1.,0.,0.],[0.8,0.2,0.],[1.,0.,0.]],
        metadatas=[{'document_id':'a','source_file':'private_hr.txt'},{'document_id':'b','source_file':'robot.txt'},{'source_file':'orphan.txt'}])
    store=object.__new__(VectorStore);store.collection=collection;store.last_query_debug={}
    monkeypatch.setattr(vector_store,'embed_text',lambda text:[1.,0.,0.])
    monkeypatch.setattr(rag_pipeline,'VectorStore',lambda:store)
    contexts=[]
    def generate(messages):
        context=messages[1]['content'].split('Question:')[0]
        contexts.append(context)
        return ('ZEBRA_5839' if 'ZEBRA_5839' in context else 'robot manual')+' [1]'
    monkeypatch.setattr(rag_pipeline,'generate_answer',generate)
    monkeypatch.setattr(rag_pipeline,'verify_answer',lambda *args:VerificationResult(verdict='PASS',reason='controlled fixture'))
    monkeypatch.setattr(rag_pipeline,'RETRIEVAL_DEBUG_ENABLED',True)
    from app.api import chat
    monkeypatch.setattr(chat.config,'RETRIEVAL_DEBUG_ENABLED',True)
    bob=headers(c,'bob'); admin=headers(c,'admin')
    payload={'question':'private_key','retrieval_mode':mode,'debug':True}
    response=c.post('/chat/query',headers=bob,json=payload)
    assert response.status_code==200,response.text
    for secret in ['ZEBRA_5839','private_hr.txt','ORPHAN_SECRET','orphan.txt']:
        assert secret not in response.text
        assert all(secret not in value for value in contexts)
    assert all(source['document_id']=='b' for source in response.json()['sources'])
    assert c.patch('/documents/a/visibility',headers=admin,json={'visibility':'shared'}).status_code==200
    shared=c.post('/chat/query',headers=bob,json=payload)
    assert shared.status_code==200,shared.text
    assert 'ZEBRA_5839' in shared.json()['answer']
    assert any(source['document_id']=='a' for source in shared.json()['sources'])
    assert 'ORPHAN_SECRET' not in shared.text
    c.patch('/documents/a/visibility',headers=admin,json={'visibility':'private'})
    assert 'ZEBRA_5839' not in c.get('/chat/history',headers=bob).text
    assert 'ZEBRA_5839' not in c.post('/chat/query',headers=bob,json=payload).text

def test_no_documents_short_circuits_all_modes(secured,monkeypatch):
    c,u=secured
    monkeypatch.setattr(rag_pipeline,'VectorStore',lambda:pytest.fail('must not construct store'))
    h=headers(c,'bob')
    for mode in ['vector','bm25','hybrid']:
        r=c.post('/chat/query',headers=h,json={'question':'secret','retrieval_mode':mode})
        assert r.status_code==200 and r.json()['sources']==[]


def test_migration_preserves_ids_and_initializes_once(secured):
    from app.db import database
    from app.services import auth_service
    from fastapi import HTTPException
    c,u=secured
    seed(u['alice']['id'],'stable-id')
    database.init_db();database.init_db()
    with database.get_connection() as db:
        assert db.execute('SELECT owner_id FROM documents WHERE document_id=?',('stable-id',)).fetchone()[0]==u['alice']['id']
    with pytest.raises(HTTPException):
        auth_service.create_user('replacement','Replacement-long-password!','admin',bootstrap=True)
