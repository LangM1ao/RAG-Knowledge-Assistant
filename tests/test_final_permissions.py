import pytest
from test_final_auth import secured, headers
from app.db import database, document_repository
from app.api import documents, chat


def seed(uid, doc='a'):
    with database.get_connection() as c:
        c.execute("INSERT INTO documents(document_id,filename,file_path,file_type,upload_time,status,chunk_count,vector_status,owner_id,visibility) VALUES(?,?,?,'txt','now','indexed',1,'indexed',?,'private')",(doc,doc+'.txt','unused',uid))


def test_document_matrix_and_aliases(secured,monkeypatch):
    c,u=secured; seed(u['alice']['id']); seed(u['bob']['id'],'b')
    a=headers(c,'alice'); b=headers(c,'bob'); admin=headers(c,'admin')
    assert [d['document_id'] for d in c.get('/documents/list',headers=b).json()['documents']]==['b']
    for method,path in [('get','/documents/a'),('delete','/documents/a'),('post','/documents/a/rebuild'),('get','/documents/a/aliases'),('delete','/documents/a/aliases')]:
        assert getattr(c,method)(path,headers=b).status_code==404
    assert c.put('/documents/a/aliases',headers=b,json={'entity_name':'test','aliases':[]}).status_code==404
    assert c.post('/documents/rebuild-all',headers=b).status_code==403
    assert c.patch('/documents/a/visibility',headers=a,json={'visibility':'shared'}).status_code==403
    assert c.patch('/documents/a/visibility',headers=admin,json={'visibility':'shared'}).status_code==200
    assert c.get('/documents/a',headers=b).status_code==200
    assert c.delete('/documents/a',headers=b).status_code==404
    assert c.post('/documents/a/rebuild',headers=b).status_code==404
    monkeypatch.setattr(documents,'rebuild_document_by_id',lambda x:{'success':True})
    assert c.post('/documents/a/rebuild',headers=a).status_code==200
    assert c.post('/documents/a/rebuild',headers=admin).status_code==200


def test_upload_ownership_and_filename(secured,monkeypatch,tmp_path):
    c,u=secured; a=headers(c,'alice')
    monkeypatch.setattr(documents,'UPLOAD_DIR',tmp_path)
    monkeypatch.setattr(documents,'parse_document',lambda p:'test document')
    monkeypatch.setattr(documents,'rebuild_document_by_id',lambda d:{'success':True})
    response=c.post('/documents/upload',headers=a,files={'file':('../../escape.txt',b'test','text/plain')},data={'owner_id':str(u['bob']['id'])})
    assert response.status_code==200
    doc=document_repository.get_document(response.json()['document_id'])
    assert doc['owner_id']==u['alice']['id'] and doc['visibility']=='private'
    from pathlib import Path
    assert Path(doc['file_path']).parent==tmp_path
    assert doc['filename']=='escape.txt'
    assert c.post('/documents/upload',headers=a,files={'file':('bad.exe',b'x')}).status_code==400
    monkeypatch.setattr(documents,'MAX_UPLOAD_BYTES',3)
    assert c.post('/documents/upload',headers=a,files={'file':('big.txt',b'1234')}).status_code==413

@pytest.mark.parametrize('mode',['vector','bm25','hybrid'])
def test_query_authorized_scope_history_and_revocation(secured,monkeypatch,mode):
    c,u=secured; seed(u['alice']['id']); seed(u['bob']['id'],'b')
    b=headers(c,'bob'); a=headers(c,'alice'); admin=headers(c,'admin'); seen=[]
    def answer(**kwargs):
        seen.append(kwargs['document_ids'])
        return {'answer':'safe','sources':[{'document_id':d,'source_file':d+'.txt'} for d in kwargs['document_ids']]}
    monkeypatch.setattr(chat,'answer_question',answer)
    assert c.post('/chat/query',json={'question':'q'}).status_code==401
    assert c.post('/chat/query',headers=b,json={'question':'q','document_ids':['a'],'retrieval_mode':mode}).status_code==403
    assert not seen
    assert c.post('/chat/query',headers=b,json={'question':'q','retrieval_mode':mode}).status_code==200
    assert seen[-1]==['b']
    assert c.get('/chat/history',headers=a).json()['history']==[]
    c.patch('/documents/a/visibility',headers=admin,json={'visibility':'shared'})
    assert c.post('/chat/query',headers=b,json={'question':'q','document_ids':['a'],'retrieval_mode':mode}).status_code==200
    assert seen[-1]==['a']
    c.patch('/documents/a/visibility',headers=admin,json={'visibility':'private'})
    assert all('a.txt' not in str(r) for r in c.get('/chat/history',headers=b).json()['history'])


def test_upload_wire_limit_before_multipart(secured):
    c,u=secured
    h=headers(c,'alice')
    h.update({'Content-Type':'multipart/form-data; boundary=boundary'})
    def stream():
        yield b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="large.txt"\r\n\r\n'
        for _ in range(22): yield b'x'*(1024*1024)
        yield b'\r\n--boundary--\r\n'
    assert c.post('/documents/upload',headers=h,content=stream()).status_code==413
    assert c.post('/documents/upload',headers={'Content-Length':str(100*1024*1024)}).status_code in {401,413}



def test_unauthenticated_upload_does_not_consume_body(secured):
    c,u=secured
    consumed=[]
    def body():
        consumed.append(True)
        yield b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.txt"\r\n\r\nprivate\r\n--x--\r\n'
    assert c.post('/documents/upload',headers={'Content-Type':'multipart/form-data; boundary=x'},content=body()).status_code==401
    assert consumed==[]
