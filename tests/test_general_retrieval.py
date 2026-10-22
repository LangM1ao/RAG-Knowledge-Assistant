"""General retrieval regressions, independent of any personal document."""
from types import SimpleNamespace
import pytest
from app.services.bm25_retriever import BM25Retriever, tokenize
from app.services.retriever import Retriever
from app.services.entity_aliases import resolve_aliases


class Collection:
    def __init__(self,rows): self.rows=rows
    def get(self,**kwargs):
        rows=self.rows
        return {'ids':[r['chunk_id'] for r in rows],'documents':[r['text'] for r in rows],
                'metadatas':[r['metadata'] for r in rows]}


def row(i,text,doc='d',**metadata):
    return {'chunk_id':i,'text':text,'metadata':{'document_id':doc,'source_file':doc+'.txt',**metadata}}


def test_metadata_only_identity_match_is_not_lexical_evidence():
    rows=[row('a','Short unrelated topic.',entity_name='Example Systems'),
          row('b','Database performance uses indexes.',entity_name='Example Systems')]
    assert BM25Retriever(collection=Collection(rows)).query('Example Systems')==[]


def test_real_body_name_and_exact_identifiers_remain_searchable():
    rows=[row('a','Example Systems operates ERR-204 with API_TIMEOUT_MS.',entity_name='Other')]
    b=BM25Retriever(collection=Collection(rows))
    assert b.query('Example Systems')[0]['chunk_id']=='a'
    assert b.query('ERR-204')[0]['chunk_id']=='a'
    assert 'err-204' in tokenize('ERR-204。')
    assert 'api_timeout_ms' in tokenize('ＡＰＩ_TIMEOUT_MS')


def test_sentence_end_punctuation_does_not_change_identifier_token():
    assert tokenize('API_TIMEOUT_MS.')==tokenize('api_timeout_ms')
    assert tokenize('version.2:timeout-ms')==['version.2:timeout-ms']


def test_invalid_bm25_identity_signal_cannot_evict_semantic_evidence():
    rows=[row('short','Unrelated.',entity_name='Example Systems'),
          row('right','Composite indexes improve database performance.',entity_name='Example Systems')]
    class Store:
        collection=Collection(rows)
        def query(self,**kw):
            return [{**rows[1],'distance':0.2}]
    r=Retriever(vector_store=Store(),alias_records=[{'document_id':'d','source_file':'d.txt',
        'entity_name':'Example Systems','aliases':['示例系统','Example Systems']}])
    results=r.query('示例系统的数据库查询如何加速？',retrieval_mode='hybrid',top_k=1,similarity_threshold=0.6)
    assert results[0]['chunk_id']=='right'
    assert r.last_debug['bm25_candidate_count']==0
    assert 'example' not in r.last_debug['content_query']


def test_multiple_entities_are_resolved_without_refusing_or_losing_scope():
    aliases=[{'document_id':d,'source_file':d+'.txt','entity_name':name,'aliases':[alias]} for d,name,alias in
             [('a','Orion Systems','猎户系统'),('b','Lyra Tools','天琴工具')]]
    calls=[]
    store=SimpleNamespace(query=lambda **kw:calls.append(kw) or [])
    r=Retriever(vector_store=store,alias_records=aliases)
    r.query('比较猎户系统和天琴工具的查询优化方法',document_ids=['a','b','c'])
    assert calls and calls[0]['document_ids']==['a','b','c']
    assert 'orion systems' in calls[0]['question'] and 'lyra tools' in calls[0]['question']
    assert len(r.last_debug['alias_matches'])==2


def test_ambiguous_or_object_mentions_do_not_silently_restrict_documents():
    aliases=[{'document_id':d,'source_file':d+'.txt','entity_name':name,'aliases':['共用名']} for d,name in [('a','Alpha'),('b','Beta')]]
    calls=[]
    store=SimpleNamespace(query=lambda **kw:calls.append(kw) or [])
    r=Retriever(vector_store=store,alias_records=aliases)
    r.query('哪些供应商使用共用名？',document_ids=['a','b','c'])
    assert calls and calls[0]['document_ids']==['a','b','c']
    assert 'stop_reason' not in r.last_debug


def test_identity_is_retained_when_it_is_the_content_target():
    aliases=[{'document_id':'d','entity_name':'Example Systems','aliases':['示例系统']}]
    resolved=resolve_aliases('示例系统是什么？',aliases)
    assert 'example systems' in resolved['content_query']


def test_scoped_alias_subject_cannot_widen_explicit_filters():
    calls=[]
    r=Retriever(vector_store=SimpleNamespace(query=lambda **kw:calls.append(kw) or []),
       alias_records=[{'document_id':'a','source_file':'a.txt','entity_name':'Example','aliases':['示例']}])
    r.query('示例的处理流程？',document_ids=['b'],source_files=['b.txt'])
    assert calls[0]['document_ids']==['b'] and calls[0]['source_files']==['b.txt']

def test_unknown_technical_identifier_cannot_match_only_generic_access_terms():
    rows=[row('policy','Access tokens must be redacted before logging.'),
          row('exact','ERR_STORAGE_204 means storage quota exceeded.')]
    b=BM25Retriever(collection=Collection(rows))
    assert b.query('What is the access password SATURN_PRIVATE_998?')==[]
    assert b.query('What does ERR_STORAGE_204 mean?')[0]['chunk_id']=='exact'
