"""Real API smoke: synthetic data in isolated temporary stores; run inside backend container."""
import os, sys, tempfile, json, logging, time, re
from pathlib import Path
sys.path.insert(0,'/app')
logging.disable(logging.CRITICAL)
work=Path(tempfile.mkdtemp(prefix='rag-upgrade-smoke-'))
os.environ['UPLOAD_DIR']=str(work/'uploads')
os.environ['CHROMA_DB_DIR']=str(work/'chroma')
os.environ['METADATA_DB_PATH']=str(work/'metadata.db')
os.environ['RETRIEVAL_DEBUG_ENABLED']='false'
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
from io import BytesIO
from app.main import app
from app.services.vector_store import VectorStore
from app.db.document_repository import list_document_records
client=TestClient(app)
results=[]
def check(name,passed,detail=None):
 results.append({'test':name,'passed':bool(passed),'detail':detail})
 if not passed: print('FAILED',name)
def upload(name,text,pdf=False):
 content=text.encode()
 if pdf:
  w=PdfWriter(); p=w.add_blank_page(width=612,height=792)
  font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
  p[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):w._add_object(font)})})
  stream=DecodedStreamObject()
  lines=['BT /F1 12 Tf 50 740 Td']
  for i,line in enumerate(text.splitlines()):
   if i: lines.append('0 -18 Td')
   escaped=line.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
   lines.append('('+escaped+') Tj')
  lines.append('ET'); stream.set_data('\n'.join(lines).encode('ascii')); p[NameObject('/Contents')]=w._add_object(stream)
  buf=BytesIO(); w.write(buf); content=buf.getvalue()
 response=client.post('/documents/upload',files={'file':(name,content,'application/pdf' if pdf else 'text/plain')})
 body=response.json(); check('upload_'+('pdf' if pdf else 'txt'),response.status_code==200 and body.get('status')=='indexed')
 return body['document_id']
a=upload('synthetic_alice.pdf','Alice Example\nEDUCATION\nExample University A\nBSc Engineering\nFinal Average: 76/100',True)
b=upload('synthetic_bob.txt','Bob Example\nEDUCATION\nExample University B\nBSc Computing\nFinal Average: 88/100')
check('list_two_documents',len(client.get('/documents/list').json()['documents'])==2)
for doc,canonical,alias in [(a,'Alice Example','示例甲'),(b,'Bob Example','示例乙')]:
 response=client.put(f'/documents/{doc}/aliases',json={'entity_name':canonical,'aliases':[alias]})
 check('persist_alias_'+canonical,response.status_code==200 and alias in client.get(f'/documents/{doc}/aliases').json()['aliases'])
rebuild_aliases=[client.post(f'/documents/{doc}/rebuild').json() for doc in (a,b)]
check('registered_entity_embeddings_rebuilt',all(r.get('success') for r in rebuild_aliases))
check('pdf_real_page_metadata',all(m.get('page_number')==1 for m in VectorStore().collection.get(where={'document_id':a})['metadatas']))
answers=[]
for label,question,scope in [('combined','示例甲的本科学校和最终均分分别是什么？',[a]),('isolated','示例乙的最终均分是多少？',[b]),('no_evidence','示例甲的银行账户密码是什么？',[a])]:
 start=time.perf_counter()
 response=client.post('/chat/query',json={'question':question,'retrieval_mode':'hybrid','document_ids':scope,'top_k':3,'similarity_threshold':0.6,'debug':True})
 body=response.json(); answer=body.get('answer','')
 answers.append({'case':label,'answer':answer,'verification':body.get('verification'),'sources':body.get('sources'),'latency_ms':round((time.perf_counter()-start)*1000,2)})
 check(label+'_http',response.status_code==200)
 check(label+'_debug_closed',not body.get('debug_enabled') and 'retrieval_trace' not in body)
 if label=='combined':
  check('synthetic_document_fact_76', '76' in answer and '88' not in answer and len(body.get('sources',[]))>0)
  check('school_and_grade_answered','university a' in answer.lower() and '76' in answer)
 if label=='isolated': check('different_person_88','88' in answer and '76' not in answer)
 if label=='no_evidence': check('unknown_fact_refused',not body.get('sources') and bool(re.search('无法确定|没有.*依据|没有提供|未.*提供',answer)))
 check(label+'_source_scope',all(s.get('document_id') in scope for s in body.get('sources',[])))
rebuild=client.post(f'/documents/{a}/rebuild').json()
check('rebuild_success',rebuild.get('success'))
row=next(x for x in list_document_records() if x['document_id']==a)
check('no_duplicate_index',len(VectorStore().collection.get(where={'document_id':a})['ids'])==row['chunk_count'])
check('delete_document',client.delete(f'/documents/{b}').status_code==200 and len(client.get('/documents/list').json()['documents'])==1)
check('delete_vectors',not VectorStore().collection.get(where={'document_id':b})['ids'])
check('saved_final_history',len(client.get('/chat/history').json()['history'])==3)
history=client.get('/chat/history').json()['history']
check('history_query_settings_persisted',all((r.get('metadata') or {}).get('settings',{}).get('retrieval_mode')=='hybrid' for r in history))
check('history_verification_persisted',all((r.get('metadata') or {}).get('verification',{}).get('status') for r in history))
report={'dataset':'explicitly_synthetic_people_not_user_resume','results':results,'answer_samples':answers,'all_passed':all(x['passed'] for x in results),'production_data_untouched':True}
Path('/tmp/synthetic_smoke_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':sum(x['passed'] for x in results),'total':len(results),'failures':[x['test'] for x in results if not x['passed']]},ensure_ascii=False))
