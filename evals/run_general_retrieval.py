"""Small fixed enterprise-corpus extension of the existing Week11 evaluators."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['before','after'],required=True)
    parser.add_argument('--with-answers',action='store_true')
    parser.add_argument('--run-id',default='v1')
    parser.add_argument('--answer-ids',default='',help='Optional comma-separated subset for paid answer generation')
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    base=repo/'backups'/'general_retrieval_20261022'
    work=base/(args.stage+'_'+args.run_id)
    os.environ['UPLOAD_DIR']=str(work/'uploads')
    os.environ['METADATA_DB_PATH']=str(work/'metadata.db')
    os.environ['CHROMA_DB_DIR']=str(work/'data'/'eval_chroma_db')
    # Import application config only after selecting an isolated runtime.
    from app.db.database import init_db
    from app.db.document_repository import create_document
    from app.services.entity_aliases import set_document_aliases
    from app.services.chunker import chunk_text
    import app.services.vector_store as vs
    from app.services.retriever import Retriever
    from app.services import rag_pipeline as pipeline
    from evals.run_eval import assert_safe_eval_path,load_question_cases
    from evals.retrieval_evaluator import source_hit,reciprocal_rank,detect_refusal
    from evals.run_retrieval_comparison import _summary_row
    logging.disable(logging.CRITICAL)
    init_db()
    spec=load_question_cases(repo/'evals'/'general_retrieval_cases.json')
    cache_file=base/'general_embedding_cache.json'
    cache=json.loads(cache_file.read_text(encoding='utf-8')) if cache_file.exists() else {}
    original_embed=vs.embed_text
    misses=0
    def cached(text):
        nonlocal misses
        if text not in cache:
            cache[text]=original_embed(text); misses+=1
            cache_file.parent.mkdir(parents=True,exist_ok=True)
            cache_file.write_text(json.dumps(cache),encoding='utf-8')
        return cache[text]
    vs.embed_text=cached
    store=vs.VectorStore(collection_name='general_'+args.stage+'_'+args.run_id,
                         db_path=assert_safe_eval_path(work/'data'/'eval_chroma_db',project_root=work))
    if store.collection.count():
        raise RuntimeError('Evaluation already exists; use a new --run-id instead of deleting data.')
    hashes={}
    for path in sorted((repo/'demo'/'general_retrieval').glob('*.txt')):
        text=path.read_text(encoding='utf-8'); doc=path.name
        hashes[doc]=hashlib.sha256(text.encode()).hexdigest()
        create_document({'document_id':doc,'filename':doc,'file_path':str(path),'file_type':'txt',
            'upload_time':'2026-10-22','status':'indexed','chunk_count':0,'vector_status':'indexed','error_message':None})
        if doc in spec['aliases']:
            set_document_aliases(doc,**spec['aliases'][doc])
        store.add_chunks(chunk_text(text,doc,chunk_size=500,overlap=50),document_id=doc)
    all_payload=store.collection.get(include=['documents','metadatas'])
    all_chunks={i:{'chunk_id':i,'text':t,'metadata':m} for i,t,m in zip(all_payload['ids'],all_payload['documents'],all_payload['metadatas'])}
    def compact(text): return re.sub(r'\s+',' ',text).casefold().strip()
    def groups(case):
        return case.get('evidence_groups') or [{'source':case['expected_source'],'text':t} for t in case['expected_evidence']]
    def supported(group,chunk):
        return chunk['metadata']['source_file']==group['source'] and compact(group['text']) in compact(chunk['text'])
    def coverage(case,chunks):
        expected=groups(case)
        hits=[any(supported(g,c) for c in chunks) for g in expected]
        return (sum(hits)/len(hits)) if hits else None
    rows=[]; answer_rows=[]
    pipeline.VectorStore=lambda:store
    pipeline.RETRIEVAL_DEBUG_ENABLED=True
    for case in spec['cases']:
        for mode in ['vector','bm25','hybrid']:
            opts={'retrieval_mode':mode,'top_k':3,'similarity_threshold':0.6}
            for field in ['document_ids','source_files']:
                if case.get(field): opts[field]=case[field]
            start=time.perf_counter()
            retriever=Retriever(vector_store=store)
            hits=retriever.query(case['question'],**opts)
            expanded=retriever.expand_context(case['question'],hits,
                        document_ids=case.get('document_ids'),source_files=case.get('source_files'))
            used,context,_=pipeline._bounded_context(expanded,retriever.last_debug.get('alias_matches',[]))
            sources=[c['metadata']['source_file'] for c in hits]
            rr=reciprocal_rank(case['expected_source'],sources)
            row={'question_id':case['id'],'question':case['question'],'question_type':case['question_type'],
                'expected_source':case['expected_source'] or '', 'retrieval_mode':mode,
                'retrieved_sources':sources,'retrieved_chunk_ids':[c['chunk_id'] for c in hits],
                'hit':'' if rr is None else int(rr>0),'reciprocal_rank':'' if rr is None else rr,
                'refused':int(not hits),'refusal_correct':int((not hits)==case['should_refuse']),
                'evidence_recall_at_k':coverage(case,hits),'context_evidence_recall':coverage(case,used),
                'context_chunk_ids':[c['chunk_id'] for c in used],
                'latency_ms':round((time.perf_counter()-start)*1000,3),'error_message':''}
            rows.append(row)
            if args.with_answers and ((case.get('qa') and not args.answer_ids) or case['id'] in args.answer_ids.split(',')):
                start=time.perf_counter()
                result=pipeline.answer_question(case['question'],debug=True,**opts)
                answer=result['answer']; sources=result['sources']
                generated=[all_chunks[c['chunk_id']] for c in result.get('retrieval_trace',{}).get('generation_context_chunks',[])]
                source_chunks=[all_chunks[s['chunk_id']] for s in sources]
                citation_values=[any(supported(g,c) for g in groups(case)) for c in source_chunks]
                citation_precision=sum(citation_values)/len(citation_values) if citation_values else None
                refused=detect_refusal(answer,[s['source_file'] for s in sources])
                answer_groups=case.get('answer_groups') or [case.get('answer_terms',[])]
                facts=all(any(compact(term) in compact(answer) for term in alternatives) for alternatives in answer_groups)
                forbidden=any(compact(t) in compact(answer) for t in case.get('forbidden_terms',[]))
                correct=(refused and not sources) if case['should_refuse'] else (facts and not forbidden and coverage(case,generated)==1 and citation_precision==1 and result.get('verification',{}).get('status')=='PASS')
                answer_rows.append({'question_id':case['id'],'retrieval_mode':mode,'answer':answer,
                    'answer_correct':bool(correct),'refusal_correct':refused==case['should_refuse'],
                    'citation_precision':citation_precision,'context_evidence_recall':coverage(case,generated),
                    'verification':result.get('verification'),'sources':sources,
                    'latency_ms':round((time.perf_counter()-start)*1000,2)})
    grouped=defaultdict(list)
    for row in rows: grouped[(row['retrieval_mode'],'all')].append(row)
    summaries=[]
    for (mode,category),group in grouped.items():
        summary=_summary_row(mode,category,group)
        answerable=[r for r in group if r['evidence_recall_at_k'] is not None]
        summary['evidence_recall_at_k']=sum(r['evidence_recall_at_k'] for r in answerable)/len(answerable)
        summary['context_evidence_recall']=sum(r['context_evidence_recall'] for r in answerable)/len(answerable)
        qa=[r for r in answer_rows if r['retrieval_mode']==mode]
        if qa:
            summary['sampled_answer_accuracy']=sum(r['answer_correct'] for r in qa)/len(qa)
            summary['sampled_refusal_accuracy']=sum(r['refusal_correct'] for r in qa)/len(qa)
            citations=[r['citation_precision'] for r in qa if r['citation_precision'] is not None]
            summary['sampled_citation_precision']=sum(citations)/len(citations) if citations else None
        summaries.append(summary)
    report={'stage':args.stage,'run_id':args.run_id,'code_commit':os.popen('git rev-parse HEAD').read().strip(),
        'time_utc':datetime.now(timezone.utc).isoformat(),'corpus_sha256':hashes,'question_count':len(spec['cases']),
        'parameters':{'top_k':3,'max_distance':0.6,'chunk_size':500,'overlap':50},
        'chunk_count':len(all_chunks),'real_embedding_cache_misses':misses,'rows':rows,'answer_samples':answer_rows,'summary':summaries,
        'notes':['Synthetic non-private corpus only; isolated SQLite and Chroma.','Week11 source Hit/MRR and additional explicit evidence-span recall are reported separately.','Answer Accuracy uses declared keyword/fact groups plus retrieved evidence and real-source checks, not an independent semantic gold evaluator.','Citation precision checks evidence-bearing cited chunks; sample text must still be reviewed.','Cached embeddings mean latency is not a production benchmark.','BM25 is not expected to translate a query with no matching lexical content.']}
    out=repo/'eval_results'/('general_retrieval_'+args.stage+'_'+args.run_id+'.json')
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'summary':summaries,'answers':len(answer_rows),'embedding_misses':misses},ensure_ascii=False))


if __name__=='__main__':
    main()
