from pathlib import Path
from typing import Iterable
import json

import chromadb
from openai import OpenAI

from app.core.config import CHROMA_DB_DIR, EMBEDDING_MODEL, OPENAI_API_KEY
from app.core.logging_config import get_logger
from app.services.chunker import TextChunk

logger = get_logger(__name__)


def _metadata_condition(field: str, values: list[str] | None) -> dict | None:
    cleaned = list(dict.fromkeys(value for value in (values or []) if value))
    if not cleaned:
        return None
    return {field: cleaned[0]} if len(cleaned) == 1 else {field: {'$in': cleaned}}


def build_where_filter(document_ids: list[str] | None = None,
                       source_files: list[str] | None = None) -> dict | None:
    conditions = [condition for condition in (
        _metadata_condition('document_id', document_ids),
        _metadata_condition('source_file', source_files),
    ) if condition is not None]
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {'$and': conditions}


def embed_text(text: str) -> list[float]:
    if not OPENAI_API_KEY:
        raise ValueError('OPENAI_API_KEY is not configured.')
    response = OpenAI(api_key=OPENAI_API_KEY).embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


class VectorStore:
    def __init__(self, collection_name: str = 'knowledge_base_cosine', db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path is not None else CHROMA_DB_DIR
        self.chroma_client = chromadb.PersistentClient(path=str(self.db_path))
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name, metadata={'hnsw:space': 'cosine'})
        self.last_query_debug = {}
        logger.info('Vector store initialized: collection=%s', collection_name)

    def prepare_chunks(self, chunks: Iterable[TextChunk], document_id: str | None = None) -> dict:
        """Finish every embedding before callers mutate the searchable collection."""
        prepared = {'ids': [], 'documents': [], 'embeddings': [], 'metadatas': []}
        # Explicit document identity is retrieval context, never a school/grade fact.
        from app.services.entity_aliases import get_document_aliases
        entity = get_document_aliases(document_id).get('entity_name') if document_id else None
        for chunk in chunks:
            metadata = {'source_file': chunk.source_file, 'start_index': chunk.start_index,
                        'end_index': chunk.end_index, 'chunk_index': chunk.chunk_index,
                        'structure_version': chunk.structure_version, 'structure_reliable': chunk.structure_reliable}
            if chunk.section_path:
                metadata['section_path'] = json.dumps(chunk.section_path, ensure_ascii=False)
                metadata['structure_id'] = chunk.structure_id
            if chunk.subsection_title:
                metadata['subsection_title'] = chunk.subsection_title
                metadata['parent_section'] = chunk.section_path[-2]
            if document_id is not None:
                metadata['document_id'] = document_id
            if chunk.section_title is not None:
                metadata['section_title'] = chunk.section_title
            if chunk.page_number is not None:
                metadata['page_number'] = chunk.page_number
            if chunk.page_range is not None:
                # Chroma metadata is scalar-only; preserve the range as JSON plus numeric bounds.
                metadata['page_range'] = json.dumps(list(chunk.page_range))
                metadata['page_start'], metadata['page_end'] = chunk.page_range
            prepared['ids'].append(chunk.chunk_id)
            prepared['documents'].append(chunk.text)
            embedding_input = ('Section: ' + ' > '.join(chunk.section_path) + '\n' if chunk.section_path else '') + chunk.text
            if entity:
                metadata['entity_name'] = entity
                embedding_input = f'Entity: {entity}\n{embedding_input}'
            prepared['embeddings'].append(embed_text(embedding_input))
            prepared['metadatas'].append(metadata)
        return prepared

    def _write_batches(self, payload: dict, *, upsert: bool = False) -> int:
        writer = self.collection.upsert if upsert else self.collection.add
        for start in range(0, len(payload['ids']), 1000):
            writer(**{key: values[start:start + 1000] for key, values in payload.items()})
        return len(payload['ids'])

    def add_prepared(self, prepared: dict) -> int:
        return self._write_batches(prepared)

    def add_chunks(self, chunks: Iterable[TextChunk], document_id: str | None = None) -> int:
        prepared = self.prepare_chunks(chunks, document_id)
        count = self.add_prepared(prepared)
        logger.info('Chunks added: count=%s document_id=%s', count, document_id)
        return count

    def snapshot_document(self, document_id: str) -> dict:
        result = self.collection.get(where={'document_id': document_id},
                                     include=['documents', 'metadatas', 'embeddings'])
        snapshot = {}
        for field in ('ids', 'documents', 'metadatas', 'embeddings'):
            value = result.get(field)
            if hasattr(value, 'tolist'):
                value = value.tolist()
            snapshot[field] = value if value is not None else []
        return snapshot

    def restore_document_snapshot(self, snapshot: dict) -> int:
        """Restore saved embeddings directly; recovery never calls the embedding API."""
        return self._write_batches(snapshot, upsert=True)

    def delete_chunk_ids(self, chunk_ids: list[str]) -> None:
        for start in range(0, len(chunk_ids), 1000):
            self.collection.delete(ids=chunk_ids[start:start + 1000])

    def query(self, question: str, top_k: int = 3, document_ids: list[str] | None = None,
              source_files: list[str] | None = None, similarity_threshold: float | None = None,
              query_embedding: list[float] | None = None) -> list[dict]:
        # Historical similarity_threshold is a maximum cosine distance, not similarity.
        if similarity_threshold is not None and similarity_threshold < 0:
            raise ValueError('similarity_threshold cannot be negative')
        if document_ids is not None and not any(document_ids):
            self.last_query_debug = {'raw_candidate_count': 0, 'stop_reason': 'empty_scope'}
            return []
        logger.info('Starting vector query: top_k=%s', top_k)
        embedding = query_embedding if query_embedding is not None else embed_text(question)
        query_kwargs = {'query_embeddings': [embedding], 'n_results': top_k}
        where_filter = build_where_filter(document_ids, source_files)
        if where_filter is not None:
            query_kwargs['where'] = where_filter
        results = self.collection.query(**query_kwargs)
        documents = results.get('documents', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]
        distances = results.get('distances', [[]])[0]
        ids = results.get('ids', [[]])[0]
        chunks, candidates = [], []
        filtered_count = 0
        for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            chunk = {'chunk_id': chunk_id, 'text': document, 'metadata': metadata or {},
                     'distance': distance, 'vector_score': distance, 'vector_distance': distance,
                     'vector_similarity': 1.0 - distance, 'similarity': 1.0 - distance}
            rejected = similarity_threshold is not None and distance > similarity_threshold
            candidates.append({**chunk, 'filtered': rejected,
                               'filter_reason': 'distance_threshold' if rejected else None})
            if rejected:
                filtered_count += 1
            else:
                chunks.append(chunk)
        self.last_query_debug = {
            'raw_candidates': candidates, 'raw_candidate_count': len(candidates),
            'kept_count': len(chunks), 'filtered_count': filtered_count,
            'filtered_reasons': {'distance_threshold': filtered_count} if filtered_count else {},
            'where_filter': where_filter, 'max_distance': similarity_threshold,
        }
        logger.info('Vector query finished: top_k=%s result_count=%s', top_k, len(chunks))
        return chunks

    def delete_by_document_id(self, document_id: str) -> None:
        self.collection.delete(where={'document_id': document_id})
        logger.info('Vectors deleted: document_id=%s', document_id)
