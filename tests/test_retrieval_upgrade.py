import sqlite3
from types import SimpleNamespace
import pytest
from app.services.bm25_retriever import tokenize
from app.services.retriever import Retriever, reciprocal_rank_fusion


def test_normalization_matches_width_and_quotes_without_losing_identifiers():
    from app.services.query_normalizer import normalize_query
    assert normalize_query('  ＡＰＩ_TIMEOUT_MS  King’s   College ') == "api_timeout_ms king's college"
    assert 'api_timeout_ms' in tokenize('ＡＰＩ_TIMEOUT_MS')


def test_rrf_keeps_different_documents_and_ignores_duplicate_votes():
    def row(doc):
        return {'chunk_id':'same','metadata':{'document_id':doc},'text':doc,'distance':0.2}
    rows=reciprocal_rank_fusion([row('a'),row('a'),row('b')],[],top_k=3)
    assert len(rows)==2
    assert rows[0]['rrf_score']==pytest.approx(1/61)
    assert rows[1]['vector_rank']==2


def test_alias_storage_persists_and_honors_both_filters(tmp_path,monkeypatch):
    from app.services import entity_aliases as aliases
    path=tmp_path/'meta.db'
    def connect():
        c=sqlite3.connect(path); c.row_factory=sqlite3.Row; return c
    monkeypatch.setattr(aliases,'get_connection',connect)
    with connect() as c:
        c.execute('CREATE TABLE documents(document_id TEXT PRIMARY KEY,filename TEXT)')
        c.executemany('INSERT INTO documents VALUES(?,?)',[('a','a.txt'),('b','b.txt')])
    aliases.set_document_aliases('a','Alice Example',['示例甲'])
    assert aliases.get_document_aliases('a')['aliases']==['示例甲','Alice Example']
    assert aliases.list_aliases(document_ids=['b'])==[]
    assert aliases.list_aliases(document_ids=['a'],source_files=['b.txt'])==[]
    assert aliases.list_aliases(document_ids=['a'])[0]['entity_name']=='Alice Example'
    aliases.delete_document_aliases('a')
    assert aliases.list_aliases()==[]


def test_alias_replaces_query_and_restricts_identity_scope():
    class Store:
        def query(self,**kwargs): self.call=kwargs; return []
    store=Store()
    rows=[{'document_id':'a','source_file':'a.txt','entity_name':'Alice Example','aliases':['示例甲','Alice Example']}]
    r=Retriever(vector_store=store,alias_records=rows)
    r.query('示例甲的学校是什么？')
    assert 'alice example' in store.call['question']
    assert store.call['document_ids']==['a']
    r.query('示例甲的学校是什么？',document_ids=['b'])
    assert store.call['document_ids']==['b']
    assert 'alice example' not in store.call['question']
    assert r.last_debug['alias_matches']==[]


def test_ambiguous_alias_does_not_mix_two_people():
    rows=[{'document_id':d,'source_file':d+'.txt','entity_name':n,'aliases':['同名']} for d,n in [('a','Alice Example'),('b','Bob Example')]]
    store=SimpleNamespace(query=lambda **kw: pytest.fail('ambiguous identity must not retrieve'))
    r=Retriever(vector_store=store,alias_records=rows)
    assert r.query('同名在哪里读书？')==[]
    assert r.last_debug['stop_reason']=='ambiguous_entity_alias'


def test_latin_alias_is_not_a_substring_of_another_name():
    from app.services.entity_aliases import resolve_aliases
    rows=[{'document_id':'a','entity_name':'Ann Example','aliases':['Ann']}]
    result=resolve_aliases('Joanne school',rows)
    assert result['matches']==[]


def test_neighbors_stay_in_document_section_and_budget(monkeypatch):
    from app.services import retriever as module
    def chunk(i,doc='a',section='EDUCATION',text=None):
        return {'chunk_id':f'{doc}-{i}','text':text or 'Evidence '+str(i),'metadata':{'document_id':doc,'source_file':doc+'.txt','chunk_index':i,'section_title':section}}
    anchor=chunk(1)
    allrows=[chunk(0,section='CONTACT'),anchor,chunk(2),chunk(2,doc='b')]
    class Collection:
        def get(self,**kw):
            doc=kw['where']['document_id']; rows=[x for x in allrows if x['metadata']['document_id']==doc]
            return {'ids':[x['chunk_id'] for x in rows],'documents':[x['text'] for x in rows],'metadatas':[x['metadata'] for x in rows]}
    r=Retriever(vector_store=SimpleNamespace(collection=Collection()),alias_records=[])
    expanded=r.expand_context('学校和成绩分别是什么？',[anchor],document_ids=['a'])
    assert [x['chunk_id'] for x in expanded]==['a-1','a-2']
    assert expanded[1]['retrieval_source']=='adjacent'
    assert len(r.expand_context('学校是什么？',[anchor],document_ids=['a']))==1
    monkeypatch.setattr(module,'CONTEXT_MAX_CHARS',len(anchor['text']))
    assert len(r.expand_context('学校和成绩？',[anchor]))==1

def test_aliases_use_real_repository_connection_without_row_factory(tmp_path, monkeypatch):
    from app.db import document_repository as repository
    from app.services import entity_aliases as aliases
    monkeypatch.setattr(repository, 'METADATA_DB_PATH', tmp_path / 'metadata.db')
    repository.create_document({'document_id':'real','filename':'real.txt','file_path':'not-used',
        'file_type':'txt','upload_time':'2026-10-22','status':'indexed','chunk_count':1,
        'vector_status':'indexed','error_message':None})
    aliases.set_document_aliases('real','Example Person',['示例人物'])
    assert aliases.get_document_aliases('real')['entity_name'] == 'Example Person'

def test_registered_identity_enriches_embedding_but_not_source_text(tmp_path, monkeypatch):
    from app.db import document_repository as repository
    from app.services import entity_aliases as aliases, vector_store
    from app.services.chunker import TextChunk
    monkeypatch.setattr(repository,'METADATA_DB_PATH',tmp_path/'metadata.db')
    repository.create_document({'document_id':'entity-doc','filename':'school.txt','file_path':'not-used',
        'file_type':'txt','upload_time':'2026-10-22','status':'indexed','chunk_count':0,
        'vector_status':'indexed','error_message':None})
    aliases.set_document_aliases('entity-doc','Example Person',['示例人物'])
    inputs=[]
    monkeypatch.setattr(vector_store,'embed_text',lambda text: inputs.append(text) or [1.0,0.0])
    store=vector_store.VectorStore.__new__(vector_store.VectorStore)
    original='EDUCATION\nExample University'
    prepared=store.prepare_chunks([TextChunk('education',original,'school.txt',0,len(original))],document_id='entity-doc')
    assert inputs==['Entity: Example Person\n'+original]
    assert prepared['documents']==[original]
    assert prepared['metadatas'][0]['entity_name']=='Example Person'
