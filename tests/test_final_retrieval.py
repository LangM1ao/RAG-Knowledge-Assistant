import pytest
from app.services.retriever import Retriever
from app.services.vector_store import VectorStore
from app.services.bm25_retriever import BM25Retriever
from app.services import rag_pipeline

class NoAccess:
    def get(self,**kwargs): raise AssertionError('Empty scope touched collection')
    def query(self,**kwargs): raise AssertionError('Empty scope queried collection')

@pytest.mark.parametrize('mode',['vector','bm25','hybrid'])
def test_empty_scope_never_queries(mode):
    store=object.__new__(VectorStore); store.collection=NoAccess()
    assert store.query('private',document_ids=[])==[]
    assert BM25Retriever(collection=store.collection).query('private',document_ids=[])==[]
    r=Retriever(vector_store=store,alias_records=[])
    assert r.query('private',retrieval_mode=mode,document_ids=[])==[]

def test_empty_scope_never_constructs_store_or_llm(monkeypatch):
    monkeypatch.setattr(rag_pipeline,'VectorStore',lambda: (_ for _ in ()).throw(AssertionError('store constructed')))
    assert rag_pipeline.answer_question('private',document_ids=[])['sources']==[]

def test_bm25_prefilters_collection():
    class Collection:
        def get(self,**kwargs):
            assert kwargs['where']=={'document_id':'allowed'}
            return {'ids':['x'],'documents':['robot manual'],'metadatas':[{'document_id':'allowed'}]}
    assert BM25Retriever(collection=Collection()).query('robot',document_ids=['allowed'])[0]['metadata']['document_id']=='allowed'
