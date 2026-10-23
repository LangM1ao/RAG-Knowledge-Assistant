from __future__ import annotations

from copy import deepcopy
import re

from app.core.config import (BM25_CANDIDATE_K, RRF_K, VECTOR_CANDIDATE_K,
                             CONTEXT_MAX_CHARS, CONTEXT_MAX_CHUNKS)
from app.services.bm25_retriever import BM25Retriever
from app.services.entity_aliases import list_aliases, resolve_aliases
from app.services.query_normalizer import normalize_query
from app.services.vector_store import VectorStore

RETRIEVAL_MODES = {'vector', 'bm25', 'hybrid'}


def _identity(chunk: dict) -> tuple[str, str]:
    return ((chunk.get('metadata') or {}).get('document_id', ''), chunk['chunk_id'])


def _normalize_vector_results(chunks: list[dict]) -> list[dict]:
    results = []
    seen = set()
    for chunk in chunks:
        identity = _identity(chunk)
        if identity in seen:
            continue
        seen.add(identity)
        distance = chunk.get('distance')
        rank = len(results) + 1
        results.append({**chunk, 'score': distance, 'rank': rank,
                        'retrieval_source': 'vector', 'vector_score': distance,
                        'vector_distance': distance,
                        'vector_similarity': None if distance is None else 1-distance,
                        'vector_rank': rank, 'bm25_score': None,
                        'bm25_rank': None, 'rrf_score': None})
    return results


def reciprocal_rank_fusion(vector_results, bm25_results, *, top_k, rrf_k=60):
    if rrf_k < 0 or top_k < 1:
        raise ValueError('rrf_k must be nonnegative and top_k positive')
    fused = {}
    for source, results in (('vector', vector_results), ('bm25', bm25_results)):
        seen = set()
        for original in results:
            key = _identity(original)
            if key in seen:
                continue
            seen.add(key)
            rank = len(seen)
            item = fused.setdefault(key, {**deepcopy(original), 'retrieval_source': 'hybrid',
                'vector_score': None, 'vector_distance': None, 'vector_similarity': None,
                'vector_rank': None, 'bm25_score': None, 'bm25_rank': None,
                'rrf_score': 0.0, 'distance': original.get('distance')})
            item['rrf_score'] += 1 / (rrf_k + rank)
            if source == 'vector':
                distance = original.get('distance', original.get('vector_score'))
                item.update(vector_score=distance, vector_distance=distance,
                            vector_similarity=None if distance is None else 1-distance,
                            vector_rank=rank, distance=distance)
            else:
                item.update(bm25_score=original.get('bm25_score', original.get('score')),
                            bm25_rank=rank)
    # 同分时按稳定的文档/Chunk 标识排序，避免读取顺序导致排名漂移。
    ranked = sorted(fused.values(), key=lambda item: (-item['rrf_score'], _identity(item)))
    for rank, item in enumerate(ranked[:top_k], 1):
        item.update(rank=rank, score=item['rrf_score'])
    return ranked[:top_k]


class Retriever:
    def __init__(self, vector_store=None, bm25_retriever=None, *, alias_records=None):
        self.vector_store = vector_store or VectorStore()
        self.bm25_retriever = bm25_retriever
        self.alias_records = alias_records
        self.last_debug = {}

    def _bm25(self):
        if self.bm25_retriever is None:
            self.bm25_retriever = BM25Retriever(collection=self.vector_store.collection)
        return self.bm25_retriever

    def query(self, question, *, retrieval_mode='vector', top_k=3,
              similarity_threshold=None, document_ids=None, source_files=None):
        from app.services.document_service import INDEX_LOCK
        with INDEX_LOCK:
            return self._query(question, retrieval_mode=retrieval_mode, top_k=top_k,
                               similarity_threshold=similarity_threshold,
                               document_ids=document_ids, source_files=source_files)

    def _query(self, question, *, retrieval_mode, top_k, similarity_threshold,
               document_ids, source_files):
        if retrieval_mode not in RETRIEVAL_MODES:
            raise ValueError(f'Unsupported retrieval mode: {retrieval_mode}')
        if top_k < 1:
            raise ValueError('top_k must be positive')
        if document_ids is not None and not any(document_ids):
            self.last_debug = {'stop_reason': 'empty_scope', 'final_chunks': []}
            return []
        # 注入记录用于独立测试；正式实例从持久 SQLite 读取，不猜测姓名。
        rows = self.alias_records
        if rows is None:
            rows = list_aliases(document_ids, source_files) if hasattr(self.vector_store, 'collection') else []
        rows = [row for row in rows
                if (document_ids is None or row['document_id'] in document_ids)
                and (not source_files or row.get('source_file') in source_files)]
        alias = resolve_aliases(question, rows)
        self.last_debug = {'normalized_query': normalize_query(question),
                           'original_query': question, 'retrieval_query': alias['query'],
                           'content_query': alias['content_query'], 'alias_matches': alias['matches'],
                           'ambiguous_aliases': alias['ambiguous_aliases'],
                           'retrieval_mode': retrieval_mode, 'top_k': top_k,
                           'max_distance': similarity_threshold,
                           'requested_filter': {'document_ids': document_ids, 'source_files': source_files},
                           'vector_candidate_count': 0, 'bm25_candidate_count': 0,
                           'fused_count': 0, 'threshold_filtered_count': 0,
                           'final_chunks': [], 'context_expansion': []}
        if not alias['query']:
            self.last_debug['stop_reason'] = 'empty_query'
            return []
        effective_ids = document_ids
        if not source_files and alias['constraint_document_ids']:
            effective_ids = [d for d in alias['constraint_document_ids'] if document_ids is None or d in document_ids]
        self.last_debug['effective_filter'] = {'document_ids': effective_ids, 'source_files': source_files}
        common = {'question': alias['query']}
        if effective_ids is not None:
            common['document_ids'] = effective_ids
        if source_files:
            common['source_files'] = source_files
        vector_results, bm25_results = [], []
        if retrieval_mode != 'bm25':
            options = {**common, 'top_k': max(top_k, VECTOR_CANDIDATE_K) if retrieval_mode=='hybrid' else top_k}
            if similarity_threshold is not None:
                options['similarity_threshold'] = similarity_threshold
            vector_results = _normalize_vector_results(self.vector_store.query(**options))
            detail = getattr(self.vector_store, 'last_query_debug', {})
            self.last_debug.update(vector_candidate_count=detail.get('raw_candidate_count', len(vector_results)),
                                   threshold_filtered_count=detail.get('filtered_count', 0),
                                   vector_filter_details=detail)
        if retrieval_mode != 'vector':
            bm25 = self._bm25()
            lexical_options = {**common, 'question': alias['content_query']}
            candidates = bm25.query(**lexical_options, top_k=max(top_k, BM25_CANDIDATE_K) if retrieval_mode=='hybrid' else top_k)
            bm25_results = [item for item in candidates if item.get('content_match', True) and item.get('bm25_score', item.get('score', 0)) > 0]
            self.last_debug['bm25_candidate_count'] = len(bm25_results)
            self.last_debug['bm25_details'] = getattr(bm25, 'last_debug', {})
        if retrieval_mode == 'hybrid':
            merged = reciprocal_rank_fusion(vector_results, bm25_results,
                        top_k=max(1,len(vector_results)+len(bm25_results)), rrf_k=RRF_K)
        else:
            merged = vector_results if retrieval_mode=='vector' else bm25_results
        self.last_debug['fused_count'] = len(merged)
        self.last_debug['fusion_ranking'] = [{'chunk_id': c['chunk_id'], 'document_id': (c.get('metadata') or {}).get('document_id'), 'vector_rank': c.get('vector_rank'), 'bm25_rank': c.get('bm25_rank'), 'rrf_score': c.get('rrf_score')} for c in merged]
        selected = merged[:top_k]
        self.last_debug['top_k_filtered_count'] = len(merged)-len(selected)
        self.last_debug['final_chunks'] = [item['chunk_id'] for item in selected]
        return selected

    def expand_context(self, question, chunks, *, document_ids=None, source_files=None):
        from app.services.document_service import INDEX_LOCK
        with INDEX_LOCK:
            return self._expand_context(question, chunks, document_ids, source_files)

    def _expand_context(self, question, chunks, document_ids, source_files):
        selected = [c for c in chunks if document_ids is None or (c.get("metadata") or {}).get("document_id") in document_ids]
        self.last_debug['context_expansion'] = []
        # 只为明确的多事实问题补充邻块；普通单点问题保持原 Top-K。
        if not re.search(r'和|以及|并且|分别|同时|[，,；;]|\band\b', normalize_query(question)):
            return selected
        collection = getattr(self.vector_store, 'collection', None)
        if collection is None:
            return selected
        seen = {_identity(item) for item in selected}
        used = sum(len(item.get('text','')) for item in selected)
        cache = {}
        for anchor in list(selected):
            meta = anchor.get('metadata') or {}
            doc, section, index = meta.get('document_id'), meta.get('section_title'), meta.get('chunk_index')
            structural = meta.get('structure_id')
            if not doc or not structural or meta.get('structure_version',0)<2 or not meta.get('structure_reliable') or not isinstance(index,int):
                continue
            if document_ids is not None and doc not in document_ids:
                continue
            if source_files and meta.get('source_file') not in source_files:
                continue
            if doc not in cache:
                payload = collection.get(where={'document_id':doc}, include=['documents','metadatas'])
                cache[doc] = [{'chunk_id':i,'text':t,'metadata':m or {}}
                              for i,t,m in zip(payload['ids'],payload['documents'],payload['metadatas'])]
            for item in sorted(cache[doc], key=lambda x:x['metadata'].get('chunk_index',-1)):
                neighbor = item['metadata']
                neighbor_index = neighbor.get('chunk_index')
                if (neighbor.get('document_id') != doc or neighbor.get('structure_id') != structural
                    or neighbor.get('structure_version',0)<2 or not neighbor.get('structure_reliable')
                    or neighbor.get('source_file') != meta.get('source_file')
                    or not isinstance(neighbor_index,int) or abs(neighbor_index-index)!=1
                    or _identity(item) in seen):
                    continue
                if len(selected) >= CONTEXT_MAX_CHUNKS or used+len(item['text']) > CONTEXT_MAX_CHARS:
                    continue
                item.update(retrieval_source='adjacent', distance=None, expanded_from=anchor['chunk_id'])
                selected.append(item)
                used += len(item['text'])
                seen.add(_identity(item))
                self.last_debug['context_expansion'].append({'chunk_id':item['chunk_id'],
                        'document_id':doc,'expanded_from':anchor['chunk_id'],'reason':'same_leaf_structure_multi_part_query'})
        self.last_debug['final_chunks'] = [item['chunk_id'] for item in selected]
        return selected
